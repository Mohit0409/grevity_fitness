param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$runner = Join-Path $PSScriptRoot 'run-notifications.py'
$envRunner = Join-Path $PSScriptRoot 'gravity-env.py'
$arguments = @($runner, '--root', $context.ProjectRoot, '--runtime-dir', $context.RuntimeDir, '--python', $context.PythonPath, '--status')
if ($context.ConfigPath) {
  & $context.PythonPath $envRunner --config $context.ConfigPath -- $context.PythonPath @arguments
} else {
  & $context.PythonPath @arguments
}
exit $LASTEXITCODE
