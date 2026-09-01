[CmdletBinding()]
param(
  [string]$ConfigPath,
  [string]$DeviceName = 'Gravity Entrance F09',
  [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')][string]$DeviceIp = '192.168.1.201',
  [ValidateRange(1, 65535)][int]$DevicePort = 4370,
  [ValidateNotNullOrEmpty()][string]$DeviceIdentifier = '1',
  [ValidateNotNullOrEmpty()][string]$Timezone = 'Asia/Kolkata',
  [ValidateRange(10, 1800)][int]$DuplicateWindowSeconds = 120,
  [ValidateRange(600, 86400)][int]$VisitGapSeconds = 14400,
  [string]$AdminUsername,
  [switch]$InstallZkDriver,
  [switch]$StartNgrok,
  [string]$NgrokConfigPath,
  [string]$NgrokExecutablePath,
  [string]$NgrokDomain,
  [switch]$SkipSync,
  [switch]$PreflightOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'gravity-common.ps1')

function Resolve-GravityConfigPath {
  param([string]$ExplicitPath)
  if ($ExplicitPath) {
    if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
      throw "Gravity configuration was not found: $ExplicitPath"
    }
    return (Resolve-Path -LiteralPath $ExplicitPath).Path
  }
  if ($env:GRAVITY_ENV_FILE -and (Test-Path -LiteralPath $env:GRAVITY_ENV_FILE -PathType Leaf)) {
    return (Resolve-Path -LiteralPath $env:GRAVITY_ENV_FILE).Path
  }
  $protected = Join-Path $env:ProgramData 'GravityFitness\gravity.env'
  if (Test-Path -LiteralPath $protected -PathType Leaf) {
    return (Resolve-Path -LiteralPath $protected).Path
  }
  $checkout = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path '.env'
  if (Test-Path -LiteralPath $checkout -PathType Leaf) {
    return (Resolve-Path -LiteralPath $checkout).Path
  }
  throw 'No Gravity configuration was found. Pass -ConfigPath with the protected gravity.env path.'
}

function ConvertTo-PlainText {
  param([Parameter(Mandatory = $true)][Security.SecureString]$Value)
  $pointer = [IntPtr]::Zero
  try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  } finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
  }
}

function Invoke-ChildPowerShell {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  $powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  if (-not (Test-Path -LiteralPath $powerShell -PathType Leaf)) { throw 'Windows PowerShell was not found.' }
  & $powerShell @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Gravity child command failed with exit code $LASTEXITCODE." }
}

function Get-ApiFailureMessage {
  param([Parameter(Mandatory = $true)]$ErrorRecord)
  $response = $ErrorRecord.Exception.Response
  if ($null -eq $response) { return $ErrorRecord.Exception.Message }
  try {
    $stream = $response.GetResponseStream()
    if ($null -eq $stream) { return "HTTP $([int]$response.StatusCode)" }
    $reader = New-Object IO.StreamReader($stream)
    try {
      $body = $reader.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop
      if ($body.error) {
        $status = if ($body.status) { " ($($body.status))" } else { '' }
        return "$($body.error)$status"
      }
    } finally { $reader.Dispose() }
  } catch { }
  return "HTTP $([int]$response.StatusCode)"
}

function Invoke-GravityApi {
  param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [hashtable]$Body,
    [string]$CsrfToken
  )
  $headers = @{
    Accept = 'application/json'
    Origin = $BaseUrl
    'ngrok-skip-browser-warning' = 'true'
  }
  if ($CsrfToken) { $headers['X-CSRF-Token'] = $CsrfToken }
  $invoke = @{
    Uri = "$BaseUrl$Path"
    Method = $Method
    WebSession = $Session
    Headers = $headers
    UserAgent = 'Gravity Fitness F09 on-site setup'
    ErrorAction = 'Stop'
  }
  if ($null -ne $Body) {
    $invoke['ContentType'] = 'application/json'
    $invoke['Body'] = $Body | ConvertTo-Json -Depth 8 -Compress
  }
  try {
    return Invoke-RestMethod @invoke
  } catch {
    throw (Get-ApiFailureMessage -ErrorRecord $_)
  }
}

