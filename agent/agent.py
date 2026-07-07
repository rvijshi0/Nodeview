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

# Scapy removed for native Windows compatibility
SCAPY_AVAILABLE = False
import uuid


class NodeViewAgent:
    """
    NodeView v1.3 Distributed Agent
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

            # Try to get real MAC natively
            if not getattr(self, "mac_address", None):
                try:
                    mac_int = uuid.getnode()
                    self.mac_address = ':'.join(['{:02x}'.format((mac_int >> elements) & 0xff) for elements in range(0,2*6,2)][::-1])
                except Exception:
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

            # Native discovery: run an async ping sweep then read ARP table
            self.run_native_ping_sweep()
            self.read_local_arp_table()

            self.push_telemetry()
            time.sleep(self.scan_frequency)

    def run_native_ping_sweep(self):
        """Uses native asynchronous ping to populate the local ARP table before reading it."""
        try:
            prefix = ".".join(self.ip_address.split(".")[:3])
            self.log(f"Initiating native ICMP ping sweep on {prefix}.0/24...")
            
            # Fire-and-forget pings for 1-254
            def ping_host(ip_str):
                cmd = ["ping", "-n", "1", "-w", "200", ip_str] if os.name == 'nt' else ["ping", "-c", "1", "-W", "1", ip_str]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            threads = []
            for i in range(1, 255):
                target = f"{prefix}.{i}"
                if target != self.ip_address:
                    t = threading.Thread(target=ping_host, args=(target,), daemon=True)
                    t.start()
                    threads.append(t)
                    
            # Wait a max of 2 seconds for all to finish
            for t in threads:
                t.join(timeout=2.0)
                
            self.log("Native ping sweep complete. Reading ARP table...")
        except Exception as e:
            self.log(f"Native ping sweep failed: {e}", is_error=True)

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
        Since raw packet spoofing is blocked on modern Windows endpoints without Npcap,
        this will simulate the test by sending a standard packet from the native IP instead,
        or just logging that spoofing is restricted.
        """
        if self.simulated:
            self.log("Simulating spoofed packet injection (mock mode)...")
            import time
            time.sleep(1)
            details = f"[SIMULATED] Injected spoofed packet: SRC_IP={spoof_ip}, SRC_MAC={spoof_mac} -> DST={target_ip}:{target_port} ({protocol.upper()})"
            self.log(details)
            self._send_ws_sync({"type": "inject_complete", "test_id": test_id, "success": True, "details": details})
            return

        if not self._check_rate_limit():
            self.log("Rate limit exceeded. Waiting...", is_error=True)
            import time
            time.sleep(1)

        try:
            self.log(f"Attempting packet injection -> {target_ip}:{target_port}")
            import socket
            if protocol == "tcp":
                conn = socket.create_connection((target_ip, int(target_port)), timeout=2.0)
                conn.close()
            elif protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(b"test_payload", (target_ip, int(target_port)))
                sock.close()
            
            details = f"INJECTED: Standard (non-spoofed) packet sent from real IP -> DST={target_ip}:{target_port} ({protocol.upper()}). Note: Raw IP spoofing is restricted natively on Windows without Npcap."
            self.log(details)
            self._send_ws_sync({"type": "inject_complete", "test_id": test_id, "success": True, "details": details})
        except Exception as e:
            details = f"INJECT FAILED: {e}"
            self.log(details, is_error=True)
            self._send_ws_sync({"type": "inject_complete", "test_id": test_id, "success": False, "details": details})

    # ── Promiscuous Listener ──

    def _run_listen_threaded(self, test_id, expected_src_ip, expected_port, protocol, timeout):
        """
        Opens a standard socket listener and waits for a connection or packet.
        """
        self._send_ws_sync({"type": "listen_ack", "test_id": test_id, "details": f"Listening natively on port={expected_port}"})

        if self.simulated:
            self.log(f"Simulating listener for src={expected_src_ip}, port={expected_port}...")
            import time
            time.sleep(3)
            details = f"[SIMULATED] Intercepted packet from {expected_src_ip} on port {expected_port} ({protocol.upper()})"
            self.log(details)
            self._send_ws_sync({"type": "packet_intercepted", "test_id": test_id, "success": True, "details": details})
            return

        try:
            import socket
            self.log(f"Opening native socket listener on port {expected_port}. Timeout: {timeout}s")
            if protocol == "tcp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(('0.0.0.0', int(expected_port)))
                sock.listen(1)
                sock.settimeout(timeout)
                conn, addr = sock.accept()
                src_ip = addr[0]
                conn.close()
                sock.close()
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(('0.0.0.0', int(expected_port)))
                sock.settimeout(timeout)
                data, addr = sock.recvfrom(1024)
                src_ip = addr[0]
                sock.close()

            details = f"INTERCEPTED: Native packet/connection received from {src_ip} on port {expected_port}."
            self.log(details)
            self._send_ws_sync({"type": "packet_intercepted", "test_id": test_id, "success": True, "details": details})

        except socket.timeout:
            self.log(f"Listen timeout: No packet received within {timeout}s.")
            self._send_ws_sync({"type": "listen_timeout", "test_id": test_id, "details": f"No packet received on port {expected_port} within {timeout}s."})
        except Exception as e:
            self.log(f"Listener error: {e}", is_error=True)
            self._send_ws_sync({"type": "listen_timeout", "test_id": test_id, "details": f"Listen error: {e}"})