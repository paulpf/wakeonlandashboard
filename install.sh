#!/usr/bin/env bash
# WoL Dashboard — Installer for Debian/Ubuntu LXC
set -euo pipefail

INSTALL_DIR="/opt/wol-dashboard"
SERVICE_NAME="wol-dashboard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== WoL Dashboard Installer ==="

# 1. System packages
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    arp-scan net-tools curl rsync

# 2. App-Dateien einspielen (data/ und venv/ bleiben bei Update erhalten)
if [ -d "$INSTALL_DIR" ]; then
    echo "Vorhandene Installation gefunden — Update wird eingespielt..."
    rsync -a --exclude='data/' --exclude='venv/' "$SCRIPT_DIR/" "$INSTALL_DIR/"
else
    echo "Neu-Installation..."
    mkdir -p "$INSTALL_DIR"
    rsync -a "$SCRIPT_DIR/" "$INSTALL_DIR/"
fi

cd "$INSTALL_DIR"

# 3. Python venv + dependencies
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

# 4. wol-updater ausfuehrbar machen
chmod +x "$INSTALL_DIR/deploy/wol-updater.sh"

# 5. Systemd-Services einrichten
cp deploy/wol-dashboard.service /etc/systemd/system/
cp deploy/wol-updater.service   /etc/systemd/system/
cp deploy/wol-updater.timer     /etc/systemd/system/
systemctl daemon-reload

systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

systemctl enable wol-updater.timer
systemctl start  wol-updater.timer

echo ""
echo "=== Installation abgeschlossen ==="
echo "Dashboard:    http://$(hostname -I | awk '{print $1}'):5000"
echo "Logs:         journalctl -u wol-dashboard -f"
echo "Auto-Update:  taeglich 03:00 Uhr (systemctl status wol-updater.timer)"
