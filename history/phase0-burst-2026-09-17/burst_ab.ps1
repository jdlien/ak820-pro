# Phase 0 interleaved burst A/B on gremlin (rule from ak820-pro-c6, 2026-09-17).
# Stops the daemon between syncs, alternates `clock --raw` reads from the e07fdfa and
# d8ead97 CLIs, then ALWAYS restarts the daemon's task. Board traffic: GET reads only.
$ErrorActionPreference = 'Continue'   # native stderr must not throw; failures below are explicit
$sp = 'C:\Users\jdlien\AppData\Local\Temp\claude\C--Users-jdlien-code-ak820-pro\2a1fe2b5-2c78-4f0e-b7e5-5c1f7cda064b\scratchpad'
$new = "$env:LOCALAPPDATA\ak820pro\bin\ak820.exe"
$old = "$sp\rollback-d8ead97\ak820.exe"
$log = "$env:LOCALAPPDATA\ak820pro\ak820-agent.log"
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$raw = "$env:LOCALAPPDATA\ak820pro\phase0-burst-$stamp.txt"
$rounds = 50

function Note($s) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff') $s"; Add-Content -Path $raw -Value $line -Encoding utf8; Write-Output $line }

Note "burst A/B start; NEW=$new ($(& $new --version)); OLD=$old ($(& $old --version))"
if ((& $new --version) -notmatch 'v0\.1\.1-22-ge07fdfa') { throw 'NEW is not e07fdfa' }
if ((& $old --version) -notmatch 'd8ead97') { throw 'OLD is not d8ead97' }

# 1. between syncs: wait for the next periodic sync's bias line, then stop the task
$before = (Get-Content $log).Count
$deadline = (Get-Date).AddSeconds(340)
while ((Get-Date) -lt $deadline) {
    $tail = Get-Content $log | Select-Object -Skip $before
    if (($tail -match 'sync \(periodic\)') -and ($tail | Select-Object -Last 1) -match 'bias (learned|hold)') { break }
    Start-Sleep -Milliseconds 500
}
Start-Sleep -Seconds 1
Note "last daemon sync before stop: $((Get-Content $log | Select-String 'sync \(periodic\)' | Select-Object -Last 1).Line)"
$stopped = $false
try {
    Stop-ScheduledTask -TaskPath '\ak820pro\' -TaskName 'AK820Pro-agent' -ErrorAction Stop
    $stopped = $true
    $gone = (Get-Date).AddSeconds(20)
    while ((Get-Process -Name 'ak820-agent' -ErrorAction SilentlyContinue) -and (Get-Date) -lt $gone) { Start-Sleep -Milliseconds 200 }
    if (Get-Process -Name 'ak820-agent' -ErrorAction SilentlyContinue) { throw 'daemon process still running 20 s after stop' }
    if (Get-Process -Name 'ak820ctl' -ErrorAction SilentlyContinue) { throw 'an ak820ctl process is running' }
    Note "daemon stopped; task state $((Get-ScheduledTask -TaskPath '\ak820pro\' -TaskName 'AK820Pro-agent').State)"

    # 2-3. 50 rounds, order alternating
    for ($r = 1; $r -le $rounds; $r++) {
        $order = if ($r % 2 -eq 1) { @(@('NEW', $new), @('OLD', $old)) } else { @(@('OLD', $old), @('NEW', $new)) }
        foreach ($pair in $order) {
            $name, $exe = $pair
            $t0 = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
            $out = & $exe clock --raw 2>&1 | ForEach-Object { "$_" }
            $code = $LASTEXITCODE
            Add-Content -Path $raw -Value "=== round $r $name at $t0 exit $code" -Encoding utf8
            Add-Content -Path $raw -Value $out -Encoding utf8
            Start-Sleep -Seconds 1
        }
    }
    Note "burst done"
}
finally {
    if ($stopped) {
        # 4. always give the clock back
        Start-ScheduledTask -TaskPath '\ak820pro\' -TaskName 'AK820Pro-agent'
        Note "task restarted; state $((Get-ScheduledTask -TaskPath '\ak820pro\' -TaskName 'AK820Pro-agent').State)"
    }
}
$mark = (Get-Content $log).Count
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $tail = Get-Content $log | Select-Object -Skip $mark
    if ($tail -match 'sync \(enumerated\)') { break }
    Start-Sleep -Milliseconds 500
}
Note "daemon log since restart:"
Get-Content $log | Select-Object -Skip $mark | ForEach-Object { Note "  $_" }
Write-Output "RAW=$raw"
