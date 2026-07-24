# ⚡ WoL Dashboard

Ein modernes Wake-on-LAN Dashboard für den Browser — läuft auf einem Proxmox LXC Container.

![Dashboard Screenshot](docs/screenshot.png)

## Features

| Feature | Beschreibung |
|---|---|
| **Netz-Scanner** | ARP-Scan des lokalen Netzwerks, entdeckte Geräte direkt hinzufügen |
| **Dashboard** | Alle verwalteten Geräte auf einen Blick — Online/Offline-Status |
| **Wake-on-LAN** | Einzelne oder mehrere Geräte per Klick wecken |
| **Gruppen** | Geräte in Gruppen organisieren (Server, Workstations, NAS, …) |
| **Geplante Weckzeiten** | Cron-basierte Schedules (z.B. jeden Morgen 07:00) |
| **Wake-Verlauf** | Protokoll aller Weck-Ereignisse inkl. CSV-Export |
| **Browser-Notifications** | Benachrichtigung wenn ein Gerät nach dem Wecken online kommt |
| **Import/Export** | Geräteliste als JSON sichern und wiederherstellen |
| **Dark/Light Mode** | Wechsel per Klick, wird gespeichert |
| **Update-Check** | Prüft automatisch ob eine neue GitHub-Version verfügbar ist |
| **REST API** | Alle Funktionen per HTTP-API erreichbar (z.B. für Home Assistant) |
| **Konfigurierbar** | Netz-Bereich, Broadcast-Adresse, WoL-Port, Intervall anpassbar |

---

## Schnellstart — Proxmox LXC

### 1. LXC Container erstellen

In der Proxmox-Oberfläche:

1. **Datacenter → Create CT**
2. Template: **Debian 13** (Trixie) oder Debian 12 (Bookworm)
3. Ressourcen (Minimum):
   - RAM: **256 MB** (512 MB empfohlen)
   - Disk: **2 GB**
   - CPU: **1 Core**
4. **Netzwerk:** Bridge auf das LAN-Interface (z.B. `vmbr0`)
5. ⚠️ **Wichtig:** Features → `nesting=1` aktivieren (für arp-scan)

Oder per CLI auf dem Proxmox-Host:

```bash
pct create 200 local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst \
  --hostname wol-dashboard \
  --memory 512 \
  --rootfs local-lvm:4 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1 \
  --unprivileged 1 \
  --start 1
```

### 2. In den Container einloggen

```bash
pct enter 200
```

### 3. Repository klonen und installieren

```bash
apt-get update && apt-get install -y git
git clone https://github.com/paulpf/wakeonlandashboard.git /opt/wol-dashboard
cd /opt/wol-dashboard
bash install.sh
```

### 4. Dashboard aufrufen

```
http://<container-ip>:5000
```

Die IP findest du mit `ip addr show eth0` im Container oder in Proxmox unter "Network".

---

## Manuelles Update

```bash
cd /opt/wol-dashboard
git pull
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```

---

## Konfiguration

Die Konfiguration kann im Dashboard unter **Einstellungen** vorgenommen werden
oder direkt in `data/config.json` bearbeitet werden.

| Einstellung | Standard | Beschreibung |
|---|---|---|
| `scan_network` | `192.168.1.0/24` | Zu scannender Netzwerkbereich |
| `broadcast_address` | `255.255.255.255` | WoL Broadcast-Adresse |
| `wol_port` | `9` | UDP-Port für Magic Packets |
| `scan_interval_seconds` | `60` | Status-Check Intervall |
| `github_repo` | — | `user/repo` für Update-Checks |

---

## REST API

| Methode | Endpunkt | Beschreibung |
|---|---|---|
| `GET` | `/api/devices` | Alle Geräte abrufen |
| `POST` | `/api/devices` | Gerät hinzufügen |
| `PUT` | `/api/devices/{id}` | Gerät bearbeiten |
| `DELETE` | `/api/devices/{id}` | Gerät entfernen |
| `POST` | `/api/devices/{id}/wake` | Gerät wecken |
| `POST` | `/api/wake/bulk` | Mehrere Geräte wecken (`{"ids":[1,2,3]}`) |
| `GET` | `/api/scan/results` | Letzte Scan-Ergebnisse |
| `POST` | `/api/scan/start` | Netz-Scan starten |
| `GET` | `/api/history` | Wake-Verlauf |
| `GET` | `/api/config` | Konfiguration abrufen |
| `POST` | `/api/config` | Konfiguration speichern |
| `GET` | `/api/update/check` | Update-Status prüfen |

### Home Assistant Beispiel

```yaml
# configuration.yaml
rest_command:
  wake_pc:
    url: "http://192.168.1.100:5000/api/devices/1/wake"
    method: POST
```

---

## Voraussetzungen für Wake-on-LAN

Das Zielgerät muss WoL unterstützen und aktiviert haben:

- **BIOS/UEFI:** Wake-on-LAN aktivieren
- **Windows:** Gerätemanager → Netzwerkadapter → Energieverwaltung → "Gerät kann den Computer aus dem Ruhezustand aktivieren"
- **Linux:** `ethtool -s eth0 wol g`

---

## Troubleshooting

**Scan findet keine Geräte?**
```bash
# arp-scan im Container testen
arp-scan --localnet
# Falls "permission denied": Container-Feature nesting=1 prüfen
```

**WoL-Paket kommt nicht an?**
- Broadcast-Adresse prüfen (bei VLANs: Subnet-Broadcast statt 255.255.255.255)
- Firewall auf dem LXC prüfen: `ufw allow 9/udp`

**Service startet nicht?**
```bash
journalctl -u wol-dashboard -n 50
```

---

## Lizenz

MIT License — frei verwendbar und anpassbar.
