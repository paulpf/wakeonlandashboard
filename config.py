import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "wol.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "app_name": "WoL Dashboard",
    "scan_network": "192.168.1.0/24",
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
    "github_repo": "yourusername/wakeonlandashboard"
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
    return cfg


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
