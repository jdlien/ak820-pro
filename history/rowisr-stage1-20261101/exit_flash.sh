#!/bin/bash
# The exit-only build's flash on white (11-03, f0ec5c68df, token 0x9e2d894a:
# the exit snapshot time only, the duration sample kept honest by the frame
# counter alone; the cadence 1d73bf3ed5 reverted on codex's P1) and its
# checks: the daemon paused, data on, the token read (the cost diagnostic,
# 0xda2a24d5, expected before), flash.sh with its backups and restores, the
# token after; the handler's sections (op 28 sub 11, two 10 s windows) and
# readcost while the board is fresh from the boot; silence_check.sh (the 16
# cases, its two battery cases inside 3 min of the boot so the ladder cannot
# sleep the board through them); then warm_windows.sh exit 0x9e2d894a
# against stage 2's and the detector's windows (its own trap puts data off
# and the daemon back). One key from JD wakes white first; his go starts it
# (exit_on_usb.sh).
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-f0ec5c68df-20261103-003613.bin
WANT=0x9e2d894a
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 15); do present && break; sleep 2; done
present || { log "no board on USB (asleep? one key wakes it)"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 2; log "board present, token before: $(token)"
log "flash: $ART"
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-exit.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 3
T=$(token); log "token after the flash: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "token mismatch"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 10
log "sections, window 1 (10 s)"
venv/bin/python scripts/rowisr_diag.py sections | tee "$D/sections-exit-1.txt"
log "sections, window 2 (10 s)"
venv/bin/python scripts/rowisr_diag.py sections --json | tee "$D/sections-exit-2.json"
log "readcost (the fixed reads count)"
venv/bin/python scripts/rowisr_diag.py readcost | tee "$D/readcost-exit.txt"
log "silence_check.sh starts (16 cases; its own data cycles and trap)"
"$D/silence_check.sh" 2>&1 | tee "$D/silence-check-exit.log"
log "silence_check.sh exit ${PIPESTATUS[0]}"
log "warm_windows.sh exit starts"
exec "$D/warm_windows.sh" exit "$WANT"
