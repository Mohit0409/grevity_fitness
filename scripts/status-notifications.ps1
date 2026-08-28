param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$runner = Join-Path $PSScriptRoot 'run-notifications.py'
$arguments = @($runner, '--root', $context.ProjectRoot, '--runtime-dir', $context.RuntimeDir, '--python', $context.PythonPath, '--status')
& $context.PythonPath @arguments
exit $LASTEXITCODE
