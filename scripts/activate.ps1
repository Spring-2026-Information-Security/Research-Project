# Dot-source this file to activate the venv in the current PowerShell session:
# Usage: . .\scripts\activate.ps1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$activate = Join-Path $scriptDir "..\.venv\Scripts\Activate.ps1"
. (Resolve-Path $activate)
Write-Host "Activated .venv"