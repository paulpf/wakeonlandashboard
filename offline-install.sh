#!/usr/bin/env bash
# offline-install.sh — Erst-Installation UND Update ohne Internet
# Ausfuehren auf dem LXC als root:
#   bash /tmp/wol-offline-vX.Y.Z/offline-install.sh
set -euo pipefail

INSTALL_DIR="/opt/wol-dashboard"
SERVICE_NAME="wol-dashboard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cat "$SCRIPT_DIR/VERSION")"

echo "=== WoL Dashboard Offline-Installer v$VERSION ==="

# --- Systempackages pruefen ---
MISSING=()
for pkg in python3 python3-venv unzip; do
    if ! dpkg -l "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo "FEHLER: Folgende Pakete fehlen und koennen ohne Internet nicht installiert werden:"
    printf "  %s\n" "${MISSING[@]}"
    echo ""
    echo "Loesungen:"
    echo "  a) Kurz Internet-Zugang ermoeglichen:  apt-get install -y ${MISSING[*]}"
    echo "  b) .deb-Dateien separat uebertragen und per dpkg -i installieren"
    exit 1
fi

# arp-scan ist optional (Netzwerk-Scanner-Funktion)
if ! dpkg -l arp-scan &>/dev/null; then
    echo "INFO: arp-scan nicht gefunden — Netzwerk-Scanner-Funktion nicht verfuegbar."
    echo "      Dashboard startet trotzdem."
fi

# --- App-Dateien einspielen ---
echo ""
if [ -d "$INSTALL_DIR" ]; then
    echo "Vorhandene Installation gefunden — Update wird eingespielt..."
    # data/ erhalten (config.json, wol.db)
    rsync -a --exclude='data/' --exclude='venv/' "$SCRIPT_DIR/" "$INSTALL_DIR/"
else
    echo "Neu-Installation..."
    mkdir -p "$INSTALL_DIR"
    rsync -a --exclude='data/' "$SCRIPT_DIR/" "$INSTALL_DIR/"
fi

# --- Python venv + Wheels offline installieren ---
echo ""
echo "Richte Python-Umgebung ein..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi

"$INSTALL_DIR/venv/bin/pip" install \
    --no-index \
    --find-links="$SCRIPT_DIR/wheels" \
    -r "$INSTALL_DIR/requirements.txt" \
    --quiet

echo "Python-Abhaengigkeiten installiert."

# --- Systemd-Service einrichten ---
echo ""
cp "$INSTALL_DIR/wol-dashboard.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" --quiet
systemctl restart "$SERVICE_NAME"

echo ""
echo "=== Fertig! ==="
echo "Version:    v$VERSION"
echo "Dashboard:  http://$(hostname -I | awk '{print $1}'):5000"
echo "Logs:       journalctl -u $SERVICE_NAME -f"
