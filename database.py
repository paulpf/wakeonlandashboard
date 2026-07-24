import sqlite3
import json
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                mac         TEXT NOT NULL UNIQUE,
                ip          TEXT,
                broadcast   TEXT DEFAULT '',
                group_name  TEXT DEFAULT 'Default',
                notes       TEXT DEFAULT '',
                port_checks TEXT DEFAULT '[]',
                is_online   INTEGER DEFAULT 0,
                last_seen   TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   INTEGER NOT NULL,
                cron_expr   TEXT NOT NULL,
                label       TEXT,
                enabled     INTEGER DEFAULT 1,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS wake_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   INTEGER,
                device_name TEXT,
                mac         TEXT,
                triggered_by TEXT DEFAULT 'manual',
                success     INTEGER DEFAULT 1,
                ts          TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS scan_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ip          TEXT NOT NULL,
                mac         TEXT,
                hostname    TEXT,
                vendor      TEXT,
                open_ports  TEXT DEFAULT '[]',
                scanned_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        # migrations for existing databases
        dev_cols = {row[1] for row in db.execute("PRAGMA table_info(devices)").fetchall()}
        if "broadcast" not in dev_cols:
            db.execute("ALTER TABLE devices ADD COLUMN broadcast TEXT DEFAULT ''")
        if "open_ports" not in dev_cols:
            db.execute("ALTER TABLE devices ADD COLUMN open_ports TEXT DEFAULT '[]'")
        if "wake_request_ts" not in dev_cols:
            db.execute("ALTER TABLE devices ADD COLUMN wake_request_ts TEXT")
        scan_cols = {row[1] for row in db.execute("PRAGMA table_info(scan_results)").fetchall()}
        if "open_ports" not in scan_cols:
            db.execute("ALTER TABLE scan_results ADD COLUMN open_ports TEXT DEFAULT '[]'")


# ---------- devices ----------

def get_all_devices() -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT d.*,
                   EXISTS(SELECT 1 FROM schedules s WHERE s.device_id=d.id AND s.enabled=1) AS has_schedule
            FROM devices d
            ORDER BY d.group_name, d.name
        """).fetchall()
    return [dict(r) for r in rows]


def get_device(device_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    return dict(row) if row else None


def upsert_device(name: str, mac: str, ip: str = "", broadcast: str = "",
                  group_name: str = "Default", notes: str = "",
                  port_checks: list = None, open_ports: list = None) -> int:
    mac = mac.upper().replace("-", ":").strip()
    port_checks_json = json.dumps(port_checks or [])
    with get_db() as db:
        existing = db.execute("SELECT id, open_ports FROM devices WHERE mac=?", (mac,)).fetchone()
        if existing:
            # preserve existing open_ports if not explicitly provided
            ports_json = json.dumps(open_ports) if open_ports is not None else (existing["open_ports"] or "[]")
            db.execute("""
                UPDATE devices SET name=?, ip=?, broadcast=?, group_name=?, notes=?, port_checks=?, open_ports=?
                WHERE mac=?
            """, (name, ip, broadcast, group_name, notes, port_checks_json, ports_json, mac))
            return existing["id"]
        ports_json = json.dumps(open_ports or [])
        cur = db.execute("""
            INSERT INTO devices (name, mac, ip, broadcast, group_name, notes, port_checks, open_ports)
            VALUES (?,?,?,?,?,?,?,?)
        """, (name, mac, ip, broadcast, group_name, notes, port_checks_json, ports_json))
        return cur.lastrowid


def delete_device(device_id: int) -> None:
    with get_db() as db:
        db.execute("DELETE FROM devices WHERE id=?", (device_id,))


def update_device_status(mac: str, is_online: bool, ip: str = None) -> None:
    mac = mac.upper().replace("-", ":").strip()
    with get_db() as db:
        if ip:
            db.execute("""
                UPDATE devices SET is_online=?, last_seen=datetime('now'), ip=?
                WHERE mac=?
            """, (1 if is_online else 0, ip, mac))
        else:
            db.execute("""
                UPDATE devices SET is_online=?, last_seen=datetime('now')
                WHERE mac=?
            """, (1 if is_online else 0, mac))


def set_wake_request(mac: str) -> None:
    """Mark device as 'waking up' by setting current timestamp."""
    mac = mac.upper().replace("-", ":").strip()
    with get_db() as db:
        db.execute(
            "UPDATE devices SET wake_request_ts=datetime('now') WHERE mac=?",
            (mac,)
        )


def has_waking_devices() -> bool:
    """Check if any devices are currently 'waking up' (wake_request_ts < 120 seconds old)."""
    with get_db() as db:
        result = db.execute("""
            SELECT COUNT(*) as cnt FROM devices
            WHERE wake_request_ts IS NOT NULL
            AND datetime('now') < datetime(wake_request_ts, '+120 seconds')
        """).fetchone()
        return result["cnt"] > 0 if result else False


# ---------- schedules ----------

def get_schedules(device_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM schedules WHERE device_id=? ORDER BY id", (device_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_schedules() -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT s.*, d.name as device_name, d.mac
            FROM schedules s JOIN devices d ON s.device_id = d.id
            WHERE s.enabled=1
        """).fetchall()
    return [dict(r) for r in rows]


