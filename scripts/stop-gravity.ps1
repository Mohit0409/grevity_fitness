$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PidFile = Join-Path $ProjectRoot '.gravity\gravity.pid'

if (-not (Test-Path -LiteralPath $PidFile)) {
  Write-Host 'Gravity Fitness is already stopped.'
  exit 0
}

$processId = [int](Get-Content -LiteralPath $PidFile -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) {
  Remove-Item -LiteralPath $PidFile -Force
  Write-Host 'Removed a stale Gravity PID file.'
  exit 0
}
$ExpectedPython = if ($env:GRAVITY_PYTHON) { (Resolve-Path $env:GRAVITY_PYTHON).Path } else { (Resolve-Path (Join-Path $ProjectRoot '.venv\Scripts\python.exe')).Path }
if ($process.Path -ne $ExpectedPython) {
  throw "Refusing to stop PID $processId because its executable is not the configured Gravity Python runtime."
}

Stop-Process -Id $processId
Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
  throw "Gravity Fitness PID $processId did not stop cleanly."
}
Remove-Item -LiteralPath $PidFile -Force
Write-Host 'Gravity Fitness stopped.' -ForegroundColor Green
