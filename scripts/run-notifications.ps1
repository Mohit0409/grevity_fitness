param(
  [string]$ConfigPath,
  [ValidateRange(30, 900)][int]$TimeoutSec = 180,
  [ValidateRange(240, 7200)][int]$StaleLockSec = 1200
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$runner = Join-Path $PSScriptRoot 'run-notifications.py'
$arguments = @(
  $runner,
  '--root', $context.ProjectRoot,
  '--runtime-dir', $context.RuntimeDir,
  '--python', $context.PythonPath,
  '--timeout-seconds', $TimeoutSec,
  '--stale-lock-seconds', $StaleLockSec
)
$output = @(& $context.PythonPath @arguments 2>&1)
$exitCode = $LASTEXITCODE
$report = $null
foreach ($line in $output) {
  $candidate = $null
  try {
    $candidate = ConvertFrom-Json -InputObject ([string]$line) -ErrorAction Stop
  } catch {
    continue
  }
  $eventProperty = $candidate.PSObject.Properties['event']
  if ($eventProperty -and [string]$eventProperty.Value -eq 'notification_cycle') {
    $report = $candidate
    break
  }
}
if ($null -eq $report) {
  Write-GravityOpsLog -Context $context -Message 'notification_cycle status=invalid_report'
  throw 'Notification runner did not return a safe report.'
}
$message = "notification_cycle status=$($report.status) created=$($report.created) deduped=$($report.deduped) suppressed_renewed=$($report.suppressed_renewed) delivery_attempted=$($report.delivery_attempted) delivery_sent=$($report.delivery_sent) delivery_failed=$($report.delivery_failed) delivery_skipped=$($report.delivery_skipped)"
$failure = $report.PSObject.Properties['failure']
if ($failure) { $message += " failure=$($failure.Value)" }
Write-GravityOpsLog -Context $context -Message $message
$report | ConvertTo-Json -Depth 6 -Compress
if ($exitCode -ne 0) { exit $exitCode }
