Set-StrictMode -Version Latest

function Import-GravityEnvironment {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Gravity environment file does not exist: $Path"
  }
  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
    $name, $value = $line.Split('=', 2)
    $name = $name.Trim()
    if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
      throw "Invalid environment variable name in ${Path}: $name"
    }
    $value = $value.Trim()
    if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}

function Get-GravityContext {
  param([string]$ConfigPath)
  $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
  $configWasExplicit = [bool]$ConfigPath -or [bool]$env:GRAVITY_ENV_FILE
  if (-not $ConfigPath) {
    $ConfigPath = if ($env:GRAVITY_ENV_FILE) { $env:GRAVITY_ENV_FILE } else { Join-Path $projectRoot '.env' }
  }
  if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    $ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
    Import-GravityEnvironment -Path $ConfigPath
    $env:GRAVITY_ENV_FILE = $ConfigPath
  } elseif ($configWasExplicit) {
    throw "Gravity environment file does not exist: $ConfigPath"
  }

  $hostAddress = if ($env:GRAVITY_HOST) { $env:GRAVITY_HOST.Trim() } else { '127.0.0.1' }
  if ($hostAddress -ne '127.0.0.1') {
    throw "Refusing unsafe GRAVITY_HOST '$hostAddress'. Managed deployment requires 127.0.0.1."
  }
  $port = if ($env:GRAVITY_PORT) { [int]$env:GRAVITY_PORT } else { 8787 }
  if ($port -lt 1 -or $port -gt 65535) { throw 'GRAVITY_PORT must be between 1 and 65535.' }

  $runtimeDir = if ($env:GRAVITY_RUNTIME_DIR) { $env:GRAVITY_RUNTIME_DIR } else { Join-Path $projectRoot '.gravity' }
  if (-not [IO.Path]::IsPathRooted($runtimeDir)) { $runtimeDir = Join-Path $projectRoot $runtimeDir }
  $runtimeDir = [IO.Path]::GetFullPath($runtimeDir)
  $pythonPath = if ($env:GRAVITY_PYTHON) { $env:GRAVITY_PYTHON } else { Join-Path $projectRoot '.venv\Scripts\python.exe' }
  if (-not [IO.Path]::IsPathRooted($pythonPath)) { $pythonPath = Join-Path $projectRoot $pythonPath }
  $pythonPath = [IO.Path]::GetFullPath($pythonPath)

  [pscustomobject]@{
    ProjectRoot = $projectRoot
    RuntimeDir = $runtimeDir
    PidFile = Join-Path $runtimeDir 'gravity.pid'
    StateFile = Join-Path $runtimeDir 'gravity.state.json'
    PythonPath = $pythonPath
    Port = $port
    HealthUrl = "http://127.0.0.1:$port/api/health"
    ConfigPath = $ConfigPath
  }
}

function Get-GravityPid {
  param([Parameter(Mandatory = $true)]$Context)
  if (-not (Test-Path -LiteralPath $Context.PidFile -PathType Leaf)) { return $null }
  $value = (Get-Content -LiteralPath $Context.PidFile -Raw).Trim()
  if ($value -notmatch '^\d+$' -or [int64]$value -gt [int]::MaxValue) { return $null }
  [int]$value
}

function Test-GravityManagedProcess {
  param(
    [Parameter(Mandatory = $true)]$Context,
    [Parameter(Mandatory = $true)][int]$ProcessId
  )
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process -or -not (Test-Path -LiteralPath $Context.StateFile -PathType Leaf)) { return $false }
  try {
    $state = Get-Content -LiteralPath $Context.StateFile -Raw | ConvertFrom-Json
    if ([int]$state.pid -ne $ProcessId) { return $false }
    if ([int]$state.formatVersion -ne 1 -or [string]$state.module -ne 'server.gravity') { return $false }
    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$state.projectRoot), $Context.ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $expectedPython = (Resolve-Path -LiteralPath $Context.PythonPath).Path
    if ([IO.Path]::GetFileName($process.Path) -notin @('python.exe', 'pythonw.exe')) { return $false }
    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$state.executable), $expectedPython, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $stateStart = [DateTimeOffset]::Parse([string]$state.startedAt).UtcDateTime
    $processStart = $process.StartTime.ToUniversalTime()
    $startDelta = ($stateStart - $processStart).TotalSeconds
    return $startDelta -ge 0 -and $startDelta -le 120
  } catch {
    return $false
  }
}

function Remove-GravityStaleState {
  param([Parameter(Mandatory = $true)]$Context)
  Remove-Item -LiteralPath $Context.PidFile -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $Context.StateFile -Force -ErrorAction SilentlyContinue
}

function Test-GravityHealth {
  param([Parameter(Mandatory = $true)]$Context, [int]$TimeoutSec = 3)
  try {
    $health = Invoke-RestMethod -Uri $Context.HealthUrl -TimeoutSec $TimeoutSec
    return $health.service -eq 'Gravity Fitness' -and $health.status -eq 'ok' -and $health.database -eq 'ok'
  } catch {
    return $false
  }
}

function Rotate-GravityLog {
  param([Parameter(Mandatory = $true)][string]$Path, [int64]$MaximumBytes = 10485760)
  if ((Test-Path -LiteralPath $Path -PathType Leaf) -and (Get-Item -LiteralPath $Path).Length -ge $MaximumBytes) {
    $archive = "$Path.1"
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $Path -Destination $archive
  }
}

function Write-GravityOpsLog {
  param([Parameter(Mandatory = $true)]$Context, [Parameter(Mandatory = $true)][string]$Message)
  New-Item -ItemType Directory -Force -Path $Context.RuntimeDir | Out-Null
  $path = Join-Path $Context.RuntimeDir 'operations.log'
  Rotate-GravityLog -Path $path
  Add-Content -LiteralPath $path -Value "$([DateTimeOffset]::UtcNow.ToString('o')) $Message" -Encoding utf8
}

function Set-GravityEnvironmentValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Name,
    [AllowEmptyString()][Parameter(Mandatory = $true)][string]$Value
  )
  $lines = if (Test-Path -LiteralPath $Path) { @(Get-Content -LiteralPath $Path) } else { @() }
  $pattern = '^\s*' + [regex]::Escape($Name) + '\s*='
  $found = $false
  $updated = foreach ($line in $lines) {
    if ($line -match $pattern) { $found = $true; "$Name=$Value" } else { $line }
  }
  if (-not $found) { $updated += "$Name=$Value" }
  $directory = Split-Path -Parent $Path
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  $temporary = "$Path.tmp"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllLines($temporary, [string[]]$updated, $utf8NoBom)
  Move-Item -LiteralPath $temporary -Destination $Path -Force
}
