import json
import threading
import queue
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template, Response
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

from . import database as db
from .lib import scanner
from .lib import wol as wol_mod
from .lib import updater
from .config import load_config, save_config, BASE_DIR
from .routes import devices_bp
from .routes.helpers import broadcast_for
from .constants import (
    EVENT_DEVICE_STATUS_CHANGED, EVENT_DEVICE_WAKING_UP,
    TRIGGER_MANUAL, TRIGGER_BULK, TRIGGER_SCHEDULE,
    POLL_INTERVAL_FAST, POLL_INTERVAL_NORMAL, SCAN_INTERVAL_NETWORK, FAST_MODE_TIMEOUT,
    SCHEDULER_TRIGGER_TYPE
)

# Flask app with absolute paths for templates and static files
template_dir = os.path.join(BASE_DIR, "templates")
static_dir = os.path.join(BASE_DIR, "static")
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)

# Register Flask blueprints
app.register_blueprint(devices_bp)

_scan_lock = threading.Lock()
_scan_status = {"running": False, "last_run": None, "found": 0}
_port_scan_status = {"running": False, "last_run": None, "scanned": 0}
_status_check_fast_mode = False  # Track if we're in fast polling mode
_fast_mode_started_at = None  # Timestamp when fast mode was activated (failsafe timeout)

# SSE (Server-Sent Events) for real-time updates
_event_subscribers = []
_event_lock = threading.Lock()

scheduler = BackgroundScheduler(daemon=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _broadcast_device_event(event_type: str, device_id: int = None, data: dict = None):
    """Broadcast a device event to all connected SSE clients."""
    event = {
        "type": event_type,
        "device_id": device_id,
        "data": data or {},
        "ts": datetime.now(timezone.utc).isoformat()
    }
    with _event_lock:
        for q in _event_subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # Client disconnected or slow


def _run_status_check():
    """Ping all managed devices and update their online status. Switch to fast mode if devices are waking up."""
    global _status_check_fast_mode, _fast_mode_started_at
    
    devices = db.get_all_devices()
    cfg = load_config()
    for dev in devices:
        try:
            online = scanner.check_device_online(dev["ip"])
            old_status = bool(dev["is_online"])  # Convert INT to BOOL for consistent comparison
            online = bool(online)  # Ensure online is BOOL, not INT
            
            # Update status and preserve IP (don't clear it when device goes offline)
            db.update_device_status(dev["mac"], online, dev["ip"])
            
            # Broadcast status change event only if status actually changed
            if old_status != online:
                _broadcast_device_event(EVENT_DEVICE_STATUS_CHANGED, dev["id"], {"online": online})
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
        if time_in_fast_mode > FAST_MODE_TIMEOUT:
            has_waking = False
            print(f"⚠ Fast polling timeout (5 min exceeded) — forcing back to normal mode")
    
    # Switch polling interval based on waking devices
    job = scheduler.get_job("status_check")
    if job is None:
        return  # Job was removed, exit
    
    try:
        if has_waking and not _status_check_fast_mode:
            # Switch to fast mode
            job.reschedule(trigger=SCHEDULER_TRIGGER_TYPE, seconds=POLL_INTERVAL_FAST)
            _status_check_fast_mode = True
            _fast_mode_started_at = datetime.now(timezone.utc)
            print(f"→ Fast status polling enabled ({POLL_INTERVAL_FAST}s)")
        elif not has_waking and _status_check_fast_mode:
            # Switch back to normal mode
            job.reschedule(trigger=SCHEDULER_TRIGGER_TYPE, seconds=POLL_INTERVAL_NORMAL)
            _status_check_fast_mode = False
            _fast_mode_started_at = None
            print(f"→ Status polling back to normal ({POLL_INTERVAL_NORMAL}s)")
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


def _enable_fast_polling():
    """Activate fast polling if not already active."""
    global _status_check_fast_mode, _fast_mode_started_at
    
    if _status_check_fast_mode:
        return  # Already in fast mode
    
    job = scheduler.get_job("status_check")
    if job is None:
        return  # Job was removed
    
    try:
        job.reschedule(trigger=SCHEDULER_TRIGGER_TYPE, seconds=POLL_INTERVAL_FAST)
        _status_check_fast_mode = True
        _fast_mode_started_at = datetime.now(timezone.utc)
        print(f"→ Fast status polling enabled ({POLL_INTERVAL_FAST}s)")
    except Exception as e:
        print(f"✗ Failed to enable fast polling: {str(e)}")


def _send_wake_packet(device_id: int, triggered_by: str = TRIGGER_MANUAL) -> tuple[bool, str]:
    """
    Consolidated WoL packet sending logic.
    
    Args:
        device_id: Device to wake
        triggered_by: Trigger source ("manual", "bulk", "schedule")
    
    Returns:
        (success: bool, error_message: str or empty string)
    """
    dev = db.get_device(device_id)
    if not dev:
        msg = f"Device {device_id} not found"
        print(f"⚠ Wake: {msg}")
        return False, msg
    
    cfg = load_config()
    try:
        wol_mod.send_magic_packet(
            dev["mac"],
            broadcast_for(dev, cfg),
            cfg.get("wol_port", 9),
        )
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by=triggered_by, success=True)
        db.set_wake_request(dev["mac"])  # Mark as "waking up"
        _broadcast_device_event(EVENT_DEVICE_WAKING_UP, device_id, {"triggered_by": triggered_by})
        return True, ""
    except Exception as e:
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by=triggered_by, success=False)
        msg = str(e)
        print(f"✗ Wake failed for {dev['name']}: {msg}")
        return False, msg


