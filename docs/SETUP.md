# Setting Up GitHub Repositories

Quick reference for deploying agents to GitHub.

## Prerequisites

- GitHub account with appropriate permissions
- `git` command-line tool installed
- SSH or HTTPS credentials configured

## Step 1: Create Repositories on GitHub

1. Go to https://github.com/new
2. Create **first repository**: `maverick-terminal-agent`
   - Description: "Maverick Terminal Agent - Terminal provisioning automation"
   - Visibility: **Private**
   - Do NOT initialize with README (we have one)
   - Click "Create repository"

3. Create **second repository**: `kit-dashboard-agent`
   - Description: "KIT Dashboard Agent - Merchant onboarding automation"
   - Visibility: **Private**
   - Do NOT initialize with README (we have one)
   - Click "Create repository"

## Step 2: Initialize and Push Maverick Agent

```bash
cd /Users/walklikeaman/GitHub/maverick-terminal-agent

# Initialize git
git init
git add .
git commit -m "Initial commit: Maverick Terminal Agent"

# Add remote (replace YOUR_ORG with your GitHub org/username)
git remote add origin https://github.com/YOUR_ORG/maverick-terminal-agent.git

# Rename branch to main and push
git branch -M main
git push -u origin main
```

## Step 3: Initialize and Push Kit Dashboard Agent

```bash
cd /Users/walklikeaman/GitHub/kit-dashboard-agent

# Initialize git
git init
git add .
git commit -m "Initial commit: KIT Dashboard Agent"

# Add remote
git remote add origin https://github.com/YOUR_ORG/kit-dashboard-agent.git

# Rename branch to main and push
git branch -M main
git push -u origin main
```

## Step 4: Configure Repository Settings

For **both repositories**:

### Branch Protection

1. Go to Settings → Branches
2. Click "Add rule"
3. Apply to branch: `main`
4. Enable:
   - ✅ Require pull request reviews before merging
   - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ Require status checks to pass before merging (when CI/CD added)
5. Save

### Collaborators (if needed)

Settings → Collaborators → Add teammates with appropriate roles

## Step 5: Install Dependencies

### Maverick Terminal Agent

```bash
cd /Users/walklikeaman/GitHub/maverick-terminal-agent
pip install -e .              # Basic installation
pip install -e '.[ocr]'       # With OCR support
pip install -e '.[dev]'       # With development tools
```

### KIT Dashboard Agent

```bash
cd /Users/walklikeaman/GitHub/kit-dashboard-agent
pip install -e .              # Basic installation
pip install -e '.[ocr,browser]'  # With OCR and browser automation
pip install -e '.[dev]'       # With development tools

# Install browser drivers
playwright install chromium
```

## Step 6: Create `.env` Files

### Maverick Agent

Create `/Users/walklikeaman/GitHub/maverick-terminal-agent/.env`:

```bash
# Email configuration (optional)
MAIL_PROVIDER=imap
MAIL_IMAP_HOST=mail.example.com
MAIL_IMAP_PORT=993
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-password
MAIL_IMAP_MAILBOX=INBOX
MAIL_SCAN_LIMIT=50
```

### Kit Dashboard Agent

Create `/Users/walklikeaman/GitHub/kit-dashboard-agent/.env`:

```bash
KIT_DASHBOARD_EMAIL=your-email@kitdashboard.com
KIT_DASHBOARD_PASSWORD=your-password
KIT_DASHBOARD_URL=https://kitdashboard.com/
```

## Step 7: Test Installations

### Maverick

```bash
cd /Users/walklikeaman/GitHub/maverick-terminal-agent
maverick parse-pdf /path/to/test.pdf
```

### Kit Dashboard

```bash
cd /Users/walklikeaman/GitHub/kit-dashboard-agent
kit parse-docs /path/to/application.pdf
```

## Ongoing Development

### Create a feature branch

```bash
git checkout -b feature/your-feature-name
# Make changes...
git add .
git commit -m "Describe your changes"
git push -u origin feature/your-feature-name
```

### Create a pull request

1. Go to GitHub repository
2. Click "Compare & pull request"
3. Add description of changes
4. Request reviewers
5. Merge when approved

### Pull latest changes

```bash
git pull origin main
```

---

## Troubleshooting

### "fatal: origin does not appear to be a git repository"

You forgot to set the remote URL. Fix with:

```bash
git remote add origin https://github.com/YOUR_ORG/repo-name.git
```

### "remote: Permission denied (publickey)"

SSH key is not configured. Either:
- Use HTTPS URLs instead of SSH, or
- Add your SSH key to GitHub (Settings → SSH Keys)

### ".env file not working"

- Verify `.gitignore` has `.env` (don't commit secrets!)
- Reload terminal or run `source .env`
- Use `python-dotenv` to load in code

### Tesseract not found

```bash
# macOS
brew install tesseract

# Ubuntu
sudo apt install tesseract-ocr
```

---

**Status:** Ready to deploy  
**Version:** 1.0.0  
**Last Updated:** 2026-04-24
