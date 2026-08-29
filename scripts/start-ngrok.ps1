param(
  [string]$ConfigPath,
  [string]$Domain,
  [string]$NgrokConfigPath,
  [string]$NgrokExecutablePath,
  [switch]$UpdateConfig
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$pidFile = Join-Path $context.RuntimeDir 'ngrok.pid'
$stateFile = Join-Path $context.RuntimeDir 'ngrok.state.json'
$urlFile = Join-Path $context.RuntimeDir 'ngrok.public-url'
$stdoutLog = Join-Path $context.RuntimeDir 'ngrok.stdout.log'
$stderrLog = Join-Path $context.RuntimeDir 'ngrok.stderr.log'
$ngrokConfig = if ($NgrokConfigPath) {
  if (-not (Test-Path -LiteralPath $NgrokConfigPath -PathType Leaf)) {
    throw "ngrok configuration was not found: $NgrokConfigPath"
  }
  (Resolve-Path -LiteralPath $NgrokConfigPath).Path
} else {
  Join-Path $env:LOCALAPPDATA 'ngrok\ngrok.yml'
}

function Resolve-Ngrok([string]$ExplicitPath) {
  if ($ExplicitPath) {
    if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
      throw "ngrok executable was not found: $ExplicitPath"
    }
    return (Resolve-Path -LiteralPath $ExplicitPath).Path
  }
  $command = Get-Command ngrok -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $root = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
  if (Test-Path -LiteralPath $root) {
    $item = Get-ChildItem -LiteralPath $root -Recurse -Filter ngrok.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match 'Ngrok\.Ngrok' } | Select-Object -First 1
    if ($item) { return $item.FullName }
  }
  throw 'ngrok is not installed. Install with: winget install --id Ngrok.Ngrok'
}

function Test-ManagedNgrok([int]$ProcessId) {
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process -or -not (Test-Path -LiteralPath $stateFile -PathType Leaf)) { return $false }
  try {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    if ([int]$state.pid -ne $ProcessId -or [int]$state.formatVersion -ne 1) { return $false }
    if ([string]$state.target -ne "http://127.0.0.1:$($context.Port)") { return $false }
    if (-not $state.PSObject.Properties['configPath'] -or -not [string]::Equals([IO.Path]::GetFullPath([string]$state.configPath), $ngrokConfig, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$state.executable), $process.Path, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $delta = ([DateTimeOffset]::Parse([string]$state.startedAt).UtcDateTime - $process.StartTime.ToUniversalTime()).TotalSeconds
    return $delta -ge 0 -and $delta -le 120
  } catch { return $false }
}

function Get-NgrokPublicUrl {
  try {
    $tunnels = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
    $match = @($tunnels.tunnels | Where-Object { $_.public_url -like 'https://*' -and [string]$_.config.addr -eq "http://127.0.0.1:$($context.Port)" }) | Select-Object -First 1
    if ($match) { return $match.public_url.TrimEnd('/') }
  } catch { }
  return $null
}

if (-not (Test-Path -LiteralPath $ngrokConfig -PathType Leaf)) {
  throw "ngrok authentication is not configured. Expected $ngrokConfig"
}
if ((Get-Content -LiteralPath $ngrokConfig -Raw) -notmatch '(?m)^\s*authtoken\s*:') {
  throw 'ngrok authtoken is missing from the private ngrok config.'
}
if (-not (Test-GravityHealth -Context $context)) {
  & (Join-Path $PSScriptRoot 'start-gravity.ps1') -ConfigPath $ConfigPath
}

New-Item -ItemType Directory -Force -Path $context.RuntimeDir | Out-Null
$process = $null
if (Test-Path -LiteralPath $pidFile) {
  $savedPid = [int](Get-Content -LiteralPath $pidFile -Raw)
  if (Test-ManagedNgrok $savedPid) {
    $process = Get-Process -Id $savedPid
  } elseif (Get-Process -Id $savedPid -ErrorAction SilentlyContinue) {
    throw "Refusing to replace live PID $savedPid because it is not the managed loopback ngrok process."
  } else {
    Remove-Item -LiteralPath $pidFile, $stateFile, $urlFile -Force -ErrorAction SilentlyContinue
  }
}

