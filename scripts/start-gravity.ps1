param(
  [string]$ConfigPath,
  [switch]$Foreground
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
if (-not (Test-Path -LiteralPath $context.PythonPath -PathType Leaf)) {
  throw 'Gravity Python environment is missing. Run .\scripts\setup-gravity.ps1 first or set GRAVITY_PYTHON.'
}
New-Item -ItemType Directory -Force -Path $context.RuntimeDir | Out-Null

$existingId = Get-GravityPid -Context $context
if ($existingId) {
  $existing = Get-Process -Id $existingId -ErrorAction SilentlyContinue
  if ($existing) {
    if (-not (Test-GravityManagedProcess -Context $context -ProcessId $existingId)) {
      throw "Refusing to replace live PID $existingId because its Gravity ownership cannot be proven."
    }
    if (Test-GravityHealth -Context $context) {
      Write-Host "Gravity Fitness is already healthy (PID $existingId)." -ForegroundColor Green
      exit 0
    }
    throw "Gravity PID $existingId is running but unhealthy. Use restart-gravity.ps1 for a controlled restart."
  }
  Remove-GravityStaleState -Context $context
}

$arguments = @('-m', 'server.gravity', '--host', '127.0.0.1', '--port', [string]$context.Port)
if ($Foreground) {
  Push-Location $context.ProjectRoot
  try { & $context.PythonPath @arguments } finally { Pop-Location }
  exit $LASTEXITCODE
}

$stdoutLog = Join-Path $context.RuntimeDir 'gravity.stdout.log'
$stderrLog = Join-Path $context.RuntimeDir 'gravity.stderr.log'
Rotate-GravityLog -Path $stdoutLog
Rotate-GravityLog -Path $stderrLog
$process = Start-Process -FilePath $context.PythonPath `
  -ArgumentList $arguments `
  -WorkingDirectory $context.ProjectRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru

for ($attempt = 0; $attempt -lt 40; $attempt++) {
  $serverId = Get-GravityPid -Context $context
  if ($serverId -and
      (Test-GravityManagedProcess -Context $context -ProcessId $serverId) -and
      (Test-GravityHealth -Context $context -TimeoutSec 1)) {
    Write-GravityOpsLog -Context $context -Message "server_started pid=$serverId launcherPid=$($process.Id) port=$($context.Port)"
    Write-Host "Gravity Fitness started with PID $serverId." -ForegroundColor Green
    Write-Host "Local health: $($context.HealthUrl)"
    exit 0
  }
  if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) -and -not $serverId) {
    Remove-GravityStaleState -Context $context
    throw "Gravity Fitness exited during startup. Check $stderrLog"
  }
  Start-Sleep -Milliseconds 500
}

$serverId = Get-GravityPid -Context $context
if ($serverId -and (Test-GravityManagedProcess -Context $context -ProcessId $serverId)) {
  Stop-Process -Id $serverId -ErrorAction SilentlyContinue
}
Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
Remove-GravityStaleState -Context $context
throw "Gravity Fitness did not become healthy on loopback. Check $stderrLog"
