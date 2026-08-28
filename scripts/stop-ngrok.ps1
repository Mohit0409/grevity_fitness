$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $ProjectRoot '.gravity'
$PidFile = Join-Path $RuntimeDir 'ngrok.pid'
$DotEnv = Join-Path $ProjectRoot '.env'

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

if (Test-Path -LiteralPath $PidFile) {
  $processId = [int](Get-Content -LiteralPath $PidFile -Raw)
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($process) {
    if ($process.Path -notlike '*ngrok.exe') {
      throw "Refusing to stop PID $processId because it is not ngrok."
    }
    Stop-Process -Id $processId
    Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

Set-DotEnvValue 'GRAVITY_ENV' 'development'
Set-DotEnvValue 'APP_BASE_URL' 'http://127.0.0.1:8787'
Set-DotEnvValue 'GRAVITY_TRUST_PROXY' 'false'
Set-DotEnvValue 'GRAVITY_TRUSTED_PROXY_CIDRS' ''

& (Join-Path $PSScriptRoot 'stop-gravity.ps1')
& (Join-Path $PSScriptRoot 'start-gravity.ps1')
Write-Host 'ngrok stopped. Gravity returned to local development URL.' -ForegroundColor Green
