param(
    [string]$AtLogon = "true"
)
$ErrorActionPreference = "Stop"
$root = "D:\clipper"
$script = Join-Path $root "scripts\run-account.ps1"
$pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $pwsh) {
    $pwsh = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
}
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)

foreach ($account in @("utama", "kedua")) {
    $taskName = "AutoClipper-$account"
    $action = New-ScheduledTaskAction -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Account $account" `
        -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $trigger.Delay = "PT2M"
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "Auto-clip channel $account" -Force | Out-Null
    Write-Output "Task $taskName terpasang."
}
Write-Output "Jalankan manual: schtasks /run /tn AutoClipper-utama ; schtasks /run /tn AutoClipper-kedua"
