param(
  [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $ProjectRoot '.gravity'
$PidFile = Join-Path $RuntimeDir 'gravity.pid'
$StdoutLog = Join-Path $RuntimeDir 'gravity.stdout.log'
$StderrLog = Join-Path $RuntimeDir 'gravity.stderr.log'
$PythonPath = if ($env:GRAVITY_PYTHON) { $env:GRAVITY_PYTHON } else { Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
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

if (-not (Test-Path -LiteralPath $PythonPath)) {
  throw 'Gravity Python environment is missing. Run .\scripts\setup-gravity.ps1 first.'
}
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (Test-Path -LiteralPath $PidFile) {
  $existingId = [int](Get-Content -LiteralPath $PidFile -Raw)
  if (Get-Process -Id $existingId -ErrorAction SilentlyContinue) {
    throw "Gravity Fitness is already running with PID $existingId."
  }
  Remove-Item -LiteralPath $PidFile -Force
}

if ($Foreground) {
  Push-Location $ProjectRoot
  try { & $PythonPath -m server.gravity } finally { Pop-Location }
  exit $LASTEXITCODE
}

$process = Start-Process -FilePath $PythonPath `
  -ArgumentList @('-m', 'server.gravity') `
  -WorkingDirectory $ProjectRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $StdoutLog `
  -RedirectStandardError $StderrLog `
  -PassThru

Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ascii
for ($attempt = 0; $attempt -lt 20; $attempt++) {
  if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw "Gravity Fitness exited during startup. Check $StderrLog"
  }
  try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 1
    if ($health.service -eq 'Gravity Fitness' -and $health.status -eq 'ok') { break }
    throw "Port $Port is responding, but not with the Gravity health contract."
  } catch {
    if ($attempt -eq 19) {
      Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
      Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
      throw "Gravity Fitness did not become healthy at $BaseUrl. Check $StderrLog"
    }
    Start-Sleep -Milliseconds 250
  }
}
Write-Host "Gravity Fitness started with PID $($process.Id)." -ForegroundColor Green
Write-Host "Health: $BaseUrl/api/health"
