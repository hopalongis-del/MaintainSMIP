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
  'smi_events.js',
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

# Single-file digest — upload THIS if RAG struggles with many files
$digestPath = Join-Path $Dest 'CODEBASE_DIGEST.md'
$digestParts = @(
  "# MaintainSMIP codebase digest",
  "Auto-generated. Search this file for functions, routes, themes.",
  "Synced: $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
  ""
)
foreach ($rel in $Files) {
  $src = Join-Path $Root $rel
  if (-not (Test-Path $src)) { continue }
  $leaf = Split-Path $rel -Leaf
  $digestParts += "----- FILE: $leaf -----"
  $digestParts += Get-Content $src -Raw
  $digestParts += ""
}
Set-Content -Path $digestPath -Value ($digestParts -join "`n") -Encoding UTF8
Write-Host "Wrote CODEBASE_DIGEST.md ($((Get-Item $digestPath).Length / 1KB | ForEach-Object { '{0:N0}' -f $_ }) KB)"

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
Set-Content -Path (Join-Path $Dest 'SYNCED_AT.txt') -Value @(
  "Last sync: $stamp",
  "Upload ALL files in this folder to Open WebUI Knowledge: MaintainSMIP-Source",
  "Minimum: CODEBASE_DIGEST.md + settings.js + themes.js + server.py",
  "Attach MaintainSMIP-Source to EVERY maintainsmip-guru chat."
) -Encoding UTF8
Write-Host "Done. Upload open-webui-knowledge\ to Open WebUI."