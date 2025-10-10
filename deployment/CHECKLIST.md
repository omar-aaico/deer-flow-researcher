# DeerFlow Deployment Checklist

## Pre-Deployment

- [ ] **AWS Lightsail Setup**
  - [ ] Create Ubuntu 22.04 instance ($5 or $10/month)
  - [ ] Create and attach static IP
  - [ ] Configure firewall (ports 22, 80, 443)
  - [ ] Download SSH key

- [ ] **Obtain API Keys**
  - [ ] OpenAI API key
  - [ ] Tavily Search API key (or alternative)
  - [ ] (Optional) Supabase credentials
  - [ ] (Optional) RAG provider credentials

- [ ] **Domain Setup** (Optional but recommended)
  - [ ] Purchase domain
  - [ ] Point A record to Lightsail static IP
  - [ ] Wait for DNS propagation (5-30 minutes)

---

## Automated Deployment

- [ ] **SSH into Instance**
  ```bash
  ssh -i LightsailDefaultKey.pem ubuntu@YOUR_STATIC_IP
  ```

- [ ] **Run Deployment Script**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/bytedance/deer-flow/main/deployment/deploy-lightsail.sh | bash
  ```

- [ ] **Configure Environment**
  ```bash
  nano /home/ubuntu/deer-flow/.env
  ```
  - [ ] Add `OPENAI_API_KEY`
  - [ ] Add `TAVILY_API_KEY`
  - [ ] Set `SKIP_AUTH=false`
  - [ ] Generate `ADMIN_API_KEY=sk_live_$(openssl rand -hex 16)`
  - [ ] Generate `DEV_API_KEY=sk_test_$(openssl rand -hex 16)`
  - [ ] Update `ALLOWED_ORIGINS` if using frontend

- [ ] **Restart Service**
  ```bash
  sudo systemctl restart deerflow
  ```

- [ ] **Verify Running**
  ```bash
  sudo systemctl status deerflow
  curl http://localhost:8000/docs
  ```

---

## SSL Setup (Highly Recommended)

- [ ] **Install SSL Certificate**
  ```bash
  sudo certbot --nginx -d api.yourdomain.com
  ```
  - [ ] Enter email
  - [ ] Agree to terms
  - [ ] Choose redirect HTTP to HTTPS

- [ ] **Test Auto-Renewal**
  ```bash
  sudo certbot renew --dry-run
  ```

---

## Testing

- [ ] **API Health Check**
  ```bash
  curl https://api.yourdomain.com/health
  # or
  curl http://YOUR_STATIC_IP/health
  ```

- [ ] **Swagger UI**
  - [ ] Visit https://api.yourdomain.com/docs
  - [ ] Check all endpoints visible

- [ ] **Authentication Test**
  ```bash
  # Should fail (401)
  curl https://api.yourdomain.com/api/chat/stream \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"test"}]}'

  # Should succeed
  curl https://api.yourdomain.com/api/chat/stream \
    -H "Authorization: Bearer YOUR_DEV_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"What is AI?"}]}'
  ```

- [ ] **SSE Streaming Test**
  ```bash
  curl -N https://api.yourdomain.com/api/chat/stream \
    -H "Authorization: Bearer YOUR_DEV_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "messages":[{"role":"user","content":"Brief overview of Python"}],
      "max_step_num":1,
      "auto_accepted_plan":true
    }'
  ```

---

## Production Hardening

- [ ] **Security**
  - [ ] Verify `SKIP_AUTH=false` in `.env`
  - [ ] Store API keys securely (password manager)
  - [ ] Restrict SSH access:
    ```bash
    sudo nano /etc/ssh/sshd_config
    # Set: PermitRootLogin no
    # Set: PasswordAuthentication no
    sudo systemctl restart sshd
    ```
  - [ ] Enable UFW firewall:
    ```bash
    sudo ufw allow 22/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw enable
    ```

- [ ] **Monitoring**
  - [ ] Verify health check working:
    ```bash
    tail -f /home/ubuntu/health-check.log
    ```
  - [ ] Test auto-restart on failure:
    ```bash
    sudo killall python  # Service should restart
    sleep 10
    sudo systemctl status deerflow  # Should be running
    ```

- [ ] **Backups**
  - [ ] Create Lightsail snapshot (via console)
  - [ ] Schedule weekly snapshots
  - [ ] Test restore process

- [ ] **Updates**
  - [ ] Enable automatic security updates:
    ```bash
    sudo apt install unattended-upgrades
    sudo dpkg-reconfigure -plow unattended-upgrades
    ```

---

## Documentation

- [ ] **Save Configuration**
  - [ ] Document API keys (in secure location)
  - [ ] Note static IP address
  - [ ] Note domain configuration
  - [ ] Save SSH key securely

- [ ] **Team Access**
  - [ ] Share API endpoint URL
  - [ ] Distribute API keys (DEV_API_KEY for testing)
  - [ ] Share API documentation link
  - [ ] Provide troubleshooting contacts

---

## Post-Deployment

- [ ] **Monitor First 24 Hours**
  - [ ] Check logs for errors:
    ```bash
    sudo journalctl -u deerflow -f
    ```
  - [ ] Monitor resource usage:
    ```bash
    htop
    ```
  - [ ] Check disk space:
    ```bash
    df -h
    ```

- [ ] **Performance Baseline**
  - [ ] Test response times
  - [ ] Note resource usage
  - [ ] Monitor memory consumption

- [ ] **User Acceptance**
  - [ ] Test with real queries
  - [ ] Verify SSE streaming works
  - [ ] Test from different locations/networks
  - [ ] Gather initial feedback

---

## Maintenance Schedule

### Daily
- [ ] Check service status
- [ ] Review error logs (if any)

### Weekly
- [ ] Review access logs
- [ ] Check disk space
- [ ] Test health check

### Monthly
- [ ] Update application:
  ```bash
  ./update-deerflow.sh
  ```
- [ ] Review and rotate API keys
- [ ] Create Lightsail snapshot
- [ ] Review resource usage trends

### Quarterly
- [ ] Security audit
- [ ] Performance review
- [ ] Cost review
- [ ] Consider scaling needs

---

## Emergency Contacts

**Deployment Issues**:
- GitHub Issues: https://github.com/bytedance/deer-flow/issues
- Documentation: `/home/ubuntu/deer-flow/deployment/README.md`

**AWS Support**:
- Lightsail Console: https://lightsail.aws.amazon.com/
- AWS Support: (if you have support plan)

---

## Quick Recovery

**If service is down**:
```bash
# 1. Check status
sudo systemctl status deerflow

# 2. View recent logs
sudo journalctl -u deerflow -n 50

# 3. Restart service
sudo systemctl restart deerflow

# 4. If still failing, check .env
nano /home/ubuntu/deer-flow/.env

# 5. Check nginx
sudo nginx -t
sudo systemctl status nginx
```

**If need to rollback**:
```bash
cd /home/ubuntu/deer-flow
git log --oneline -5  # Find previous commit
git checkout COMMIT_HASH
~/.local/bin/uv sync
sudo systemctl restart deerflow
```

---

## Success Criteria

✅ Service running and stable
✅ Accessible via HTTPS
✅ Authentication working
✅ SSE streaming functional
✅ Health checks passing
✅ Auto-restart on failure
✅ Logs being written
✅ SSL certificate valid
✅ All tests passing

---

**Deployment Date**: _____________
**Deployed By**: _____________
**Instance IP**: _____________
**Domain**: _____________
**Notes**: _____________
