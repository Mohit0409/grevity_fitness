param(
  [Parameter(Mandatory = $true)][string]$ConfigPath,
  [Parameter(Mandatory = $true)][string]$ExpectedReleaseSha,
  [Parameter(Mandatory = $true)][string]$NgrokConfigPath,
  [Parameter(Mandatory = $true)][string]$NgrokExecutablePath,
  [string]$OffsiteBackupDirectory,
  [ValidateRange(15, 1440)][int]$NotificationIntervalMinutes = 60
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
function Fail-Json([string]$Code) { [ordered]@{ ready=$false; blockers=@($Code); warnings=@() } | ConvertTo-Json -Compress; exit 2 }
foreach ($required in @(@($ConfigPath,'config_missing'),@($NgrokConfigPath,'ngrok_config_missing'),@($NgrokExecutablePath,'ngrok_executable_missing'))) { if (-not (Test-Path -LiteralPath $required[0] -PathType Leaf)) { Fail-Json $required[1] } }
try { $context = Get-GravityContext -ConfigPath $ConfigPath } catch { Fail-Json 'gravity_context_invalid' }
$collectionBlockers = New-Object System.Collections.ArrayList

function Add-CollectionBlocker([string]$Value) { [void]$collectionBlockers.Add($Value) }
function Read-JsonObject([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
  catch { return $null }
}
function Get-Field($Object, [string]$Name) {
  if ($null -eq $Object) { return $null }
  $property = $Object.PSObject.Properties[$Name]
  if ($property) { return $property.Value }
  return $null
}
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$NgrokConfigPath = (Resolve-Path -LiteralPath $NgrokConfigPath).Path
$NgrokExecutablePath = (Resolve-Path -LiteralPath $NgrokExecutablePath).Path
$now = [DateTimeOffset]::UtcNow.UtcDateTime.ToString('o')
try { $bootTime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o') }
catch { Add-CollectionBlocker 'boot_time_unavailable'; $bootTime = $null }

$actualSha = (& git -C $context.ProjectRoot rev-parse HEAD 2>$null | Out-String).Trim()
$clean = -not [bool]((& git -C $context.ProjectRoot status --porcelain 2>$null | Out-String).Trim())
& git -C $context.ProjectRoot symbolic-ref -q --short HEAD *> $null
$detached = $LASTEXITCODE -ne 0

$pidFileValue = Get-GravityPid -Context $context
$state = Read-JsonObject $context.StateFile
$serverProcess = if ($pidFileValue) { Get-Process -Id $pidFileValue -ErrorAction SilentlyContinue } else { $null }
$serverCim = if ($pidFileValue) { Get-CimInstance Win32_Process -Filter "ProcessId=$pidFileValue" -ErrorAction SilentlyContinue } else { $null }
$expectedPython = $context.PythonPath
if (Test-Path -LiteralPath $context.PythonPath -PathType Leaf) { $expectedPython = (Resolve-Path -LiteralPath $context.PythonPath).Path }
else { Add-CollectionBlocker 'gravity_python_missing' }

$serverCommand = if ($serverCim) { [string]$serverCim.CommandLine } else { '' }
$commandValid = $serverCommand -match '(?i)-m\s+server\.gravity' -and
  $serverCommand -match '(?i)--host\s+127\.0\.0\.1' -and
  $serverCommand -match '(?i)--port\s+8787'
try {
  $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $context.Port -ErrorAction Stop)
  $listenerValid = $listeners.Count -eq 1 -and [string]$listeners[0].LocalAddress -eq '127.0.0.1' -and [int]$listeners[0].OwningProcess -eq [int]$pidFileValue
} catch { Add-CollectionBlocker 'gravity_listener_probe_failed'; $listenerValid = $false }
try {
  $health = Invoke-RestMethod -Uri $context.HealthUrl -TimeoutSec 5
  $healthOk = $health.status -eq 'ok' -and $health.service -eq 'Gravity Fitness' -and $health.database -eq 'ok'
} catch { $healthOk = $false }

$releaseEvidence = [ordered]@{
  expectedSha = $ExpectedReleaseSha
  actualSha = $actualSha
  clean = $clean
  detached = $detached
  projectRoot = $context.ProjectRoot
  stateProjectRoot = if ($state) { [string](Get-Field $state 'projectRoot') } else { $null }
  expectedPython = $expectedPython
  stateExecutable = if ($state) { [string](Get-Field $state 'executable') } else { $null }
  processExecutable = if ($serverCim) { [string]$serverCim.ExecutablePath } else { $null }
  pid = if ($serverProcess) { [int]$serverProcess.Id } else { $null }
  pidFile = $pidFileValue
  statePid = if ($state) { [int](Get-Field $state 'pid') } else { $null }
  processStartedAt = if ($serverProcess) { $serverProcess.StartTime.ToUniversalTime().ToString('o') } else { $null }
  stateStartedAt = if ($state) { [string](Get-Field $state 'startedAt') } else { $null }
  commandValid = [bool]$commandValid
  listenerValid = [bool]$listenerValid
  healthOk = [bool]$healthOk
  port = [int]$context.Port
}
$taskArgs = @{
  ConfigPath = $ConfigPath
  ExpectedReleaseSha = $ExpectedReleaseSha
  RequireDetachedHead = $true
  EnsureNgrok = $true
  NgrokConfigPath = $NgrokConfigPath
  NgrokExecutablePath = $NgrokExecutablePath
  NotificationIntervalMinutes = $NotificationIntervalMinutes
}
if ($OffsiteBackupDirectory) { $taskArgs.OffsiteBackupDirectory = $OffsiteBackupDirectory }
try {
  $taskOutput = & (Join-Path $PSScriptRoot 'verify-gravity-tasks.ps1') @taskArgs
  $taskExit = $LASTEXITCODE
  $taskVerification = (($taskOutput | Out-String).Trim() | ConvertFrom-Json)
  if ($taskExit -ne 0 -and -not $taskVerification) { Add-CollectionBlocker 'task_verifier_failed' }
} catch {
  Add-CollectionBlocker 'task_verifier_exception'
  $taskVerification = [pscustomobject]@{ ready=$false; blockers=@('verification_exception') }
}

$taskRuntime = New-Object System.Collections.ArrayList
foreach ($taskName in @('GravityFitness-Watchdog','GravityFitness-DailyBackup','GravityFitness-Notifications')) {
  $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  if (-not $task) {
    [void]$taskRuntime.Add([ordered]@{ name=$taskName; present=$false; enabled=$false })
    continue
  }
  $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
  [void]$taskRuntime.Add([ordered]@{
    name = $taskName
    present = $true
    enabled = [bool]$task.Settings.Enabled
    state = [string]$task.State
    lastTaskResult = if ($info) { [int64]$info.LastTaskResult } else { $null }
    lastRunTime = if ($info -and $info.LastRunTime -gt [DateTime]::MinValue) { $info.LastRunTime.ToUniversalTime().ToString('o') } else { $null }
    nextRunTime = if ($info -and $info.NextRunTime -gt [DateTime]::MinValue) { $info.NextRunTime.ToUniversalTime().ToString('o') } else { $null }
    missedRuns = if ($info) { [int]$info.NumberOfMissedRuns } else { $null }
  })
}

$ngrokPidPath = Join-Path $context.RuntimeDir 'ngrok.pid'
$ngrokStatePath = Join-Path $context.RuntimeDir 'ngrok.state.json'
$ngrokUrlPath = Join-Path $context.RuntimeDir 'ngrok.public-url'
$ngrokState = Read-JsonObject $ngrokStatePath
$ngrokPidFile = $null
if (Test-Path -LiteralPath $ngrokPidPath -PathType Leaf) {
  $rawNgrokPid = (Get-Content -LiteralPath $ngrokPidPath -Raw).Trim()
  if ($rawNgrokPid -match '^\d+$') { $ngrokPidFile = [int]$rawNgrokPid }
}
$ngrokProcess = if ($ngrokPidFile) { Get-Process -Id $ngrokPidFile -ErrorAction SilentlyContinue } else { $null }
$ngrokCim = if ($ngrokPidFile) { Get-CimInstance Win32_Process -Filter "ProcessId=$ngrokPidFile" -ErrorAction SilentlyContinue } else { $null }
$ngrokCommand = if ($ngrokCim) { [string]$ngrokCim.CommandLine } else { '' }
$ngrokCommandValid = $ngrokCommand.IndexOf('http://127.0.0.1:8787', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
  $ngrokCommand.IndexOf($NgrokConfigPath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
  $ngrokCommand -notmatch '(?i)--authtoken|authtoken='
$stateUrl = if (Test-Path -LiteralPath $ngrokUrlPath -PathType Leaf) { (Get-Content -LiteralPath $ngrokUrlPath -Raw).Trim().TrimEnd('/') } else { $null }
$tunnelMatches = @()
try {
  $tunnelResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 3
  $tunnelMatches = @($tunnelResponse.tunnels | Where-Object {
    $_.public_url -like 'https://*' -and [string]$_.config.addr -eq 'http://127.0.0.1:8787'
  })
} catch { Add-CollectionBlocker 'ngrok_tunnel_api_unavailable' }
$tunnelUrl = if ($tunnelMatches.Count -eq 1) { [string]$tunnelMatches[0].public_url.TrimEnd('/') } else { $null }
$publicHealthOk = $false
if ($tunnelUrl) {
  try {
    $publicHealth = Invoke-RestMethod -Uri "$tunnelUrl/api/health" -Headers @{ 'ngrok-skip-browser-warning' = 'true' } -TimeoutSec 8
    $publicHealthOk = $publicHealth.status -eq 'ok' -and $publicHealth.service -eq 'Gravity Fitness' -and $publicHealth.database -eq 'ok'
  } catch { $publicHealthOk = $false }
}
$ngrokEvidence = [ordered]@{
  managed = [bool]($ngrokState -and $ngrokPidFile -and $stateUrl)
  pid = if ($ngrokProcess) { [int]$ngrokProcess.Id } else { $null }
  pidFile = $ngrokPidFile
  statePid = if ($ngrokState) { [int](Get-Field $ngrokState 'pid') } else { $null }
  expectedExecutable = $NgrokExecutablePath
  stateExecutable = if ($ngrokState) { [string](Get-Field $ngrokState 'executable') } else { $null }
  processExecutable = if ($ngrokCim) { [string]$ngrokCim.ExecutablePath } else { $null }
  expectedConfig = $NgrokConfigPath
  stateConfig = if ($ngrokState -and $ngrokState.PSObject.Properties['configPath']) { [string](Get-Field $ngrokState 'configPath') } else { $null }
  target = if ($ngrokState) { [string](Get-Field $ngrokState 'target') } else { $null }
  stateStartedAt = if ($ngrokState) { [string](Get-Field $ngrokState 'startedAt') } else { $null }
  processStartedAt = if ($ngrokProcess) { $ngrokProcess.StartTime.ToUniversalTime().ToString('o') } else { $null }
  commandValid = [bool]$ngrokCommandValid
  tunnelCount = [int]$tunnelMatches.Count
  tunnelUrl = $tunnelUrl
  stateUrl = $stateUrl
  publicHealthOk = [bool]$publicHealthOk
}

$notificationStatePath = Join-Path $context.RuntimeDir 'notification-state.json'
$notificationLockPath = Join-Path $context.RuntimeDir 'notification-runner.lock'
$notificationState = Read-JsonObject $notificationStatePath
$providerStatuses = [ordered]@{}
if ($notificationState -and $notificationState.PSObject.Properties['provider_readiness']) {
  foreach ($name in @('email','sms','whatsapp','owner_email','owner_phone','owner_whatsapp')) {
    $provider = $notificationState.provider_readiness.PSObject.Properties[$name]
    if ($provider -and $provider.Value.PSObject.Properties['status']) { $providerStatuses[$name] = [string]$provider.Value.status }
  }
}
$lastReportStatus = $null
if ($notificationState -and $notificationState.PSObject.Properties['last_report']) {
  $lastReport = $notificationState.last_report
  if ($lastReport -and $lastReport.PSObject.Properties['status']) { $lastReportStatus = [string]$lastReport.status }
}
$notificationEvidence = [ordered]@{
  statePresent = [bool]$notificationState
  lastSuccessfulScanAt = if ($notificationState -and $notificationState.PSObject.Properties['last_successful_scan_at']) { [string]$notificationState.last_successful_scan_at } else { $null }
  lastSuccessfulDeliveryAt = if ($notificationState -and $notificationState.PSObject.Properties['last_successful_delivery_at']) { [string]$notificationState.last_successful_delivery_at } else { $null }
  lastReportStatus = $lastReportStatus
  consecutiveFailures = if ($notificationState -and $notificationState.PSObject.Properties['consecutive_failures']) { [int]$notificationState.consecutive_failures } else { 0 }
  providerReadiness = $providerStatuses
  lockPresent = Test-Path -LiteralPath $notificationLockPath -PathType Leaf
}

$backupEvidence = [ordered]@{ evidencePresent=$false; lastVerifiedAt=$null; recoveryDrillPassed=$false }
$operationsLog = Join-Path $context.RuntimeDir 'operations.log'
if (Test-Path -LiteralPath $operationsLog -PathType Leaf) {
  $lastBackupLine = @(Get-Content -LiteralPath $operationsLog | Where-Object { $_ -match '\sbackup_verified\s' }) | Select-Object -Last 1
  if ($lastBackupLine) {
    $parts = [string]$lastBackupLine -split '\s+', 2
    $backupEvidence.evidencePresent = $true
    $backupEvidence.lastVerifiedAt = $parts[0]
    $backupEvidence.recoveryDrillPassed = [bool]([string]$lastBackupLine -match 'recoveryDrill=True')
  }
}
$evidence = [ordered]@{
  now = $now
  bootTime = $bootTime
  collectionBlockers = @($collectionBlockers)
  release = $releaseEvidence
  taskVerification = $taskVerification
  tasks = @($taskRuntime)
  ngrok = $ngrokEvidence
  notifications = $notificationEvidence
  backup = $backupEvidence
}

$helper = Join-Path $PSScriptRoot 'release-lifecycle-check.py'
if (-not (Test-Path -LiteralPath $context.PythonPath -PathType Leaf)) {
  [ordered]@{ ready=$false; blockers=@('gravity_python_missing'); warnings=@() } | ConvertTo-Json -Compress
  exit 2
}
try {
  $evidenceJson = $evidence | ConvertTo-Json -Depth 12 -Compress
  $result = $evidenceJson | & $context.PythonPath $helper
  $validatorExit = $LASTEXITCODE
  ($result | Out-String).Trim()
  if ($validatorExit -ne 0) { exit 2 }
  exit 0
} catch {
  [ordered]@{ ready=$false; blockers=@('lifecycle_validator_failed'); warnings=@() } | ConvertTo-Json -Compress
  exit 2
}
