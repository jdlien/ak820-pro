#!/bin/bash
# Stage 3's second flash on white (11-03, 67a4ccf2b3, token 0x4326ec84: the
# frame counter's two reads twelve cycles apart) and what the first run
# left undone or wants again: the flash (white woken by the presser if
# asleep), the status, then a 10 min watch of the frame counter's record
# (the rejections must stay at 0 with no silence injected), the short-tap
# gate, the silence set (the ladder held through its data cuts now), the
# warm windows (page 4 with the sections out), the boundary batches (8 and
# 10 ms repeated for the debounce boundary's comparison), then
# soak_watch.sh until the morning. Each script restores the standing state.
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-67a4ccf2b3-20261103-041520.bin
WANT=0x4326ec84
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 5); do present && break; sleep 2; done
if ! present; then
    log "white not on USB: asleep, one press to wake it"
    venv/bin/python scripts/presser_repl.py pulse A1 100 || { log "the wake press failed"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
    for i in $(seq 1 15); do present && break; sleep 1; done
    present || { log "no board after the wake press"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
fi
sleep 2; log "board present, token before: $(token)"
log "flash: $ART"
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-stage3b.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 3
T=$(token); log "token after the flash: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "token mismatch"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
venv/bin/python scripts/rowisr_diag.py status | tee "$D/status-stage3b.txt" | grep -i 'col_map\|fault\|prime' || true
log "the frame counter watched for 10 min (the record now, then after)"
venv/bin/python -c "import sys; sys.path.insert(0, 'hostagent'); import ak820health as hp; hp.reset_counters()" && log "health counters reset"
venv/bin/python scripts/rowisr_diag.py usb | tee "$D/usb-stage3b-0.txt"
sleep 600
venv/bin/python scripts/rowisr_diag.py usb | tee "$D/usb-stage3b-10min.txt"
venv/bin/python scripts/rowisr_diag.py record | tee "$D/record-stage3b-10min.txt"
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "standing state for the gates (each pauses and restores on its own)"
"$D/presser_gate.sh" stage3b "$WANT" 2>&1 | tee "$D/presser-gate-stage3b.log"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; sleep 4
log "silence_check.sh starts (16 cases, the ladder held through the data cuts)"
"$D/silence_check.sh" 2>&1 | tee "$D/silence-check-stage3b.log"
mv "$D/silence-check.json" "$D/silence-check-stage3b.json" 2>/dev/null
"$D/warm_windows.sh" stage3b "$WANT" 2>&1 | tee "$D/warm-windows-stage3b.log"
"$D/presser_gate.sh" stage3b-boundary "$WANT" boundary 2>&1 | tee "$D/presser-gate-stage3b-boundary.log"
log "the soak watch starts"
exec "$D/soak_watch.sh" stage3b "$WANT"
