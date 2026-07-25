# v1.2.2 Release Notes

## Features

- **Display schedules on device widgets** — Enabled schedules are now visible directly on device cards with human-readable cron times (e.g., "19:00 — Mo–Fr")
- Better visual organization with cron descriptions and optional labels

## Bug Fixes

- **IP persistence fix** — Device IP is now preserved when going offline, ensuring proper status detection when devices reconnect
- **Status comparison fix** — Normalized bool/int status comparisons to prevent state mismatches
- **Broken edit modal fix** — Removed stale references preventing device edit button from functioning  
- **Network scan filter** — Broadcast and multicast addresses (255.255.255.255, 224.0.0.0-239.255.255.255, x.x.x.0, x.x.x.255) are now excluded from scan results, showing only real devices

## Technical Improvements

- Schedule CRUD in database now includes enabled schedules in device responses
- ARP scanner validates all discovered IPs as unicast addresses
- Improved type safety in status checks

## Installation

```bash
pip install -r requirements.txt
python app.py
```

See README.md for full setup instructions.
