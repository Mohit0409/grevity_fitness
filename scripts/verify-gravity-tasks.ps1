param(
  [Parameter(Mandatory = $true)][string]$ConfigPath,
  [Parameter(Mandatory = $true)][string]$ExpectedReleaseSha,
  [switch]$RequireDetachedHead,
  [switch]$EnsureNgrok,
  [string]$NgrokConfigPath,
  [string]$NgrokExecutablePath,
  [string]$OffsiteBackupDirectory,
  [ValidateRange(15, 1440)][int]$NotificationIntervalMinutes = 60
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$projectRoot = $context.ProjectRoot
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$watchScript = Join-Path $PSScriptRoot 'watch-gravity.ps1'
$backupScript = Join-Path $PSScriptRoot 'backup-gravity.ps1'
$notificationScript = Join-Path $PSScriptRoot 'run-notifications.ps1'
$blockers = New-Object System.Collections.ArrayList
$taskReports = New-Object System.Collections.ArrayList

function Add-Blocker([string]$Message) { [void]$blockers.Add($Message) }
function Quote-TaskArgument([string]$Value) { return '"' + $Value.Replace('"', '""') + '"' }
function Same-Path([string]$Left, [string]$Right) {
  try { return [string]::Equals([IO.Path]::GetFullPath($Left), [IO.Path]::GetFullPath($Right), [StringComparison]::OrdinalIgnoreCase) }
  catch { return $false }
}

$actualSha = (& git -C $projectRoot rev-parse HEAD 2>$null | Out-String).Trim()
if (-not $actualSha -or $actualSha -ne $ExpectedReleaseSha) {
  Add-Blocker "release_sha_mismatch expected=$ExpectedReleaseSha actual=$actualSha"
}
$dirty = (& git -C $projectRoot status --porcelain 2>$null | Out-String).Trim()
if ($dirty) { Add-Blocker 'release_checkout_dirty' }
if ($RequireDetachedHead) {
  & git -C $projectRoot symbolic-ref -q --short HEAD *> $null
  if ($LASTEXITCODE -eq 0) { Add-Blocker 'release_checkout_not_detached' }
}
if ($context.Port -lt 1 -or $context.Port -gt 65535) { Add-Blocker 'invalid_gravity_port' }

if ($EnsureNgrok) {
  if (-not $NgrokConfigPath -or -not $NgrokExecutablePath) {
    Add-Blocker 'missing_explicit_ngrok_paths'
  } else {
    if (-not (Test-Path -LiteralPath $NgrokConfigPath -PathType Leaf)) { Add-Blocker 'ngrok_config_missing' }
    if (-not (Test-Path -LiteralPath $NgrokExecutablePath -PathType Leaf)) { Add-Blocker 'ngrok_executable_missing' }
    if (Test-Path -LiteralPath $NgrokConfigPath -PathType Leaf) { $NgrokConfigPath = (Resolve-Path -LiteralPath $NgrokConfigPath).Path }
    if (Test-Path -LiteralPath $NgrokExecutablePath -PathType Leaf) { $NgrokExecutablePath = (Resolve-Path -LiteralPath $NgrokExecutablePath).Path }
  }
}

$watchArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $watchScript) + ' -ConfigPath ' + (Quote-TaskArgument $ConfigPath)
if ($EnsureNgrok -and $NgrokConfigPath -and $NgrokExecutablePath) {
  $watchArguments += ' -EnsureNgrok -NgrokConfigPath ' + (Quote-TaskArgument $NgrokConfigPath) + ' -NgrokExecutablePath ' + (Quote-TaskArgument $NgrokExecutablePath)
}
$backupArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $backupScript) + ' -Label daily -ConfigPath ' + (Quote-TaskArgument $ConfigPath)
if ($OffsiteBackupDirectory) {
  $OffsiteBackupDirectory = [IO.Path]::GetFullPath($OffsiteBackupDirectory)
  $backupArguments += ' -OffsiteDirectory ' + (Quote-TaskArgument $OffsiteBackupDirectory)
}
$notificationArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + (Quote-TaskArgument $notificationScript) + ' -ConfigPath ' + (Quote-TaskArgument $ConfigPath)

