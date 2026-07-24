# Claude Code — Projektregeln

## Pre-Commit Security Check (PFLICHT, KEINE AUSNAHMEN)

**Vor jedem `git add` / `git commit` muss folgendes geprüft werden:**

1. `git diff --cached` durchsuchen nach:
   - Passwörter, Tokens, API-Keys, Secrets (`password`, `token`, `secret`, `api_key`, `Bearer`, `Authorization`)
   - Private IPs oder interne Hostnamen die nicht öffentlich gehören
   - Credential-Dateien: `.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, JSON mit Zugangsdaten

2. `git status` prüfen auf unbeabsichtigte Dateien:
   - `data/config.json` (enthält ggf. Netzwerk-Konfiguration)
   - `data/wol.db` (SQLite-Datenbank mit Gerätedaten und MAC-Adressen)
   - `.env`, `*.log`, temporäre Dateien

3. Bei Fund: **NICHT committen** — Datei aus Staging entfernen (`git restore --staged <file>`) und Nutzer informieren.

4. Erst nach sauberem Scan: Commit durchführen.

Diese Regel gilt auf **jedem Rechner** und für **jeden Commit**, egal wie klein oder routinemäßig.

---

## Weitere Projektregeln

- `updater.py` darf ausschließlich die GitHub Releases API aufrufen (kein `subprocess.run(["git", "pull"])`, kein `systemctl restart`)
- Die UI zeigt Update-Befehle als `<pre>`-Block an, führt sie aber niemals programmatisch aus
- `data/` ist in `.gitignore` und darf niemals commitet werden
