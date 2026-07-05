# Copy MaintainSMIP source into open-webui-knowledge/ for Open WebUI upload.
# Usage: cd C:\MaintainSMIP ; .\scripts\sync-open-webui-knowledge.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$Dest = Join-Path $Root 'open-webui-knowledge'

$Files = @(
  'HANDOFF.md',
  'DEPLOY.md',
  'OPENWEBUI.md',
  'settings.js',
  'themes.js',
  'db.js',
  'admin.js',
  'admin.html',
  'index.html',
  'activity.js',
  'activity.html',
  'server.py',
  'shared.css',
  'test_smoke.py',
  'ollama\SYSTEM_PROMPT.md',
  'ollama\MODEL_UPDATES.md',
  'training\TRAINING-theme-admin-reset.md'
)

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

foreach ($rel in $Files) {
  $src = Join-Path $Root $rel
  if (-not (Test-Path $src)) {
    Write-Warning "Skip missing $rel"
    continue
  }
  $leaf = Split-Path $rel -Leaf
  Copy-Item -Path $src -Destination (Join-Path $Dest $leaf) -Force
  Write-Host "Copied $leaf"
}

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
Set-Content -Path (Join-Path $Dest 'SYNCED_AT.txt') -Value "Last sync: $stamp`nUpload this folder to Open WebUI Knowledge collection MaintainSMIP-Source."
Write-Host "Done. Upload open-webui-knowledge\ to Open WebUI."