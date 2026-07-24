#!/usr/bin/env python3
"""Create GitHub Releases for v1.2.2, v1.2.3, v1.2.4"""
import subprocess
import json

releases = [
    {
        "tag": "v1.2.2",
        "title": "v1.2.2 - Schedule Display on Widgets",
        "body": """## Changes
- Display enabled schedules on device cards with human-readable cron descriptions
- Consolidated schedule modal for add/edit operations
- Fix false "online" status after delay by preserving device IP on offline
- Filter multicast, broadcast, and invalid addresses from network scanner
- Fix update checking to detect Git tags when GitHub Release doesn't exist
- Proper timestamp conversion from SQLite to ISO 8601 for JavaScript Date parsing

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.2
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```
"""
    },
    {
        "tag": "v1.2.3",
        "title": "v1.2.3 - Schedule Edit Fix",
        "body": """## Changes
- Fix hour select value matching when editing existing schedules
- Hour dropdown values now correctly match parsed cron expressions (string format)
- Ensures proper time display when opening schedule editor

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.3
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```
"""
    },
    {
        "tag": "v1.2.4",
        "title": "v1.2.4 - Server Time Display",
        "body": """## Changes
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
"""
    }
]

for rel in releases:
    cmd = [
        "gh", "release", "create", rel["tag"],
        "--title", rel["title"],
        "--notes", rel["body"],
        "--repo", "paulpf/wakeonlandashboard"
    ]
    
    print(f"Creating {rel['tag']}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ {rel['tag']} created")
    else:
        print(f"⚠️  {rel['tag']}: {result.stderr}")

print("\nDone!")
