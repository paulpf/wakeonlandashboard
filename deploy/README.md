# 🚀 Deployment — WoL Dashboard

Systemd-Units und Deployment-Skripte für Linux-Systeme.

## 📋 Enthaltene Files

- **wol-dashboard.service** — Main Dashboard Service
- **wol-updater.service** — Update-Check Service
- **wol-updater.timer** — Timer für automatische Updates (tägliche Ausführung)
- **wol-updater.sh** — Skript für Update-Durchführung

## ⚙️ Installation

### 1. Service-Dateien installieren

```bash
sudo cp wol-dashboard.service /etc/systemd/system/
sudo cp wol-updater.service /etc/systemd/system/
sudo cp wol-updater.timer /etc/systemd/system/
sudo cp wol-updater.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/wol-updater.sh
```

### 2. Systemd neu laden

```bash
sudo systemctl daemon-reload
```

### 3. Service starten

```bash
# Dashboard
sudo systemctl start wol-dashboard
sudo systemctl enable wol-dashboard

# Update-Timer
sudo systemctl start wol-updater.timer
sudo systemctl enable wol-updater.timer
```

### 4. Status prüfen

```bash
sudo systemctl status wol-dashboard
sudo systemctl list-timers wol-updater.timer
```

## 📝 Logs anschauen

```bash
# Dashboard-Logs
sudo journalctl -u wol-dashboard -f

# Update-Logs
sudo journalctl -u wol-updater.service -f
```
