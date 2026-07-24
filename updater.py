import os
import requests
from config import load_config, BASE_DIR

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")


def get_local_version() -> str:
    try:
        with open(VERSION_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def get_latest_release() -> dict | None:
    cfg = load_config()
    repo = cfg.get("github_repo", "")
    if not repo or repo == "yourusername/wakeonlandashboard":
        return None
    try:
        resp = requests.get(GITHUB_API.format(repo=repo), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "tag": data.get("tag_name", ""),
            "name": data.get("name", ""),
            "body": data.get("body", ""),
            "url": data.get("html_url", ""),
            "published_at": data.get("published_at", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def is_update_available() -> dict:
    local = get_local_version()
    cfg = load_config()
    repo = cfg.get("github_repo", "")
    if not repo or repo == "yourusername/wakeonlandashboard":
        return {"available": False, "local": local, "remote": None, "not_configured": True}
    remote = get_latest_release()
    if not remote:
        return {"available": False, "local": local, "remote": None, "not_configured": True}
    if "error" in remote:
        return {"available": False, "local": local, "remote": None, "error": remote["error"]}
    remote_tag = remote["tag"].lstrip("v")
    try:
        local_parts = [int(x) for x in local.split(".")]
        remote_parts = [int(x) for x in remote_tag.split(".")]
        available = remote_parts > local_parts
    except ValueError:
        available = False
    return {"available": available, "local": local, "remote": remote}