function Test-ZkDriver {
  param([Parameter(Mandatory = $true)]$Context, [switch]$Install)
  & $Context.PythonPath -c 'from zk import ZK; print("ready")' *> $null
  if ($LASTEXITCODE -eq 0) { return }
  if (-not $Install) {
    throw 'The ZKTeco direct-TCP driver is missing. Re-run with -InstallZkDriver while this PC has internet access.'
  }
  $requirements = Join-Path $PSScriptRoot 'requirements-biometric-driver.txt'
  if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) { throw 'Biometric driver requirements file is missing.' }
  Write-Host 'Installing the pinned ZKTeco direct-TCP driver...' -ForegroundColor Yellow
  & $Context.PythonPath -m pip install --disable-pip-version-check --require-hashes -r $requirements
  if ($LASTEXITCODE -ne 0) { throw 'The ZKTeco driver installation failed. Check internet access and Python permissions, then retry.' }
  & $Context.PythonPath -c 'from zk import ZK; print("ready")' *> $null
  if ($LASTEXITCODE -ne 0) { throw 'The ZKTeco driver was installed but cannot be imported.' }
}

function Get-PortalBaseUrl {
  param([Parameter(Mandatory = $true)]$Context, [switch]$UseNgrok)
  if ($UseNgrok) {
    $urlFile = Join-Path $Context.RuntimeDir 'ngrok.public-url'
    if (-not (Test-Path -LiteralPath $urlFile -PathType Leaf)) { throw 'ngrok did not record a public HTTPS URL.' }
    $url = (Get-Content -LiteralPath $urlFile -Raw).Trim().TrimEnd('/')
    if ($url -notmatch '^https://[^/]+$') { throw 'ngrok returned an invalid public HTTPS URL.' }
    return $url
  }
  if ($env:GRAVITY_ENV -eq 'production') {
    $configuredUrl = if ($env:APP_BASE_URL) { $env:APP_BASE_URL } else { '' }
    $url = $configuredUrl.Trim().TrimEnd('/')
    if ($url -notmatch '^https://[^/]+$') {
      throw 'Production admin configuration requires an HTTPS public URL. Re-run with -StartNgrok or restore the approved tunnel first.'
    }
    return $url
  }
  return "http://127.0.0.1:$($Context.Port)"
}

function Get-TaskSummary {
  $names = @('GravityFitness-Watchdog', 'GravityFitness-DailyBackup', 'GravityFitness-Notifications')
  try {
    $missing = @($names | Where-Object { -not (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue) })
    if ($missing.Count -eq 0) { return 'Windows reboot tasks: present' }
    return "Windows reboot tasks missing: $($missing -join ', ')"
  } catch {
    return 'Windows reboot task status could not be read from this PowerShell session.'
  }
}

$ConfigPath = Resolve-GravityConfigPath -ExplicitPath $ConfigPath
$context = Get-GravityContext -ConfigPath $ConfigPath
$projectRoot = $context.ProjectRoot
$startScript = Join-Path $PSScriptRoot 'start-gravity.ps1'
$ngrokScript = Join-Path $PSScriptRoot 'start-ngrok.ps1'
foreach ($required in @($context.PythonPath, $startScript)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required Gravity path was not found: $required" }
}

$plan = [ordered]@{
  mode = if ($PreflightOnly) { 'preflight' } else { 'configure' }
  projectRoot = $projectRoot
  configPath = $ConfigPath
  gravityTarget = "http://127.0.0.1:$($context.Port)"
  device = [ordered]@{ name=$DeviceName; model='F09'; host=$DeviceIp; port=$DevicePort; deviceIdentifier=$DeviceIdentifier; timezone=$Timezone }
  startNgrok = [bool]$StartNgrok
  installZkDriver = [bool]$InstallZkDriver
  syncDevice = -not [bool]$SkipSync
}
if ($PreflightOnly) {
  $plan | ConvertTo-Json -Depth 6 -Compress
  exit 0
}

