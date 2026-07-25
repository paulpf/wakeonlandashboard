"""Shared helper functions for routes."""


def broadcast_for(dev: dict, cfg: dict) -> str:
    """Get the broadcast address for a device (device-specific or config default)."""
    return dev.get("broadcast") or cfg.get("broadcast_address", "255.255.255.255")
