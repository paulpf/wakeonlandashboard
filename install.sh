#!/usr/bin/env bash
# WoL Dashboard — Installer for Debian/Ubuntu LXC
set -euo pipefail

INSTALL_DIR="/opt/wol-dashboard"
SERVICE_NAME="wol-dashboard"

echo "=== WoL Dashboard Installer ==="

# 1. System packages
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    arp-scan net-tools git

# 2. Clone or update repo
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing installation…"
    git -C "$INSTALL_DIR" pull --ff-only
else
    if [ -d "$INSTALL_DIR" ]; then
        echo "Moving existing files into place…"
        cp -r . "$INSTALL_DIR"
    else
        # If run from git clone, just use current dir
        mkdir -p "$INSTALL_DIR"
        cp -r . "$INSTALL_DIR/"
    fi
fi

cd "$INSTALL_DIR"

# 3. Python venv + dependencies
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

# 4. Systemd service
cp wol-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "=== Installation abgeschlossen ==="
echo "Dashboard erreichbar unter: http://$(hostname -I | awk '{print $1}'):5000"
echo "Logs anzeigen: journalctl -u wol-dashboard -f"
