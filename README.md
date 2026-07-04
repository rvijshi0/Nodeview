# **NodeView — Your entire network, in single sight**

NodeView is a client-server network analysis platform that uses distributed agents to map network topologies, perform cross-VLAN connectivity testing, and provide real-time infrastructure monitoring through a premium web dashboard.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  NodeView Server (Ubuntu/Windows)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────┐ │
│  │  FastAPI     │  │  SQLite /   │  │  Neo4j Graph Engine      │ │
│  │  REST + WS   │  │  PostgreSQL │  │  (Topology Relationships)│ │
│  └─────────────┘  └─────────────┘  └──────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Premium Web Dashboard (HTML/CSS/JS + Cytoscape.js)          ││
│  │  • Real-time Topology Map  • Troubleshoot Panel              ││
│  │  • Agent Inventory         • Network Config                  ││
│  │  • Agent Downloads         • Live Console Stream             ││
│  │  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
        ▲ REST/WS API (port 8000)
        │
  ┌─────┼──────────────────────┐
  │     │                      │
  ▼     ▼                      ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Agent 1 │  │ Agent 2 │  │ Agent N │   (Distributed across VLANs)
│ VLAN 10 │  │ VLAN 20 │  │ VLAN 30 │
└─────────┘  └─────────┘  └─────────┘
```

## Project Structure

```
NodeView/
├── server/                    # Central C2 server
│   ├── main.py                # FastAPI application entry point
│   ├── database_pg.py         # SQLAlchemy ORM models (SQLite/PostgreSQL)
│   ├── database_neo4j.py      # Neo4j graph connector + mock fallback
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile             # Container build instructions
│   └── static/                # Web dashboard assets
│       ├── index.html         # Entry point HTML
│       ├── app.js             # Frontend application controller
│       └── styles.css         # Premium dark theme CSS
├── agent/                     # Distributed network agent
│   ├── agent.py               # Core agent logic
│   ├── agent_service.py       # Windows Service wrapper
│   ├── config.json            # Connection configuration
│   └── requirements.txt       # Agent Python dependencies
├── docker-compose.yml         # Docker orchestration
├── setup.sh                   # Automated Ubuntu 24.04 setup script
├── .gitignore                 # Files excluded from version control
└── run.bat                    # Windows quick-start launcher
```

## Production Deployment (Ubuntu 24.04 LTS) — Automated

For a fresh Ubuntu 24.04 server, you can deploy the complete multi-container stack (PostgreSQL, Neo4j, and the FastAPI application) in a single command using the automated setup script. This script automatically provisions Docker, installs all dependencies, and starts the system.

### 1. Run the Setup Script
```bash
# Clone the repository
git clone https://github.com/rvijshi0/Nodeview.git
cd Nodeview

# Make the setup script executable and run it
chmod +x setup.sh
./setup.sh
```

### 2. Access the Dashboard
Once the containers are built and running, the platform dashboard will be instantly available on:
* **URL:** `http://<your-ubuntu-server-ip>:8000`
* **Default Credentials:**
  * **Username:** `admin`
  * **Password:** `admin`

---

## Local Development & Quick Start

### Prerequisites
- Python 3.10+
- pip (Python package manager)

### 1. Start the Server Natively
```bash
cd server
pip install -r requirements.txt
python main.py
```
The dashboard will be available at `http://localhost:8000`

### 2. Start an Agent (Mock Mode for Testing)
```bash
cd agent
pip install -r requirements.txt
python agent.py --name Agent-East --mock
```

---

## Key Features

- **Real-time Network Topology** — Hierarchical Cytoscape.js graph with auto-device classification
- **Cross-VLAN Troubleshooting** — TCP/UDP/ICMP connectivity tests with IP/MAC spoofing support
- **Collaborative Mode** — Two agents coordinate: one sends, one listens (validates segmentation)
- **Internet Path Analysis** — Agents traceroute to configured internet IPs, auto-detecting breakout firewalls
- **Agent Inventory** — Live online/offline status with auto-refresh
- **Agent Package Downloads** — Generate pre-configured agent packages from the dashboard
- **Password-Protected Registration** — Agents authenticate with a shared password set in the dashboard
- **Device Classification** — MAC OUI-based auto-detection (laptop, mobile, IoT, server, etc.)
- **Premium UI** — Dark glassmorphism theme with custom SVG icons per device type

---

## Manual Deployment & Customization

See the **[Installation Guide](INSTALL.md)** for detailed instructions on deploying natively (without Docker) to:
- Ubuntu Server 24.04 LTS (systemd service & Nginx reverse proxy configuration)
- Windows Server / Windows 10+ (using PyInstaller and Windows Services)

## License

Internal enterprise tool. All rights reserved.
