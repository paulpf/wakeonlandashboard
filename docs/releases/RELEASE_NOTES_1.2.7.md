## v1.2.7 Release Notes

**Title:** v1.2.7 - Update Button Bugfix

**Description:**

## Bugfix
- Fix "Update durchführen" button error: "'newer' key not found"
- Corrected update check logic in `/api/update/apply` endpoint
- Now uses `is_update_available()` for proper version comparison

## Installation
```bash
cd /opt/wol-dashboard
git fetch --tags
git checkout v1.2.7
./venv/bin/pip install -r requirements.txt -q
systemctl restart wol-dashboard
```

## Testing Update Button
1. Go to Settings → Updates
2. Click "Auf Updates prüfen"
3. Click "Update durchführen" to apply update
