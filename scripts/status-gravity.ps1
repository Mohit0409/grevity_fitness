param([string]$ConfigPath, [switch]$Json)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$processId = Get-GravityPid -Context $context
$running = $false
$managed = $false
if ($processId) {
  $running = [bool](Get-Process -Id $processId -ErrorAction SilentlyContinue)
  if ($running) { $managed = Test-GravityManagedProcess -Context $context -ProcessId $processId }
}
$healthy = $managed -and (Test-GravityHealth -Context $context)
$status = [pscustomobject]@{
  running = $running
  managed = $managed
  healthy = $healthy
  pid = $processId
  healthUrl = $context.HealthUrl
  runtimeDir = $context.RuntimeDir
}
if ($Json) { $status | ConvertTo-Json -Compress }
elseif ($healthy) { Write-Host "Gravity Fitness is healthy (PID $processId) at $($context.HealthUrl)." -ForegroundColor Green }
elseif ($running -and -not $managed) { Write-Host "PID $processId is live but is not provably owned by this Gravity checkout." -ForegroundColor Red }
elseif ($running) { Write-Host "Gravity Fitness PID $processId is running but unhealthy." -ForegroundColor Yellow }
else { Write-Host 'Gravity Fitness is stopped.' }
if ($healthy) { exit 0 }
if ($running) { exit 2 }
exit 1
