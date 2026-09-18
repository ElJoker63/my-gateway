# My Gateway AI — self-host installer (Windows PowerShell)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Yes

param(
  [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Say($msg)  { Write-Host "`n$msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "  [X] $msg" -ForegroundColor Red; exit 1 }

$cwd = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $cwd

Say "  My Gateway AI — self-host installer"
Say "  ────────────────────────────────"

# Prereqs
foreach ($cmd in @("docker", "git")) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Die "missing dependency: $cmd" }
  Ok "$cmd found"
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { Die "Docker daemon is not running" }
Ok "Docker daemon reachable"

# Env file
$envFile = ".env"
if (-not (Test-Path $envFile)) {
  Say "Creating .env from .env.example ..."
  Copy-Item ".env.example" $envFile
} else {
  Warn ".env already exists — leaving it alone. Delete it to start fresh."
  if (-not $Yes) {
    $resp = Read-Host "  Continue with existing .env? [y/N]"
    if ($resp -notmatch '^[Yy]$') { exit 1 }
  }
}

# Secrets
if (-not $Yes) {
  $gw = Read-Host "Gateway API key [auto-generate if empty]"
  $mk = Read-Host "Master encryption key [auto-generate if empty]"
}
$gw = if ($gw) { $gw } else { -join ((1..40) | ForEach-Object { -join (97..122 + 65..90 + 48..57 | ForEach-Object {[char]$_}) | Get-Random }) }
$mk = if ($mk) { $mk } else { -join ((1..48) | ForEach-Object { -join (97..122 + 65..90 + 48..57 | ForEach-Object {[char]$_}) | Get-Random }) }

# Upsert into .env
$text = Get-Content $envFile -Raw
if ($text -match '(?m)^GATEWAY_API_KEY=') {
  $text = $text -replace '(?m)^GATEWAY_API_KEY=.*', "GATEWAY_API_KEY=$gw"
} else { $text += "`nGATEWAY_API_KEY=$gw" }
if ($text -match '(?m)^GATEWAY_MASTER_KEY=') {
  $text = $text -replace '(?m)^GATEWAY_MASTER_KEY=.*', "GATEWAY_MASTER_KEY=$mk"
} else { $text += "`nGATEWAY_MASTER_KEY=$mk" }
Set-Content $envFile $text -NoNewline

Warn "Write these down NOW — they are shown only once:"
Write-Host "  GATEWAY_API_KEY   = $gw" -ForegroundColor Yellow
Write-Host "  GATEWAY_MASTER_KEY= $mk" -ForegroundColor Yellow
Say ""

Say "Pulling images and starting the stack..."
docker compose pull
docker compose up -d --build --remove-orphans

Ok "gateway is starting; dashboard will be at http://localhost:8000/dashboard"
Ok "health check: http://localhost:8000/health"
Ok "open the dashboard and log in with GATEWAY_API_KEY"
Say ""
