import os
import requests
from ..config import load_config, BASE_DIR

GITHUB_API_RELEASES = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_API_TAGS = "https://api.github.com/repos/{repo}/tags"
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
    
    latest_release = None
    latest_tag = None
    
    # Try to get the latest release
    try:
        resp = requests.get(GITHUB_API_RELEASES.format(repo=repo), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        tarball = f"https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz"
        latest_release = {
            "tag": tag,
            "name": data.get("name", ""),
            "body": data.get("body", ""),
            "url": data.get("html_url", ""),
            "tarball_url": tarball,
            "published_at": data.get("published_at", ""),
        }
    except Exception:
        pass
    
    # Try to get the latest tag
    try:
        resp = requests.get(GITHUB_API_TAGS.format(repo=repo), timeout=10)
        resp.raise_for_status()
        tags = resp.json()
        if tags:
            latest_tag_obj = tags[0]  # First tag is latest
            tag = latest_tag_obj.get("name", "")
            tarball = f"https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz"
            latest_tag = {
                "tag": tag,
                "name": f"Release {tag}",
                "body": "(from Git tag)",
                "url": f"https://github.com/{repo}/releases/tag/{tag}",
                "tarball_url": tarball,
                "published_at": "",
            }
    except Exception:
        pass
    
    # Return the newer version (tag-based comparison)
    if latest_release and latest_tag:
        try:
            rel_version = latest_release["tag"].lstrip("v").split(".")
            tag_version = latest_tag["tag"].lstrip("v").split(".")
            rel_nums = [int(x) for x in rel_version]
            tag_nums = [int(x) for x in tag_version]
            return latest_tag if tag_nums > rel_nums else latest_release
        except (ValueError, IndexError):
            return latest_release or latest_tag
    
    return latest_release or latest_tag


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
