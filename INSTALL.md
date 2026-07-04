# NodeView — Installation Guide

Step-by-step instructions for deploying the NodeView server and agents on fresh machines.

---

## Table of Contents

1. [Server Installation — Ubuntu 24.04 LTS](#1-server-installation--ubuntu-2404-lts)
2. [Server Installation — Windows](#2-server-installation--windows)
3. [Agent Installation — Ubuntu / Debian Linux](#3-agent-installation--ubuntu--debian-linux)
4. [Agent Installation — Windows](#4-agent-installation--windows)
5. [Post-Installation — Dashboard Setup](#5-post-installation--dashboard-setup)
6. [Firewall & Network Configuration](#6-firewall--network-configuration)
7. [Running as a System Service](#7-running-as-a-system-service)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Server Installation — Ubuntu 24.04 LTS

### 1.1 System Prerequisites

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python 3, pip, and venv
sudo apt install -y python3 python3-pip python3-venv git
```

### 1.2 Create Application Directory

```bash
# Create a dedicated directory
sudo mkdir -p /opt/nodeview
sudo chown $USER:$USER /opt/nodeview

# Copy the server files (from your local machine or git)
# Option A: Copy from local machine via SCP
# scp -r ./server/ user@server-ip:/opt/nodeview/

# Option B: If using git
# git clone <your-repo-url> /opt/nodeview
```

### 1.3 Set Up Python Virtual Environment

```bash
cd /opt/nodeview/server

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 1.4 Test the Server

```bash
# Start the server manually to verify
cd /opt/nodeview/server
source venv/bin/activate
python main.py
```

Open `http://<server-ip>:8000` in your browser. You should see the NodeView login page.

**Default credentials:** `admin` / `admin`

### 1.5 Create a Systemd Service (Production)

```bash
sudo tee /etc/systemd/system/nodeview.service > /dev/null << 'EOF'
[Unit]
Description=NodeView Enterprise Network Monitoring Server
After=network.target

[Service]
Type=simple
User=nodeview
Group=nodeview
WorkingDirectory=/opt/nodeview/server
Environment="PATH=/opt/nodeview/server/venv/bin"
ExecStart=/opt/nodeview/server/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

```bash
# Create a dedicated service user
sudo useradd -r -s /bin/false nodeview
sudo chown -R nodeview:nodeview /opt/nodeview

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable nodeview
sudo systemctl start nodeview

# Check status
sudo systemctl status nodeview

# View logs
sudo journalctl -u nodeview -f
```

### 1.6 (Optional) Configure Reverse Proxy with Nginx

```bash
sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/nodeview > /dev/null << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain or IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/nodeview /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 2. Server Installation — Windows

### 2.1 System Prerequisites

1. **Install Python 3.10+** from [python.org](https://www.python.org/downloads/)
   - During installation, check **"Add Python to PATH"**
2. Open **Command Prompt (as Administrator)**

### 2.2 Set Up the Server

```cmd
REM Create application directory
mkdir C:\NodeView\server
cd C:\NodeView\server

REM Copy server files here (main.py, database_pg.py, database_neo4j.py, requirements.txt, static/)

REM Install dependencies
pip install -r requirements.txt

REM Test the server
python main.py
```

Open `http://localhost:8000` in your browser.

### 2.3 Run as a Windows Service (Optional)

Use [NSSM](https://nssm.cc/) (Non-Sucking Service Manager):

```cmd
REM Download NSSM and extract to C:\NodeView\nssm.exe

nssm install NodeViewServer
```

Configure in the NSSM GUI:
- **Path:** `C:\Python312\python.exe` (or your Python path)
- **Startup directory:** `C:\NodeView\server`
- **Arguments:** `main.py`

```cmd
REM Start the service
nssm start NodeViewServer
```

---

## 3. Agent Installation — Ubuntu / Debian Linux

### 3.1 Install Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

### 3.2 Set Up the Agent

```bash
# Create agent directory
sudo mkdir -p /opt/nodeview-agent
sudo chown $USER:$USER /opt/nodeview-agent

cd /opt/nodeview-agent

# Copy agent files (agent.py, requirements.txt)
# Or download from the NodeView dashboard → Downloads tab

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3.3 Configure the Agent

Create or edit `config.json`:

```json
{
  "server_url": "http://<SERVER_IP>:8000",
  "password": "<REGISTRATION_PASSWORD>",
  "mock": false
}
```

> **Note:** The `password` must match the Registration Password set on the server's Downloads page. The agent name defaults to the machine's hostname automatically.

### 3.4 Test the Agent

```bash
cd /opt/nodeview-agent
source venv/bin/activate
sudo python agent.py
```

> **Important:** The agent requires **root/sudo** privileges for ARP scanning and raw packet operations (Scapy). Without root, it will fall back to reading the OS ARP table only.

### 3.5 Create a Systemd Service (Production)

```bash
sudo tee /etc/systemd/system/nodeview-agent.service > /dev/null << 'EOF'
[Unit]
Description=NodeView Network Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/nodeview-agent
Environment="PATH=/opt/nodeview-agent/venv/bin"
ExecStart=/opt/nodeview-agent/venv/bin/python agent.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable nodeview-agent
sudo systemctl start nodeview-agent

# Check status
sudo systemctl status nodeview-agent

# View logs
sudo journalctl -u nodeview-agent -f
```

---

## 4. Agent Installation — Windows

### 4.1 Method A: Standalone Python Script

1. Install Python 3.10+ (ensure "Add to PATH" is checked)
2. Open **Command Prompt as Administrator**

```cmd
REM Create agent directory
mkdir C:\NodeView\agent
cd C:\NodeView\agent

REM Copy agent files (agent.py, agent_service.py, config.json, requirements.txt)
REM Or download the package from the NodeView dashboard → Downloads tab

REM Install dependencies
pip install -r requirements.txt

REM Run the agent (requires Administrator for Scapy)
python agent.py
```

### 4.2 Method B: Windows Service (.exe)

#### Build the Executable (on a build machine):

```cmd
REM Install build tools
pip install pyinstaller pywin32

REM Build the service executable
cd agent
pyinstaller --onefile --hidden-import=win32timezone --name=NodeViewAgent agent_service.py
```

The output binary will be at `dist/NodeViewAgent.exe`.

#### Deploy to Target Machine:

1. Copy `NodeViewAgent.exe` and `config.json` to a directory (e.g., `C:\NodeView\`)
2. Open **Command Prompt as Administrator**:

```cmd
cd C:\NodeView

REM Install the Windows service
NodeViewAgent.exe install

REM (Optional) Set to auto-start on boot
NodeViewAgent.exe --startup auto install

REM Start the service
NodeViewAgent.exe start
```

#### Manage the Service:

```cmd
REM Check status — open services.msc and look for "NodeView Distributed Agent"

REM Stop the service
NodeViewAgent.exe stop
REM Or: net stop NodeViewAgent

REM Remove/Uninstall
NodeViewAgent.exe remove
```

---

## 5. Post-Installation — Dashboard Setup

Once the server is running and accessible:

### 5.1 Login

Navigate to `http://<server-ip>:8000` and login:
- **Username:** `admin`
- **Password:** `admin`

> ⚠️ **Change the default password** after first login in a production environment.

### 5.2 Configure Networks

1. Go to **Networks** tab
2. Add your VLAN/subnet CIDR ranges (e.g., `10.0.10.0/24`)
3. Set scan frequency (default: 60 seconds)

### 5.3 Configure Internet Targets

1. In the **Networks** tab, scroll to "Define Internet IP Target"
2. Add public IPs for traceroute analysis (e.g., `8.8.8.8` — Google DNS)
3. Agents will automatically traceroute to these IPs and map breakout paths

### 5.4 Generate Agent Packages

1. Go to **Downloads** tab
2. Enter the **Server IP** (the IP agents will connect to)
3. Enter the **Server Port** (default: `8000`)
4. Set a **Registration Password** (agents must provide this to register)
5. Click **Generate Agent Package**
6. Download `config.json` and distribute to agent machines

### 5.5 Deploy Agents

Install agents on 2-3 machines per VLAN/network segment. Each agent will:
- Auto-detect its hostname as the agent name
- Register with the server using the configured password
- Begin ARP scanning its local subnet
- Push discovered devices to the server
- Periodically traceroute to configured internet targets
- Maintain a persistent WebSocket link for real-time commands

---

## 6. Firewall & Network Configuration

### Ports to Open

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 8000 | TCP | Inbound on Server | Dashboard Web UI + REST API |
| 8000 | TCP | Outbound on Agents | Agent → Server communication |

### Ubuntu UFW Rules (Server)

```bash
sudo ufw allow 8000/tcp comment "NodeView Dashboard"
sudo ufw enable
sudo ufw status
```

### Windows Firewall (Server)

```powershell
New-NetFirewallRule -DisplayName "NodeView Server" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

---

## 7. Running as a System Service

### Ubuntu — Summary

| Component | Service Name | Config File |
|-----------|-------------|-------------|
| Server | `nodeview.service` | `/etc/systemd/system/nodeview.service` |
| Agent | `nodeview-agent.service` | `/etc/systemd/system/nodeview-agent.service` |

```bash
# Useful commands
sudo systemctl start nodeview          # Start server
sudo systemctl stop nodeview           # Stop server
sudo systemctl restart nodeview        # Restart server
sudo journalctl -u nodeview -f         # Live logs

sudo systemctl start nodeview-agent    # Start agent
sudo systemctl stop nodeview-agent     # Stop agent
sudo journalctl -u nodeview-agent -f   # Agent logs
```

### Windows — Summary

| Component | Service Name | Display Name |
|-----------|-------------|-------------|
| Agent | `NodeViewAgent` | NodeView Distributed Agent |

```cmd
net start NodeViewAgent                REM Start
net stop NodeViewAgent                 REM Stop
NodeViewAgent.exe remove               REM Uninstall
```

---

## 8. Troubleshooting

### Server won't start

```bash
# Check if port 8000 is already in use
sudo ss -tlnp | grep 8000    # Linux
netstat -aon | findstr :8000  # Windows

# Check Python dependencies
pip list | grep -i fastapi
pip list | grep -i uvicorn
```

### Agent can't connect to server

```bash
# Test connectivity from agent machine
curl http://<server-ip>:8000/api/agents
# Should return a JSON array

# Check agent logs
sudo journalctl -u nodeview-agent -f   # Linux
# Or check console output if running manually
```

### Agent shows "Registration rejected"

- Verify the password in `config.json` matches the Registration Password set on the server's Downloads page
- Re-generate the agent package from the dashboard

### Topology shows no devices

- Ensure agents are running with `sudo` / Administrator privileges
- Check that network ranges are configured in the Networks tab
- Verify agents show as "online" in the Agents tab
- Check the console stream at the bottom of the dashboard for telemetry messages

### WebSocket disconnects frequently

- If using Nginx reverse proxy, ensure the WebSocket proxy configuration includes:
  ```
  proxy_read_timeout 86400;
  ```
- Check server logs for connection errors:
  ```bash
  sudo journalctl -u nodeview -f
  ```
