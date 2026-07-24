#!/usr/bin/env python3
"""Test script to check if schedules are registered."""

from app import db

db.init_db()

# Check if there are any schedules
schedules = db.get_all_schedules()
print(f'Found {len(schedules)} enabled schedule(s)')

if schedules:
    for s in schedules:
        print(f'  - Device {s["device_id"]}: {s["cron_expr"]}')
else:
    print('  (no schedules found)')
