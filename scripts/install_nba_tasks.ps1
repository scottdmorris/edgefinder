# Registers the NBA prop jobs with Windows Task Scheduler. Re-running it
# replaces the existing tasks. Remove them with:
#   Unregister-ScheduledTask -TaskName 'EdgeFinderNba*' -Confirm:$false
#
# - EdgeFinderNbaSnapshot: every 30 minutes, 12:00-22:30. Most runs do
#   nothing and spend nothing; the policy in nba_snapshot_plan decides
#   when a game is due, and a reserve stops it before the quota runs dry.
# - EdgeFinderNbaSettle: 9:00 each morning, grades the night before.
#
# Triggers use this PC's local time, and the NBA schedule assumes Eastern.
# Jobs run windowless (pythonw) and log to data\nba_jobs.log. They only run
# while you are logged in. A run due while the PC sleeps wakes it (WakeToRun), and one
# missed anyway is started when it next wakes.

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) { throw "Expected $python. Create the virtualenv first." }
if ((Get-TimeZone).Id -notlike 'Eastern*') {
    Write-Warning "This PC is not on Eastern time, so the schedule below will be off."
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$logArg = '--log-file data\nba_jobs.log'

# Snapshot: a daily trigger that repeats every 30 minutes for 10.5 hours.
$snapshotTrigger = New-ScheduledTaskTrigger -Daily -At 12:00PM
$snapshotTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At 12:00PM `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 10 -Minutes 30)).Repetition
Register-ScheduledTask -TaskName 'EdgeFinderNbaSnapshot' -Force `
    -Description 'Archive FanDuel NBA player-point lines and log model picks (paper only).' `
    -Action (New-ScheduledTaskAction -Execute $python -WorkingDirectory $repo `
        -Argument "scripts\nba_props_snapshot.py $logArg") `
    -Trigger $snapshotTrigger -Settings $settings | Out-Null

Register-ScheduledTask -TaskName 'EdgeFinderNbaSettle' -Force `
    -Description 'Settle last night''s NBA paper picks and report calibration vs the market.' `
    -Action (New-ScheduledTaskAction -Execute $python -WorkingDirectory $repo `
        -Argument "scripts\nba_props_settle.py $logArg") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 9:00AM) -Settings $settings | Out-Null

Get-ScheduledTask -TaskName 'EdgeFinderNba*' |
    Select-Object TaskName, State, @{n = 'NextRun'; e = { (Get-ScheduledTaskInfo $_).NextRunTime } } |
    Format-Table -AutoSize
