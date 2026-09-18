# Sample the live daemon's memory against its own exchange counters (read-only).
# The daemon has been up since 2026-09-17 10:19:13, so every sample here is long
# past warm-up: the slope is leak, not ramp. Appends CSV so a killed session
# still leaves the data behind.
$ErrorActionPreference = 'Continue'
$csv = "$env:LOCALAPPDATA\ak820pro\mem-samples-e07fdfa.csv"
$status = "$env:LOCALAPPDATA\ak820pro\ak820-agent.status"
$minutes = 5
$hours = 4

if (-not (Test-Path $csv)) {
    Add-Content $csv 'at,pid,elapsed_h,cpu_s,private_bytes,working_set,peak_working_set,handles,threads,smtc_polls,clock_syncs,health_reads_hint'
}
$end = (Get-Date).AddHours($hours)
while ($true) {
    $p = Get-Process ak820-agent -ErrorAction SilentlyContinue
    if ($p) {
        $perf = Get-CimInstance Win32_PerfRawData_PerfProc_Process -Filter "IDProcess=$($p.Id)"
        $s = @{}
        foreach ($line in Get-Content $status) { $k, $v = $line -split '=', 2; if ($v) { $s[$k] = $v } }
        $row = '{0},{1},{2:N4},{3:N1},{4},{5},{6},{7},{8},{9},{10},{11}' -f `
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $p.Id, ((Get-Date) - $p.StartTime).TotalHours, $p.CPU,
            $perf.PrivateBytes, $p.WorkingSet64, $p.PeakWorkingSet64, $p.HandleCount, $p.Threads.Count,
            $s['smtc_polls'], $s['clock_syncs'], $s['health_read_at']
        Add-Content $csv $row
        Write-Output $row
    } else {
        Add-Content $csv "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),,,,,,,,,,,daemon not running"
        Write-Output 'daemon not running'
    }
    if ((Get-Date) -ge $end) { break }
    Start-Sleep -Seconds ($minutes * 60)
}
Write-Output "CSV=$csv"
