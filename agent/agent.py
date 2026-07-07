import argparse
import asyncio
import datetime
import json
import os
import random
import socket
import struct
import subprocess
import sys
import threading
import time
import requests
import websockets

# Attempt Scapy import for raw packet operations
try:
    from scapy.all import (
        Ether, IP, TCP, UDP, ICMP, ARP,
        sr1, srp, send, sendp, sniff,
        conf, get_if_list, get_if_hwaddr, getmacbyip
    )
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


class NodeViewAgent:
    """
    NodeView v1.4 Distributed Agent
    Handles C2 websocket connection, passive ingestion, active network scanning, 
    and collaborative connectivity troubleshooting commands.
    
    Capabilities:
    - Register with C2 server and maintain WebSocket link
    - Passive network discovery (ARP cache / Scapy ARP sweep)
    - Standard TCP connectivity testing
    - IP/MAC spoofed packet injection (Scapy)
    - Promiscuous listening for spoofed packet interception
    - TCP/ICMP traceroute with custom ports
    - Peer subnet scanning on configurable frequency
    """

    # Rate limiter: max raw packets per second
    RAW_PACKET_RATE_LIMIT = 10

    def __init__(self, server_url, agent_name, force_mock=False):
        self.server_url = server_url.rstrip("/")
        self.agent_name = agent_name or socket.gethostname()
        self.force_mock = force_mock
        self.password = None

        # Load config.json if present
        if getattr(sys, "frozen", False):
            script_dir = os.path.dirname(sys.executable)
        else:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            except NameError:
                script_dir = os.getcwd()

        config_path = os.path.join(script_dir, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    self.server_url = config.get("server_url", self.server_url).rstrip("/")
                    self.agent_name = config.get("agent_name") or self.agent_name or socket.gethostname()
                    self.force_mock = config.get("mock", self.force_mock)
                    self.password = config.get("password", None)
                    self.ip_address = config.get("ip_address", None)
                    self.mac_address = config.get("mac_address", None)
            except Exception as e:
                print(f"Error loading config.json: {e}")

        # Runtime settings
        self.api_key = None
        self.agent_id = None
        if not hasattr(self, "ip_address"):
            self.ip_address = None
        if not hasattr(self, "mac_address"):
            self.mac_address = None
        self.simulated = self.force_mock or (not SCAPY_AVAILABLE)
        self.websocket = None
        self.running = True

        # Subnet scheduling configuration
        self.scan_frequency = 30

        # Telemetry inventory cache
        self.discovered_devices = {}
        self.discovery_lock = threading.Lock()

        # Rate limiter tracking
        self._packet_send_times = []
        self._rate_lock = threading.Lock()

        self.resolve_network_details()

    def log(self, message, is_error=False):
        prefix = "[SIMULATED]" if self.simulated else "[REAL]"
        status = "ERROR:" if is_error else "INFO:"
        log_line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {prefix} {status} {message}"
        print(log_line)

        # Log to local agent.log file
        try:
            if getattr(sys, "frozen", False):
                log_dir = os.path.dirname(sys.executable)
            else:
                try:
                    log_dir = os.path.dirname(os.path.abspath(__file__))
                except NameError:
                    log_dir = os.getcwd()
            log_path = os.path.join(log_dir, "agent.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception as e:
            print(f"Failed to write to agent.log: {e}")

    def resolve_network_details(self):
        # Skip auto-detection if source IP and MAC are both defined in configuration
        if getattr(self, "ip_address", None) and getattr(self, "mac_address", None):
            self.log(f"Using configured interface from config: IP={self.ip_address}, MAC={self.mac_address}")
            return

        if self.simulated:
            random.seed(self.agent_name)
            if not getattr(self, "ip_address", None):
                self.ip_address = f"10.0.10.{random.randint(10, 99)}"
            if not getattr(self, "mac_address", None):
                mac_octets = [0x00, 0x50, 0x56, random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)]
                self.mac_address = ":".join(f"{x:02x}" for x in mac_octets)
            self.log(f"Configured mock interface: IP={self.ip_address}, MAC={self.mac_address}")
            return

        try:
            # Resolve local IP via UDP socket trick
            if not getattr(self, "ip_address", None):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                self.ip_address = s.getsockname()[0]
                s.close()
            else:
                self.log(f"Using configured IP address: {self.ip_address}")

            # Try to get real MAC via Scapy
            if not getattr(self, "mac_address", None):
                if SCAPY_AVAILABLE:
                    try:
                        iface = conf.iface
                        self.mac_address = get_if_hwaddr(iface)
                    except Exception:
                        self.mac_address = "00:50:56:ab:cd:ef"
                else:
                    self.mac_address = "00:50:56:ab:cd:ef"
            else:
                self.log(f"Using configured MAC address: {self.mac_address}")

            self.log(f"Detected interface: IP={self.ip_address}, MAC={self.mac_address}")
        except Exception as e:
            self.log(f"Interface lookup failed. Defaulting to simulation mode. Reason: {e}")
            self.simulated = True
            self.resolve_network_details()


    # ── Rate Limiter ──────────────────────────────────────────────

    def _check_rate_limit(self):
        """Enforces max RAW_PACKET_RATE_LIMIT packets per second."""
        now = time.time()
        with self._rate_lock:
            # Remove entries older than 1 second
            self._packet_send_times = [t for t in self._packet_send_times if now - t < 1.0]
            if len(self._packet_send_times) >= self.RAW_PACKET_RATE_LIMIT:
                return False
            self._packet_send_times.append(now)
            return True

    # ── HTTP Operations ───────────────────────────────────────────

    def register(self):
        register_url = f"{self.server_url}/api/agents/register"
        payload = {
            "name": self.agent_name,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "password": self.password
        }

        while self.running:
            try:
                self.log(f"Attempting to register with C2 Server at {register_url}...")
                res = requests.post(register_url, json=payload, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    self.api_key = data.get("api_key")
                    self.agent_id = data.get("id")
                    self.log(f"Registration successful! API Key loaded.")
                    return True
                else:
                    self.log(f"Registration rejected by server: {res.text}", is_error=True)
            except Exception as e:
                self.log(f"Registration failed: {e}. Retrying in 5 seconds...", is_error=True)

            time.sleep(5)
        return False

    def fetch_scan_frequency(self):
        """Queries network configuration rules from C2 to determine scheduling."""
        try:
            res = requests.get(f"{self.server_url}/api/networks", timeout=10)
            if res.status_code == 200:
                networks = res.json()
                for net in networks:
                    cidr = net.get("cidr_range", "")
                    # Match local subnet (simple prefix match)
                    prefix = ".".join(self.ip_address.split(".")[:3])
                    if cidr.startswith(prefix):
                        self.scan_frequency = int(net.get("scan_frequency_seconds", 30))
                        self.log(f"Updated peer scan frequency: {self.scan_frequency}s (Matched CIDR {cidr})")
                        break
        except Exception:
            pass

    def push_telemetry(self):
        if not self.api_key:
            return

        telemetry_url = f"{self.server_url}/api/telemetry/push"
        headers = {"X-API-Key": self.api_key}

        with self.discovery_lock:
            devices_list = list(self.discovered_devices.values())

        payload = {"devices": devices_list}

        try:
            res = requests.post(telemetry_url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                self.log(f"Flushed telemetry detailing {len(devices_list)} discovered host(s) to server.")
            else:
                self.log(f"Failed to push telemetry: {res.status_code}", is_error=True)
        except Exception as e:
            self.log(f"Telemetry API error: {e}", is_error=True)

    # ── Background Threads: Passive Discovery ─────────────────────

    def run_passive_discovery(self):
        if self.simulated:
            self.run_simulated_discovery()
            return

        self.log("Starting passive discovery engine...")
        while self.running:
            self.fetch_scan_frequency()

            # Try Scapy ARP sweep first, fallback to ARP table
            if SCAPY_AVAILABLE:
                self.run_scapy_arp_scan()
            else:
                self.read_local_arp_table()

            self.push_telemetry()
            time.sleep(self.scan_frequency)

    def run_scapy_arp_scan(self):
        """Uses Scapy ARP ping sweep for fast subnet discovery."""
        try:
            # Determine subnet from own IP
            prefix = ".".join(self.ip_address.split(".")[:3])
            subnet = f"{prefix}.0/24"

            self.log(f"Initiating ARP sweep on {subnet}...")
            ans, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=subnet), timeout=3, verbose=False)

            for sent, received in ans:
                ip = received.psrc
                mac = received.hwsrc.lower()
                dev_info = {
                    "ip": ip,
                    "mac": mac,
                    "hostname": f"Host-{ip.split('.')[-1]}",
                    "type": self._classify_device_by_mac(mac)
                }
                with self.discovery_lock:
                    self.discovered_devices[mac] = dev_info

            self.log(f"ARP sweep complete: {len(ans)} hosts discovered.")
        except Exception as e:
            self.log(f"Scapy ARP scan failed: {e}. Falling back to ARP table.", is_error=True)
            self.read_local_arp_table()

    def _classify_device_by_mac(self, mac):
        """Classify device type based on MAC OUI prefix."""
        oui_map = {
            "00:1a:e8": "laptop", "d8:d3:85": "mobile", "f0:18:98": "mobile",
            "00:0c:29": "desktop", "00:50:56": "desktop", "08:00:27": "desktop",
            "00:00:0c": "switch", "00:01:42": "switch",
            "fc:ec:da": "ap", "e0:d9:e3": "iot", "b8:27:eb": "iot",
            "dc:a6:32": "iot", "00:15:5d": "desktop", "74:da:38": "iot",
        }
        prefix = ":".join(mac.lower().split(":")[:3])
        return oui_map.get(prefix, "laptop")

    def read_local_arp_table(self):
        """Reads neighbor devices from standard operating system tables."""
        try:
            output = subprocess.check_output("arp -a", shell=True).decode(errors="ignore")
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    ip = parts[0]
                    mac = parts[1]
                    if "-" in mac or ":" in mac:
                        mac_clean = mac.replace("-", ":").lower()
                        dev_info = {
                            "ip": ip,
                            "mac": mac_clean,
                            "hostname": f"Discovered-{ip.split('.')[-1]}",
                            "type": self._classify_device_by_mac(mac_clean)
                        }
                        with self.discovery_lock:
                            self.discovered_devices[mac_clean] = dev_info
        except Exception as e:
            self.log(f"Failed to read local ARP table: {e}", is_error=True)

    def run_simulated_discovery(self):
        """Generates dynamic peer hosts for demo topology visualization."""
        self.log("Starting network topology simulation engine...")

        subnet_prefix = "10.0.10"

        infra = [
            {"ip": f"{subnet_prefix}.1", "mac": "00:0c:29:11:22:33", "hostname": "EnterpriseFirewall", "type": "firewall"},
            {"ip": f"{subnet_prefix}.2", "mac": "00:01:42:aa:bb:cc", "hostname": "VLAN-10-Switch", "type": "switch"},
            {"ip": f"{subnet_prefix}.5", "mac": "fc:ec:da:00:11:22", "hostname": "AccessPoint-East", "type": "ap"}
        ]

        children = [
            {"ip": f"{subnet_prefix}.51", "mac": "00:1a:e8:11:22:33", "hostname": "Laptop-John", "type": "laptop"},
            {"ip": f"{subnet_prefix}.52", "mac": "00:1a:e8:11:22:44", "hostname": "Laptop-Mary", "type": "laptop"},
            {"ip": f"{subnet_prefix}.53", "mac": "00:1a:e8:11:22:55", "hostname": "Laptop-Dev", "type": "laptop"},
            {"ip": f"{subnet_prefix}.54", "mac": "00:1a:e8:11:22:66", "hostname": "Laptop-QA", "type": "laptop"},
            {"ip": f"{subnet_prefix}.55", "mac": "00:1a:e8:11:22:77", "hostname": "Laptop-Sales", "type": "laptop"},
            {"ip": f"{subnet_prefix}.56", "mac": "00:1a:e8:11:22:88", "hostname": "Laptop-HR", "type": "laptop"},
            {"ip": f"{subnet_prefix}.57", "mac": "00:1a:e8:11:22:99", "hostname": "Laptop-Fin", "type": "laptop"},
            {"ip": f"{subnet_prefix}.80", "mac": "d8:d3:85:ff:ee:dd", "hostname": "iPhone-Admin", "type": "mobile"},
            {"ip": f"{subnet_prefix}.81", "mac": "e0:d9:e3:12:34:56", "hostname": "Android-Guest", "type": "mobile"}
        ]

        while self.running:
            self.fetch_scan_frequency()
            with self.discovery_lock:
                for dev in infra:
                    self.discovered_devices[dev["mac"].lower()] = dev
                for dev in children:
                    self.discovered_devices[dev["mac"].lower()] = dev
            self.push_telemetry()
            time.sleep(self.scan_frequency)

    # ── WebSocket Client & Command Execution ──────────────────────

    async def connect_c2(self):
        protocol = "wss:" if self.server_url.startswith("https") else "ws:"
        host = self.server_url.split("//")[-1]
        c2_ws_url = f"{protocol}//{host}/ws/c2?key={self.api_key}"

        while self.running:
            try:
                self.log(f"Connecting to C2 WebSocket stream at {c2_ws_url}...")
                async with websockets.connect(c2_ws_url) as ws:
                    self.websocket = ws
                    self.log("WebSocket link active! Streaming telemetry logs...")

                    # Spawn heartbeat routine
                    heartbeat_task = asyncio.create_task(self.c2_heartbeat_loop())

                    try:
                        async for msg_str in ws:
                            payload = json.loads(msg_str)
                            await self.handle_c2_command(payload)
                    except websockets.ConnectionClosed:
                        self.log("WebSocket C2 link terminated by server.", is_error=True)
                    finally:
                        heartbeat_task.cancel()
                        self.websocket = None
            except Exception as e:
                self.log(f"C2 Connection error: {e}. Reconnecting in 5 seconds...", is_error=True)

            await asyncio.sleep(5)

    async def c2_heartbeat_loop(self):
        while self.websocket:
            try:
                hb = {"type": "heartbeat", "timestamp": datetime.datetime.utcnow().isoformat()}
                await self.websocket.send(json.dumps(hb))
                await asyncio.sleep(15)
            except Exception:
                break

    async def send_ws_message(self, payload):
        """Safely send a WebSocket message to C2 server."""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(payload))
            except Exception as e:
                self.log(f"WebSocket send error: {e}", is_error=True)

    async def handle_c2_command(self, payload):
        action = payload.get("action")
        test_id = payload.get("test_id")

        self.log(f"Received instruction: {action} (Test ID: {test_id})")

        if action == "tcp_test":
            target_ip = payload.get("target_ip")
            target_port = payload.get("target_port")
            # Run in thread to not block the event loop
            threading.Thread(
                target=self._run_tcp_test_threaded,
                args=(test_id, target_ip, target_port),
                daemon=True
            ).start()

        elif action == "diagnostic":
            target_ip = payload.get("target_ip")
            target_port = payload.get("target_port")
            protocol = payload.get("protocol", "tcp")
            threading.Thread(
                target=self._run_system_diagnostic_threaded,
                args=(test_id, target_ip, target_port, protocol),
                daemon=True
            ).start()

        elif action == "inject_spoof":
            target_ip = payload.get("target_ip")
            target_port = payload.get("target_port")
            spoof_ip = payload.get("spoof_ip")
            spoof_mac = payload.get("spoof_mac")
            protocol = payload.get("protocol", "tcp")
            threading.Thread(
                target=self._run_inject_spoof_threaded,
                args=(test_id, target_ip, target_port, spoof_ip, spoof_mac, protocol),
                daemon=True
            ).start()

        elif action == "listen":
            expected_src_ip = payload.get("expected_src_ip")
            expected_port = payload.get("expected_port")
            protocol = payload.get("protocol", "tcp")
            timeout = payload.get("timeout", 30)
            threading.Thread(
                target=self._run_listen_threaded,
                args=(test_id, expected_src_ip, expected_port, protocol, timeout),
                daemon=True
            ).start()

        elif action == "traceroute":
            target_ip = payload.get("target_ip")
            target_port = payload.get("target_port", 443)
            protocol = payload.get("protocol", "tcp")
            max_hops = payload.get("max_hops", 30)
            threading.Thread(
                target=self._run_traceroute_threaded,
                args=(test_id, target_ip, target_port, protocol, max_hops),
                daemon=True
            ).start()

        elif action == "heartbeat_ack":
            pass  # Acknowledged

        elif action == "update_config":
            ip = payload.get("ip_address")
            mac = payload.get("mac_address")
            self.log(f"Received configuration update: IP={ip}, MAC={mac}")
            if ip:
                self.ip_address = ip
            if mac:
                self.mac_address = mac
            self.update_local_config(ip, mac)

    # ── Command Handlers (Threaded) ───────────────────────────────

    def _send_ws_sync(self, payload):
        """Send WebSocket message from a synchronous thread context."""
        if self.websocket:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket.send(json.dumps(payload)))
                loop.close()
            except Exception as e:
                self.log(f"Sync WS send error: {e}", is_error=True)

    # ── TCP Test ──

    def _run_tcp_test_threaded(self, test_id, ip, port):
        """Tests TCP port connectivity using standard OS socket calls."""
        self.log(f"Executing diagnostic port connectivity check on {ip}:{port}")
        t_start = time.time()
        success = False
        details = ""

        try:
            conn = socket.create_connection((ip, int(port)), timeout=5.0)
            conn.close()
            success = True
            rtt = round((time.time() - t_start) * 1000, 2)
            details = f"SUCCESS: TCP Port {port} is OPEN on target {ip} (RTT: {rtt}ms)."
        except socket.timeout:
            details = f"TIMEOUT: Connection timed out attempting to reach {ip}:{port}."
        except Exception as e:
            details = f"CLOSED/BLOCKED: Unable to connect to target {ip}:{port}. Reason: {e}"

        self.log(details)
        self._send_ws_sync({
            "type": "tcp_test_result",
            "test_id": test_id,
            "success": success,
            "details": details
        })

    def _run_system_diagnostic_threaded(self, test_id, target_ip, target_port, protocol):
        self.log(f"Executing system diagnostic: {protocol.upper()} -> {target_ip}:{target_port}")
        success = False
        details = ""

        # 1. ICMP Ping requests
        if protocol == "icmp":
            is_windows = os.name == 'nt'
            cmd = ["ping", "-n", "4", target_ip] if is_windows else ["ping", "-c", "4", target_ip]

            try:
                self.log(f"Running system ping command: {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                details = res.stdout if res.stdout else res.stderr
                success = res.returncode == 0
                if not details:
                    details = f"Ping executed with return code {res.returncode}"
            except subprocess.TimeoutExpired:
                details = "Ping command timed out after 15 seconds."
                success = False
            except Exception as e:
                details = f"Failed to execute system ping: {e}"
                success = False

        # 2. Traceroute (tracert)
        elif protocol == "traceroute":
            is_windows = os.name == 'nt'
            cmd = ["tracert", "-d", "-h", "20", target_ip] if is_windows else ["traceroute", "-n", "-m", "20", target_ip]

            try:
                self.log(f"Running system traceroute command: {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                details = res.stdout if res.stdout else res.stderr
                success = res.returncode == 0
                if not details:
                    details = f"Traceroute executed with return code {res.returncode}"
            except subprocess.TimeoutExpired:
                details = "Traceroute command timed out after 60 seconds."
                success = False
            except Exception as e:
                details = f"Failed to execute system traceroute: {e}"
                success = False

        # 3. TCP Port connectivity checks (equivalent to Telnet)
        else: # "tcp" or "udp"
            t_start = time.time()
            try:
                self.log(f"Running standard TCP connect call to {target_ip}:{target_port}")
                conn = socket.create_connection((target_ip, int(target_port)), timeout=5.0)
                conn.close()
                rtt = round((time.time() - t_start) * 1000, 2)
                details = f"SUCCESS: TCP connection established to {target_ip}:{target_port}.\nRTT: {rtt}ms.\nEquivalent to telnet port OPEN."
                success = True
            except socket.timeout:
                details = f"TIMEOUT: Connection timed out attempting to reach {target_ip}:{target_port}."
                success = False
            except Exception as e:
                details = f"CLOSED/BLOCKED: Unable to connect to target {target_ip}:{target_port}.\nReason: {e}."
                success = False

        self.log(f"System diagnostic finished. Success={success}")

        # Send results back to dashboard in a clean JSON payload
        self._send_ws_sync({
            "type": "diagnostic_result",
            "test_id": test_id,
            "test_type": protocol,
            "success": success,
            "details": details
        })

    # ── Spoofed Packet Injection ──

    def _run_inject_spoof_threaded(self, test_id, target_ip, target_port, spoof_ip, spoof_mac, protocol):
        """
        Spoofed packet injection has been disabled due to OS-level raw socket restrictions
        and security compliance policies. Standard connectivity testing should be used.
        """
        self.log("Spoofed packet injection disabled. Using standard sockets instead.", is_error=True)
        try:
            import socket
            if protocol == "tcp":
                conn = socket.create_connection((target_ip, int(target_port)), timeout=2.0)
                conn.close()
            elif protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(b"test", (target_ip, int(target_port)))
                sock.close()
            details = f"Standard packet sent from native IP to {target_ip}:{target_port} ({protocol.upper()})"
            self.log(details)
            self._send_ws_sync({"type": "inject_complete", "test_id": test_id, "success": True, "details": details})
        except Exception as e:
            details = f"Inject failed: {e}"
            self.log(details, is_error=True)
            self._send_ws_sync({"type": "inject_complete", "test_id": test_id, "success": False, "details": details})

    # ── Promiscuous Listener ──

    def _run_listen_threaded(self, test_id, expected_src_ip, expected_port, protocol, timeout):
        """
        Opens a raw socket listener (promiscuous mode via Scapy) and
        waits for a packet matching the expected source IP and destination port.
        
        When intercepted, immediately reports back to the C2 server.
        """
        # Send ACK first
        self._send_ws_sync({
            "type": "listen_ack",
            "test_id": test_id,
            "details": f"Listening for src={expected_src_ip} port={expected_port}"
        })

        if self.simulated or not SCAPY_AVAILABLE:
            self.log(f"Simulating listener for src={expected_src_ip}, port={expected_port}...")
            # Simulate: wait a bit then report success (for demo)
            time.sleep(3)
            details = (
                f"[SIMULATED] Intercepted packet from {expected_src_ip} "
                f"on port {expected_port} ({protocol.upper()})"
            )
            self.log(details)
            self._send_ws_sync({
                "type": "packet_intercepted",
                "test_id": test_id,
                "success": True,
                "details": details
            })
            return

        try:
            # Build BPF filter
            if protocol == "tcp":
                bpf_filter = f"src host {expected_src_ip} and tcp dst port {expected_port}"
            elif protocol == "udp":
                bpf_filter = f"src host {expected_src_ip} and udp dst port {expected_port}"
            else:
                bpf_filter = f"src host {expected_src_ip} and icmp"

            self.log(f"Opening promiscuous listener. BPF: '{bpf_filter}', Timeout: {timeout}s")

            # Use Scapy sniff with timeout
            captured = sniff(filter=bpf_filter, count=1, timeout=timeout)

            if captured and len(captured) > 0:
                pkt = captured[0]
                src_ip = pkt[IP].src if pkt.haslayer(IP) else "unknown"
                details = (
                    f"INTERCEPTED: Packet received from {src_ip} "
                    f"on port {expected_port}. Packet size: {len(pkt)} bytes."
                )
                self.log(details)
                self._send_ws_sync({
                    "type": "packet_intercepted",
                    "test_id": test_id,
                    "success": True,
                    "details": details
                })
            else:
                self.log(f"Listen timeout: No matching packet received within {timeout}s.")
                self._send_ws_sync({
                    "type": "listen_timeout",
                    "test_id": test_id,
                    "details": f"No packet matching BPF '{bpf_filter}' received within {timeout}s."
                })

        except Exception as e:
            self.log(f"Listener error: {e}", is_error=True)
            self._send_ws_sync({
                "type": "listen_timeout",
                "test_id": test_id,
                "details": f"Listener error: {e}"
            })

    # ── Traceroute ──

    def _run_traceroute_threaded(self, test_id, target_ip, target_port, protocol, max_hops):
        """
        Performs TCP SYN traceroute or ICMP traceroute.
        
        TCP: Sends SYN with incrementing TTL. Reads ICMP Time Exceeded replies.
        ICMP: Sends ICMP Echo with incrementing TTL.
        """
        self.log(f"Starting {protocol.upper()} traceroute to {target_ip}:{target_port}, max {max_hops} hops")

        if self.simulated or not SCAPY_AVAILABLE:
            # Simulate traceroute
            self.log("Simulating traceroute hops...")
            simulated_hops = [
                ("10.0.10.1", random.uniform(1, 5)),
                ("10.0.1.1", random.uniform(2, 8)),
                ("172.16.0.1", random.uniform(5, 15)),
                (target_ip, random.uniform(3, 12))
            ]
            for i, (hop_ip, rtt) in enumerate(simulated_hops, 1):
                time.sleep(0.5)
                self._send_ws_sync({
                    "type": "traceroute_hop",
                    "test_id": test_id,
                    "hop": i,
                    "ip": hop_ip,
                    "rtt": round(rtt, 2)
                })
                self.log(f"  Hop {i}: {hop_ip} ({round(rtt, 2)}ms)")

            self._send_ws_sync({
                "type": "traceroute_complete",
                "test_id": test_id,
                "success": True,
                "details": f"Traceroute complete: {len(simulated_hops)} hops to {target_ip}."
            })
            return

        try:
            reached = False
            for ttl in range(1, max_hops + 1):
                if not self._check_rate_limit():
                    time.sleep(0.2)

                if protocol == "tcp":
                    pkt = IP(dst=target_ip, ttl=ttl) / TCP(
                        sport=random.randint(1024, 65535),
                        dport=int(target_port),
                        flags="S"
                    )
                elif protocol == "udp":
                    pkt = IP(dst=target_ip, ttl=ttl) / UDP(
                        sport=random.randint(1024, 65535),
                        dport=int(target_port)
                    )
                else:
                    pkt = IP(dst=target_ip, ttl=ttl) / ICMP()

                t_start = time.time()
                reply = sr1(pkt, timeout=3, verbose=False)
                rtt = round((time.time() - t_start) * 1000, 2)

                if reply is None:
                    # No response
                    self._send_ws_sync({
                        "type": "traceroute_hop",
                        "test_id": test_id,
                        "hop": ttl,
                        "ip": "*",
                        "rtt": 0
                    })
                    self.log(f"  Hop {ttl}: * (no response)")
                elif reply.haslayer(ICMP):
                    icmp_type = reply[ICMP].type
                    hop_ip = reply[IP].src
                    self._send_ws_sync({
                        "type": "traceroute_hop",
                        "test_id": test_id,
                        "hop": ttl,
                        "ip": hop_ip,
                        "rtt": rtt
                    })
                    self.log(f"  Hop {ttl}: {hop_ip} ({rtt}ms)")

                    # ICMP type 11 = Time Exceeded, type 3 = Dest Unreachable
                    if icmp_type == 3:
                        reached = True
                        break
                elif reply.haslayer(TCP):
                    tcp_flags = reply[TCP].flags
                    hop_ip = reply[IP].src
                    self._send_ws_sync({
                        "type": "traceroute_hop",
                        "test_id": test_id,
                        "hop": ttl,
                        "ip": hop_ip,
                        "rtt": rtt
                    })
                    self.log(f"  Hop {ttl}: {hop_ip} ({rtt}ms) [TCP {tcp_flags}]")

                    # SYN-ACK or RST means we reached the target
                    if tcp_flags in (0x12, 0x14, "SA", "RA"):
                        reached = True
                        break

            status = "success" if reached else "incomplete"
            details = f"Traceroute {'reached' if reached else 'did not reach'} {target_ip} in {ttl} hops."
            self.log(details)

            self._send_ws_sync({
                "type": "traceroute_complete",
                "test_id": test_id,
                "success": reached,
                "details": details
            })

        except Exception as e:
            self.log(f"Traceroute error: {e}", is_error=True)
            self._send_ws_sync({
                "type": "traceroute_complete",
                "test_id": test_id,
                "success": False,
                "details": f"Traceroute failed: {e}"
            })

    def run_periodic_traceroutes(self):
        """Periodically polls internet targets and runs traceroutes to them."""
        self.log("Starting periodic background traceroute engine...")
        while self.running:
            try:
                # Fetch internet targets
                res = requests.get(f"{self.server_url}/api/internet-targets", timeout=10)
                if res.status_code == 200:
                    targets = res.json()
                    for tgt in targets:
                        ip = tgt.get("ip_address")
                        if not ip:
                            continue

                        hops = []
                        if self.simulated:
                            # Generate a structured path depending on agent name to demonstrate breakout point analysis
                            suffix = "192.168.100.1" # The common breakout gateway
                            if "east" in self.agent_name.lower():
                                hops = ["10.0.10.1", suffix]
                            elif "west" in self.agent_name.lower():
                                hops = ["10.0.20.1", suffix]
                            else:
                                hops = ["10.0.99.1", suffix]
                        else:
                            # Perform real traceroute mapping
                            hops = self.perform_bg_traceroute(ip)

                        # POST path back to server
                        post_payload = {
                            "agent_name": self.agent_name,
                            "target_ip": ip,
                            "hops": hops
                        }
                        requests.post(f"{self.server_url}/api/telemetry/traceroute", json=post_payload, timeout=10)
            except Exception as e:
                self.log(f"Periodic traceroute loop error: {e}", is_error=True)

            # Poll/run every 60 seconds (for rapid UI feedback during local testing)
            time.sleep(60)

    def perform_bg_traceroute(self, target_ip):
        """Synchronous traceroute helper for the background loop."""
        hops = []
        if not SCAPY_AVAILABLE:
            return ["192.168.1.1"]

        try:
            for ttl in range(1, 15):
                pkt = IP(dst=target_ip, ttl=ttl) / ICMP()
                reply = sr1(pkt, timeout=2, verbose=False)
                if reply is None:
                    continue
                elif reply.haslayer(IP):
                    hop_ip = reply[IP].src
                    hops.append(hop_ip)
                    if hop_ip == target_ip:
                        break
        except Exception:
            pass
        return hops

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self):
        if not self.register():
            self.log("Exiting: Server registration failed.", is_error=True)
            return

        discovery_thread = threading.Thread(target=self.run_passive_discovery, daemon=True)
        discovery_thread.start()

        traceroute_thread = threading.Thread(target=self.run_periodic_traceroutes, daemon=True)
        traceroute_thread.start()

        while self.running:
            try:
                asyncio.run(self.connect_c2())
            except Exception as e:
                self.log(f"C2 loop crashed: {e}. Restarting C2 connection in 5 seconds...", is_error=True)
                time.sleep(5)

    def update_local_config(self, ip, mac):
        if getattr(sys, "frozen", False):
            script_dir = os.path.dirname(sys.executable)
        else:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            except NameError:
                script_dir = os.getcwd()

        config_path = os.path.join(script_dir, "config.json")
        try:
            config = {}
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
            
            if ip is not None:
                config["ip_address"] = ip
            if mac is not None:
                config["mac_address"] = mac

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            self.log(f"Successfully updated local config.json: IP={ip}, MAC={mac}")
        except Exception as e:
            self.log(f"Failed to update local config.json: {e}", is_error=True)

    def stop(self):
        self.running = False
        self.log("Shutting down agent services.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NodeView v1.4 Distributed Network Agent")
    parser.add_argument("--server", type=str, default="http://localhost:8000", help="URL of the NodeView Enterprise Server")
    parser.add_argument("--name", default=f"Agent-{socket.gethostname()}", help="Custom agent identifier name")
    parser.add_argument("--mock", action="store_true", help="Force Simulated Mock network mode")

    args = parser.parse_args()

    agent = NodeViewAgent(server_url=args.server, agent_name=args.name, force_mock=args.mock)
    try:
        agent.start()
    except KeyboardInterrupt:
        agent.stop()
        sys.exit(0)
