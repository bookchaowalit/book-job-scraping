# Windows Task Scheduler equivalent of setup_cron.sh.
#
# Usage (PowerShell, no admin needed — runs as the current user):
#   .\ops\windows\scheduled-task.ps1 install   # every 5 minutes while logged on
#   .\ops\windows\scheduled-task.ps1 status
#   .\ops\windows\scheduled-task.ps1 remove
#
# Each tick runs scripts/scheduled_run.py, which holds a non-blocking lock so
# ticks never overlap, then logs to data/logs/cron.log.
param([Parameter(Mandatory)][ValidateSet('install', 'remove', 'status')][string]$Action)

$ErrorActionPreference = 'Stop'
$TaskName = 'book-job-scraping-scheduler'
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $ProjectDir '.venv\Scripts\pythonw.exe'
$Runner = Join-Path $ProjectDir 'scripts\scheduled_run.py'

switch ($Action) {
    'install' {
        if (-not (Test-Path $Python)) { throw "Missing $Python — create .venv and install requirements.txt first." }
        $taskAction = New-ScheduledTaskAction -Execute $Python -Argument "`"$Runner`"" -WorkingDirectory $ProjectDir
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes 5)
        # Priority 4 = normal. The default (7) also drops I/O priority, which
        # stalled Python imports for minutes on a busy host.
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Priority 4 `
            -ExecutionTimeLimit (New-TimeSpan -Hours 1)
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings `
            -Description 'book-job-scraping: run due jobs + pipeline health monitor' -Force | Out-Null
        Write-Host "Installed $TaskName (every 5 minutes). Log: $ProjectDir\data\logs\cron.log"
    }
    'remove' {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Removed $TaskName"
    }
    'status' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $task) { Write-Host 'Status: NOT INSTALLED'; break }
        $info = $task | Get-ScheduledTaskInfo
        Write-Host "Status: $($task.State)  LastRun: $($info.LastRunTime)  LastResult: $($info.LastTaskResult)  NextRun: $($info.NextRunTime)"
    }
}
