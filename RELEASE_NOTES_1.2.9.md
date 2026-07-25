## v1.2.9 Release Notes

**Title:** v1.2.9 - Fix Day-of-Week Scheduling Bug

**Description:**

## Bugfix
- Fix schedule day-of-week conversion from standard cron (Sun=0…Sat=6) to APScheduler's ISO 8601 convention (Mon=0…Sat=5, Sun=6)
- Schedules for Saturday and other days were firing on the wrong day (e.g. Saturday fired on Sunday)
- Added `_convert_cron_dow()` helper to correctly remap day values before registering APScheduler triggers

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.9
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```

## Testing
1. Create a schedule for a specific day (e.g. Saturday at 08:45)
2. Verify the schedule fires on the correct day
