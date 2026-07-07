import asyncio
import datetime
import io
import json
import os
import uuid
import secrets
import zipfile
from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

# Import database configurations
from database_pg import init_pg, get_pg_db, User, NetworkRange, Agent, DiagnosticTest, InternetTarget, AgentTraceroute, SystemSetting
from database_neo4j import neo4j_store

try:
    from mac_vendor_lookup import MacLookup, VendorNotFoundError
    mac_lookup = MacLookup()
    # Fetch latest vendors on startup (might fail if no internet, handled silently by the library or try block)
    try:
        mac_lookup.update_vendors()
    except:
        pass
except ImportError:
    mac_lookup = None

def identify_device_type(mac_addr, default="laptop"):
    if not mac_addr or not mac_lookup: return default
    try:
        vendor = mac_lookup.lookup(mac_addr).lower()
        if any(x in vendor for x in ["cisco", "juniper", "arista", "mikrotik"]): return "switch"
        if any(x in vendor for x in ["apple", "samsung", "huawei", "oneplus"]): return "mobile"
        if any(x in vendor for x in ["hikvision", "dahua"]): return "camera"
        if any(x in vendor for x in ["espressif", "raspberry"]): return "iot"
        if any(x in vendor for x in ["ubiquiti", "aruba", "ruckus"]): return "ap"
        if any(x in vendor for x in ["intel", "dell", "hp", "lenovo", "asus"]): return "desktop"
        return "laptop" # fallback
    except Exception:
        return default

def identify_manufacturer(mac_addr):
    if not mac_addr:
        return "Unknown"
    mac_clean = mac_addr.replace("-", ":").lower()
    
    if len(mac_clean) >= 2:
        if mac_clean[1] in ['2', '6', 'a', 'e']:
            return "Private-MAC"

    if mac_lookup:
        try:
            return mac_lookup.lookup(mac_addr)
        except Exception:
            pass
    return "Unknown"

app = FastAPI(title="NodeView v1.5.1 Enterprise Server")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active C2 socket connections: agent_key -> WebSocket
active_agents: Dict[str, WebSocket] = {}
# Active UI logging connections
active_ui_clients: List[WebSocket] = []

# Mock JWT token check for simple authentication mapping
ACCESS_TOKEN = "enterprise-admin-token"

# Database initialization
@app.on_event("startup")
def startup_event():
    init_pg()

    # Initialize a default admin user if not present
    db = next(get_pg_db())
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin = User(username="admin", hashed_password="admin")  # Plaintext check for demo validation
        db.add(admin)
        db.commit()
        print("Default admin account created.")

    # Initialize a default network range if none exist
    default_net = db.query(NetworkRange).filter(NetworkRange.cidr_range == "192.168.1.0/24").first()
    if not default_net:
        net = NetworkRange(name="Default LAN", cidr_range="192.168.1.0/24", scan_frequency_seconds=60)
        db.add(net)
        db.commit()
        print("Default network range created.")

# Helper: Broadcast logging payload to dashboard listeners
async def broadcast_ui_log(message: str, msg_type: str = "info"):
    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "type": msg_type,
        "message": message
    }
    dead_clients = []
    for client in active_ui_clients:
        try:
            await client.send_text(json.dumps(payload))
        except Exception:
            dead_clients.append(client)
    for client in dead_clients:
        if client in active_ui_clients:
            active_ui_clients.remove(client)

# --- Admin Authentication REST APIs ---

