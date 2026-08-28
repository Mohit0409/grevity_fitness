param(
  [string]$BaseUrl = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonPath = if ($env:GRAVITY_PYTHON) { $env:GRAVITY_PYTHON } else { Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) {
  throw 'Gravity Python environment is missing. Run .\scripts\setup-gravity.ps1 first.'
}
$Arguments = @('-m', 'server.gravity', '--cutover-check')
if ($BaseUrl) { $Arguments += @('--smoke-base-url', $BaseUrl) }
Push-Location $ProjectRoot
try {
  & $PythonPath @Arguments
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
