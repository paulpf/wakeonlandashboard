# build-offline-bundle.ps1
# Erstellt ein offline-installierbares ZIP-Bundle fuer den LXC.
# Ausfuehren im Repo-Root: .\build-offline-bundle.ps1
# Voraussetzung: Python 3.x + pip installiert, Internet-Zugang auf diesem PC.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Version = (Get-Content "$PSScriptRoot\VERSION" -Raw).Trim()
$BundleName = "wol-offline-v$Version"
$BundleDir  = "$PSScriptRoot\dist\$BundleName"
$ZipPath    = "$PSScriptRoot\dist\$BundleName.zip"

Write-Host "=== WoL Dashboard Offline-Bundle Builder ===" -ForegroundColor Cyan
Write-Host "Version: $Version"

# --- Aufraumen ---
if (Test-Path $BundleDir) { Remove-Item $BundleDir -Recurse -Force }
New-Item -ItemType Directory -Path "$BundleDir\wheels" | Out-Null

# --- App-Dateien kopieren (ohne data/, venv/, .git/, __pycache__) ---
Write-Host "`nKopiere App-Dateien..." -ForegroundColor Yellow
$Exclude = @("dist", "data", "venv", ".git", "__pycache__", "*.pyc", "*.db", "*.log", ".env")
Get-ChildItem -Path $PSScriptRoot -Exclude $Exclude | ForEach-Object {
    if ($_.Name -notin $Exclude) {
        Copy-Item $_.FullName -Destination $BundleDir -Recurse -Force
    }
}
# __pycache__ innerhalb von Unterordnern entfernen
Get-ChildItem -Path $BundleDir -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force

# --- Python-Wheels herunterladen ---
Write-Host "`nLade Python-Wheels herunter..." -ForegroundColor Yellow
# --only-binary :all: stellt sicher, dass plattformunabhaengige Wheels geladen werden.
# Alle Abhaengigkeiten dieses Projekts sind pure Python (keine C-Extensions).
pip download `
    --only-binary :all: `
    --python-version 3.11 `
    --platform manylinux_2_17_x86_64 `
    --implementation cp `
    -r "$PSScriptRoot\requirements.txt" `
    -d "$BundleDir\wheels" `
    --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "Fehler beim Laden der Wheels. Versuche ohne Plattform-Filter..." -ForegroundColor Red
    pip download -r "$PSScriptRoot\requirements.txt" -d "$BundleDir\wheels" --quiet
}

$WheelCount = (Get-ChildItem "$BundleDir\wheels").Count
Write-Host "$WheelCount Wheels heruntergeladen."

# --- ZIP erstellen ---
Write-Host "`nErstelle ZIP..." -ForegroundColor Yellow
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $BundleDir -DestinationPath $ZipPath

$SizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host "`n=== Fertig! ===" -ForegroundColor Green
Write-Host "Bundle: dist\$BundleName.zip ($SizeMB MB)"
Write-Host ""
Write-Host "Naechste Schritte:" -ForegroundColor Cyan
Write-Host "  1. dist\$BundleName.zip per WinSCP nach /tmp/ auf den LXC kopieren"
Write-Host "  2. Im LXC:"
Write-Host "       cd /tmp"
Write-Host "       unzip $BundleName.zip"
Write-Host "       bash $BundleName/offline-install.sh"
