param(
  [string]$PythonPath = $env:GRAVITY_PYTHON
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not $PythonPath) {
  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    $PythonPath = $pyLauncher.Source
  } else {
    $CodexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $CodexPython) {
      $PythonPath = $CodexPython
    } else {
      $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
      if ($pythonCommand) { $PythonPath = $pythonCommand.Source }
    }
  }
}

if (-not $PythonPath) {
  throw 'Python 3.11+ was not found. Install Python or set GRAVITY_PYTHON to python.exe.'
}

if ((Split-Path $PythonPath -Leaf) -eq 'py.exe') {
  & $PythonPath -3 -m venv (Join-Path $ProjectRoot '.venv')
} else {
  & $PythonPath -m venv (Join-Path $ProjectRoot '.venv')
}
if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Gravity Python environment.' }

& $VenvPython --version
& $VenvPython -m server.gravity --root $ProjectRoot --check-db
if ($LASTEXITCODE -ne 0) { throw 'Gravity database initialization failed.' }

Write-Host 'Gravity Fitness setup is ready.' -ForegroundColor Green
Write-Host 'Start with: .\scripts\start-gravity.ps1'