Write-Host 'Gravity Fitness F09 on-site setup' -ForegroundColor Cyan
Write-Host "Configuration: $ConfigPath"
Write-Host "F09 direct TCP target: $DeviceIp`:$DevicePort"

$tcp = Test-NetConnection -ComputerName $DeviceIp -Port $DevicePort -WarningAction SilentlyContinue
if (-not $tcp.TcpTestSucceeded) {
  throw "The F09 TCP port is unreachable at $DeviceIp`:$DevicePort. Join the gym network and check the F09 IP/network settings before retrying."
}
Write-Host 'F09 TCP network check passed.' -ForegroundColor Green

Test-ZkDriver -Context $context -Install:$InstallZkDriver

Invoke-ChildPowerShell -Arguments @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $startScript, '-ConfigPath', $ConfigPath)
if (-not (Test-GravityHealth -Context $context -TimeoutSec 5)) { throw 'Gravity started but its local health check is not green.' }
Write-Host 'Admin backend is healthy.' -ForegroundColor Green

if ($StartNgrok) {
  if (-not (Test-Path -LiteralPath $ngrokScript -PathType Leaf)) { throw 'start-ngrok.ps1 is missing.' }
  $ngrokArgs = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $ngrokScript, '-ConfigPath', $ConfigPath, '-UpdateConfig')
  if ($NgrokConfigPath) { $ngrokArgs += @('-NgrokConfigPath', $NgrokConfigPath) }
  if ($NgrokExecutablePath) { $ngrokArgs += @('-NgrokExecutablePath', $NgrokExecutablePath) }
  if ($NgrokDomain) { $ngrokArgs += @('-Domain', $NgrokDomain) }
  Invoke-ChildPowerShell -Arguments $ngrokArgs
}

$portalBaseUrl = Get-PortalBaseUrl -Context $context -UseNgrok:$StartNgrok
try {
  $health = Invoke-RestMethod -Uri "$portalBaseUrl/api/health" -Headers @{ 'ngrok-skip-browser-warning' = 'true' } -TimeoutSec 15 -ErrorAction Stop
} catch {
  throw "The admin portal public health check failed at $portalBaseUrl/api/health. $($_.Exception.Message)"
}
if ($health.status -ne 'ok' -or $health.service -ne 'Gravity Fitness') { throw 'The admin portal did not return the expected health contract.' }

if (-not $AdminUsername) { $AdminUsername = Read-Host 'Owner or administrator username' }
if (-not $AdminUsername.Trim()) { throw 'An owner or administrator username is required.' }
$passwordSecure = Read-Host 'Admin password' -AsSecureString
$password = ConvertTo-PlainText -Value $passwordSecure
$passwordSecure = $null
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
try {
  $login = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path '/api/admin/login' -Method 'POST' -Session $session -Body @{ username=$AdminUsername.Trim(); password=$password }
} finally {
  $password = $null
}
if (-not $login.authenticated) {
  if (-not $login.secondFactorRequired) { throw 'The admin login did not return an authenticated session.' }
  $factor = Read-Host 'Six-digit authenticator code or an unused recovery code'
  if (-not $factor.Trim()) { throw 'A second-factor code is required.' }
  try {
    $login = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path '/api/admin/verify' -Method 'POST' -Session $session -Body @{ code=$factor.Trim() }
  } finally {
    $factor = $null
  }
}
if (-not $login.authenticated -or -not $login.csrfToken) { throw 'Admin authentication did not complete.' }
$permissions = @($login.admin.permissions)
if ($permissions -notcontains '*' -and $permissions -notcontains 'biometric.manage') {
  throw "The $($login.admin.role) account cannot manage biometric devices. Sign in as an owner or administrator."
}
$csrf = [string]$login.csrfToken