def _scheduled_wake(device_id: int):
    """Execute a scheduled wake for a device."""
    success, error = _send_wake_packet(device_id, triggered_by=TRIGGER_SCHEDULE)
    if success:
        dev = db.get_device(device_id)
        if dev:
            print(f"✓ Scheduled wake sent to {dev['name']} ({dev['mac']})")
        _enable_fast_polling()
    # Error message already printed by _send_wake_packet()


def _convert_cron_dow(dow: str) -> str:
    """Convert standard Unix cron day-of-week (Sun=0, Mon=1, ..., Sat=6) to
    APScheduler's ISO 8601 convention (Mon=0, Tue=1, ..., Sat=5, Sun=6).
    Formula: apscheduler_value = (cron_value + 6) % 7
    Handles '*', comma-separated values, and ranges (e.g. '1-5').
    """
    if dow == '*':
        return dow
    result = []
    for part in dow.split(','):
        if '-' in part:
            start, end = part.split('-', 1)
            result.append(f"{(int(start) + 6) % 7}-{(int(end) + 6) % 7}")
        else:
            result.append(str((int(part) + 6) % 7))
    return ','.join(result)


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
            # The UI stores day-of-week using standard Unix cron (Sun=0, Mon=1, ..., Sat=6).
            # APScheduler's CronTrigger uses ISO 8601 (Mon=0, ..., Sat=5, Sun=6).
            # Convert so the trigger fires on the correct day.
            dow_aps = _convert_cron_dow(dow)

            trigger = CronTrigger(
                minute=minute, hour=hour,
                day=day,
                month=month,
                day_of_week=dow_aps,
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
    interval = cfg.get("scan_interval_seconds", POLL_INTERVAL_NORMAL)
    scheduler.add_job(_run_status_check, SCHEDULER_TRIGGER_TYPE, seconds=interval, id="status_check")
    scheduler.add_job(_run_network_scan, SCHEDULER_TRIGGER_TYPE, seconds=SCAN_INTERVAL_NETWORK, id="net_scan")
    _rebuild_schedules()
    scheduler.start()
    # Run initial status check to ensure devices have correct online/offline status on startup
    print("> Running initial status check...")
    _run_status_check()
    print(f"+ APScheduler started with {len(scheduler.get_jobs())} job(s)")


# ---------------------------------------------------------------------------
# API — Devices (see routes/devices.py)
# ---------------------------------------------------------------------------


@app.post("/api/devices/<int:device_id>/wake")
def api_wake_device(device_id):
    """Wake a single device."""
    dev = db.get_device(device_id)
    if not dev:
        return jsonify({"error": "not found"}), 404
    
    success, error = _send_wake_packet(device_id, triggered_by=TRIGGER_MANUAL)
    if success:
        _enable_fast_polling()  # Activate fast polling to show "Waking up" status
        return jsonify({"ok": True})
    else:
        return jsonify({"error": error}), 500


@app.post("/api/wake/bulk")
def api_wake_bulk():
    """Wake multiple devices at once."""
    data = request.json or {}
    ids = data.get("ids", [])
    results = []
    for dev_id in ids:
        dev = db.get_device(dev_id)
        if not dev:
            # Skip non-existent devices (don't add to results)
            continue
        
        success, error = _send_wake_packet(dev_id, triggered_by=TRIGGER_BULK)
        if success:
            results.append({"id": dev_id, "ok": True})
        else:
            results.append({"id": dev_id, "ok": False, "error": error})
    
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
def api_patch_schedule(schedule_id):
    data = request.json or {}
    # Toggle enabled status
    if "enabled" in data:
        db.toggle_schedule(schedule_id, data.get("enabled", True))
    # Update cron expression and/or label
    if "cron_expr" in data or "label" in data:
        db.update_schedule(
            schedule_id,
            cron_expr=data.get("cron_expr"),
            label=data.get("label")
        )
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
        scheduler.reschedule_job("status_check", trigger=SCHEDULER_TRIGGER_TYPE,
                                 seconds=cfg.get("scan_interval_seconds", POLL_INTERVAL_NORMAL))
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


@app.post("/api/update/apply")
def api_update_apply():
    """Apply available update: fetch tags, checkout, reinstall, restart."""
    import subprocess
    import os
    
    try:
        # Check if update is available
        update_info = updater.is_update_available()
        if not update_info.get("available"):
            return jsonify({"error": "No update available"}), 400
        
        remote = update_info.get("remote")
        if not remote:
            return jsonify({"error": "Could not determine remote version"}), 400
        
        new_version = remote.get("tag", "").lstrip("v")
        if not new_version:
            return jsonify({"error": "Could not determine version"}), 400
        
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Run update in subprocess (will restart service)
        def do_update():
            try:
                # Fetch latest tags
                subprocess.run(["git", "fetch", "--tags"], cwd=repo_root, check=True, capture_output=True, timeout=30)
                
                # Checkout new version
                subprocess.run(["git", "checkout", f"v{new_version}"], cwd=repo_root, check=True, capture_output=True, timeout=30)
                
                # Clean local changes
                subprocess.run(["git", "clean", "-fd"], cwd=repo_root, check=True, capture_output=True, timeout=30)
                
                # Reinstall dependencies
                venv_pip = os.path.join(repo_root, "venv", "bin", "pip")
                subprocess.run([venv_pip, "install", "-r", "requirements.txt", "-q"], cwd=repo_root, check=True, timeout=60)
                
                # Restart service
                subprocess.run(["systemctl", "restart", "wol-dashboard"], check=True, capture_output=True, timeout=10)
                
                print(f"✅ Update to v{new_version} completed")
            except subprocess.CalledProcessError as e:
                print(f"❌ Update failed: {e}")
            except Exception as e:
                print(f"❌ Update error: {e}")
        
        # Run in background thread to avoid blocking
        import threading
        t = threading.Thread(target=do_update, daemon=True)
        t.start()
        
        return jsonify({"message": f"Updating to v{new_version}...", "version": new_version})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/time")
def api_time():
    """Return current server time in ISO 8601 format and human-readable format."""
    from datetime import datetime
    now = datetime.now()
    return jsonify({
        "timestamp": now.isoformat(),
        "iso": now.strftime("%Y-%m-%d %H:%M:%S"),
        "formatted": now.strftime("%d.%m.%Y %H:%M:%S")  # German format: DD.MM.YYYY HH:MM:SS
    })


@app.get("/api/events")
def subscribe_events():
    """SSE endpoint for real-time device status updates."""
    q = queue.Queue(maxsize=50)
    with _event_lock:
        _event_subscribers.append(q)
    
    def event_stream():
        try:
            while True:
                try:
                    event = q.get(timeout=30)  # 30sec timeout for keep-alive
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Keep-alive ping
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _event_lock:
                if q in _event_subscribers:
                    _event_subscribers.remove(q)
    
    return Response(event_stream(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no"
    })


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
