# Creates the VoiceOS virtual environment and installs dependencies.
# Run from the project folder in PowerShell:
#     .\scripts\setup_environment.ps1
# Safe to run again: it reuses an existing .venv.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment in .venv ..."
    py -3 -m venv .venv
}

$py = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "Upgrading pip ..."
& $py -m pip install --upgrade pip
Write-Host "Installing dependencies ..."
& $py -m pip install -r requirements-dev.txt
Write-Host ""
& $py scripts\check_environment.py
