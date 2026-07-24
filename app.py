import json
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

import database as db
import scanner
import wol as wol_mod
import updater
from config import load_config, save_config

app = Flask(__name__)
CORS(app)

_scan_lock = threading.Lock()
_scan_status = {"running": False, "last_run": None, "found": 0}
_port_scan_status = {"running": False, "last_run": None, "scanned": 0}
_status_check_fast_mode = False  # Track if we're in fast polling mode
_fast_mode_started_at = None  # Timestamp when fast mode was activated (failsafe timeout)

scheduler = BackgroundScheduler(daemon=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_status_check():
    """Ping all managed devices and update their online status. Switch to fast mode if devices are waking up."""
    global _status_check_fast_mode, _fast_mode_started_at
    
    devices = db.get_all_devices()
    cfg = load_config()
    for dev in devices:
        try:
            online = scanner.check_device_online(dev["ip"])
            db.update_device_status(dev["mac"], online, dev["ip"] if online else None)
        except Exception as e:
            print(f"⚠ Status check failed for {dev.get('name', 'Unknown')}: {str(e)}")
    
    # Check if any devices are still waking up
    try:
        has_waking = db.has_waking_devices()
    except Exception as e:
        print(f"⚠ Error checking waking devices: {str(e)} — falling back to normal polling")
        has_waking = False  # Fallback on error
    
    # Check for failsafe timeout: if fast mode was active for >5 min, force back to normal
    if _fast_mode_started_at:
        time_in_fast_mode = (datetime.now(timezone.utc) - _fast_mode_started_at).total_seconds()
        if time_in_fast_mode > 300:  # 5 minutes failsafe
            has_waking = False
            print(f"⚠ Fast polling timeout (5 min exceeded) — forcing back to normal mode")
    
    # Switch polling interval based on waking devices
    job = scheduler.get_job("status_check")
    if job is None:
        return  # Job was removed, exit
    
    try:
        if has_waking and not _status_check_fast_mode:
            # Switch to fast mode (10 seconds)
            job.reschedule(trigger="interval", seconds=10)
            _status_check_fast_mode = True
            _fast_mode_started_at = datetime.now(timezone.utc)
            print("→ Fast status polling enabled (10s)")
        elif not has_waking and _status_check_fast_mode:
            # Switch back to normal mode (60 seconds)
            job.reschedule(trigger="interval", seconds=60)
            _status_check_fast_mode = False
            _fast_mode_started_at = None
            print("→ Status polling back to normal (60s)")
    except Exception as e:
        print(f"✗ Failed to reschedule status check: {str(e)} — keeping current interval")


def _run_network_scan():
    if _scan_status["running"]:
        return
    _scan_status["running"] = True
    try:
        cfg = load_config()
        networks = cfg.get("scan_networks", ["192.168.1.0/24"])
        hosts = scanner.scan_network(networks)
        db.save_scan_results(hosts)
        _scan_status["found"] = len(hosts)
        _scan_status["last_run"] = datetime.now(timezone.utc).isoformat()
    finally:
        _scan_status["running"] = False


def _broadcast_for(dev: dict, cfg: dict) -> str:
    return dev.get("broadcast") or cfg.get("broadcast_address", "255.255.255.255")


def _enable_fast_polling():
    """Activate fast polling (10 sec) if not already active."""
    global _status_check_fast_mode, _fast_mode_started_at
    
    if _status_check_fast_mode:
        return  # Already in fast mode
    
    job = scheduler.get_job("status_check")
    if job is None:
        return  # Job was removed
    
    try:
        job.reschedule(trigger="interval", seconds=10)
        _status_check_fast_mode = True
        _fast_mode_started_at = datetime.now(timezone.utc)
        print("→ Fast status polling enabled (10s)")
    except Exception as e:
        print(f"✗ Failed to enable fast polling: {str(e)}")


def _scheduled_wake(device_id: int):
    dev = db.get_device(device_id)
    if not dev:
        print(f"⚠ Scheduled wake: Device {device_id} not found")
        return
    cfg = load_config()
    try:
        wol_mod.send_magic_packet(dev["mac"], _broadcast_for(dev, cfg), cfg.get("wol_port", 9))
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="schedule", success=True)
        db.set_wake_request(dev["mac"])  # Mark as "waking up"
        _enable_fast_polling()  # Activate fast polling to show "Waking up" status
        print(f"✓ Scheduled wake sent to {dev['name']} ({dev['mac']})")
    except Exception as e:
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="schedule", success=False)
        print(f"✗ Scheduled wake failed for {dev['name']}: {str(e)}")


