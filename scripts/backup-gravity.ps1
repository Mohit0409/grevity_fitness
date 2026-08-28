param(
  [ValidatePattern('^[a-z0-9][a-z0-9-]{0,31}$')][string]$Label = 'manual',
  [string]$ConfigPath,
  [string]$OffsiteDirectory,
  [switch]$SkipRecoveryDrill
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'gravity-common.ps1')
$context = Get-GravityContext -ConfigPath $ConfigPath
if (-not (Test-Path -LiteralPath $context.PythonPath -PathType Leaf)) {
  throw 'Gravity Python environment is missing.'
}

function Invoke-GravityJsonOperation([string[]]$Arguments) {
  Push-Location $context.ProjectRoot
  try {
    $output = & $context.PythonPath -m server.gravity @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Gravity operation failed: $($Arguments -join ' ')" }
    return ($output | Out-String).Trim() | ConvertFrom-Json
  } finally {
    Pop-Location
  }
}

$created = Invoke-GravityJsonOperation @('--create-backup', '--backup-label', $Label)
$archive = [IO.Path]::GetFullPath([string]$created.path)
$verified = Invoke-GravityJsonOperation @('--verify-backup', $archive)
if (-not $verified.valid) { throw 'New backup did not pass verification.' }
$drill = $null
if (-not $SkipRecoveryDrill) {
  $drill = Invoke-GravityJsonOperation @('--recovery-drill', $archive)
  if (-not $drill.drillPassed) { throw 'New backup did not pass the recovery drill.' }
}

$offsitePath = $null
if ($OffsiteDirectory) {
  $offsiteRoot = [IO.Path]::GetFullPath($OffsiteDirectory)
  New-Item -ItemType Directory -Force -Path $offsiteRoot | Out-Null
  $offsitePath = Join-Path $offsiteRoot (Split-Path -Leaf $archive)
  if (Test-Path -LiteralPath $offsitePath) { throw "Off-device backup already exists: $offsitePath" }
  Copy-Item -LiteralPath $archive -Destination $offsitePath
  $offsiteVerification = Invoke-GravityJsonOperation @('--verify-backup', $offsitePath)
  if (-not $offsiteVerification.valid) {
    Remove-Item -LiteralPath $offsitePath -Force -ErrorAction SilentlyContinue
    throw 'Copied off-device backup failed verification.'
  }
}

$summary = [ordered]@{
  created = $created
  verified = $verified
  recoveryDrill = $drill
  offsitePath = $offsitePath
}
Write-GravityOpsLog -Context $context -Message "backup_verified path=$archive recoveryDrill=$(-not $SkipRecoveryDrill) offsite=$([bool]$offsitePath)"
$summary | ConvertTo-Json -Depth 8 -Compress
