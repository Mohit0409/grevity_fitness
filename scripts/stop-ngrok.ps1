param(
  [string]$ConfigPath,
  [switch]$ReturnToDevelopment
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$pidFile = Join-Path $context.RuntimeDir 'ngrok.pid'
$stateFile = Join-Path $context.RuntimeDir 'ngrok.state.json'
$urlFile = Join-Path $context.RuntimeDir 'ngrok.public-url'
if (Test-Path -LiteralPath $pidFile) {
  $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($process) {
    if (-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) {
      throw "Refusing to stop PID $processId because it is not the managed loopback ngrok process."
    }
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $delta = ([DateTimeOffset]::Parse([string]$state.startedAt).UtcDateTime - $process.StartTime.ToUniversalTime()).TotalSeconds
    if ([int]$state.pid -ne $processId -or [string]$state.target -ne "http://127.0.0.1:$($context.Port)" -or
        -not [string]::Equals([IO.Path]::GetFullPath([string]$state.executable), $process.Path, [StringComparison]::OrdinalIgnoreCase) -or
        $delta -lt 0 -or $delta -gt 120) {
      throw "Refusing to stop PID $processId because it is not the managed loopback ngrok process."
    }
    Stop-Process -Id $processId
    try { Wait-Process -Id $processId -Timeout 15 -ErrorAction Stop } catch { }
    if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { throw "ngrok PID $processId did not stop." }
  }
}
Remove-Item -LiteralPath $pidFile, $stateFile, $urlFile -Force -ErrorAction SilentlyContinue

if ($ReturnToDevelopment) {
  if (-not $context.ConfigPath) { throw '-ReturnToDevelopment requires an explicit config file.' }
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'GRAVITY_ENV' -Value 'development'
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'APP_BASE_URL' -Value "http://127.0.0.1:$($context.Port)"
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'GRAVITY_TRUST_PROXY' -Value 'false'
  Set-GravityEnvironmentValue -Path $context.ConfigPath -Name 'GRAVITY_TRUSTED_PROXY_CIDRS' -Value ''
  & (Join-Path $PSScriptRoot 'restart-gravity.ps1') -ConfigPath $context.ConfigPath
}
Write-GravityOpsLog -Context $context -Message 'ngrok_stopped'
Write-Host 'ngrok stopped. Gravity remains loopback-only.' -ForegroundColor Green
