param(
  [Parameter(Mandatory = $true)][string]$ConfigPath,
  [Parameter(Mandatory = $true)][string]$NgrokConfigPath,
  [Parameter(Mandatory = $true)][string]$NgrokExecutablePath,
  [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$ProcessId,
  [string]$NgrokApiUrl = 'http://127.0.0.1:4040/api/tunnels',
  [string]$PythonPath,
  [switch]$ConfirmAdopt
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
$helper = Join-Path $PSScriptRoot 'ngrok-adoption.py'
if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
  throw 'ngrok adoption helper is missing.'
}
$python = if ($PythonPath) { [IO.Path]::GetFullPath($PythonPath) } else { $context.PythonPath }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw 'Gravity Python environment is missing; pass -PythonPath for an immutable checkout without its own virtualenv.'
}
$NgrokConfigPath = (Resolve-Path -LiteralPath $NgrokConfigPath).Path
$NgrokExecutablePath = (Resolve-Path -LiteralPath $NgrokExecutablePath).Path
$expectedTarget = "http://127.0.0.1:$($context.Port)"
if (-not (Test-GravityHealth -Context $context)) {
  throw 'Gravity loopback health must be green before adopting ngrok.'
}

$process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
$runtimeProcess = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
$processExists = $null -ne $process -and $null -ne $runtimeProcess
$tunnelResponse = Invoke-RestMethod -Uri $NgrokApiUrl -TimeoutSec 3
$tunnels = @($tunnelResponse.tunnels)

$evidence = [ordered]@{
  pid = $ProcessId
  processExists = $processExists
  processName = if ($process) { [string]$process.Name } else { '' }
  processExecutable = if ($process) { [string]$process.ExecutablePath } else { '' }
  commandLine = if ($process) { [string]$process.CommandLine } else { '' }
  processStartedAt = if ($runtimeProcess) { $runtimeProcess.StartTime.ToUniversalTime().ToString('o') } else { '' }
  processCreationTime = if ($process -and $process.CreationDate) { $process.CreationDate.ToUniversalTime().ToString('o') } else { '' }
  expectedExecutable = $NgrokExecutablePath
  expectedConfig = $NgrokConfigPath
  target = $expectedTarget
  tunnels = $tunnels
}
$temporaryEvidence = Join-Path ([IO.Path]::GetTempPath()) ("gravity-ngrok-evidence-{0}.json" -f [guid]::NewGuid().ToString('N'))
$evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporaryEvidence -Encoding utf8

try {
  $probeOutput = & $python $helper --evidence-json $temporaryEvidence --runtime-dir $context.RuntimeDir --probe-only
  $probeCode = $LASTEXITCODE
  $probeText = ($probeOutput | Out-String).Trim()
  try { $probe = $probeText | ConvertFrom-Json -ErrorAction Stop } catch { throw 'ngrok adoption helper returned an invalid preflight report.' }
  if ($null -eq $probe) { throw 'ngrok adoption helper returned an empty preflight report.' }
  if ($probeCode -ne 0 -or -not $probe.ready) {
    $reason = if ($probe.PSObject.Properties['error']) { [string]$probe.error } else { 'validation failed' }
    throw "ngrok adoption preflight failed: $reason"
  }

  $publicHealth = Invoke-RestMethod -Uri "$($probe.publicUrl)/api/health" `
    -Headers @{ 'ngrok-skip-browser-warning' = 'true' } -TimeoutSec 10
  if ($publicHealth.status -ne 'ok' -or $publicHealth.service -ne 'Gravity Fitness') {
    throw 'Existing ngrok tunnel did not return the Gravity public health contract.'
  }

  if (-not $ConfirmAdopt) {
    $probe | ConvertTo-Json -Depth 6 -Compress
    Write-Host 'Probe only: managed ngrok state was not changed. Re-run with -ConfirmAdopt during the controlled release operation.'
    exit 0
  }

  $adoptOutput = & $python $helper --evidence-json $temporaryEvidence --runtime-dir $context.RuntimeDir
  $adoptCode = $LASTEXITCODE
  $adoptText = ($adoptOutput | Out-String).Trim()
  try { $adopt = $adoptText | ConvertFrom-Json -ErrorAction Stop } catch { throw 'ngrok adoption helper returned an invalid adoption report.' }
  if ($null -eq $adopt) { throw 'ngrok adoption helper returned an empty adoption report.' }
  if ($adoptCode -ne 0 -or -not $adopt.ready) {
    $reason = if ($adopt.PSObject.Properties['error']) { [string]$adopt.error } else { 'validation failed' }
    throw "ngrok adoption failed: $reason"
  }

  Write-GravityOpsLog -Context $context -Message "ngrok_adopted pid=$($adopt.pid) publicUrl=$($adopt.publicUrl)"
  $adopt | ConvertTo-Json -Depth 6 -Compress
  Write-Host "Existing ngrok tunnel is now managed (PID $($adopt.pid))." -ForegroundColor Green
} finally {
  Remove-Item -LiteralPath $temporaryEvidence -Force -ErrorAction SilentlyContinue
}
