param(
  [Parameter(Mandatory = $true)][string]$OutputDirectory,
  [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$resultText = & (Join-Path $PSScriptRoot 'backup-gravity.ps1') `
  -Label migration `
  -ConfigPath $ConfigPath `
  -OffsiteDirectory $outputRoot
if ($LASTEXITCODE -ne 0) { throw 'Migration backup export failed.' }
$result = ($resultText | Out-String).Trim() | ConvertFrom-Json
$archive = [IO.Path]::GetFullPath([string]$result.offsitePath)
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$commit = (& git -C $projectRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not identify the deployed Git commit.' }
$manifest = [ordered]@{
  formatVersion = 1
  createdAt = [DateTimeOffset]::UtcNow.ToString('o')
  sourceCommit = $commit
  backupFile = Split-Path -Leaf $archive
  backupSha256 = $hash
  recoveryDrillPassed = [bool]$result.recoveryDrill.drillPassed
  containsSecrets = $false
}
$manifestPath = Join-Path $outputRoot 'gravity-migration.json'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json) + [Environment]::NewLine, $utf8NoBom)
Write-Host "Migration bundle exported to $outputRoot" -ForegroundColor Green
Write-Host "Backup SHA-256: $hash"
