# GitHub Repository Setup Guide

**Purpose**: Push your DeerFlow code to your own GitHub repository before deploying to Lightsail.

---

## Current Status

Your repository is currently pointing to the original ByteDance repository:
```
origin: https://github.com/bytedance/deer-flow.git
```

You need to create your own GitHub repository and push your code there.

---

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. **Repository name**: `deer-flow` (or your preferred name)
3. **Visibility**: Choose **Private** or **Public**
4. **Important**: Do NOT initialize with README, .gitignore, or license (you already have these)
5. Click **"Create repository"**

GitHub will show you setup instructions - ignore them and follow the steps below instead.

---

## Step 2: Update Git Remote

```bash
# Navigate to your project directory
cd /Users/busaileh/Playground/agents/deer-flow

# Remove the ByteDance remote
git remote remove origin

# Add YOUR repository as origin
# Replace YOUR_USERNAME and YOUR_REPO_NAME with your actual values
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# If using SSH instead of HTTPS:
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git

# Verify the new remote
git remote -v
```

**Expected output**:
```
origin  https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git (fetch)
origin  https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git (push)
```

---

## Step 3: Stage All Changes

```bash
# Add deployment files
git add deployment/

# Add documentation files
git add API_DOCUMENTATION.md CLAUDE.md PROJECT_ORGANIZATION.md

# Add new source code directories
git add src/jobs/ src/middleware/

# Add new files
git add src/server/async_request.py src/server/job_manager.py
git add src/tools/firecrawl.py

# Add modified files
git add -u

# Add .dockerignore changes
git add .dockerignore
```

---

## Step 4: Commit Changes

```bash
git commit -m "Add deployment configuration and manual setup guide

- Add deployment scripts and configuration files
- Update .dockerignore to exclude documentation from builds
- Add comprehensive deployment documentation
- Add API documentation and project organization guides
- Add async job management system
- Add authentication middleware"
```

---

## Step 5: Push to GitHub

```bash
# Push your main branch to GitHub
git push -u origin main

# If your branch has a different name (check with: git branch)
git push -u origin YOUR_BRANCH_NAME
```

**First time push**: You may be prompted for GitHub credentials:
- **HTTPS**: Enter your GitHub username and Personal Access Token (not password)
- **SSH**: Make sure your SSH key is added to GitHub (Settings → SSH and GPG keys)

---

## Verification

After pushing, verify your code is on GitHub:

1. Go to `https://github.com/YOUR_USERNAME/YOUR_REPO_NAME`
2. You should see all your files including:
   - `deployment/` directory
   - `API_DOCUMENTATION.md`
   - `CLAUDE.md`
   - Updated source code

---

## Troubleshooting

### Issue: "Failed to push some refs"

**Solution**: Pull first, then push
```bash
git pull origin main --rebase
git push -u origin main
```

### Issue: "Remote origin already exists"

**Solution**: Remove and re-add
```bash
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

### Issue: Authentication failed (HTTPS)

**Solution**: Use Personal Access Token instead of password
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate new token with `repo` scope
3. Use token as password when prompted

### Issue: Permission denied (SSH)

**Solution**: Add SSH key to GitHub
```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy public key
cat ~/.ssh/id_ed25519.pub

# Add to GitHub: Settings → SSH and GPG keys → New SSH key
```

---

## After GitHub Push

Once your code is on GitHub, you can deploy to Lightsail:

```bash
# SSH to Lightsail instance
ssh -i LightsailDefaultKey.pem ubuntu@YOUR_LIGHTSAIL_IP

# Clone YOUR repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME

# Follow deployment/README.md for manual deployment steps
```

---

## Files That Won't Be Pushed (Good!)

These files are in `.gitignore` and won't be pushed to GitHub:

- `.env` - Your API keys (keep secret!)
- `conf.yaml` - Your LLM configuration
- `__pycache__/` - Python cache files
- `.venv/` - Virtual environment
- `server.log` - Log files
- `.DS_Store` - Mac system files

You'll need to create `.env` and `conf.yaml` on your Lightsail server separately.

---

## Next Steps

After successfully pushing to GitHub:

1. ✅ Code is backed up on GitHub
2. ✅ Ready to deploy to Lightsail
3. ✅ Can collaborate with others
4. ✅ Version history preserved

**Follow**: `deployment/README.md` for Lightsail deployment steps
**Follow**: `deployment/CHECKLIST.md` for deployment verification

---

**Created**: 2025-10-10
**For**: Manual GitHub repository setup before Lightsail deployment
