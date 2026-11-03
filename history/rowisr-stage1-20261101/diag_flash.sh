#!/bin/bash
# The cost diagnostic's flash on white (11-02 night, 95ef5cbc5d, token
# 0xda2a24d5: the handler's sections stamped, op 28 sub 11, and the cost of a
# register read, sub 10) and its readings: the daemon paused, data on, the
# token read (the trim, 0x1a291156, expected before), flash.sh with its
# backups and restores, the board back, then readcost, two 10 s section
# windows (the lights as JD left them, then the RGB off through the dev LED
# op is not needed: the sections are what they are), a page-7 window, the
# record and the frame counter's record; data off and the daemon back. One
# key from JD wakes white first; his go starts it (diag_on_wake.sh).
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-95ef5cbc5d-20261102-233608.bin
WANT=0xda2a24d5
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 15); do present && break; sleep 2; done
present || { log "no board on USB (asleep? one key wakes it)"; exit 1; }
sleep 2; log "board present, token before: $(token)"
log "flash: $ART"
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-diag.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; exit 1; }
sleep 3
T=$(token); log "token after the flash: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "token mismatch"; exit 1; }
sleep 20   # the restores settle; the handler has run a while
log "readcost (op 28 sub 10)"
venv/bin/python scripts/rowisr_diag.py readcost | tee "$D/readcost-diag.txt"
venv/bin/python scripts/rowisr_diag.py readcost --json >> "$D/readcost-diag.txt"
log "sections, window 1 (10 s)"
venv/bin/python scripts/rowisr_diag.py sections | tee "$D/sections-diag-1.txt"
log "sections, window 2 (10 s)"
venv/bin/python scripts/rowisr_diag.py sections --json | tee "$D/sections-diag-2.json"
log "page-7 window (20 s)"
venv/bin/python - <<'PY' | tee "$D/sched-window-diag.txt"
import sys, time
sys.path.insert(0, "hostagent")
import ak820health as hp
h = hp.open_device()
try:
    A = hp.read_sched(h); tA = time.time(); time.sleep(20); B = hp.read_sched(h); tB = time.time()
    w = hp.sched_window(A, B, tB - tA)
    for k in ("win_slots_per_s", "win_missed_slots", "win_pulses_omitted", "win_elapsed_mean_us", "win_cpu_pct"):
        print(f"{k:24s} {w.get(k)}")
    print("page 4 since the boot:", hp.read_isr(h))
finally:
    h.close()
PY
log "record and the frame counter's record"
venv/bin/python scripts/rowisr_diag.py record | tee "$D/record-diag.txt"
venv/bin/python scripts/rowisr_diag.py usb | tee "$D/usb-diag.txt"
log "done"
