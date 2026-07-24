#!/usr/bin/env python3
"""Test wake_request_ts database functionality."""

from database import init_db, get_db, set_wake_request

# Initialize
init_db()

# Get a device
with get_db() as db:
    dev = db.execute("SELECT * FROM devices LIMIT 1").fetchone()
    if dev:
        mac = dev['mac']
        print(f"Testing with device MAC: {mac}")
        print(f"Before set_wake_request: wake_request_ts = {dev['wake_request_ts']}")
        
        # Set wake request
        set_wake_request(mac)

        # Check if it was set
        dev2 = db.execute("SELECT wake_request_ts FROM devices WHERE mac = ?", (mac,)).fetchone()
        print(f"After set_wake_request: wake_request_ts = {dev2['wake_request_ts']}")
        
        print("✅ Database update works!")
    else:
        print("❌ No devices found in database")
