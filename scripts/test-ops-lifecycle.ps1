param([string]$PythonPath)

$ErrorActionPreference = 'Stop'
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $PythonPath) { $PythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempBase ('gravity-ops-lifecycle-' + [guid]::NewGuid().ToString('N'))
$runtime = Join-Path $testRoot 'runtime'
$config = Join-Path $testRoot 'gravity.env'
$completed = $false

New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$lines = @(
  'GRAVITY_ENV=development',
  'GRAVITY_HOST=127.0.0.1',
  "GRAVITY_PORT=$port",
  "APP_BASE_URL=http://127.0.0.1:$port",
  "GRAVITY_RUNTIME_DIR=$runtime",
  ('GRAVITY_DATA_DIR=' + (Join-Path $testRoot 'data')),
  ('GRAVITY_LOG_DIR=' + (Join-Path $runtime 'logs')),
  ('GRAVITY_BACKUP_DIR=' + (Join-Path $testRoot 'backups')),
  "GRAVITY_PYTHON=$PythonPath",
  ('SECRET_KEY=' + ('x' * 40))
)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines($config, $lines, $utf8NoBom)

try {
  & (Join-Path $PSScriptRoot 'start-gravity.ps1') -ConfigPath $config
  & (Join-Path $PSScriptRoot 'status-gravity.ps1') -ConfigPath $config -Json
  & (Join-Path $PSScriptRoot 'watch-gravity.ps1') -ConfigPath $config
  & (Join-Path $PSScriptRoot 'backup-gravity.ps1') -ConfigPath $config -Label lifecycle-test
  $migrationDirectory = Join-Path $testRoot 'migration'
  & (Join-Path $PSScriptRoot 'export-gravity-migration.ps1') -ConfigPath $config -OutputDirectory $migrationDirectory
  if (-not (Test-Path -LiteralPath (Join-Path $migrationDirectory 'gravity-migration.json'))) {
    throw 'Migration export did not create its manifest.'
  }

  $crashedId = [int](Get-Content -LiteralPath (Join-Path $runtime 'gravity.pid') -Raw)
  Stop-Process -Id $crashedId -Force
  Start-Sleep -Seconds 2
  & (Join-Path $PSScriptRoot 'watch-gravity.ps1') -ConfigPath $config
  $recoveredId = [int](Get-Content -LiteralPath (Join-Path $runtime 'gravity.pid') -Raw)
  if ($recoveredId -eq $crashedId) { throw 'Watchdog did not replace the crashed process.' }
  & (Join-Path $PSScriptRoot 'status-gravity.ps1') -ConfigPath $config -Json
  & (Join-Path $PSScriptRoot 'stop-gravity.ps1') -ConfigPath $config
  $completed = $true
  Write-Host "Windows lifecycle drill passed on temporary port $port." -ForegroundColor Green
} finally {
  if (Test-Path -LiteralPath (Join-Path $runtime 'gravity.pid')) {
    try { & (Join-Path $PSScriptRoot 'stop-gravity.ps1') -ConfigPath $config } catch { }
  }
  $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
  if ($completed -and $resolvedTestRoot.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
  } elseif (-not $completed) {
    Write-Warning "Lifecycle drill artifacts retained for diagnosis: $resolvedTestRoot"
  }
}
