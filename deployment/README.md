# DeerFlow Deployment Guide

**Last Updated**: 2025-10-10
**For**: AWS Lightsail and Docker deployments

---

## Quick Start

### Option 1: Automated Lightsail Deployment (Recommended)

**One command deployment** - perfect for PoC:

```bash
# On your Lightsail instance
curl -fsSL https://raw.githubusercontent.com/bytedance/deer-flow/main/deployment/deploy-lightsail.sh | bash
```

Or manually:

```bash
# 1. SSH into your Lightsail instance
ssh -i LightsailDefaultKey.pem ubuntu@YOUR_IP

# 2. Download and run deployment script
wget https://raw.githubusercontent.com/bytedance/deer-flow/main/deployment/deploy-lightsail.sh
chmod +x deploy-lightsail.sh
./deploy-lightsail.sh
```

**What it does**:
- ✅ Installs all dependencies (uv, git, nginx, certbot)
- ✅ Clones repository
- ✅ Sets up systemd service
- ✅ Configures nginx reverse proxy
- ✅ Sets up health monitoring
- ✅ Creates update script

**Time**: ~5 minutes

---

### Option 2: Docker Deployment

**For containerized deployment**:

```bash
# On your server
curl -fsSL https://raw.githubusercontent.com/bytedance/deer-flow/main/deployment/deploy-docker.sh | bash
```

Or manually:

```bash
git clone https://github.com/bytedance/deer-flow.git
cd deer-flow
cp .env.example .env
nano .env  # Add your API keys
docker-compose up -d
```

---

## Prerequisites

### For Lightsail Instance

**Recommended Instance**:
- OS: Ubuntu 22.04 LTS
- Plan: $5/month (512MB RAM, 1 vCPU, 20GB SSD)
- OR: $10/month (1GB RAM, 1 vCPU, 40GB SSD) for better performance

**Network Setup**:
1. Create static IP and attach to instance
2. Configure firewall rules:
   - Port 22 (SSH)
   - Port 80 (HTTP)
   - Port 443 (HTTPS)

**Domain Setup** (Optional):
- Point your domain A record to Lightsail static IP
- Example: `api.yourdomain.com → YOUR_STATIC_IP`

---

## Configuration

### Required Environment Variables

Edit `/home/ubuntu/deer-flow/.env`:

```bash
# LLM Configuration (REQUIRED)
OPENAI_API_KEY=sk-...

# Search Provider (REQUIRED - choose one or more)
TAVILY_API_KEY=tvly-...
# FIRECRAWL_API_KEY=fc-...
# BRAVE_API_KEY=...

# Authentication (IMPORTANT for production!)
SKIP_AUTH=false
ADMIN_API_KEY=sk_live_$(openssl rand -hex 16)
DEV_API_KEY=sk_test_$(openssl rand -hex 16)

# Optional: Database (for job persistence)
# SUPABASE_URL=https://xxx.supabase.co
# SUPABASE_KEY=...

# Optional: RAG Provider
# RAG_PROVIDER=ragflow
# RAGFLOW_API_KEY=...

# CORS (adjust for your frontend domain)
ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# Server Configuration
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=info
```

### After Editing .env

```bash
# Restart service to apply changes
sudo systemctl restart deerflow

# Check if running
sudo systemctl status deerflow
```

---

## Post-Deployment Steps

### 1. Test API

```bash
# Check API is responding
curl http://localhost:8000/docs

# From your computer (replace with your IP)
curl http://YOUR_STATIC_IP/docs
```

You should see the Swagger UI HTML.

---

### 2. Enable HTTPS (Recommended)

**With domain**:

```bash
# Install certbot (already done by script)
sudo certbot --nginx -d api.yourdomain.com

# Follow prompts to:
# - Enter email
# - Agree to terms
# - Choose redirect HTTP to HTTPS
```

Certbot will:
- Get SSL certificate from Let's Encrypt
- Update nginx configuration
- Set up auto-renewal

**Test renewal**:
```bash
sudo certbot renew --dry-run
```

