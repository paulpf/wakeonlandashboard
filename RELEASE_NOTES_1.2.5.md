## v1.2.5 Release Notes

**Title:** v1.2.5 - One-Click Update from UI

**Description:**

## Changes
- Add one-click "Update durchführen" button in Settings → Updates
- Automatically fetches tags, checks out new version, reinstalls dependencies, restarts service
- Shows progress status during update
- Auto-reloads page after service restart
- Confirmation dialog prevents accidental updates

## Features
- No manual command entry needed
- Backend handles: `git fetch`, `git checkout`, `pip install`, `systemctl restart`
- Safe background execution via threading
- Perfect for Proxmox LXC deployments where SSH access may be limited

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.5
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```

## Usage
1. Go to Settings → Updates
2. Click "Auf Updates prüfen"
3. When update available, click "Update durchführen" button
4. Confirm the dialog
5. Service will restart automatically and page will reload
