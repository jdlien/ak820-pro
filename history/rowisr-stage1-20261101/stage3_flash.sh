#!/bin/bash
# Stage 3's flash on white and its gates, hands-free (11-03, 8e9f9aaff2 = cf7b61560d plus the daily build fix,
# token 0x1a9d6392; JD's advance go for the night): the daemon paused, data
# on, white woken by the presser if asleep, the token before, flash.sh with
# its backups and restores, the token after; then the status (col_map_fault
# must be 0), the FRMNO scan (sub 14, 30 s: the tear seen or not), the six
# row counts over 20 s (within one of each other), the short-tap gate
# (presser_gate.sh: the counts at the scan now too), Q1's settle sweep
# (settle_sweep.sh), the silence set (the torn-read fix: the battery 20 ms
# case back to 2 losses), the warm windows (page 4 with the sections out),
# and deep sleep's five wakes (deep_wake_presser.sh). Each script restores
# the standing state itself. Usage: stage3_flash.sh.
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-3673b234f0-20261103-030608.bin
WANT=0x0a2f280e
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 5); do present && break; sleep 2; done
if ! present; then
    log "white not on USB: asleep, one press to wake it"
    venv/bin/python scripts/presser_repl.py pulse A1 100 || { log "the wake press failed"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
    for i in $(seq 1 15); do present && break; sleep 1; done
    present || { log "no board after the wake press"; uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
fi
sleep 2; log "board present, token before: $(token)"
log "flash: $ART"
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-stage3.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 3
T=$(token); log "token after the flash: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "token mismatch"; uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
venv/bin/python scripts/rowisr_diag.py status --json | tee "$D/status-stage3.json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"status: col_map_fault {d[\"col_map_fault\"]}, hw_fault {d[\"hw_fault\"]}, prime_timed_out {d[\"prime_timed_out\"]}")'
log "the column settle in force: $(venv/bin/python scripts/rowisr_diag.py settle)"
log "FRMNO scan, 30 s"
venv/bin/python scripts/rowisr_diag.py frmscan 30000; sleep 36
venv/bin/python scripts/rowisr_diag.py frmscan | tee "$D/frmscan-stage3.txt"
log "the six row counts over 20 s"
venv/bin/python - <<'PY' | tee "$D/rows-stage3.txt"
import sys, time
sys.path.insert(0, "hostagent")
import ak820health as hp
h = hp.open_device()
try:
    a = hp.read_rows(h); time.sleep(20); b = hp.read_rows(h)
finally:
    h.close()
d = [(y - x) & 0xFFFFFFFF for x, y in zip(a["row_samples"], b["row_samples"])]
print(f"row samples in 20 s: {d}; spread {max(d) - min(d)} (want <= 1); row_gap_max {b['row_gap_max_ms']} ms on row {b['row_gap_max_row']}; raw_edges {b['raw_edges']} consumes {b['consumes']}")
PY
uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "standing state for the gates (each pauses and restores on its own)"
"$D/presser_gate.sh" stage3 "$WANT" 2>&1 | tee "$D/presser-gate-stage3.log"
"$D/settle_sweep.sh" stage3 "$WANT" 2>&1 | tee "$D/settle-sweep-stage3.log"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; sleep 4
log "silence_check.sh starts (16 cases)"
"$D/silence_check.sh" 2>&1 | tee "$D/silence-check-stage3.log"
mv "$D/silence-check.json" "$D/silence-check-stage3.json" 2>/dev/null
"$D/warm_windows.sh" stage3 "$WANT" 2>&1 | tee "$D/warm-windows-stage3.log"
log "deep sleep's wakes start (5 cycles, ~25 min)"
exec "$D/deep_wake_presser.sh" 5 stage3 "$WANT"