def _rebuild_schedules():
    """Register all enabled schedules in APScheduler."""
    for job in scheduler.get_jobs():
        if job.id.startswith("dev_"):
            job.remove()

    for sched in db.get_all_schedules():
        job_id = f"dev_{sched['device_id']}_{sched['id']}"
        try:
            from apscheduler.triggers.cron import CronTrigger
            cron_str = sched["cron_expr"].strip()
            parts = cron_str.split()
            
            if len(parts) < 5:
                print(f"⚠ Schedule {sched['id']} (device {sched['device_id']}): Invalid cron expression format: {cron_str}")
                continue
            
            minute, hour, day, month, dow = parts[0], parts[1], parts[2], parts[3], parts[4]
            
            trigger = CronTrigger(
                minute=minute, hour=hour,
                day=day,
                month=month,
                day_of_week=dow,
            )
            scheduler.add_job(_scheduled_wake, trigger, args=[sched["device_id"]],
                              id=job_id, replace_existing=True)
            print(f"✓ Schedule {sched['id']} registered: {sched['device_name']} at {cron_str}")
        except Exception as e:
            print(f"✗ Failed to schedule {sched['id']}: {str(e)}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def startup():
    db.init_db()
    cfg = load_config()
    interval = cfg.get("scan_interval_seconds", 60)
    scheduler.add_job(_run_status_check, "interval", seconds=interval, id="status_check")
    scheduler.add_job(_run_network_scan, "interval", seconds=300, id="net_scan")
    _rebuild_schedules()
    scheduler.start()
    print(f"✓ APScheduler started with {len(scheduler.get_jobs())} job(s)")


# ---------------------------------------------------------------------------
# API — Devices
# ---------------------------------------------------------------------------

@app.get("/api/devices")
def api_get_devices():
    return jsonify(db.get_all_devices())


@app.post("/api/devices")
def api_add_device():
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


@app.put("/api/devices/<int:device_id>")
def api_update_device(device_id):
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


@app.delete("/api/devices/<int:device_id>")
def api_delete_device(device_id):
    db.delete_device(device_id)
    return jsonify({"ok": True})


@app.post("/api/devices/<int:device_id>/wake")
def api_wake_device(device_id):
    dev = db.get_device(device_id)
    if not dev:
        return jsonify({"error": "not found"}), 404
    cfg = load_config()
    try:
        wol_mod.send_magic_packet(
            dev["mac"],
            _broadcast_for(dev, cfg),
            cfg.get("wol_port", 9),
        )
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="manual", success=True)
        db.set_wake_request(dev["mac"])  # Mark as "waking up"
        _enable_fast_polling()  # Activate fast polling to show "Waking up" status
        return jsonify({"ok": True})
    except Exception as e:
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="manual", success=False)
        return jsonify({"error": str(e)}), 500


@app.post("/api/wake/bulk")
def api_wake_bulk():
    data = request.json or {}
    ids = data.get("ids", [])
    cfg = load_config()
    results = []
    for dev_id in ids:
        dev = db.get_device(dev_id)
        if not dev:
            continue
        try:
            wol_mod.send_magic_packet(dev["mac"], _broadcast_for(dev, cfg), cfg.get("wol_port", 9))
            db.log_wake(dev_id, dev["name"], dev["mac"], triggered_by="bulk", success=True)
            db.set_wake_request(dev["mac"])  # Mark as "waking up"
            results.append({"id": dev_id, "ok": True})
        except Exception as e:
            results.append({"id": dev_id, "ok": False, "error": str(e)})
    _enable_fast_polling()  # Activate fast polling to show "Waking up" status for all
    return jsonify(results)


# ---------------------------------------------------------------------------
# API — Schedules
# ---------------------------------------------------------------------------