$devicesResponse = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path '/api/admin/biometric/devices' -Method 'GET' -Session $session
$devices = @($devicesResponse.devices)
$matches = @($devices | Where-Object { $_.vendor -eq 'zkteco' -and $_.deviceIdentifier -eq $DeviceIdentifier })
if ($matches.Count -gt 1) { throw "More than one ZKTeco device uses Device ID $DeviceIdentifier. Resolve that duplicate in the portal before using this script." }
$existing = $matches | Select-Object -First 1

$commKeySecure = Read-Host 'F09 numeric Comm Key (never shown or saved in command history; press Enter only to retain an existing key)' -AsSecureString
$commKey = ConvertTo-PlainText -Value $commKeySecure
$commKeySecure = $null
if ($commKey -and $commKey -notmatch '^\d+$') { throw 'The F09 Comm Key must be numeric for the installed ZKTeco driver.' }
if (-not $existing -and -not $commKey) { throw 'A new F09 device requires the real Comm Key. Obtain it from the device administrator; do not guess it.' }
if ($existing -and -not $existing.commKeyConfigured -and -not $commKey) { throw 'This F09 has no stored Comm Key. Enter the real key; do not guess it.' }

$deviceBody = @{
  name = $DeviceName
  model = 'F09'
  deviceIdentifier = $DeviceIdentifier
  host = $DeviceIp
  port = $DevicePort
  connectionMode = 'tcp'
  enabled = $true
  timezone = $Timezone
  duplicateWindowSeconds = $DuplicateWindowSeconds
  visitGapSeconds = $VisitGapSeconds
}
if ($commKey) { $deviceBody.commKey = $commKey }
try {
  if ($existing) {
    $saved = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path "/api/admin/biometric/devices/$($existing.id)" -Method 'PATCH' -Session $session -Body $deviceBody -CsrfToken $csrf
  } else {
    $saved = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path '/api/admin/biometric/devices' -Method 'POST' -Session $session -Body $deviceBody -CsrfToken $csrf
  }
} finally {
  $commKey = $null
}
$device = $saved.device
Write-Host "F09 device record $($device.id) saved." -ForegroundColor Green

$tested = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path "/api/admin/biometric/devices/$($device.id)/test" -Method 'POST' -Session $session -CsrfToken $csrf
if ($tested.status -ne 'online') { throw "The F09 TCP test did not pass (status: $($tested.status))." }
Write-Host 'F09 TCP test passed.' -ForegroundColor Green

$sync = $null
if (-not $SkipSync) {
  try {
    $sync = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path "/api/admin/biometric/devices/$($device.id)/sync" -Method 'POST' -Session $session -CsrfToken $csrf
  } catch {
    throw "F09 synchronization failed. Verify the numeric Comm Key and device compatibility before retrying. $($_.Exception.Message)"
  }
  Write-Host "F09 sync passed: $($sync.usersSynced) user IDs, $($sync.stored) new attendance events, $($sync.unmatched) unmatched events." -ForegroundColor Green
}

$unmatchedResponse = Invoke-GravityApi -BaseUrl $portalBaseUrl -Path "/api/admin/biometric/unmatched?deviceId=$($device.id)" -Method 'GET' -Session $session
$unmatched = @($unmatchedResponse.unmatched)
Write-GravityOpsLog -Context $context -Message "biometric_onsite_setup_complete deviceId=$($device.id) deviceIdentifier=$DeviceIdentifier host=$DeviceIp port=$DevicePort sync=$([bool]$sync)"

Write-Host ''
Write-Host 'ON-SITE SETUP COMPLETE' -ForegroundColor Green
Write-Host "Admin portal: $portalBaseUrl/admin"
Write-Host "Unmatched fingerprint IDs awaiting human mapping: $($unmatched.Count)"
Write-Host (Get-TaskSummary)
Write-Host 'Next: open More tools > Biometric Devices, map each verified F09 user ID to the correct member or staff record, then perform one member and one staff live-scan check.' -ForegroundColor Yellow
