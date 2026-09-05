<#
.SYNOPSIS
    Install the AK820 Pro host agents as per-user Scheduled Tasks.

.DESCRIPTION
    The Windows counterpart of install-agents.sh (which installs macOS
    LaunchAgents). Two tasks, both running as the logged-in user:

      timekeeper   syncs the board clock; every ~5 min, on wake, and whenever
                   the board re-enumerates. Logs to
                   %LOCALAPPDATA%\ak820pro\ak820pro-timekeeper.log
      nowplaying   pushes the current track to the LCD, read from SMTC
                   (Windows' own media-session API). Logs to
                   %LOCALAPPDATA%\ak820pro\ak820pro-nowplaying.log

    Both run as the INTERACTIVE user, not as SYSTEM, and only while someone is
    logged on. That is a requirement, not a convenience: SMTC sessions belong to
    a user session, so a SYSTEM task would see no media at all.

    They launch via pythonw.exe so no console window flashes on every logon;
    that also means stdout goes nowhere, which is why both agents take a
    --log/-log path.

    Runs as a normal user -- no elevation. Tasks live under \ak820pro\.

.PARAMETER Status
    Show whether each task is registered, its state, and the last run result.

.PARAMETER Uninstall
    Remove both tasks. Leaves the log files alone.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1
    powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1 -Status
    powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Folder   = '\ak820pro\'
$LogDir   = Join-Path $env:LOCALAPPDATA 'ak820pro'
$PythonW  = Join-Path $Root 'venv-win\Scripts\pythonw.exe'

$Agents = @(
    @{
        Name   = 'AK820Pro-timekeeper'
        Script = Join-Path $Root 'hostagent\ak820-timekeeper.py'
        Args   = @()          # writes its own log path internally
        Desc   = 'AK820 Pro: keep the keyboard LCD clock in sync with this PC.'
    },
    @{
        Name   = 'AK820Pro-nowplaying'
        Script = Join-Path $Root 'hostagent\nowplaying-windows.py'
        Args   = @('--log', (Join-Path $LogDir 'ak820pro-nowplaying.log'))
        Desc   = 'AK820 Pro: push the currently playing track to the keyboard LCD.'
    }
)

function Get-AgentTask($name) {
    Get-ScheduledTask -TaskPath $Folder -TaskName $name -ErrorAction SilentlyContinue
}

if ($Status) {
    foreach ($a in $Agents) {
        $t = Get-AgentTask $a.Name
        if (-not $t) {
            "{0,-22} NOT INSTALLED" -f $a.Name
            continue
        }
        $info = Get-ScheduledTaskInfo -TaskPath $Folder -TaskName $a.Name
        "{0,-22} {1,-10} last run {2}  result 0x{3:X}" -f `
            $a.Name, $t.State, $info.LastRunTime, $info.LastTaskResult
    }
    ""
    "logs in $LogDir"
    Get-ChildItem $LogDir -Filter 'ak820pro-*.log' -ErrorAction SilentlyContinue |
        ForEach-Object { "  {0,-34} {1,8} bytes  {2}" -f $_.Name, $_.Length, $_.LastWriteTime }
    return
}

if ($Uninstall) {
    foreach ($a in $Agents) {
        if (Get-AgentTask $a.Name) {
            Unregister-ScheduledTask -TaskPath $Folder -TaskName $a.Name -Confirm:$false
            "removed $($a.Name)"
        } else {
            "$($a.Name) was not installed"
        }
    }
    "log files left in $LogDir"
    return
}

# --- install ---------------------------------------------------------------
if (-not (Test-Path $PythonW)) {
    throw "no pythonw.exe at $PythonW -- run ./setup.sh from the MSYS2 MinGW 64-bit shell first."
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

foreach ($a in $Agents) {
    if (-not (Test-Path $a.Script)) { throw "missing agent script: $($a.Script)" }

    $argLine = ('"{0}"' -f $a.Script)
    if ($a.Args.Count) { $argLine += ' ' + ($a.Args -join ' ') }

    $action = New-ScheduledTaskAction -Execute $PythonW -Argument $argLine -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    # InteractiveToken: the agent must live in the user's own session. SMTC
    # media sessions are per-session, so a task running as SYSTEM or with
    # "run whether user is logged on or not" sees no media whatsoever.
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                                            -LogonType Interactive -RunLevel Limited
    # ExecutionTimeLimit 0 = never kill it; these are loops, not jobs. Restart
    # on failure covers a board unplugged at the wrong moment. Battery settings
    # are explicit because the defaults stop the task on battery, which would
    # silently kill the clock sync on a laptop.
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -MultipleInstances IgnoreNew

    if (Get-AgentTask $a.Name) {
        Unregister-ScheduledTask -TaskPath $Folder -TaskName $a.Name -Confirm:$false
    }
    Register-ScheduledTask -TaskPath $Folder -TaskName $a.Name `
        -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description $a.Desc | Out-Null
    "installed $($a.Name)"
}

""
"Starting them now so you do not have to log out and back in:"
foreach ($a in $Agents) {
    Start-ScheduledTask -TaskPath $Folder -TaskName $a.Name
    "  started $($a.Name)"
}
""
"Check with:  -Status      Logs: $LogDir"
