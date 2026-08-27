param(
  [Parameter(Mandatory = $true)][string]$BackupPath,
  [switch]$Confirm
)

$ErrorActionPreference = 'Stop'
if (-not $Confirm) { throw 'Restore requires -Confirm. Stop Gravity Fitness before continuing.' }
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonPath = if ($env:GRAVITY_PYTHON) { $env:GRAVITY_PYTHON } else { Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Gravity Python environment is missing.' }
Push-Location $ProjectRoot
try {
  & $PythonPath -m server.gravity --restore-backup $BackupPath --confirm-live-restore
  if ($LASTEXITCODE -ne 0) { throw 'Gravity live restore failed.' }
} finally {
  Pop-Location
}