---

### 3. Set Up API Keys

**Generate secure API keys**:

```bash
# Generate admin key
echo "ADMIN_API_KEY=sk_live_$(openssl rand -hex 16)"

# Generate dev key
echo "DEV_API_KEY=sk_test_$(openssl rand -hex 16)"
```

Add these to `/home/ubuntu/deer-flow/.env`:

```bash
SKIP_AUTH=false
ADMIN_API_KEY=sk_live_a1b2c3d4e5f6...
DEV_API_KEY=sk_test_1a2b3c4d5e6f...
```

**Restart service**:
```bash
sudo systemctl restart deerflow
```

---

### 4. Test Authentication

```bash
# Should fail (401 Unauthorized)
curl http://YOUR_IP/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'

# Should succeed
curl http://YOUR_IP/api/chat/stream \
  -H "Authorization: Bearer YOUR_DEV_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'
```

---

## Management Commands

### Service Management

```bash
# View logs (follow mode)
sudo journalctl -u deerflow -f

# View last 100 lines
sudo journalctl -u deerflow -n 100

# Restart service
sudo systemctl restart deerflow

# Stop service
sudo systemctl stop deerflow

# Start service
sudo systemctl start deerflow

# Check status
sudo systemctl status deerflow

# Disable service (won't start on boot)
sudo systemctl disable deerflow

# Enable service (start on boot)
sudo systemctl enable deerflow
```

---

### Update Application

**Quick update** (uses provided script):

```bash
./update-deerflow.sh
```

**Manual update**:

```bash
cd /home/ubuntu/deer-flow
git pull origin main
~/.local/bin/uv sync
sudo systemctl restart deerflow
```

---

### Nginx Management

```bash
# Test configuration
sudo nginx -t

# Reload configuration
sudo systemctl reload nginx

# Restart nginx
sudo systemctl restart nginx

# View nginx logs
sudo tail -f /var/log/nginx/deerflow-access.log
sudo tail -f /var/log/nginx/deerflow-error.log
```

---

## Monitoring

### Health Check

The deployment script sets up automatic health checks every 5 minutes.

**View health check logs**:
```bash
tail -f /home/ubuntu/health-check.log
```

**Manual health check**:
```bash
curl http://localhost:8000/docs
```

---

### Resource Usage

```bash
# CPU and memory usage
htop

# Disk usage
df -h

# Check service resource usage
systemctl status deerflow
```

---

### Application Metrics

**Check current connections**:
```bash
sudo ss -tunlp | grep :8000
```

**Monitor requests** (via nginx logs):
```bash
sudo tail -f /var/log/nginx/deerflow-access.log | grep POST
```

---

## Troubleshooting

### Issue: Service won't start

**Check logs**:
```bash
sudo journalctl -u deerflow -n 100 --no-pager
```

**Common causes**:
1. Missing API keys in `.env`
2. Port 8000 already in use
3. Python dependencies not installed

**Fix**:
```bash
# Ensure .env exists
ls -la /home/ubuntu/deer-flow/.env

# Reinstall dependencies
cd /home/ubuntu/deer-flow
~/.local/bin/uv sync

# Check if port is in use
sudo ss -tunlp | grep :8000

# Restart service
sudo systemctl restart deerflow
```

---

### Issue: Can't access from browser

**Check if service is running**:
```bash
sudo systemctl status deerflow
curl http://localhost:8000/docs  # From server
```

**Check nginx**:
```bash
sudo nginx -t
sudo systemctl status nginx
```

**Check firewall**:
```bash
# On Lightsail, check console firewall rules
# Ensure ports 80 and 443 are open
```

**Check from outside**:
```bash
# From your computer
curl -v http://YOUR_STATIC_IP/docs
```

---

### Issue: SSE streaming not working

**Check nginx configuration**:

Ensure these lines are present in nginx config:
```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;
```

**Reload nginx**:
```bash
sudo systemctl reload nginx
```

---

### Issue: 502 Bad Gateway

