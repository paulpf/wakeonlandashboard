import json
import threading
from datetime import datetime

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

scheduler = BackgroundScheduler(daemon=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_status_check():
    """Ping all managed devices and update their online status."""
    devices = db.get_all_devices()
    cfg = load_config()
    for dev in devices:
        online = scanner.check_device_online(dev["ip"])
        db.update_device_status(dev["mac"], online, dev["ip"] if online else None)


def _run_network_scan():
    if _scan_status["running"]:
        return
    _scan_status["running"] = True
    try:
        cfg = load_config()
        hosts = scanner.scan_network(cfg.get("scan_network", "192.168.1.0/24"))
        db.save_scan_results(hosts)
        _scan_status["found"] = len(hosts)
        _scan_status["last_run"] = datetime.utcnow().isoformat()
    finally:
        _scan_status["running"] = False


def _scheduled_wake(device_id: int):
    dev = db.get_device(device_id)
    if not dev:
        return
    cfg = load_config()
    try:
        wol_mod.send_magic_packet(dev["mac"], cfg.get("broadcast_address", "255.255.255.255"), cfg.get("wol_port", 9))
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="schedule", success=True)
    except Exception as e:
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="schedule", success=False)


def _rebuild_schedules():
    """Register all enabled schedules in APScheduler."""
    for job in scheduler.get_jobs():
        if job.id.startswith("dev_"):
            job.remove()

    for sched in db.get_all_schedules():
        job_id = f"dev_{sched['device_id']}_{sched['id']}"
        try:
            from apscheduler.triggers.cron import CronTrigger
            parts = sched["cron_expr"].split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2] if len(parts) > 2 else "*",
                month=parts[3] if len(parts) > 3 else "*",
                day_of_week=parts[4] if len(parts) > 4 else "*",
            )
            scheduler.add_job(_scheduled_wake, trigger, args=[sched["device_id"]],
                              id=job_id, replace_existing=True)
        except Exception:
            pass


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
    dev_id = db.upsert_device(
        name=data["name"],
        mac=data["mac"],
        ip=data.get("ip", ""),
        group_name=data.get("group_name", "Default"),
        notes=data.get("notes", ""),
        port_checks=data.get("port_checks", []),
    )
    return jsonify({"id": dev_id}), 201


@app.put("/api/devices/<int:device_id>")
def api_update_device(device_id):
    data = request.json or {}
    dev = db.get_device(device_id)
    if not dev:
        return jsonify({"error": "not found"}), 404
    db.upsert_device(
        name=data.get("name", dev["name"]),
        mac=dev["mac"],
        ip=data.get("ip", dev["ip"]),
        group_name=data.get("group_name", dev["group_name"]),
        notes=data.get("notes", dev["notes"]),
        port_checks=data.get("port_checks", json.loads(dev["port_checks"] or "[]")),
    )
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
            cfg.get("broadcast_address", "255.255.255.255"),
            cfg.get("wol_port", 9),
        )
        db.log_wake(device_id, dev["name"], dev["mac"], triggered_by="manual", success=True)
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
            wol_mod.send_magic_packet(dev["mac"], cfg.get("broadcast_address", "255.255.255.255"), cfg.get("wol_port", 9))
            db.log_wake(dev_id, dev["name"], dev["mac"], triggered_by="bulk", success=True)
            results.append({"id": dev_id, "ok": True})
        except Exception as e:
            results.append({"id": dev_id, "ok": False, "error": str(e)})
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
    return jsonify({"results": db.get_scan_results(), "status": _scan_status})


@app.post("/api/scan/start")
def api_scan_start():
    if _scan_status["running"]:
        return jsonify({"error": "scan already running"}), 409
    t = threading.Thread(target=_run_network_scan, daemon=True)
    t.start()
    return jsonify({"ok": True})


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
