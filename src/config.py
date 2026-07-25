import os
import json

# BASE_DIR now points to src/ directory, so go up one level to project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "wol.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "app_name": "WoL Dashboard",
    "scan_networks": ["192.168.1.0/24"],
    "scan_interval_seconds": 60,
    "broadcast_address": "255.255.255.255",
    "wol_port": 9,
    "port_checks": {
        "SSH": 22,
        "RDP": 3389,
        "HTTP": 80,
        "HTTPS": 443,
        "SMB": 445
    },
    "auto_update_enabled": True,
    "github_repo": "paulpf/wakeonlandashboard"
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    # merge any missing defaults
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    # migrate old single-string scan_network → list
    if "scan_network" in cfg and "scan_networks" not in cfg:
        cfg["scan_networks"] = [cfg.pop("scan_network")]
        save_config(cfg)
    elif isinstance(cfg.get("scan_networks"), str):
        cfg["scan_networks"] = [cfg["scan_networks"]]
    return cfg


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
