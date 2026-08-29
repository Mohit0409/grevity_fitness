param(
  [Parameter(Mandatory = $true)][string]$ConfigPath,
  [switch]$EnsureNgrok,
  [string]$NgrokConfigPath,
  [string]$NgrokExecutablePath,
  [string]$OffsiteBackupDirectory,
  [ValidateRange(15, 1440)][int]$NotificationIntervalMinutes = 60,
  [string]$ExpectedReleaseSha,
  [switch]$RequireDetachedHead,
  [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$watchScript = Join-Path $PSScriptRoot 'watch-gravity.ps1'
$backupScript = Join-Path $PSScriptRoot 'backup-gravity.ps1'
$notificationScript = Join-Path $PSScriptRoot 'run-notifications.ps1'

function Quote-TaskArgument([string]$Value) {
  return '"' + $Value.Replace('"', '""') + '"'
}

foreach ($requiredPath in @($watchScript, $backupScript, $notificationScript, $powerShell)) {
  if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
    throw "Required task path was not found: $requiredPath"
  }
}

if ($ExpectedReleaseSha) {
  $actualSha = (& git -C $projectRoot rev-parse HEAD 2>$null | Out-String).Trim()
  if (-not $actualSha -or $actualSha -ne $ExpectedReleaseSha) {
    throw "Release checkout SHA mismatch. Expected $ExpectedReleaseSha but found $actualSha"
  }
  $dirty = (& git -C $projectRoot status --porcelain 2>$null | Out-String).Trim()
  if ($dirty) { throw 'Release checkout has uncommitted changes.' }
}
if ($RequireDetachedHead -and -not $ExpectedReleaseSha) {
  throw '-RequireDetachedHead requires -ExpectedReleaseSha.'
}
if ($RequireDetachedHead) {
  & git -C $projectRoot symbolic-ref -q --short HEAD *> $null
  if ($LASTEXITCODE -eq 0) { throw 'Release checkout must use a detached HEAD.' }
}

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
}

$watchArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $watchScript) + ' -ConfigPath ' + (Quote-TaskArgument $ConfigPath)
if ($EnsureNgrok) {
  $watchArguments += ' -EnsureNgrok -NgrokConfigPath ' + (Quote-TaskArgument $NgrokConfigPath) + ' -NgrokExecutablePath ' + (Quote-TaskArgument $NgrokExecutablePath)
}
$backupArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $backupScript) + ' -Label daily -ConfigPath ' + (Quote-TaskArgument $ConfigPath)
if ($OffsiteBackupDirectory) {
  $OffsiteBackupDirectory = [IO.Path]::GetFullPath($OffsiteBackupDirectory)
  $backupArguments += ' -OffsiteDirectory ' + (Quote-TaskArgument $OffsiteBackupDirectory)
}
$notificationArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $notificationScript) + ' -ConfigPath ' + (Quote-TaskArgument $ConfigPath)

$plan = [ordered]@{
  projectRoot = $projectRoot
  configPath = $ConfigPath
  gravityTarget = "http://127.0.0.1:$($context.Port)"
  runtimeDir = $context.RuntimeDir
  pythonPath = $context.PythonPath
  expectedReleaseSha = $ExpectedReleaseSha
  detachedHeadRequired = [bool]$RequireDetachedHead
  tasks = @(
    [ordered]@{ name='GravityFitness-Watchdog'; execute=$powerShell; arguments=$watchArguments; workingDirectory=$projectRoot; principal='SYSTEM'; runLevel='Highest'; triggers=@('AtStartup','Every1Minute') },
    [ordered]@{ name='GravityFitness-DailyBackup'; execute=$powerShell; arguments=$backupArguments; workingDirectory=$projectRoot; principal='SYSTEM'; runLevel='Highest'; triggers=@('Daily02:00') },
    [ordered]@{ name='GravityFitness-Notifications'; execute=$powerShell; arguments=$notificationArguments; workingDirectory=$projectRoot; principal='SYSTEM'; runLevel='Highest'; triggers=@('AtStartup',"Every${NotificationIntervalMinutes}Minutes") }
  )
}
if ($PreflightOnly) {
  $plan | ConvertTo-Json -Depth 8 -Compress
  exit 0
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Run this script from an elevated PowerShell window. Tasks run as SYSTEM for reboot recovery.'
}

$systemPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$watchAction = New-ScheduledTaskAction -Execute $powerShell -Argument $watchArguments -WorkingDirectory $projectRoot
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$minuteTrigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'GravityFitness-Watchdog' -Action $watchAction -Trigger @($startupTrigger, $minuteTrigger) -Settings $settings -Principal $systemPrincipal -Description 'Keep the loopback-only Gravity Fitness backend healthy.' -Force | Out-Null

$backupAction = New-ScheduledTaskAction -Execute $powerShell -Argument $backupArguments -WorkingDirectory $projectRoot
$backupTrigger = New-ScheduledTaskTrigger -Daily -At '02:00'
$backupSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName 'GravityFitness-DailyBackup' -Action $backupAction -Trigger $backupTrigger -Settings $backupSettings -Principal $systemPrincipal -Description 'Create, verify, and recovery-drill a Gravity Fitness SQLite backup.' -Force | Out-Null

$notificationAction = New-ScheduledTaskAction -Execute $powerShell -Argument $notificationArguments -WorkingDirectory $projectRoot
$notificationStartupTrigger = New-ScheduledTaskTrigger -AtStartup
$notificationIntervalTrigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes $NotificationIntervalMinutes)
$notificationSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName 'GravityFitness-Notifications' -Action $notificationAction -Trigger @($notificationStartupTrigger, $notificationIntervalTrigger) -Settings $notificationSettings -Principal $systemPrincipal -Description 'Run idempotent membership-expiry scans and due-notification delivery.' -Force | Out-Null

Write-Host 'Installed GravityFitness-Watchdog, GravityFitness-DailyBackup, and GravityFitness-Notifications.' -ForegroundColor Green
Write-Host 'Run verify-gravity-tasks.ps1, then inspect Task Scheduler history and operations.log.'
