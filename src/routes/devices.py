"""Device Management Blueprint — handles CRUD operations for managed devices."""

import json
import threading
from flask import Blueprint, jsonify, request

from .. import database as db
from ..lib import wol as wol_mod
from ..config import load_config
from .helpers import broadcast_for

devices_bp = Blueprint("devices", __name__)


# ============================================================================
# Helpers for devices blueprint
# ============================================================================

def _scan_single_device_ports(ip: str) -> None:
    """Scan ports on a single device IP (background task)."""
    # Import here to avoid circular dependency
    from ..lib import scanner
    
    if not ip or not ip.strip():
        return
    try:
        ports = scanner.scan_ports_for_ip(ip.strip())
        if ports:
            db.save_port_scan({ip.strip(): ports})
            print(f"✓ Ports scanned for {ip}: {ports}")
    except Exception as e:
        print(f"⚠ Port scan failed for {ip}: {str(e)}")


# ============================================================================
# Device Endpoints
# ============================================================================

@devices_bp.get("/api/devices")
def api_get_devices():
    """Get all managed devices."""
    return jsonify(db.get_all_devices())


@devices_bp.post("/api/devices")
def api_add_device():
    """Add a new device."""
    data = request.json or {}
    if not data.get("mac") or not data.get("name"):
        return jsonify({"error": "name and mac required"}), 400
    
    # Check if ports were already scanned for this IP
    existing_ports = []
    if data.get("ip"):
        existing_ports = db.get_ports_from_scan(data["ip"])
    
    dev_id = db.upsert_device(
        name=data["name"],
        mac=data["mac"],
        ip=data.get("ip", ""),
        broadcast=data.get("broadcast", ""),
        group_name=data.get("group_name", "Default"),
        notes=data.get("notes", ""),
        port_checks=data.get("port_checks", []),
        open_ports=existing_ports if existing_ports else None,
    )
    
    # If no ports were found from scan, scan them now in background
    if data.get("ip") and not existing_ports:
        t = threading.Thread(target=_scan_single_device_ports, args=(data["ip"],), daemon=True)
        t.start()
    
    return jsonify({"id": dev_id}), 201


@devices_bp.put("/api/devices/<int:device_id>")
def api_update_device(device_id):
    """Update device details."""
    data = request.json or {}
    dev = db.get_device(device_id)
    if not dev:
        return jsonify({"error": "not found"}), 404
    new_ip = data.get("ip", dev["ip"])
    old_ip = dev.get("ip", "")
    
    # Check if ports were already scanned for the new IP
    open_ports_to_set = None
    if new_ip and new_ip != old_ip:
        existing_ports = db.get_ports_from_scan(new_ip)
        open_ports_to_set = existing_ports if existing_ports else None
    
    db.upsert_device(
        name=data.get("name", dev["name"]),
        mac=dev["mac"],
        ip=new_ip,
        broadcast=data.get("broadcast", dev.get("broadcast", "")),
        group_name=data.get("group_name", dev["group_name"]),
        notes=data.get("notes", dev["notes"]),
        port_checks=data.get("port_checks", json.loads(dev["port_checks"] or "[]")),
        open_ports=open_ports_to_set,
    )
    
    # If IP changed and no ports found from scan, scan them now in background
    if new_ip and new_ip != old_ip and not open_ports_to_set:
        t = threading.Thread(target=_scan_single_device_ports, args=(new_ip,), daemon=True)
        t.start()
    
    return jsonify({"ok": True})


@devices_bp.delete("/api/devices/<int:device_id>")
def api_delete_device(device_id):
    """Delete a device."""
    db.delete_device(device_id)
    return jsonify({"ok": True})
