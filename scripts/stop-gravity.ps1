param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$processId = Get-GravityPid -Context $context
if (-not $processId) {
  Remove-GravityStaleState -Context $context
  Write-Host 'Gravity Fitness is already stopped.'
  exit 0
}
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) {
  Remove-GravityStaleState -Context $context
  Write-Host 'Removed stale Gravity runtime state.'
  exit 0
}
if (-not (Test-GravityManagedProcess -Context $context -ProcessId $processId)) {
  throw "Refusing to stop PID $processId because its Gravity ownership cannot be proven."
}

Stop-Process -Id $processId -Force
try { Wait-Process -Id $processId -Timeout 10 -ErrorAction Stop } catch { }
if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
  if (Test-GravityHealth -Context $context -TimeoutSec 2) {
    throw "Gravity Fitness PID $processId did not stop within 10 seconds and still answers health checks."
  }
  Write-GravityOpsLog -Context $context -Message "server_process_handle_lingered_after_termination pid=$processId"
}
Remove-GravityStaleState -Context $context
Write-GravityOpsLog -Context $context -Message "server_stopped pid=$processId"
Write-Host 'Gravity Fitness stopped.' -ForegroundColor Green
