"""Application constants for WoL Dashboard."""

# ============================================================================
# Event Types
# ============================================================================

EVENT_DEVICE_STATUS_CHANGED = "device_status_changed"
EVENT_DEVICE_WAKING_UP = "device_waking_up"


# ============================================================================
# Wake Trigger Sources
# ============================================================================

TRIGGER_MANUAL = "manual"
TRIGGER_BULK = "bulk"
TRIGGER_SCHEDULE = "schedule"


# ============================================================================
# Polling Intervals (seconds)
# ============================================================================

POLL_INTERVAL_FAST = 10  # Fast mode: check every 10 seconds while devices are waking
POLL_INTERVAL_NORMAL = 60  # Normal mode: check every 60 seconds (default)
SCAN_INTERVAL_NETWORK = 300  # Network scan: every 5 minutes
FAST_MODE_TIMEOUT = 300  # Fast mode failsafe: max 5 minutes before fallback to normal


# ============================================================================
# Scheduler Configuration
# ============================================================================

SCHEDULER_TRIGGER_TYPE = "interval"