@app.post("/api/auth/login")
def admin_login(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    username = payload.get("username")
    password = payload.get("password")

    user = db.query(User).filter(User.username == username, User.hashed_password == password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"token": ACCESS_TOKEN, "username": username}

@app.post("/api/auth/change-password")
def change_password(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    username = payload.get("username", "admin")
    current_password = payload.get("current_password")
    new_password = payload.get("new_password")

    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Current password and new password are required")

    user = db.query(User).filter(User.username == username, User.hashed_password == current_password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect current password")

    user.hashed_password = new_password
    db.commit()
    return {"status": "success", "message": "Password updated successfully"}


# --- Network/VLAN Configuration APIs ---

@app.get("/api/networks")
def get_networks(db: Session = Depends(get_pg_db)):
    return db.query(NetworkRange).all()

@app.post("/api/networks")
def add_network(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    name = payload.get("name")
    cidr = payload.get("cidr_range")
    freq = payload.get("scan_frequency_seconds", 60)

    if not name or not cidr:
        raise HTTPException(status_code=400, detail="name and cidr_range are required")

    existing = db.query(NetworkRange).filter(NetworkRange.cidr_range == cidr).first()
    if existing:
        existing.name = name
        existing.scan_frequency_seconds = int(freq)
        db.commit()
        db.refresh(existing)
        return existing

    net = NetworkRange(name=name, cidr_range=cidr, scan_frequency_seconds=int(freq))
    db.add(net)
    db.commit()
    db.refresh(net)
    return net

@app.delete("/api/networks/{net_id}")
def delete_network(net_id: int, db: Session = Depends(get_pg_db)):
    net = db.query(NetworkRange).filter(NetworkRange.id == net_id).first()
    if not net:
        raise HTTPException(status_code=404, detail="Network range not found")
    db.delete(net)
    db.commit()
    return {"status": "deleted"}

# --- Internet Targets Configuration APIs ---

@app.get("/api/internet-targets")
def get_internet_targets(db: Session = Depends(get_pg_db)):
    return db.query(InternetTarget).all()

@app.post("/api/internet-targets")
def add_internet_target(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    ip = payload.get("ip_address")
    desc = payload.get("description", "")

    if not ip:
        raise HTTPException(status_code=400, detail="ip_address is required")

    existing = db.query(InternetTarget).filter(InternetTarget.ip_address == ip).first()
    if existing:
        existing.description = desc
        db.commit()
        db.refresh(existing)
        return existing

    target = InternetTarget(ip_address=ip, description=desc)
    db.add(target)
    db.commit()
    db.refresh(target)
    return target

@app.delete("/api/internet-targets/{target_id}")
def delete_internet_target(target_id: int, db: Session = Depends(get_pg_db)):
    target = db.query(InternetTarget).filter(InternetTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Internet target not found")
    db.delete(target)
    db.commit()
    return {"status": "deleted"}

# --- Traceroute Telemetry API ---

@app.post("/api/telemetry/traceroute")
async def push_agent_traceroute(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    agent_name = payload.get("agent_name")
    target_ip = payload.get("target_ip")
    hops = payload.get("hops", [])

    if not agent_name or not target_ip:
        raise HTTPException(status_code=400, detail="agent_name and target_ip are required")

    existing = db.query(AgentTraceroute).filter(
        AgentTraceroute.agent_name == agent_name,
        AgentTraceroute.target_ip == target_ip
    ).first()

    if existing:
        existing.hops = json.dumps(hops)
        existing.last_updated = datetime.datetime.utcnow()
    else:
        tr = AgentTraceroute(
            agent_name=agent_name,
            target_ip=target_ip,
            hops=json.dumps(hops),
            last_updated=datetime.datetime.utcnow()
        )
        db.add(tr)

    db.commit()
    await broadcast_ui_log(f"Received traceroute path from '{agent_name}' to {target_ip} ({len(hops)} hops).", "info")
    return {"status": "success"}

# --- Topology REST APIs ---

@app.get("/api/topology")
def fetch_graph_topology(db: Session = Depends(get_pg_db)):
    # Returns merged node relationships from Neo4j Connector (or fallback mock topology)
    base_topo = neo4j_store.get_topology_data()
    nodes = base_topo.get("nodes", [])
    edges = base_topo.get("edges", [])

    # Grouping logic for discovered nodes
    agent_devices = {}
    for edge in edges:
        if edge["data"].get("type") == "DISCOVERED_BY":
            tgt = edge["data"]["target"]
            src = edge["data"]["source"]
            if tgt not in agent_devices: agent_devices[tgt] = []
            agent_devices[tgt].append(src)

    to_remove_nodes = set()
    to_remove_edges = set()
    for agent_id, dev_ids in agent_devices.items():
        if len(dev_ids) > 1:
            agent_name = agent_id
            for n in nodes:
                if n["data"]["id"] == agent_id:
                    agent_name = n["data"].get("label", agent_name)
                    break
            
            cluster_node_id = f"cluster_{agent_id}"
            clustered_data = []
            for nid in dev_ids:
                to_remove_nodes.add(nid)
                for n in nodes:
                    if n["data"]["id"] == nid:
                        n["data"]["discovered_by"] = agent_name
                        clustered_data.append(n["data"])
                        break
                for e in edges:
                    if e["data"]["source"] == nid and e["data"]["target"] == agent_id:
                        to_remove_edges.add(e["data"]["id"])
            
            nodes.append({
                "data": {
                    "id": cluster_node_id,
                    "label": f"{agent_name}+{len(dev_ids)} more",
                    "type": "cluster_group",
                    "groupList": clustered_data
                }
            })
            edges.append({
                "data": {
                    "id": f"edge_{cluster_node_id}_to_{agent_id}",
                    "source": cluster_node_id,
                    "target": agent_id,
                    "type": "DISCOVERED_BY"
                }
            })
    
    nodes = [n for n in nodes if n["data"]["id"] not in to_remove_nodes]
    edges = [e for e in edges if e["data"]["id"] not in to_remove_edges]

    # Fetch configured internet targets
    targets = db.query(InternetTarget).all()
    # Fetch active agent traceroutes
    traceroutes = db.query(AgentTraceroute).all()

    if not targets and not traceroutes:
        return base_topo

    # Set of existing node IDs and edge keys to avoid duplicate graph elements
    existing_node_ids = {n["data"]["id"] for n in nodes}
    existing_edge_keys = {f"{e['data']['source']}->{e['data']['target']}" for e in edges}

    # Add Internet target nodes
    for tgt in targets:
        node_id = f"internet_{tgt.ip_address}"
        if node_id not in existing_node_ids:
            nodes.append({
                "data": {
                    "id": node_id,
                    "label": f"Internet ({tgt.description or tgt.ip_address})",
                    "type": "internet",
                    "ip": tgt.ip_address
                }
            })
            existing_node_ids.add(node_id)

    # Process traceroutes to overlay paths
    paths_by_target = {}
    for tr in traceroutes:
        try:
            hops = json.loads(tr.hops)
        except Exception:
            continue
        if not hops:
            continue
        tgt = tr.target_ip
        if tgt not in paths_by_target:
            paths_by_target[tgt] = []
        paths_by_target[tgt].append((tr.agent_name, hops))

    # To calculate breakout points, we analyze path segments
    for tgt_ip, agent_paths in paths_by_target.items():
        tgt_node_id = f"internet_{tgt_ip}"

        for agent_name, path in agent_paths:
            # Map agent to existing agent node or create fallback
            agent_node_id = None
            for node in nodes:
                if node["data"].get("type") == "agent" and node["data"].get("label") == agent_name:
                    agent_node_id = node["data"]["id"]
                    break

            if not agent_node_id:
                agent_node_id = f"agent_{agent_name}"
                if agent_node_id not in existing_node_ids:
                    nodes.append({
                        "data": {
                            "id": agent_node_id,
                            "label": agent_name,
                            "type": "agent"
                        }
                    })
                    existing_node_ids.add(agent_node_id)

            prev_node_id = agent_node_id

            import ipaddress
            def is_private(ip):
                try:
                    return ipaddress.ip_address(ip).is_private
                except:
                    return False
            
            local_path = []
            for hop in path:
                if not is_private(hop):
                    break
                local_path.append(hop)
            if not local_path:
                continue

            # Loop hops and create hop nodes
            for idx, hop_ip in enumerate(local_path):
                # The last private hop is the breakout firewall
                is_last_hop = (idx == len(local_path) - 1)
                hop_type = "firewall" if is_last_hop else "switch"

                hop_node_id = f"hop_{hop_ip}"

                if hop_node_id not in existing_node_ids:
                    nodes.append({
                        "data": {
                            "id": hop_node_id,
                            "label": f"Breakout Gateway ({hop_ip})" if is_last_hop else f"Hop ({hop_ip})",
                            "type": hop_type,
                            "ip": hop_ip
                        }
                    })
                    existing_node_ids.add(hop_node_id)

                # Create edge to next hop
                edge_key = f"{prev_node_id}->{hop_node_id}"
                if edge_key not in existing_edge_keys:
                    edges.append({
                        "data": {
                            "id": f"edge_{prev_node_id}_to_{hop_node_id}",
                            "source": prev_node_id,
                            "target": hop_node_id,
                            "type": "CONNECTED_TO"
                        }
                    })
                    existing_edge_keys.add(edge_key)

                prev_node_id = hop_node_id

            # Connect last hop directly to the internet target node
            edge_key = f"{prev_node_id}->{tgt_node_id}"
            if edge_key not in existing_edge_keys:
                edges.append({
                    "data": {
                        "id": f"edge_{prev_node_id}_to_{tgt_node_id}",
                        "source": prev_node_id,
                        "target": tgt_node_id,
                        "type": "CONNECTED_TO"
                    }
                })
                existing_edge_keys.add(edge_key)

    return {"nodes": nodes, "edges": edges}

@app.get("/api/devices")
def get_all_devices():
    base_topo = neo4j_store.get_topology_data()
    nodes = base_topo.get("nodes", [])
    edges = base_topo.get("edges", [])
    
    devices = []
    # Identify agent mapped for each device
    agent_map = {}
    for e in edges:
        if e["data"].get("type") == "DISCOVERED_BY":
            agent_map[e["data"]["source"]] = e["data"]["target"]

    for n in nodes:
        node_type = n["data"].get("type", "")
        if node_type not in ["agent", "internet", "firewall", "switch", "router", "ap", "wlc", "server", "cluster_group"]:
            # Peripheral device
            discovered_by = "Unknown"
            agent_id = agent_map.get(n["data"]["id"])
            if agent_id:
                for a in nodes:
                    if a["data"]["id"] == agent_id:
                        discovered_by = a["data"].get("label", agent_id)
                        break
            n["data"]["discovered_by"] = discovered_by
            devices.append(n["data"])
    return devices

# --- Agent REST APIs ---

@app.get("/api/agents")
def list_registered_agents(db: Session = Depends(get_pg_db)):
    agents = db.query(Agent).all()
    result = []
    for agent in agents:
        key = agent.name.lower()
        is_online = key in active_agents
        status_val = "online" if is_online else "offline"

        if agent.status != status_val:
            agent.status = status_val
            db.commit()

        result.append({
            "id": agent.id,
            "name": agent.name,
            "ip_address": agent.ip_address,
            "mac_address": agent.mac_address,
            "status": status_val,
            "last_seen": agent.last_seen.isoformat()
        })
    return result

@app.get("/api/agents/by-ip/{ip}")
def get_agent_by_ip(ip: str, db: Session = Depends(get_pg_db)):
    """Lookup agent by IP address — used for collaborative mode auto-detection."""
    agent = db.query(Agent).filter(Agent.ip_address == ip).first()
    if not agent:
        raise HTTPException(status_code=404, detail="No agent found at this IP")

    key = agent.name.lower()
    return {
        "id": agent.id,
        "name": agent.name,
        "ip_address": agent.ip_address,
        "status": "online" if key in active_agents else "offline"
    }

@app.post("/api/agents/register")
def register_agent(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    name = payload.get("name")
    ip = payload.get("ip_address")
    mac = payload.get("mac_address")
    password = payload.get("password")

    # Authenticate registration password if set on server
    db_pass_setting = db.query(SystemSetting).filter(SystemSetting.key == "agent_registration_password").first()
    if db_pass_setting and db_pass_setting.value != password:
        raise HTTPException(status_code=403, detail="Invalid agent registration password")

    if not name:
        raise HTTPException(status_code=400, detail="Agent name is required")

    agent = db.query(Agent).filter(Agent.name == name).first()
    if agent:
        agent.ip_address = ip or agent.ip_address
        agent.mac_address = mac or agent.mac_address
        agent.last_seen = datetime.datetime.utcnow()
        db.commit()
        db.refresh(agent)
    else:
        api_key = secrets.token_hex(16)
        agent = Agent(
            name=name,
            ip_address=ip,
            mac_address=mac,
            api_key=api_key,
            status="offline",
            last_seen=datetime.datetime.utcnow()
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

    # Write into Neo4j graph store
    manufacturer = identify_manufacturer(agent.mac_address)
    label = f"{agent.name} - {manufacturer}" if manufacturer != "Unknown" else agent.name
    neo4j_store.merge_agent_node(name=agent.name, ip=agent.ip_address, mac=agent.mac_address, label=label)

    return {
        "id": agent.id,
        "name": agent.name,
        "api_key": agent.api_key,
        "status": agent.status
    }

@app.post("/api/agents/{agent_id}/edit")
async def edit_agent(agent_id: int, payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ip = payload.get("ip_address")
    mac = payload.get("mac_address")

    agent.ip_address = ip
    agent.mac_address = mac
    db.commit()
    db.refresh(agent)

    # Also update the Neo4j node visualization
    try:
        manufacturer = identify_manufacturer(agent.mac_address)
        label = f"{agent.name} - {manufacturer}" if manufacturer != "Unknown" else agent.name
        neo4j_store.merge_agent_node(name=agent.name, ip=agent.ip_address, mac=agent.mac_address, label=label)
    except Exception as e:
        print(f"Failed to update Neo4j node: {e}")

    # Notify agent via C2 WebSocket if online
    agent_key = agent.name.lower()
    if agent_key in active_agents:
        try:
            await active_agents[agent_key].send_text(json.dumps({
                "action": "update_config",
                "ip_address": ip,
                "mac_address": mac
            }))
            await broadcast_ui_log(f"Sent configuration update to agent '{agent.name}': IP={ip}, MAC={mac}", "info")
        except Exception as e:
            await broadcast_ui_log(f"Failed to push config update to agent '{agent.name}': {e}", "warning")

    return {"status": "success", "agent": {
        "id": agent.id,
        "name": agent.name,
        "ip_address": agent.ip_address,
        "mac_address": agent.mac_address,
        "status": agent.status
    }}



# --- Telemetry Ingestion Endpoint ---

@app.post("/api/telemetry/push")
async def push_agent_telemetry(payload: dict = Body(...), x_api_key: str = Header(None), db: Session = Depends(get_pg_db)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header is missing")

    agent = db.query(Agent).filter(Agent.api_key == x_api_key).first()
    if not agent:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    agent.last_seen = datetime.datetime.utcnow()
    agent.status = "online"
    db.commit()

    devices = payload.get("devices", [])
    agent_mac = agent.mac_address.lower() if agent.mac_address else f"agent_{agent.name}".lower()

    # Ingest discovered devices into Neo4j
    for dev in devices:
        ip = dev.get("ip")
        mac = dev.get("mac", "")
        raw_hostname = dev.get("hostname", ip or "Unknown Peripheral")
        dtype = identify_device_type(mac, default=dev.get("type", "laptop"))
        
        manufacturer = identify_manufacturer(mac)
        if manufacturer == "Private-MAC":
            label = "Private-MAC"
        elif manufacturer != "Unknown":
            label = manufacturer
        else:
            label = raw_hostname

        neo4j_store.merge_peripheral_device(
            ip=ip,
            mac=mac,
            label=label,
            device_type=dtype,
            agent_mac=agent_mac
        )

    await broadcast_ui_log(f"Received telemetry from '{agent.name}' detailing {len(devices)} discovered hosts.", "info")
    return {"status": "success"}

# --- Downloads Generation Endpoints ---

@app.post("/api/downloads/generate")
def generate_agent_downloads(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    ip = payload.get("ip", "localhost")
    port = payload.get("port", "8000")
    password = payload.get("password", "")

    # Save the registration password in settings
    db_pass = db.query(SystemSetting).filter(SystemSetting.key == "agent_registration_password").first()
    if password:
        if db_pass:
            db_pass.value = password
        else:
            db_pass = SystemSetting(key="agent_registration_password", value=password)
            db.add(db_pass)
        db.commit()
    else:
        if db_pass:
            db.delete(db_pass)
            db.commit()

    # Dynamic config generation: omit agent_name so agent defaults to its hostname
    config_data = {
        "server_url": f"http://{ip}:{port}",
        "password": password,
        "mock": False
    }

    return {
        "config_filename": "config.json",
        "config_content": json.dumps(config_data, indent=2),
        "download_url": f"http://{ip}:{port}/api/downloads/generate-zip"
    }

@app.post("/api/downloads/generate-zip")
def generate_agent_zip(payload: dict = Body(default={}), db: Session = Depends(get_pg_db)):
    """Generates a ZIP bundle containing the complete Python agent package + config."""
    ip = payload.get("ip", "localhost")
    port = payload.get("port", "8000")
    password = payload.get("password", "")

    # Retrieve saved password if not provided in this request
    if not password:
        db_pass = db.query(SystemSetting).filter(SystemSetting.key == "agent_registration_password").first()
        if db_pass:
            password = db_pass.value

    # Dynamic config generation
    config_data = {
        "server_url": f"http://{ip}:{port}",
        "password": password,
        "mock": False
    }

    # Locate agent source directory
    server_dir = os.path.dirname(os.path.abspath(__file__))
    agent_dir = os.path.join(os.path.dirname(server_dir), "agent")

    # Create in-memory ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add generated config.json
        zf.writestr("config.json", json.dumps(config_data, indent=2))

        # Bundle agent Python source files
        agent_files = ["agent.py", "agent_service.py", "requirements.txt"]
        for fname in agent_files:
            fpath = os.path.join(agent_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, fname)

        # Add installation README
        zf.writestr("README.txt",
            f"NodeView v1.5.1 Agent Package\n"
            f"==========================\n\n"
            f"Server: http://{ip}:{port}\n\n"
            f"--- Linux (Ubuntu/Debian) ---\n"
            f"1. Install Python: sudo apt install -y python3 python3-pip\n"
            f"2. Install dependencies: pip install -r requirements.txt\n"
            f"3. Run agent (requires root): sudo python3 agent.py\n\n"
            f"--- Windows ---\n"
            f"1. Install Python 3.10+ from python.org\n"
            f"2. Install dependencies: pip install -r requirements.txt\n"
            f"3. Run agent (as Administrator): python agent.py\n\n"
            f"--- Windows Service (optional) ---\n"
            f"1. pip install pywin32 pyinstaller\n"
            f"2. pyinstaller --onefile --hidden-import=win32timezone --name=NodeViewAgent agent_service.py\n"
            f"3. NodeViewAgent.exe install\n"
            f"4. net start NodeViewAgent\n"
        )

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=NodeViewAgent.zip"}
    )

# --- Safe TCP Troubleshooting Diagnostics (Basic) ---

@app.post("/api/diagnostics/test")
async def run_diagnostics_test(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    source_agent_id = payload.get("source_agent_id")
    target_ip = payload.get("target_ip")
    target_port = payload.get("target_port")

    if not source_agent_id or not target_ip or not target_port:
        raise HTTPException(status_code=400, detail="source_agent_id, target_ip, and target_port are required")

    agent = db.query(Agent).filter(Agent.id == source_agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    key = agent.name.lower()
    if key not in active_agents:
        raise HTTPException(status_code=400, detail=f"Source Agent '{agent.name}' is offline")

    test_id = str(uuid.uuid4())
    test_cmd = {
        "action": "tcp_test",
        "test_id": test_id,
        "target_ip": target_ip,
        "target_port": int(target_port)
    }

    # Record test
    test_record = DiagnosticTest(
        test_id=test_id,
        source_agent_name=agent.name,
        target_ip=target_ip,
        target_port=int(target_port),
        test_type="tcp_test",
        status="initiated"
    )
    db.add(test_record)
    db.commit()

    await active_agents[key].send_text(json.dumps(test_cmd))
    await broadcast_ui_log(f"[{agent.name}] Instructed: TCP connectivity check → {target_ip}:{target_port}", "info")
    return {"test_id": test_id, "status": "initiated"}

# --- Advanced Diagnostics with Spoofing & Collaborative Mode ---

@app.post("/api/diagnostics/advanced")
async def run_advanced_diagnostics(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    """
    Advanced diagnostic endpoint supporting:
    - Standard TCP/UDP/ICMP connectivity tests
    - IP spoofing (test connectivity of unmanaged devices)
    - MAC spoofing
    - Collaborative mode (target agent listens for spoofed packet)
    """
    source_agent_id = payload.get("source_agent_id")
    target_ip = payload.get("target_ip")
    target_port = payload.get("target_port")
    protocol = payload.get("protocol", "tcp")
    spoof_ip = payload.get("spoof_ip")
    spoof_mac = payload.get("spoof_mac")

    if not source_agent_id or not target_ip or target_port is None:
        raise HTTPException(status_code=400, detail="source_agent_id, target_ip, and target_port are required")

    # Validate source agent
    source_agent = db.query(Agent).filter(Agent.id == source_agent_id).first()
    if not source_agent:
        raise HTTPException(status_code=404, detail="Source agent not found")

    src_key = source_agent.name.lower()
    if src_key not in active_agents:
        raise HTTPException(status_code=400, detail=f"Source Agent '{source_agent.name}' is offline")

    test_id = str(uuid.uuid4())
    is_spoofed = bool(spoof_ip or spoof_mac)

    # Check if target has an agent (collaborative mode)
    target_agent = db.query(Agent).filter(Agent.ip_address == target_ip).first()
    is_collaborative = False
    tgt_key = None

    if target_agent and is_spoofed:
        tgt_key = target_agent.name.lower()
        if tgt_key in active_agents:
            is_collaborative = True

    # Record in database
    test_record = DiagnosticTest(
        test_id=test_id,
        source_agent_name=source_agent.name,
        target_ip=target_ip,
        target_port=int(target_port),
        protocol=protocol,
        spoof_ip=spoof_ip,
        spoof_mac=spoof_mac,
        test_type="spoof_test" if is_spoofed else protocol,
        status="initiated",
        is_collaborative=is_collaborative,
        target_agent_name=target_agent.name if target_agent else None
    )
    db.add(test_record)
    db.commit()

    effective_src_ip = spoof_ip or source_agent.ip_address

    # ── Phase 1: Server Coordination ──
    await broadcast_ui_log(f"[SERVER] Initializing test {test_id[:8]}... Source: {source_agent.name}, Target: {target_ip}:{target_port}", "info")

    if is_collaborative:
        # ── Phase 2a: Instruct target agent to LISTEN ──
        await broadcast_ui_log(f"[SERVER] Collaborative mode active. Instructing {target_agent.name} to listen for spoofed packet...", "info")

        listen_cmd = {
            "action": "listen",
            "test_id": test_id,
            "expected_src_ip": effective_src_ip,
            "expected_port": int(target_port),
            "protocol": protocol,
            "timeout": 30
        }
        try:
            await active_agents[tgt_key].send_text(json.dumps(listen_cmd))
            await broadcast_ui_log(f"[{target_agent.name}] ACK: Listening mode activated. Filter: src={effective_src_ip}, port={target_port}", "success")
        except Exception as e:
            await broadcast_ui_log(f"[ERROR] Failed to reach target agent: {e}", "error")

        # Small delay to let listener setup
        await asyncio.sleep(1)

    # ── Phase 3: Instruct source agent to INJECT / TEST ──
    if is_spoofed:
        inject_cmd = {
            "action": "inject_spoof",
            "test_id": test_id,
            "target_ip": target_ip,
            "target_port": int(target_port),
            "protocol": protocol,
            "spoof_ip": spoof_ip,
            "spoof_mac": spoof_mac
        }
        await broadcast_ui_log(f"[SERVER] Instructing {source_agent.name} to inject spoofed packet: SRC_IP={effective_src_ip} → DST={target_ip}:{target_port}", "info")
    else:
        inject_cmd = {
            "action": "diagnostic",
            "test_id": test_id,
            "target_ip": target_ip,
            "target_port": int(target_port),
            "protocol": protocol
        }
        await broadcast_ui_log(f"[SERVER] Instructing {source_agent.name}: Run standard diagnostic ({protocol.upper()}) → {target_ip}:{target_port}", "info")


    try:
        await active_agents[src_key].send_text(json.dumps(inject_cmd))
    except Exception as e:
        await broadcast_ui_log(f"[ERROR] Failed to reach source agent: {e}", "error")
        raise HTTPException(status_code=500, detail="Failed to reach source agent")

    return {
        "test_id": test_id,
        "status": "initiated",
        "mode": "collaborative" if is_collaborative else ("blind_spoof" if is_spoofed else "standard"),
        "source_agent": source_agent.name,
        "target_ip": target_ip,
        "effective_src_ip": effective_src_ip
    }

# --- Traceroute Endpoint ---

@app.post("/api/diagnostics/traceroute")
async def run_traceroute(payload: dict = Body(...), db: Session = Depends(get_pg_db)):
    """Instructs agent to perform TCP/ICMP traceroute and stream hop-by-hop results."""
    source_agent_id = payload.get("source_agent_id")
    target_ip = payload.get("target_ip")
    target_port = payload.get("target_port", 443)
    protocol = payload.get("protocol", "tcp")

    if not source_agent_id or not target_ip:
        raise HTTPException(status_code=400, detail="source_agent_id and target_ip are required")

    agent = db.query(Agent).filter(Agent.id == source_agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    key = agent.name.lower()
    if key not in active_agents:
        raise HTTPException(status_code=400, detail=f"Agent '{agent.name}' is offline")

    test_id = str(uuid.uuid4())
    trace_cmd = {
        "action": "traceroute",
        "test_id": test_id,
        "target_ip": target_ip,
        "target_port": int(target_port),
        "protocol": protocol,
        "max_hops": 30
    }

    test_record = DiagnosticTest(
        test_id=test_id,
        source_agent_name=agent.name,
        target_ip=target_ip,
        target_port=int(target_port),
        protocol=protocol,
        test_type="traceroute",
        status="initiated"
    )
    db.add(test_record)
    db.commit()

    await active_agents[key].send_text(json.dumps(trace_cmd))
    await broadcast_ui_log(f"[{agent.name}] Traceroute initiated → {target_ip}:{target_port} ({protocol.upper()})", "info")

    return {"test_id": test_id, "status": "initiated"}

# --- WebSocket channels ---

@app.websocket("/ws/ui")
async def ws_ui_feed(websocket: WebSocket):
    await websocket.accept()
    active_ui_clients.append(websocket)
    try:
        # Greet UI client
        await websocket.send_text(json.dumps({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "type": "info",
            "message": "Connected to NodeView Enterprise C2 console stream."
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_ui_clients:
            active_ui_clients.remove(websocket)

@app.websocket("/ws/c2")
async def ws_agent_c2(websocket: WebSocket, key: str = None, name: str = None, db: Session = Depends(get_pg_db)):
    if not key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    agent = db.query(Agent).filter(Agent.api_key == key).first()
    if not agent and name:
        agent = db.query(Agent).filter(Agent.name == name).first()

    if not agent:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    agent_key = agent.name.lower()

    await websocket.accept()
    active_agents[agent_key] = websocket

    agent.status = "online"
    agent.last_seen = datetime.datetime.utcnow()
    db.commit()

    await broadcast_ui_log(f"Agent '{agent.name}' established WebSocket C2 link.", "success")

    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                agent.last_seen = datetime.datetime.utcnow()
                agent.status = "online"
                db.commit()
                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))

            elif msg_type == "tcp_test_result":
                success = data.get("success", False)
                details = data.get("details", "")
                test_id = data.get("test_id")
                result_type = "success" if success else "warning"
                await broadcast_ui_log(f"[{agent.name} Diagnostics] {details}", result_type)

                # Update test record
                if test_id:
                    test_rec = db.query(DiagnosticTest).filter(DiagnosticTest.test_id == test_id).first()
                    if test_rec:
                        test_rec.status = "success" if success else "failed"
                        test_rec.result_details = details
                        test_rec.completed_at = datetime.datetime.utcnow()
                        db.commit()

            elif msg_type == "diagnostic_result":
                success = data.get("success", False)
                details = data.get("details", "")
                test_id = data.get("test_id")
                test_type = data.get("test_type", "diagnostic")
                result_type = "success" if success else "warning"
                await broadcast_ui_log(f"[{agent.name} {test_type.upper()}] {details}", result_type)

                # Update test record
                if test_id:
                    test_rec = db.query(DiagnosticTest).filter(DiagnosticTest.test_id == test_id).first()
                    if test_rec:
                        test_rec.status = "success" if success else "failed"
                        test_rec.result_details = details
                        test_rec.completed_at = datetime.datetime.utcnow()
                        db.commit()


            elif msg_type == "inject_complete":
                details = data.get("details", "Packet injected")
                test_id = data.get("test_id")
                await broadcast_ui_log(f"[{agent.name}] {details}", "info")

                if test_id:
                    test_rec = db.query(DiagnosticTest).filter(DiagnosticTest.test_id == test_id).first()
                    if test_rec:
                        test_rec.result_details = (test_rec.result_details or "") + f"\n[INJECT] {details}"
                        db.commit()

            elif msg_type == "packet_intercepted":
                details = data.get("details", "Packet intercepted!")
                test_id = data.get("test_id")
                await broadcast_ui_log(f"[{agent.name}] ✅ PACKET INTERCEPTED: {details}", "success")

                if test_id:
                    test_rec = db.query(DiagnosticTest).filter(DiagnosticTest.test_id == test_id).first()
                    if test_rec:
                        test_rec.status = "success"
                        test_rec.result_details = (test_rec.result_details or "") + f"\n[INTERCEPTED] {details}"
                        test_rec.completed_at = datetime.datetime.utcnow()
                        db.commit()

            elif msg_type == "listen_timeout":
                test_id = data.get("test_id")
                await broadcast_ui_log(f"[{agent.name}] ⏱ Listen timeout — no matching packet received within deadline.", "warning")

                if test_id:
                    test_rec = db.query(DiagnosticTest).filter(DiagnosticTest.test_id == test_id).first()
                    if test_rec:
                        test_rec.status = "timeout"
                        test_rec.result_details = (test_rec.result_details or "") + "\n[TIMEOUT] No matching packet received."
                        test_rec.completed_at = datetime.datetime.utcnow()
                        db.commit()

            elif msg_type == "listen_ack":
                await broadcast_ui_log(f"[{agent.name}] Listener activated. Awaiting matching packet...", "info")

            elif msg_type == "traceroute_hop":
                hop_num = data.get("hop", "?")
                hop_ip = data.get("ip", "*")
                rtt = data.get("rtt", "")
                await broadcast_ui_log(f"[{agent.name} Traceroute] Hop {hop_num}: {hop_ip} ({rtt}ms)", "info")

            elif msg_type == "traceroute_complete":
                details = data.get("details", "Traceroute complete")
                test_id = data.get("test_id")
                success = data.get("success", True)
                result_type = "success" if success else "warning"
                await broadcast_ui_log(f"[{agent.name} Traceroute] {details}", result_type)

                if test_id:
                    test_rec = db.query(DiagnosticTest).filter(DiagnosticTest.test_id == test_id).first()
                    if test_rec:
                        test_rec.status = "success" if success else "failed"
                        test_rec.result_details = details
                        test_rec.completed_at = datetime.datetime.utcnow()
                        db.commit()

            elif msg_type == "log":
                await broadcast_ui_log(f"[{agent.name}] {data.get('message')}", "agent_log")

    except WebSocketDisconnect:
        active_agents.pop(agent_key, None)
        agent.status = "offline"
        db.commit()
        await broadcast_ui_log(f"Agent '{agent.name}' disconnected from C2.", "warning")

# Mount React static files
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
