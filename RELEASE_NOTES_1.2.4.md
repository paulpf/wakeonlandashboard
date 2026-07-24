## v1.2.4 Release Notes

**Title:** v1.2.4 - Server Time Display

**Description:**

## Changes
- Add server time display in topbar to show LXC container timezone
- Display format: DD.MM.YYYY HH:MM:SS (e.g., 24.07.2026 23:31:19)
- Updates every 5 seconds from container
- Shows "Server-Zeit (LXC Container)" in tooltip
- Helpful for verifying timezone configuration on Proxmox LXC

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.4
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```

## Note: Timezone Configuration
If the time shows UTC instead of your local timezone:
```bash
timedatectl set-timezone Europe/Berlin  # or your timezone
systemctl restart wol-dashboard
```
