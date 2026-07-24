## v1.2.6 Release Notes

**Title:** v1.2.6 - Dual Clock Display (Local + LXC)

**Description:**

## Changes
- Display both local machine time and LXC container time in topbar
- Local time: Full format HH:MM:SS (e.g., 23:57:01)
- LXC time: Compact format HH:SS (e.g., LXC 23:01) 
- Display format: "23:57:01 | LXC 23:01"
- Hover tooltip shows complete timestamps for both
- Useful for debugging timezone and time sync issues on Proxmox LXC

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.6
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```
