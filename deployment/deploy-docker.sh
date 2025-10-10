#!/bin/bash
# DeerFlow Docker Deployment Script
# Usage: ./deploy-docker.sh

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}DeerFlow Docker Deployment${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo -e "${BLUE}[i]${NC} Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo -e "${GREEN}[✓]${NC} Docker installed"
    echo -e "${YELLOW}[!]${NC} Please log out and back in for docker group changes to take effect"
    echo -e "${YELLOW}[!]${NC} Then run this script again"
    exit 0
fi

# Install docker-compose if not present
if ! command -v docker-compose &> /dev/null; then
    echo -e "${BLUE}[i]${NC} Installing docker-compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}[✓]${NC} docker-compose installed"
fi

# Clone or update repository
APP_DIR="/home/$(whoami)/deer-flow"
if [ -d "$APP_DIR" ]; then
    echo -e "${BLUE}[i]${NC} Updating repository..."
    cd "$APP_DIR"
    git pull origin main
else
    echo -e "${BLUE}[i]${NC} Cloning repository..."
    git clone https://github.com/bytedance/deer-flow.git "$APP_DIR"
    cd "$APP_DIR"
fi

# Setup .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}[!]${NC} Created .env file - please edit with your API keys"
    echo -e "${YELLOW}[!]${NC} nano .env"
    exit 1
fi

# Build and start containers
echo -e "${BLUE}[i]${NC} Building Docker image..."
docker-compose build

echo -e "${BLUE}[i]${NC} Starting containers..."
docker-compose up -d

# Wait for container to be ready
echo -e "${BLUE}[i]${NC} Waiting for service to start..."
sleep 5

# Check if running
if docker-compose ps | grep -q "Up"; then
    echo -e "${GREEN}[✓]${NC} Container running"

    # Get container IP/port
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}')

    echo ""
    echo -e "${GREEN}Deployment successful! 🎉${NC}"
    echo ""
    echo -e "Access your API at:"
    echo -e "  ${BLUE}http://$PUBLIC_IP:8000/docs${NC}"
    echo ""
    echo -e "Useful commands:"
    echo -e "  View logs:    ${BLUE}docker-compose logs -f${NC}"
    echo -e "  Restart:      ${BLUE}docker-compose restart${NC}"
    echo -e "  Stop:         ${BLUE}docker-compose stop${NC}"
    echo -e "  Status:       ${BLUE}docker-compose ps${NC}"
    echo -e "  Update:       ${BLUE}git pull && docker-compose up -d --build${NC}"
else
    echo -e "${RED}[✗]${NC} Container failed to start"
    docker-compose logs
    exit 1
fi
