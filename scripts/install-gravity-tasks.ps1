param(
  [Parameter(Mandatory = $true)][string]$ConfigPath,
  [switch]$EnsureNgrok,
  [string]$NgrokConfigPath,
  [string]$NgrokExecutablePath,
  [string]$OffsiteBackupDirectory
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Run this script from an elevated PowerShell window. Tasks run as SYSTEM for reboot recovery.'
}
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$watchScript = Join-Path $PSScriptRoot 'watch-gravity.ps1'
$backupScript = Join-Path $PSScriptRoot 'backup-gravity.ps1'

function Quote-TaskArgument([string]$Value) {
  return '"' + $Value.Replace('"', '""') + '"'
}

$watchArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $watchScript) + ' -ConfigPath ' + (Quote-TaskArgument $ConfigPath)
if ($EnsureNgrok) {
  if (-not $NgrokConfigPath -or -not $NgrokExecutablePath) {
    throw 'NgrokConfigPath and NgrokExecutablePath are required with -EnsureNgrok because the task runs as SYSTEM.'
  }
  if (-not (Test-Path -LiteralPath $NgrokConfigPath -PathType Leaf)) {
    throw "ngrok configuration was not found: $NgrokConfigPath"
  }
  if (-not (Test-Path -LiteralPath $NgrokExecutablePath -PathType Leaf)) {
    throw "ngrok executable was not found: $NgrokExecutablePath"
  }
  $NgrokConfigPath = (Resolve-Path -LiteralPath $NgrokConfigPath).Path
  $NgrokExecutablePath = (Resolve-Path -LiteralPath $NgrokExecutablePath).Path
  $watchArguments += ' -EnsureNgrok -NgrokConfigPath ' + (Quote-TaskArgument $NgrokConfigPath) + ' -NgrokExecutablePath ' + (Quote-TaskArgument $NgrokExecutablePath)
}
$watchAction = New-ScheduledTaskAction -Execute $powerShell -Argument $watchArguments -WorkingDirectory $projectRoot
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$minuteTrigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$systemPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'GravityFitness-Watchdog' -Action $watchAction -Trigger @($startupTrigger, $minuteTrigger) -Settings $settings -Principal $systemPrincipal -Description 'Keep the loopback-only Gravity Fitness backend healthy.' -Force | Out-Null

$backupArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $backupScript) + ' -Label daily -ConfigPath ' + (Quote-TaskArgument $ConfigPath)
if ($OffsiteBackupDirectory) { $backupArguments += ' -OffsiteDirectory ' + (Quote-TaskArgument ([IO.Path]::GetFullPath($OffsiteBackupDirectory))) }
$backupAction = New-ScheduledTaskAction -Execute $powerShell -Argument $backupArguments -WorkingDirectory $projectRoot
$backupTrigger = New-ScheduledTaskTrigger -Daily -At '02:00'
$backupSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName 'GravityFitness-DailyBackup' -Action $backupAction -Trigger $backupTrigger -Settings $backupSettings -Principal $systemPrincipal -Description 'Create, verify, and recovery-drill a Gravity Fitness SQLite backup.' -Force | Out-Null

Write-Host 'Installed GravityFitness-Watchdog and GravityFitness-DailyBackup.' -ForegroundColor Green
Write-Host 'Run watch-gravity.ps1 once now, then inspect Task Scheduler history and operations.log.'
