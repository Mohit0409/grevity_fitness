param(
  [string]$ConfigPath,
  [ValidateRange(30, 900)][int]$TimeoutSec = 900
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$runner = Join-Path $PSScriptRoot 'run-notifications.py'
$envRunner = Join-Path $PSScriptRoot 'gravity-env.py'
$arguments = @(
  $runner,
  '--root', $context.ProjectRoot,
  '--runtime-dir', $context.RuntimeDir,
  '--python', $context.PythonPath,
  '--timeout-seconds', $TimeoutSec
)
if ($context.ConfigPath) {
  $output = @(& $context.PythonPath $envRunner --config $context.ConfigPath -- $context.PythonPath @arguments 2>&1)
} else {
  $output = @(& $context.PythonPath @arguments 2>&1)
}
$exitCode = $LASTEXITCODE
$report = $null
foreach ($line in $output) {
  try {
    $candidate = $line | ConvertFrom-Json -ErrorAction Stop
    if ($candidate.event -eq 'notification_cycle') { $report = $candidate }
  } catch { }
}
if (-not $report) {
  Write-GravityOpsLog -Context $context -Message 'notification_cycle status=invalid_report'
  throw 'Notification runner did not return a safe report.'
}
$message = "notification_cycle status=$($report.status) created=$($report.created) deduped=$($report.deduped) suppressed_renewed=$($report.suppressed_renewed) delivery_attempted=$($report.delivery_attempted) delivery_sent=$($report.delivery_sent) delivery_failed=$($report.delivery_failed) delivery_skipped=$($report.delivery_skipped)"
$failure = $report.PSObject.Properties['failure']
if ($failure) { $message += " failure=$($failure.Value)" }
Write-GravityOpsLog -Context $context -Message $message
$report | ConvertTo-Json -Depth 6 -Compress
if ($exitCode -ne 0) { exit $exitCode }
