# Starts VoiceOS using the project's virtual environment (no need to activate it first).
# Run from anywhere:  D:\project\VoiceOS\scripts\start_voiceos.ps1
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& (Join-Path $root ".venv\Scripts\python.exe") main.py @args
