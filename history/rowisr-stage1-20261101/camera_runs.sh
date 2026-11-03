#!/bin/bash
# The camera gate on stage 4b (plans/ROW-ISR-PLAN.md, stage 4: "a forced PCF
# write filmed shows no dark frame"), JD filming white's keys at 240 fps.
# The dev build has no direct forced-write op (HC_RTCTEST is the instrumented
# build's), so the write is the writer's own, triggered by the daemon's sync
# as it starts (sync (enumerated), ~3 s after the start), which the firmware
# admits on the data line only after 10 min without a key (pcf-unseen): so
# white is woken by one press ahead of time and nothing touches it after.
# At T: a positive control, 20 held 7-byte reads 100 ms apart (dev op 23,
# the short deadline, the row ISR held off through each: brief dark frames
# expected, ~3 ms each); at T+8 s: the daemon started, its sync, the
# writer's three transactions unmasked (no dark frame expected); page 4
# read before and after (runs_ok +1 says the write happened). Usage:
# camera_runs.sh HH:MM:SS (the control's start, local time).
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
T=${1:?the start time HH:MM:SS}
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S.%N | cut -c1-12)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; log "daemon paused (it is started at T+8 for the sync)"
sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 5); do present && break; sleep 2; done
present || { log "white not on USB: it must be awake and idle (no key for 10 min) before the run"; exit 1; }
venv/bin/python hostagent/rtc_phase0.py status 2>/dev/null | grep 'page4' | tee "$D/camera-page4-before.txt"
now=$(date +%s); tgt=$(date -j -f "%H:%M:%S" "$T" +%s 2>/dev/null); [ -n "$tgt" ] || { log "bad time $T"; exit 1; }
wait=$((tgt - now)); log "waiting $wait s for T=$T"
[ "$wait" -gt 0 ] && sleep "$wait"
log "T: the control, 20 held reads 100 ms apart (dark frames expected for ~2 s)"
venv/bin/python scripts/overrun_diag.py burst 20 --lo 100 --hi 100 2>&1 | tail -1
sleep 2.5
venv/bin/python scripts/overrun_diag.py burst stop >/dev/null 2>&1
log "the control done"
sleep 4
log "T+8: the daemon started; its sync and the writer's unmasked write follow within seconds (no dark frame expected)"
launchctl bootstrap "gui/$UID" "$PL" 2>&1
sleep 15
log "T+23: reading back"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 2
venv/bin/python hostagent/rtc_phase0.py status 2>/dev/null | grep 'page4' | tee "$D/camera-page4-after.txt"
grep -E "^$(date +%Y-%m-%d) " ~/Library/Logs/ak820pro/ak820-agent.log | tail -4 | cut -c1-160
python3 - "$D/camera-page4-before.txt" "$D/camera-page4-after.txt" <<'PY'
import re, sys
def runs(f):
    m = re.search(r"'runs_ok': (\d+)", open(f).read()); return int(m.group(1)) if m else None
b, a = runs(sys.argv[1]), runs(sys.argv[2])
print(f"the writer's runs: {b} -> {a} ({'the write happened' if a is not None and b is not None and a > b else 'NO WRITE: the deferral still held, or the sync did not land'})")
PY
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"
launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon back: the standing state"
