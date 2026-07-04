#!/bin/bash
# =========================================================================
#  NodeView Central C2 Server - Automated Ubuntu 24.04 Setup Script
# =========================================================================
# This script automates:
#   1. Checking/installing Docker Engine and Docker Compose
#   2. Initializing & starting the multi-container production stack:
#      - PostgreSQL (Primary relation metadata & auth database)
#      - Neo4j Graph DB (Network topology & device relationships)
#      - NodeView C2 Server (FastAPI websocket-enabled C2 app)
# =========================================================================

set -e

# ANSI escape codes for coloring output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================================================${NC}"
echo -e "${BLUE}       NodeView C2 Central Server Deployment Script             ${NC}"
echo -e "${BLUE}=================================================================${NC}"

# Ensure the script is run on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}[ERROR] This setup script is meant for Linux environments (Ubuntu 24.04 recommended).${NC}"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}[*] Docker Engine not found. Installing Docker...${NC}"
    
    # Update package index and install basic prerequisites
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    
    # Create GPG key directories
    sudo install -m 0755 -d /etc/apt/keyrings
    
    # Fetch Docker official GPG key
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add official Docker apt repository to package source lists
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
      
    sudo apt-get update -y
    
    # Install Docker Engine components and plugins
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Start and enable Docker daemon
    sudo systemctl start docker
    sudo systemctl enable docker
    
    echo -e "${GREEN}[+] Docker installed successfully!${NC}"
else
    echo -e "${GREEN}[+] Docker is already installed.${NC}"
fi

# Verify Docker Compose command group
if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}[*] Docker Compose plugin not found. Installing now...${NC}"
    sudo apt-get update -y
    sudo apt-get install -y docker-compose-plugin
    echo -e "${GREEN}[+] Docker Compose installed successfully!${NC}"
else
    echo -e "${GREEN}[+] Docker Compose is ready.${NC}"
fi

echo -e "${YELLOW}[*] Deploying NodeView Docker containers...${NC}"
# Spin up production services (detached mode) and force-build image definitions
sudo docker compose up --build -d

echo -e "${BLUE}=================================================================${NC}"
echo -e "${GREEN}[+] NodeView server has been successfully deployed!${NC}"
echo -e "${BLUE}=================================================================${NC}"
echo ""
echo -e "You can access the GUI dashboard externally at:"
echo -e "   ${YELLOW}http://<YOUR_SERVER_IP_OR_DOMAIN>:8000${NC}"
echo ""
echo -e "Default Administrator Credentials:"
echo -e "   Username: ${GREEN}admin${NC}"
echo -e "   Password: ${GREEN}admin${NC}"
echo ""
echo -e "Useful Commands:"
echo -e "   - View running containers:  ${BLUE}sudo docker compose ps${NC}"
echo -e "   - View logs in real-time:   ${BLUE}sudo docker compose logs -f${NC}"
echo -e "   - Stop central services:    ${BLUE}sudo docker compose down${NC}"
echo -e "   - Restart services:         ${BLUE}sudo docker compose restart${NC}"
echo -e "${BLUE}=================================================================${NC}"