if (-not $process) {
  $unmanagedPublicUrl = Get-NgrokPublicUrl
  if ($unmanagedPublicUrl) {
    throw "Refusing to start a second ngrok process because an unmanaged tunnel already targets http://127.0.0.1:$($context.Port). Stop or adopt the existing tunnel first."
  }
  $ngrokExe = Resolve-Ngrok -ExplicitPath $NgrokExecutablePath
  Rotate-GravityLog -Path $stdoutLog
  Rotate-GravityLog -Path $stderrLog
  $arguments = @('http', "http://127.0.0.1:$($context.Port)", '--log=stdout', '--log-format=json', '--config', $ngrokConfig)
  if ($Domain) { $arguments += "--domain=$Domain" }
  $process = Start-Process -FilePath $ngrokExe -ArgumentList $arguments `
    -WorkingDirectory $context.ProjectRoot -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
  Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
  [ordered]@{
    formatVersion = 1
    pid = $process.Id
    executable = [IO.Path]::GetFullPath($ngrokExe)
    configPath = $ngrokConfig
    target = "http://127.0.0.1:$($context.Port)"
    startedAt = $process.StartTime.ToUniversalTime().ToString('o')
  } | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
}

$publicUrl = $null
for ($attempt = 0; $attempt -lt 60; $attempt++) {
  if (-not (Test-ManagedNgrok $process.Id)) {
    Remove-Item -LiteralPath $pidFile, $stateFile, $urlFile -Force -ErrorAction SilentlyContinue
    throw "ngrok exited during startup. Check $stderrLog"
  }
  $publicUrl = Get-NgrokPublicUrl
  if ($publicUrl) { break }
  Start-Sleep -Milliseconds 500
}
if (-not $publicUrl) { throw 'ngrok did not publish an HTTPS tunnel within 30 seconds.' }
Set-Content -LiteralPath $urlFile -Value $publicUrl -Encoding ascii

if ($UpdateConfig -and ($env:APP_BASE_URL -ne $publicUrl -or $env:GRAVITY_ENV -ne 'production' -or $env:GRAVITY_TRUST_PROXY -ne 'true' -or $env:GRAVITY_TRUSTED_PROXY_CIDRS -ne '127.0.0.1/32')) {
  if (-not $context.ConfigPath) { throw '-UpdateConfig requires an explicit config file.' }
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'GRAVITY_ENV' -Value 'production'
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'APP_BASE_URL' -Value $publicUrl
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'GRAVITY_TRUST_PROXY' -Value 'true'
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'GRAVITY_TRUSTED_PROXY_CIDRS' -Value '127.0.0.1/32'
  & (Join-Path $PSScriptRoot 'restart-gravity.ps1') -ConfigPath $context.ConfigPath
} elseif (-not $UpdateConfig -and $env:APP_BASE_URL -ne $publicUrl) {
  throw "Tunnel is online at $publicUrl but APP_BASE_URL does not match. Re-run with -UpdateConfig or configure a reserved ngrok domain."
}

$publicHealth = Invoke-RestMethod -Uri "$publicUrl/api/health" -Headers @{ 'ngrok-skip-browser-warning' = 'true' } -TimeoutSec 10
if ($publicHealth.status -ne 'ok' -or $publicHealth.service -ne 'Gravity Fitness') {
  throw 'Public ngrok health check did not return the Gravity contract.'
}
Write-GravityOpsLog -Context $context -Message "ngrok_healthy pid=$($process.Id) publicUrl=$publicUrl"
Write-Host "ngrok HTTPS tunnel is healthy (PID $($process.Id))." -ForegroundColor Green
Write-Host "Public URL: $publicUrl"
