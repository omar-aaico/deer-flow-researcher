#!/bin/bash
# DeerFlow Automated Deployment Script for AWS Lightsail
# Usage: ./deploy-lightsail.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="deerflow-api"
APP_DIR="/home/ubuntu/deer-flow"
SERVICE_NAME="deerflow"

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}DeerFlow Lightsail Deployment${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

# Check if running on Ubuntu
if [ ! -f /etc/lsb-release ]; then
    print_error "This script is designed for Ubuntu. Please run on an Ubuntu system."
    exit 1
fi

print_info "Detected OS: $(lsb_release -d | cut -f2)"

# Update system
echo ""
print_info "Step 1: Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
print_status "System updated"

# Install uv (Python package manager)
echo ""
print_info "Step 2: Installing uv package manager..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    source $HOME/.cargo/env 2>/dev/null || true
    print_status "uv installed"
else
    print_status "uv already installed"
fi

# Install git if not present
if ! command -v git &> /dev/null; then
    print_info "Installing git..."
    sudo apt-get install -y git
    print_status "git installed"
fi

# Clone or update repository
echo ""
print_info "Step 3: Setting up application code..."
if [ -d "$APP_DIR" ]; then
    print_warning "Application directory exists. Pulling latest changes..."
    cd "$APP_DIR"
    git fetch origin
    git pull origin main
    print_status "Code updated"
else
    print_info "Cloning repository..."
    git clone https://github.com/bytedance/deer-flow.git "$APP_DIR"
    cd "$APP_DIR"
    print_status "Repository cloned"
fi

# Setup environment file
echo ""
print_info "Step 4: Configuring environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        print_warning "Created .env from .env.example"
        print_warning "IMPORTANT: Edit $APP_DIR/.env with your API keys!"
        print_warning "Required: OPENAI_API_KEY, TAVILY_API_KEY"
        print_warning "Security: Set SKIP_AUTH=false and configure API keys"
    else
        print_error ".env.example not found!"
        exit 1
    fi
else
    print_status ".env already exists"
fi

# Install Python dependencies
echo ""
print_info "Step 5: Installing Python dependencies..."
cd "$APP_DIR"
$HOME/.local/bin/uv sync
print_status "Dependencies installed"

# Create systemd service
echo ""
print_info "Step 6: Creating systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null <<EOF
[Unit]
Description=DeerFlow API Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
Environment="PATH=$HOME/.local/bin:/usr/bin"
ExecStart=$HOME/.local/bin/uv run python server.py --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
print_status "Systemd service created"

# Install and configure nginx
echo ""
print_info "Step 7: Installing nginx..."
if ! command -v nginx &> /dev/null; then
    sudo apt-get install -y nginx
    print_status "nginx installed"
else
    print_status "nginx already installed"
fi

# Configure nginx
print_info "Configuring nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;  # Replace with your domain: api.yourdomain.com

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # WebSocket and SSE support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CRITICAL for SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }

    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Enable site
if [ ! -L /etc/nginx/sites-enabled/$APP_NAME ]; then
    sudo ln -s /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
fi

# Remove default site if exists
if [ -L /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
fi

# Test nginx config
if sudo nginx -t; then
    sudo systemctl restart nginx
    print_status "nginx configured and restarted"
else
    print_error "nginx configuration test failed!"
    exit 1
fi

# Install certbot for SSL (optional but recommended)
echo ""
print_info "Step 8: Installing certbot for SSL..."
if ! command -v certbot &> /dev/null; then
    sudo apt-get install -y certbot python3-certbot-nginx
    print_status "certbot installed"
    print_warning "To enable HTTPS, run: sudo certbot --nginx -d yourdomain.com"
else
    print_status "certbot already installed"
fi

# Start application
echo ""
print_info "Step 9: Starting application..."
sudo systemctl start $SERVICE_NAME

# Wait for service to start
sleep 3

# Check if service is running
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    print_status "Application started successfully"
else
    print_error "Application failed to start"
    print_info "Check logs with: sudo journalctl -u $SERVICE_NAME -f"
    exit 1
fi

# Setup health check cron job
echo ""
print_info "Step 10: Setting up health monitoring..."
HEALTH_CHECK_SCRIPT="/home/ubuntu/health-check.sh"
cat > "$HEALTH_CHECK_SCRIPT" <<'HEALTHEOF'
#!/bin/bash
if ! curl -f http://localhost:8000/docs > /dev/null 2>&1; then
    echo "$(date): API is down, restarting..." >> /home/ubuntu/health-check.log
    sudo systemctl restart deerflow
fi
HEALTHEOF

chmod +x "$HEALTH_CHECK_SCRIPT"

# Add to crontab if not already present
(crontab -l 2>/dev/null | grep -q health-check.sh) || \
(crontab -l 2>/dev/null; echo "*/5 * * * * $HEALTH_CHECK_SCRIPT") | crontab -

print_status "Health check monitoring configured (runs every 5 minutes)"

# Setup log rotation
echo ""
print_info "Step 11: Configuring log rotation..."
sudo tee /etc/logrotate.d/$SERVICE_NAME > /dev/null <<EOF
/var/log/journal/*/*.journal {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
EOF
print_status "Log rotation configured"

# Create update script
echo ""
print_info "Step 12: Creating update script..."
cat > /home/ubuntu/update-deerflow.sh <<'UPDATEEOF'
#!/bin/bash
echo "Updating DeerFlow..."
cd /home/ubuntu/deer-flow
git pull origin main
~/.local/bin/uv sync
sudo systemctl restart deerflow
echo "Update complete!"
sudo systemctl status deerflow
UPDATEEOF

chmod +x /home/ubuntu/update-deerflow.sh
print_status "Update script created at /home/ubuntu/update-deerflow.sh"

# Final status check
echo ""
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Deployment Complete!${NC}"
echo -e "${BLUE}================================${NC}"
echo ""
print_status "Application is running"
print_status "Service: sudo systemctl status $SERVICE_NAME"
print_status "Logs: sudo journalctl -u $SERVICE_NAME -f"

# Get public IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "Unable to detect")

echo ""
echo -e "${GREEN}Access your API at:${NC}"
echo -e "  HTTP:  http://$PUBLIC_IP/docs"
echo -e "  Swagger UI: http://$PUBLIC_IP/docs"
echo -e "  ReDoc: http://$PUBLIC_IP/redoc"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Edit .env file with your API keys:"
echo -e "   ${BLUE}nano $APP_DIR/.env${NC}"
echo -e ""
echo -e "2. Set SKIP_AUTH=false and configure authentication:"
echo -e "   ${BLUE}SKIP_AUTH=false${NC}"
echo -e "   ${BLUE}ADMIN_API_KEY=sk_live_\$(openssl rand -hex 16)${NC}"
echo -e ""
echo -e "3. Restart service after editing .env:"
echo -e "   ${BLUE}sudo systemctl restart $SERVICE_NAME${NC}"
echo -e ""
echo -e "4. (Optional) Enable HTTPS with your domain:"
echo -e "   ${BLUE}sudo certbot --nginx -d api.yourdomain.com${NC}"
echo -e ""
echo -e "5. Test your API:"
echo -e "   ${BLUE}curl http://$PUBLIC_IP/docs${NC}"
echo ""

echo -e "${GREEN}Useful Commands:${NC}"
echo -e "  View logs:    ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "  Restart:      ${BLUE}sudo systemctl restart $SERVICE_NAME${NC}"
echo -e "  Stop:         ${BLUE}sudo systemctl stop $SERVICE_NAME${NC}"
echo -e "  Status:       ${BLUE}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "  Update app:   ${BLUE}./update-deerflow.sh${NC}"
echo -e "  Edit config:  ${BLUE}nano $APP_DIR/.env${NC}"
echo ""

print_warning "IMPORTANT: Don't forget to configure your API keys in .env!"
print_warning "SECURITY: Enable authentication by setting SKIP_AUTH=false"

echo ""
echo -e "${GREEN}Deployment successful! 🎉${NC}"