$expected = @{
  'GravityFitness-Watchdog' = @{ arguments=$watchArguments; script=$watchScript; boot=$true; repeat=1; dailyHour=$null }
  'GravityFitness-DailyBackup' = @{ arguments=$backupArguments; script=$backupScript; boot=$false; repeat=$null; dailyHour=2 }
  'GravityFitness-Notifications' = @{ arguments=$notificationArguments; script=$notificationScript; boot=$true; repeat=$NotificationIntervalMinutes; dailyHour=$null }
}
$forbidden = @('SECRET_KEY=','SMTP_PASSWORD=','SMS_API_KEY=','WHATSAPP_ACCESS_TOKEN=','RAZORPAY_KEY_SECRET=','RAZORPAY_WEBHOOK_SECRET=','FIREBASE_SERVICE_ACCOUNT=','authtoken=')

foreach ($name in @('GravityFitness-Watchdog','GravityFitness-DailyBackup','GravityFitness-Notifications')) {
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if (-not $task) {
    Add-Blocker "task_missing:$name"
    [void]$taskReports.Add([ordered]@{ name=$name; present=$false })
    continue
  }
  $issues = New-Object System.Collections.ArrayList
  if ([string]$task.Principal.UserId -notin @('SYSTEM','NT AUTHORITY\SYSTEM')) { [void]$issues.Add('principal_not_system') }
  if ([string]$task.Principal.RunLevel -ne 'Highest') { [void]$issues.Add('runlevel_not_highest') }
  if ([string]$task.Settings.MultipleInstances -ne 'IgnoreNew') { [void]$issues.Add('multiple_instances_not_ignorenew') }
  if (-not $task.Settings.Enabled) { [void]$issues.Add('task_disabled') }

  $actions = @($task.Actions)
  if ($actions.Count -ne 1) { [void]$issues.Add('unexpected_action_count') }
  $action = $actions | Select-Object -First 1
  if ($action) {
    if (-not (Same-Path ([string]$action.Execute) $powerShell)) { [void]$issues.Add('powershell_path_mismatch') }
    if (-not (Same-Path ([string]$action.WorkingDirectory) $projectRoot)) { [void]$issues.Add('working_directory_mismatch') }
    if ([string]$action.Arguments -ne [string]$expected[$name].arguments) { [void]$issues.Add('arguments_mismatch') }
    foreach ($marker in $forbidden) {
      if ([string]$action.Arguments -like "*$marker*") { [void]$issues.Add("secret_marker:$marker") }
    }
  }

  $triggers = @($task.Triggers)
  $triggerClasses = @($triggers | ForEach-Object { $_.CimClass.CimClassName })
  if ($expected[$name].boot -and $triggerClasses -notcontains 'MSFT_TaskBootTrigger') { [void]$issues.Add('startup_trigger_missing') }
  if ($null -ne $expected[$name].repeat) {
    $repeatMinutes = @()
    foreach ($trigger in $triggers) {
      if ($trigger.Repetition -and $trigger.Repetition.Interval) {
        try { $repeatMinutes += [System.Xml.XmlConvert]::ToTimeSpan([string]$trigger.Repetition.Interval).TotalMinutes } catch { }
      }
    }
    if ($repeatMinutes -notcontains [double]$expected[$name].repeat) { [void]$issues.Add('repetition_interval_mismatch') }
  }
  if ($null -ne $expected[$name].dailyHour) {
    $daily = @($triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskDailyTrigger' }) | Select-Object -First 1
    if (-not $daily) { [void]$issues.Add('daily_trigger_missing') }
    elseif (([DateTime]$daily.StartBoundary).Hour -ne [int]$expected[$name].dailyHour) { [void]$issues.Add('daily_trigger_time_mismatch') }
  }

  foreach ($issue in $issues) { Add-Blocker "$name`:$issue" }
  [void]$taskReports.Add([ordered]@{ name=$name; present=$true; issues=@($issues) })
}

$report = [ordered]@{
  ready = $blockers.Count -eq 0
  projectRoot = $projectRoot
  releaseSha = $actualSha
  expectedReleaseSha = $ExpectedReleaseSha
  gravityTarget = "http://127.0.0.1:$($context.Port)"
  tasks = @($taskReports)
  blockers = @($blockers)
}
$report | ConvertTo-Json -Depth 8 -Compress
if ($blockers.Count -ne 0) { exit 2 }
