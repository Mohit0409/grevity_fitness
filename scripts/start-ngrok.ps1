param(
  [int]$Port = 8787
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $ProjectRoot '.gravity'
$PidFile = Join-Path $RuntimeDir 'ngrok.pid'
$StdoutLog = Join-Path $RuntimeDir 'ngrok.stdout.log'
$StderrLog = Join-Path $RuntimeDir 'ngrok.stderr.log'
$DotEnv = Join-Path $ProjectRoot '.env'
$NgrokConfig = Join-Path $env:LOCALAPPDATA 'ngrok\ngrok.yml'

function Resolve-Ngrok {
  $command = Get-Command ngrok -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $root = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
  if (Test-Path $root) {
    $item = Get-ChildItem $root -Recurse -Filter ngrok.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match 'Ngrok\.Ngrok' } | Select-Object -First 1
    if ($item) { return $item.FullName }
  }
  throw 'ngrok is not installed. Install with: winget install --id Ngrok.Ngrok'
}

function Set-DotEnvValue([string]$Name, [string]$Value) {
  $lines = if (Test-Path $DotEnv) { @(Get-Content -LiteralPath $DotEnv) } else { @() }
  $pattern = '^\s*' + [regex]::Escape($Name) + '\s*='
  $replaced = $false
  $updated = foreach ($line in $lines) {
    if ($line -match $pattern) {
      $replaced = $true
      "$Name=$Value"
    } else { $line }
  }
  if (-not $replaced) { $updated += "$Name=$Value" }
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllLines($DotEnv, [string[]]$updated, $utf8NoBom)
}

$NgrokExe = Resolve-Ngrok
if (-not (Test-Path -LiteralPath $NgrokConfig)) {
  throw "ngrok authentication is not configured. Run: & '$NgrokExe' config add-authtoken <YOUR_NGROK_TOKEN>"
}
$configText = Get-Content -LiteralPath $NgrokConfig -Raw
if ($configText -notmatch '(?m)^\s*authtoken\s*:') {
  throw "ngrok authtoken is missing. Run: & '$NgrokExe' config add-authtoken <YOUR_NGROK_TOKEN>"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
if (Test-Path -LiteralPath $PidFile) {
  $existingId = [int](Get-Content -LiteralPath $PidFile -Raw)
  if (Get-Process -Id $existingId -ErrorAction SilentlyContinue) {
    throw "ngrok is already running with PID $existingId."
  }
  Remove-Item -LiteralPath $PidFile -Force
}
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
  if ($health.status -ne 'ok' -or $health.service -ne 'Gravity Fitness') { throw 'invalid health response' }
} catch {
  & (Join-Path $PSScriptRoot 'start-gravity.ps1')
}

$process = Start-Process -FilePath $NgrokExe `
  -ArgumentList @('http', "http://127.0.0.1:$Port", '--log=stdout', '--log-format=json') `
  -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
  -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -PassThru
Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ascii

$PublicUrl = $null
for ($attempt = 0; $attempt -lt 40; $attempt++) {
  if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw "ngrok exited during startup. Check $StderrLog"
  }
  try {
    $tunnels = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 1
    $match = @($tunnels.tunnels | Where-Object { $_.public_url -like 'https://*' }) | Select-Object -First 1
    if ($match) { $PublicUrl = $match.public_url.TrimEnd('/'); break }
  } catch { }
  Start-Sleep -Milliseconds 250
}
if (-not $PublicUrl) {
  Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
  throw 'ngrok did not publish an HTTPS tunnel.'
}
Set-DotEnvValue 'GRAVITY_ENV' 'production'
Set-DotEnvValue 'APP_BASE_URL' $PublicUrl
Set-DotEnvValue 'GRAVITY_TRUST_PROXY' 'true'
Set-DotEnvValue 'GRAVITY_TRUSTED_PROXY_CIDRS' '127.0.0.1/32'

& (Join-Path $PSScriptRoot 'stop-gravity.ps1')
& (Join-Path $PSScriptRoot 'start-gravity.ps1')

$publicHealth = Invoke-RestMethod -Uri "$PublicUrl/api/health" -Headers @{ 'ngrok-skip-browser-warning' = 'true' } -TimeoutSec 8
if ($publicHealth.status -ne 'ok' -or $publicHealth.service -ne 'Gravity Fitness') {
  throw 'Public ngrok health check did not return the Gravity contract.'
}

Write-Host "ngrok HTTPS tunnel started with PID $($process.Id)." -ForegroundColor Green
Write-Host "Public URL: $PublicUrl" -ForegroundColor Green
Write-Host "Gravity APP_BASE_URL was updated and the server restarted in production mode."