def add_schedule(device_id: int, cron_expr: str, label: str = "") -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO schedules (device_id, cron_expr, label) VALUES (?,?,?)",
            (device_id, cron_expr, label)
        )
        return cur.lastrowid


def delete_schedule(schedule_id: int) -> None:
    with get_db() as db:
        db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))


def toggle_schedule(schedule_id: int, enabled: bool) -> None:
    with get_db() as db:
        db.execute("UPDATE schedules SET enabled=? WHERE id=?", (1 if enabled else 0, schedule_id))


# ---------- history ----------

def log_wake(device_id: int | None, device_name: str, mac: str,
             triggered_by: str = "manual", success: bool = True) -> None:
    with get_db() as db:
        db.execute("""
            INSERT INTO wake_history (device_id, device_name, mac, triggered_by, success)
            VALUES (?,?,?,?,?)
        """, (device_id, device_name, mac, triggered_by, 1 if success else 0))


def get_history(limit: int = 100) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM wake_history ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- scan results ----------

def save_scan_results(hosts: list[dict]) -> None:
    with get_db() as db:
        db.execute("DELETE FROM scan_results")
        db.executemany("""
            INSERT INTO scan_results (ip, mac, hostname, vendor, open_ports)
            VALUES (:ip, :mac, :hostname, :vendor, :open_ports)
        """, [{**h, "open_ports": json.dumps(h.get("open_ports") or [])} for h in hosts])


def get_scan_results() -> list[dict]:
    with get_db() as db:
        rows = db.execute("SELECT * FROM scan_results ORDER BY ip").fetchall()
    return [dict(r) for r in rows]


def get_ports_from_scan(ip: str) -> list[int]:
    """Get already-scanned ports for an IP from scan_results."""
    with get_db() as db:
        row = db.execute(
            "SELECT open_ports FROM scan_results WHERE ip=?", (ip,)
        ).fetchone()
    if row and row["open_ports"]:
        try:
            return json.loads(row["open_ports"])
        except Exception:
            return []
    return []


def save_port_scan(port_map: dict[str, list[int]]) -> None:
    """Persist port scan results: update scan_results and devices by IP."""
    with get_db() as db:
        for ip, ports in port_map.items():
            ports_json = json.dumps(ports)
            db.execute(
                "UPDATE scan_results SET open_ports=? WHERE ip=?",
                (ports_json, ip),
            )
            db.execute(
                "UPDATE devices SET open_ports=? WHERE ip=?",
                (ports_json, ip),
            )
