$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PidFile = Join-Path $ProjectRoot '.gravity\gravity.pid'
$DotEnv = Join-Path $ProjectRoot '.env'
$DotEnvPort = $null
$DotEnvBaseUrl = $null
if (Test-Path -LiteralPath $DotEnv) {
  foreach ($line in Get-Content -LiteralPath $DotEnv) {
    if ($line -match '^\s*GRAVITY_PORT\s*=\s*([0-9]+)\s*$') { $DotEnvPort = [int]$Matches[1] }
    if ($line -match '^\s*APP_BASE_URL\s*=\s*(.+?)\s*$') { $DotEnvBaseUrl = $Matches[1].Trim('"', "'").TrimEnd('/') }
  }
}
$Port = if ($env:GRAVITY_PORT) { [int]$env:GRAVITY_PORT } elseif ($DotEnvPort) { $DotEnvPort } else { 8787 }
$BaseUrl = if ($env:APP_BASE_URL) { $env:APP_BASE_URL.TrimEnd('/') } elseif ($DotEnvBaseUrl) { $DotEnvBaseUrl } else { "http://127.0.0.1:$Port" }
$HealthUrl = "http://127.0.0.1:$Port"

if (-not (Test-Path -LiteralPath $PidFile)) {
  Write-Host 'Gravity Fitness is stopped (no PID file).'
  exit 1
}

$processId = [int](Get-Content -LiteralPath $PidFile -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) {
  Write-Host "Gravity Fitness is stopped (stale PID $processId)."
  exit 1
}

try {
  $health = Invoke-RestMethod -Uri "$HealthUrl/api/health" -TimeoutSec 3
  Write-Host "Gravity Fitness is running (PID $processId)." -ForegroundColor Green
  $health | ConvertTo-Json -Compress
  if ($health.status -ne 'ok' -or $health.database -ne 'ok') { exit 2 }
} catch {
  Write-Host "Process $processId is running, but the health endpoint is unavailable." -ForegroundColor Yellow
  exit 2
}
