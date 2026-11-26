# Auto-start: run the JARVIS server by itself every time you log in to Windows.
# (Replaces the old 8am "JARVIS morning" task - the morning briefing is now a daily reminder.)
#
#   powershell -ExecutionPolicy Bypass -File setup_autostart.ps1
#
# Start it now:  Start-ScheduledTask -TaskName "JARVIS server"
# Stop it:       Stop-ScheduledTask  -TaskName "JARVIS server"
# Remove it:     Unregister-ScheduledTask -TaskName "JARVIS server" -Confirm:$false
# What happened: open logs\server.log

$folder = $PSScriptRoot
$python = Join-Path $folder ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force (Join-Path $folder "logs") | Out-Null

# conhost --headless = no black window. cmd /c lets us save everything JARVIS prints to logs\server.log.
# python.exe (not pythonw.exe) because the Windows Firewall rule for the speaker is for python.exe.
$command = "set PYTHONIOENCODING=utf-8&& `"$python`" -u server.py >> logs\server.log 2>&1"
$action   = New-ScheduledTaskAction -Execute "conhost.exe" -Argument "--headless cmd.exe /c `"$command`"" -WorkingDirectory $folder
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "JARVIS server" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Starts the JARVIS assistant server (dashboard: http://127.0.0.1:8000)" -Force | Out-Null

# Retire the old step-2 task, if it's still there.
if (Get-ScheduledTask -TaskName "JARVIS morning" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "JARVIS morning" -Confirm:$false
    Write-Host "Removed the old 'JARVIS morning' task (the 8am briefing is now a reminder)."
}

Write-Host "Done! JARVIS will start by himself when you log in. Dashboard: http://127.0.0.1:8000"
