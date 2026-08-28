$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonPath = if ($env:GRAVITY_PYTHON) { $env:GRAVITY_PYTHON } else { Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) {
  throw 'Gravity Python environment is missing. Run .\scripts\setup-gravity.ps1 first.'
}
Push-Location $ProjectRoot
try {
  & $PythonPath -m server.gravity --launch-check
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
