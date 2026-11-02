$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "logs\run.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
Set-Location $root
& (Join-Path $root ".venv\Scripts\python.exe") -m autoclip run *>> $log
