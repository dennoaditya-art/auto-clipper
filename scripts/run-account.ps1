param(
    [Parameter(Mandatory = $true)][string]$Account,
    [int]$Limit = 0
)
$ErrorActionPreference = "Stop"
$root = "D:\clipper"
$py = Join-Path $root ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$log = Join-Path $root "logs\run-$Account.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
Add-Content -Path $log -Value "=== run account=$Account $stamp ==="
$args = @("-m", "autoclip.cli", "--root", $root, "run", "--account", $Account)
if ($Limit -gt 0) { $args += @("--limit", "$Limit") }
& $py @args *>> $log
exit $LASTEXITCODE
