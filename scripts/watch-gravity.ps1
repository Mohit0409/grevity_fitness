param(
  [string]$ConfigPath,
  [switch]$EnsureNgrok,
  [string]$NgrokConfigPath,
  [string]$NgrokExecutablePath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
New-Item -ItemType Directory -Force -Path $context.RuntimeDir | Out-Null
$lockPath = Join-Path $context.RuntimeDir 'watchdog.lock'
$lock = $null
try {
  try {
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
  } catch [IO.IOException] {
    exit 0
  }
  $managedProcessId = Get-GravityPid -Context $context
  $managed = $managedProcessId -and (Test-GravityManagedProcess -Context $context -ProcessId $managedProcessId)
  if (-not ($managed -and (Test-GravityHealth -Context $context))) {
    Write-GravityOpsLog -Context $context -Message 'watchdog_detected_unhealthy_server'
    if ($managedProcessId -and (Get-Process -Id $managedProcessId -ErrorAction SilentlyContinue)) {
      if (-not $managed) { throw "Watchdog found untrusted live PID $managedProcessId and will not terminate it." }
      & (Join-Path $PSScriptRoot 'stop-gravity.ps1') -ConfigPath $ConfigPath
    } else {
      Remove-GravityStaleState -Context $context
    }
    & (Join-Path $PSScriptRoot 'start-gravity.ps1') -ConfigPath $ConfigPath
    Write-GravityOpsLog -Context $context -Message 'watchdog_recovered_server'
  }
  if ($EnsureNgrok) {
    if (-not $NgrokConfigPath -or -not $NgrokExecutablePath) {
      throw 'NgrokConfigPath and NgrokExecutablePath are required with -EnsureNgrok for SYSTEM task recovery.'
    }
    & (Join-Path $PSScriptRoot 'start-ngrok.ps1') -ConfigPath $ConfigPath -NgrokConfigPath $NgrokConfigPath -NgrokExecutablePath $NgrokExecutablePath -UpdateConfig
  }
} catch {
  Write-GravityOpsLog -Context $context -Message "watchdog_failed error=$($_.Exception.Message)"
  throw
} finally {
  if ($lock) { $lock.Dispose() }
  Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
