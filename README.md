# ⚡ WoL Dashboard

[![GitHub Release](https://img.shields.io/github/v/release/paulpf/wakeonlandashboard?label=version)](https://github.com/paulpf/wakeonlandashboard/releases)
[![Tests](https://github.com/paulpf/wakeonlandashboard/workflows/Tests/badge.svg)](https://github.com/paulpf/wakeonlandashboard/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Ein modernes, vollständig konfigurierbares **Wake-on-LAN (WoL) Dashboard** für den Browser — optimiert für Proxmox LXC Container.

![Dashboard Screenshot](docs/screenshot.png)

---

## 📑 Inhaltsverzeichnis

- [Features](#-features)
- [Systemanforderungen](#-systemanforderungen)
- [Installation](#-installation)
  - [Schnellstart (Proxmox LXC)](#schnellstart--proxmox-lxc)
  - [Offline-Installation](#installation-ohne-internet-offline--air-gap)
- [Konfiguration](#-konfiguration)
- [REST API](#-rest-api)
- [Entwicklung](#-entwicklung)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| **Netz-Scanner** | ARP-Scan des lokalen Netzwerks mit automatischer Geräte-Erkennung |
| **Live-Dashboard** | Echtzeit Online/Offline-Status aller verwalteten Geräte |
| **Wake-on-LAN** | Einzelne oder Bulk-Weckzeiten mit Verlauf-Protokollierung |
| **Geplante Weckzeiten** | Cron-basierte Schedules (z.B. Mo-Fr 07:00 Uhr) |
| **Port-Scanner** | Erkennt offene Services (SSH, RDP, Proxmox, Cockpit, …) mit Farbkodierung |
| **Wake-Verlauf** | Vollständiges Weck-Protokoll mit CSV-Export |
| **Browser-Notifications** | Benachrichtigung sobald gewecktes Gerät online kommt |
| **Dark/Light Mode** | Theme-Wechsel, wird lokal gespeichert |
| **Import/Export** | Geräte-Backups als JSON |
| **REST API** | Alle Funktionen per HTTP-API (Home Assistant-kompatibel) |
| **Update-Check** | Automatische GitHub-Release-Überwachung |
| **Konfigurierbar** | Netzwerk-Bereich, Broadcast, WoL-Port, Scan-Intervalle, … |

---

## 📋 Systemanforderungen

### Server (LXC Container)
- **OS:** Debian 12+ / Ubuntu 22.04+
- **RAM:** 256 MB Minimum (512 MB empfohlen)
- **Disk:** 2 GB
- **CPU:** 1 Core
- **Python:** 3.11+

### Client
- Moderner Browser (Chrome, Firefox, Safari, Edge)
- JavaScript aktiviert

### Zielgeräte (WoL)
- BIOS/UEFI-Feature WoL aktiviert
- Netzwerkadapter unterstützt Magic Packets
- Verbunden mit demselben Netzwerk (oder per Subnet-Broadcast)

---

## 🚀 Installation

### Schnellstart — Proxmox LXC

#### 1. LXC Container erstellen

**Über Proxmox UI:**
1. Datacenter → **Create CT**
2. Template: **Debian 13** oder Debian 12
3. Ressourcen (Minimum):
   - RAM: **256 MB** (512 MB empfohlen)
   - Disk: **2 GB**
   - CPU: **1 Core**
4. Netzwerk: Bridge → LAN-Interface (z.B. `vmbr0`)
5. ⚠️ **Wichtig:** Features → `nesting=1` (erforderlich für arp-scan)

**Oder per CLI:**
```bash
pct create 200 local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst \
  --hostname wol-dashboard \
  --memory 512 \
  --rootfs local-lvm:4 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1 \
  --start 1
```

#### 2. Container-Shell starten
```bash
pct enter 200
```

#### 3. App installieren
```bash
apt-get update && apt-get install -y git
git clone https://github.com/paulpf/wakeonlandashboard.git /opt/wol-dashboard
cd /opt/wol-dashboard
bash install.sh
```

#### 4. ⚠️ Zeitzone konfigurieren (KRITISCH!)

Geplante Weckzeiten funktionieren nur mit korrekter Zeitzone:

```bash
# Aktuelle Zeitzone prüfen
timedatectl

# Auf Berlin setzen (oder andere Zeitzone anpassen)
timedatectl set-timezone Europe/Berlin

# Überprüfen
date
systemctl restart wol-dashboard
```

#### 5. Dashboard öffnen
```
http://<container-ip>:5000
```

IP ermitteln: `ip addr show eth0` (Container) oder Proxmox UI.

---

### Installation ohne Internet (Offline / Air-Gap)

Für Proxmox-Server ohne Internetzugang:

#### 1. Bundle auf Windows bauen
```powershell
cd w:\wakeonlandashboard
.\build-offline-bundle.ps1
```

Erzeugt `dist\wol-offline-v1.3.0.zip` (App-Code + Python-Wheels).

#### 2. ZIP per WinSCP übertragen
- WinSCP → SFTP → LXC-IP, Port 22, User `root`
- Datei nach `/tmp/` kopieren

#### 3. Im LXC installieren
```bash
cd /tmp
unzip wol-offline-v1.3.0.zip
bash wol-offline-v1.3.0/offline-install.sh
```

Das Skript erkennt Updates automatisch und erhält `data/` (Konfiguration + Datenbank).

#### Voraussetzungen
- `python3`, `python3-venv`, `unzip` muss vorhanden sein
- Falls nicht: `.deb`-Pakete von [packages.debian.org](https://packages.debian.org) besorgen und mit `dpkg -i` einspielen

---

### Manuelles Update

```bash
TAG=v1.3.0  # Gewünschte Version

cd /opt
wget -q "https://github.com/paulpf/wakeonlandashboard/archive/refs/tags/${TAG}.tar.gz" -O wol-update.tar.gz
tar -xzf wol-update.tar.gz
cp -r wakeonlandashboard-${TAG#v}/* wol-dashboard/
rm -rf wakeonlandashboard-${TAG#v} wol-update.tar.gz
cd /opt/wol-dashboard
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```

> Die genauen Befehle werden im Dashboard unter **Einstellungen → Updates** angezeigt.

---

## ⚙️ Konfiguration

Konfiguration im Dashboard (**Einstellungen**) oder direkt in `data/config.json`:

| Einstellung | Standard | Beschreibung |
|---|---|---|
| `scan_networks` | `["192.168.1.0/24"]` | Zu scannende Netzwerkbereiche (CIDR) |
| `broadcast_address` | `255.255.255.255` | WoL Broadcast-Adresse (bei VLAN: Subnet-Broadcast) |
| `wol_port` | `9` | UDP-Port für Magic Packets |
| `scan_interval_seconds` | `60` | Status-Check Intervall (Sekunden) |
| `github_repo` | — | `user/repo` für automatische Update-Checks |

---

## 🔌 REST API

| Methode | Endpunkt | Beschreibung |
|---|---|---|
| `GET` | `/api/devices` | Alle Geräte abrufen |
| `POST` | `/api/devices` | Gerät hinzufügen |
| `PUT` | `/api/devices/{id}` | Gerät bearbeiten |
| `DELETE` | `/api/devices/{id}` | Gerät entfernen |
| `POST` | `/api/devices/{id}/wake` | Gerät wecken |
| `POST` | `/api/wake/bulk` | Mehrere Geräte wecken |
| `GET` | `/api/devices/{id}/schedules` | Schedules für Gerät |
| `POST` | `/api/devices/{id}/schedules` | Schedule hinzufügen |
| `GET` | `/api/scan/results` | Letzte Scan-Ergebnisse |
| `POST` | `/api/scan/start` | Netz-Scan starten |
| `POST` | `/api/scan/ports` | Port-Scan starten |
| `GET` | `/api/history` | Wake-Verlauf |
| `GET` | `/api/config` | Konfiguration |
| `POST` | `/api/config` | Konfiguration speichern |
| `GET` | `/api/update/check` | Update-Status |
| `GET` | `/api/events` | Server-Sent Events (Live-Updates) |

### Home Assistant Beispiel
```yaml
rest_command:
  wake_pc:
    url: "http://192.168.1.100:5000/api/devices/1/wake"
    method: POST
```

---

## 💻 Entwicklung

### Tech Stack
- **Backend:** Python 3.11+ / Flask 3.0
- **Frontend:** Vanilla JavaScript + Bootstrap 5
- **Scheduler:** APScheduler 3.10
- **Database:** SQLite3 with WAL
- **Package:** Modular Python Package Structure (src/)

### Lokale Entwicklung

#### Vorbereitung
```bash
git clone https://github.com/paulpf/wakeonlandashboard.git
cd wakeonlandashboard
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# Linux/Mac
source .venv/bin/activate

pip install -r requirements-dev.txt
```

#### App starten
```bash
python -m src
# Dashboard: http://localhost:5000
```

#### Tests ausführen
```bash
pytest tests/ -v
```

### Projektstruktur
```
src/                      # Main package
├── __main__.py           # Entry point (python -m src)
├── app.py                # Flask application & endpoints
├── config.py             # Configuration management
├── constants.py          # App constants
├── database.py           # SQLite CRUD operations
├── lib/                  # Library modules
│   ├── scanner.py        # Network scanning (ARP, ping, ports)
│   ├── wol.py            # Wake-on-LAN packet sending
│   └── updater.py        # GitHub release checking
└── routes/               # Flask blueprints
    ├── devices.py        # Device management endpoints
    └── helpers.py        # Route utilities

tests/                    # Pytest test suite (31 tests)
static/                   # CSS, JavaScript
templates/                # HTML templates
data/                     # Runtime: config.json, wol.db (gitignored)
```

### Architektur-Prinzipien
- **Relative Imports:** Package-interne Imports nutzen Relative Imports (z.B. `from .config import ...`)
- **Separation of Concerns:** Logic (lib/), Routes (routes/), Config (config.py)
- **No Shell Execution:** Updater nutzt nur GitHub API, keine `subprocess.run(["git", ...])` Calls
- **Type Hints:** Neu-Code mit Type Hints schreiben

---

## 🔧 Troubleshooting

### Geplante Weckzeiten (Schedules) funktionieren nicht
⚠️ **Häufigste Ursache:** Falsche Zeitzone

```bash
timedatectl
# Sollte anzeigen: Time zone: Europe/Berlin (nicht: Etc/UTC!)

# Falls nötig:
timedatectl set-timezone Europe/Berlin
systemctl restart wol-dashboard
```

### Scan findet keine Geräte
```bash
# arp-scan testen
arp-scan --localnet

# Falls "permission denied": Container nesting=1 prüfen
pct config 200 | grep nesting
```

### WoL-Paket kommt nicht an
- Broadcast-Adresse prüfen (bei VLAN: Subnet-Broadcast statt 255.255.255.255)
- Zielgerät: BIOS/UEFI WoL aktiviert?
- Firewall: `ufw allow 9/udp` (Port 9 ist WoL-Standard)

### Service startet nicht
```bash
# Logs prüfen
journalctl -u wol-dashboard -n 50 -f

# Service Status
systemctl status wol-dashboard
```

### Port bereits in Verwendung
```bash
# Port 5000 belegt? Anderen Port in systemd-Unit ändern
# /etc/systemd/system/wol-dashboard.service

systemctl daemon-reload
systemctl restart wol-dashboard
```

---

## 📄 Lizenz

MIT License — frei verwendbar und anpassbar.

---

## 📞 Kontakt & Support

Probleme? [GitHub Issues](https://github.com/paulpf/wakeonlandashboard/issues)

Weitere Docs: [docs/](docs/)
