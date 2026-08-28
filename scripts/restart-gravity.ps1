param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop-gravity.ps1') -ConfigPath $ConfigPath
& (Join-Path $PSScriptRoot 'start-gravity.ps1') -ConfigPath $ConfigPath
