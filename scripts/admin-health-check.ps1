param(
  [string]$ConfigPath,
  [ValidateRange(15, 1440)][int]$SchedulerMaxAgeMinutes = 90
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$runner = Join-Path $PSScriptRoot 'admin-health-check.py'
$arguments = @(
  $runner,
  '--root', $context.ProjectRoot,
  '--runtime-dir', $context.RuntimeDir,
  '--base-url', "http://127.0.0.1:$($context.Port)",
  '--scheduler-max-age-minutes', $SchedulerMaxAgeMinutes
)
& $context.PythonPath @arguments
exit $LASTEXITCODE