@app.get("/api/devices/<int:device_id>/schedules")
def api_get_schedules(device_id):
    return jsonify(db.get_schedules(device_id))


@app.post("/api/devices/<int:device_id>/schedules")
def api_add_schedule(device_id):
    data = request.json or {}
    if not data.get("cron_expr"):
        return jsonify({"error": "cron_expr required"}), 400
    sched_id = db.add_schedule(device_id, data["cron_expr"], data.get("label", ""))
    _rebuild_schedules()
    return jsonify({"id": sched_id}), 201


@app.delete("/api/schedules/<int:schedule_id>")
def api_delete_schedule(schedule_id):
    db.delete_schedule(schedule_id)
    _rebuild_schedules()
    return jsonify({"ok": True})


@app.patch("/api/schedules/<int:schedule_id>")
def api_toggle_schedule(schedule_id):
    data = request.json or {}
    db.toggle_schedule(schedule_id, data.get("enabled", True))
    _rebuild_schedules()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Scanner
# ---------------------------------------------------------------------------

@app.get("/api/scan/results")
def api_scan_results():
    return jsonify({"results": db.get_scan_results(), "status": _scan_status,
                    "port_scan_status": _port_scan_status})


@app.post("/api/scan/start")
def api_scan_start():
    if _scan_status["running"]:
        return jsonify({"error": "scan already running"}), 409
    t = threading.Thread(target=_run_network_scan, daemon=True)
    t.start()
    return jsonify({"ok": True})


def _run_port_scan():
    if _port_scan_status["running"]:
        return
    _port_scan_status["running"] = True
    try:
        results = db.get_scan_results()
        devices_list = db.get_all_devices()
        ips = list({r["ip"] for r in results} | {d["ip"] for d in devices_list if d.get("ip")})
        port_map = scanner.scan_ports_bulk(ips)
        db.save_port_scan(port_map)
        _port_scan_status["scanned"] = len(ips)
        _port_scan_status["last_run"] = datetime.now(timezone.utc).isoformat()
    finally:
        _port_scan_status["running"] = False


def _scan_single_device_ports(ip: str) -> None:
    """Scan ports on a single device IP (background task)."""
    if not ip or not ip.strip():
        return
    try:
        ports = scanner.scan_ports_for_ip(ip.strip())
        if ports:
            db.save_port_scan({ip.strip(): ports})
            print(f"✓ Ports scanned for {ip}: {ports}")
    except Exception as e:
        print(f"⚠ Port scan failed for {ip}: {str(e)}")


@app.post("/api/scan/ports")
def api_port_scan_start():
    if _port_scan_status["running"]:
        return jsonify({"error": "port scan already running"}), 409
    t = threading.Thread(target=_run_port_scan, daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.get("/api/scan/ports/status")
def api_port_scan_status():
    return jsonify(_port_scan_status)


# ---------------------------------------------------------------------------
# API — History
# ---------------------------------------------------------------------------

@app.get("/api/history")
def api_history():
    limit = int(request.args.get("limit", 100))
    return jsonify(db.get_history(limit))


# ---------------------------------------------------------------------------
# API — Config
# ---------------------------------------------------------------------------

@app.get("/api/config")
def api_get_config():
    return jsonify(load_config())


@app.post("/api/config")
def api_save_config():
    data = request.json or {}
    cfg = load_config()
    # normalize scan_networks: accept string (newline-separated) or list
    if "scan_networks" in data and isinstance(data["scan_networks"], str):
        data["scan_networks"] = [n.strip() for n in data["scan_networks"].splitlines() if n.strip()]
    cfg.update(data)
    save_config(cfg)
    # reschedule status check with new interval
    try:
        scheduler.reschedule_job("status_check", trigger="interval",
                                 seconds=cfg.get("scan_interval_seconds", 60))
    except Exception:
        pass
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Update check
# ---------------------------------------------------------------------------

@app.get("/api/update/check")
def api_update_check():
    return jsonify(updater.is_update_available())


@app.get("/api/update/version")
def api_version():
    return jsonify({"version": updater.get_local_version()})


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    startup()
    app.run(host="0.0.0.0", port=5000, debug=False)
