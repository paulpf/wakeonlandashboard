#!/usr/bin/env bash
# wol-updater.sh — Automatisches Update des WoL Dashboards via GitHub Releases API
# Wird von wol-updater.timer taeglich um 03:00 aufgerufen.
set -euo pipefail

INSTALL_DIR="/opt/wol-dashboard"
CONFIG="$INSTALL_DIR/data/config.json"
LOG_TAG="wol-updater"

log()  { echo "[$LOG_TAG] $*"; }
fail() { log "FEHLER: $*"; exit 1; }

# --- GitHub-Repo aus config.json lesen ---
if [ ! -f "$CONFIG" ]; then
    log "Keine config.json gefunden — Update uebersprungen."
    exit 0
fi

REPO=$(python3 -c "import json,sys; d=json.load(open('$CONFIG')); print(d.get('github_repo',''))" 2>/dev/null || true)

if [ -z "$REPO" ] || [ "$REPO" = "yourusername/wakeonlandashboard" ]; then
    log "Kein GitHub-Repo konfiguriert — Update uebersprungen."
    exit 0
fi

# --- Lokale Version lesen ---
LOCAL=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null | tr -d '[:space:]')
if [ -z "$LOCAL" ]; then
    fail "Lokale VERSION-Datei nicht gefunden."
fi

# --- Neueste Release-Version von GitHub holen ---
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
RESPONSE=$(curl -sf --max-time 15 "$API_URL" 2>/dev/null) || {
    log "GitHub API nicht erreichbar — Update uebersprungen."
    exit 0
}

REMOTE_TAG=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tag_name',''))" 2>/dev/null || true)
if [ -z "$REMOTE_TAG" ]; then
    log "Kein Release gefunden — Update uebersprungen."
    exit 0
fi

REMOTE="${REMOTE_TAG#v}"

# --- Versionen vergleichen ---
if [ "$LOCAL" = "$REMOTE" ]; then
    log "Bereits aktuell (v$LOCAL)."
    exit 0
fi

log "Update verfuegbar: v$LOCAL → v$REMOTE_TAG"

TARBALL="https://github.com/${REPO}/archive/refs/tags/${REMOTE_TAG}.tar.gz"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

# --- Tarball herunterladen und entpacken ---
log "Lade $TARBALL ..."
curl -sL --max-time 120 "$TARBALL" -o "$WORKDIR/update.tar.gz" \
    || fail "Download fehlgeschlagen."

tar -xzf "$WORKDIR/update.tar.gz" -C "$WORKDIR" \
    || fail "Entpacken fehlgeschlagen."

EXTRACTED=$(find "$WORKDIR" -maxdepth 1 -mindepth 1 -type d | head -1)
[ -d "$EXTRACTED" ] || fail "Entpacktes Verzeichnis nicht gefunden."

# --- App-Dateien einspielen (data/ und venv/ bleiben erhalten) ---
log "Spiele App-Dateien ein..."
rsync -a --exclude='data/' --exclude='venv/' "$EXTRACTED/" "$INSTALL_DIR/"

# --- Python-Abhaengigkeiten aktualisieren ---
log "Aktualisiere Python-Abhaengigkeiten..."
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q \
    || fail "pip install fehlgeschlagen."

# --- Service neu starten ---
log "Starte wol-dashboard neu..."
systemctl restart wol-dashboard

log "Update auf v$REMOTE_TAG erfolgreich abgeschlossen."
