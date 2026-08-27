param([Parameter(Mandatory = $true)][string]$BackupPath)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonPath = if ($env:GRAVITY_PYTHON) { $env:GRAVITY_PYTHON } else { Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Gravity Python environment is missing.' }
Push-Location $ProjectRoot
try {
  & $PythonPath -m server.gravity --verify-backup $BackupPath
  if ($LASTEXITCODE -ne 0) { throw 'Gravity backup verification failed.' }
} finally {
  Pop-Location
}