**Cause**: Backend not running or not accessible

**Fix**:
```bash
# Check if backend is running
sudo systemctl status deerflow

# Check if listening on port 8000
sudo ss -tunlp | grep :8000

# Restart backend
sudo systemctl restart deerflow

# Check nginx error log
sudo tail -f /var/log/nginx/deerflow-error.log
```

---

### Issue: Out of memory

**Symptoms**: Service crashes, high memory usage

**Quick fix**:
```bash
# Restart service
sudo systemctl restart deerflow
```

**Long-term solutions**:
1. Upgrade to $10/month instance (1GB RAM)
2. Add swap space:

```bash
# Create 1GB swap
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Security Best Practices

### 1. Enable Authentication

```bash
# In .env
SKIP_AUTH=false
ADMIN_API_KEY=sk_live_...
DEV_API_KEY=sk_test_...
```

### 2. Use HTTPS

```bash
sudo certbot --nginx -d api.yourdomain.com
```

### 3. Restrict SSH Access

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Set:
PermitRootLogin no
PasswordAuthentication no

# Restart SSH
sudo systemctl restart sshd
```

### 4. Enable UFW Firewall

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 5. Regular Updates

```bash
# Set up automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Manual Deployment

If you prefer to deploy manually without the script:

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

### 2. Clone Repository

```bash
git clone https://github.com/bytedance/deer-flow.git
cd deer-flow
```

### 3. Configure Environment

```bash
cp .env.example .env
nano .env  # Add your API keys
```

### 4. Install Dependencies

```bash
uv sync
```

### 5. Setup Systemd Service

```bash
sudo cp deployment/deerflow.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable deerflow
sudo systemctl start deerflow
```

### 6. Setup Nginx

```bash
sudo apt install nginx
sudo cp deployment/nginx-deerflow.conf /etc/nginx/sites-available/deerflow
sudo ln -s /etc/nginx/sites-available/deerflow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7. Setup SSL

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

---

## Files Reference

### Deployment Files

```
deployment/
├── README.md                    # This file
├── deploy-lightsail.sh         # Automated deployment script
├── deploy-docker.sh            # Docker deployment script
├── deerflow.service            # Systemd service template
└── nginx-deerflow.conf         # Nginx configuration template
```

### Application Files

```
/home/ubuntu/deer-flow/
├── .env                         # Environment configuration
├── server.py                    # Main server entry point
├── src/                         # Application code
└── pyproject.toml              # Python dependencies
```

### System Files

```
/etc/systemd/system/deerflow.service  # Systemd service
/etc/nginx/sites-available/deerflow   # Nginx configuration
/home/ubuntu/update-deerflow.sh       # Update script
/home/ubuntu/health-check.sh          # Health check script
```

---

## Cost Estimate

**Monthly Costs**:
- Lightsail instance: $5-10/month
- Static IP: Free (when attached)
- Data transfer: 1TB included
- Domain: ~$1/month (if using)
- SSL certificate: Free (Let's Encrypt)

**Total**: $5-11/month for PoC deployment

---

## Support

**Documentation**:
- Main docs: `CLAUDE.md`
- API reference: `API_DOCUMENTATION.md`
- Architecture guides: `education/`

**Issues**:
- GitHub: https://github.com/bytedance/deer-flow/issues

---

## Upgrade Path

When ready to scale beyond PoC:

1. **Vertical Scaling**: Upgrade Lightsail instance
   - $20/month: 2GB RAM, 1 vCPU
   - $40/month: 4GB RAM, 2 vCPU

2. **Horizontal Scaling**: Move to Lightsail Load Balancer
   - Multiple instances behind load balancer
   - $18/month for load balancer

3. **Full AWS**: Migrate to EC2 + RDS + ALB
   - More control and scalability
   - Use AWS Elastic Beanstalk for easier management

4. **Kubernetes**: For enterprise scale
   - AWS EKS or similar
   - Auto-scaling, high availability

---

**Last Updated**: 2025-10-10
**Deployment Version**: 1.0.0
