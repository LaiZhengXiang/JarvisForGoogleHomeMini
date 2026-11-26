# Step 2 - Timer.
# Creates a Windows Task Scheduler task that runs morning.py every day at 8am.
# Run it again any time to update the task; it replaces the old one.
#
#   powershell -ExecutionPolicy Bypass -File setup_timer.ps1
#   powershell -ExecutionPolicy Bypass -File setup_timer.ps1 -Time 7:30am
#
# Remove it:   Unregister-ScheduledTask -TaskName "JARVIS morning" -Confirm:$false
# Test it now: Start-ScheduledTask -TaskName "JARVIS morning"

param([string]$Time = "8:00am")

$folder = $PSScriptRoot
$python = Join-Path $folder ".venv\Scripts\python.exe"
# We use python.exe (not pythonw.exe) because the Windows Firewall rule that lets
# the speaker's replies in is for python.exe. "conhost --headless" hides its black window.

$action   = New-ScheduledTaskAction -Execute "conhost.exe" `
    -Argument "--headless `"$python`" morning.py" -WorkingDirectory $folder
$trigger  = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "JARVIS morning" -Action $action -Trigger $trigger `
    -Settings $settings -Description "JARVIS says good morning on the Google Home Mini" -Force | Out-Null

Write-Host "Done! JARVIS will speak every day at $Time."
