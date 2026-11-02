$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $pwsh) {
    $pwsh = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
}
$action = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSScriptRoot\start.ps1`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT2M"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "AutoClipper" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Auto-clip video baru saat login" -Force | Out-Null
Write-Output "Task AutoClipper terpasang. Jalankan manual: schtasks /run /tn AutoClipper"
