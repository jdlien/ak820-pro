#!/bin/bash
# Stage 4b's flash on white (11-03, 6b90f3b821: stage 4 with the hold-off kept for the 5 ms transactions alone, token 0x4215c3e2: the clock
# chip's transaction with the row ISR unmasked, the bracket's width on status
# page 4) and its hands-free gates: the flash (white woken by the presser if
# asleep), the clock status pages before anything, a burst of 300 PCF reads
# (dev op 23) with the presser's 200 presses at 25 ms running through it
# (the delivery under I2C load, the handler now running through the
# transactions), the stall counters and i2c_max_cycles after it (the plan:
# <= ~3.5 ms, 118 ILRC cycles at 33.6 kHz), the stuck-bus test (op 23 sub
# 5: the transfer into its deadline and the restart, no pass >= 25 ms), the
# warm windows against stage 3's, then soak_watch_awake.sh until the
# morning (data on, the daemon syncing the clock, a read every 20 min). The
# camera gate (a forced write with no dark frame) is JD's in the morning.
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-6b90f3b821-20261103-045632.bin
WANT=0x4215c3e2
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
pkill -f "soak_watch" 2>/dev/null && log "the stage 3b soak watch stopped"
sleep 2; pkill -f presser_repl.py 2>/dev/null; launchctl bootstrap "gui/$UID" "$HOME/Library/LaunchAgents/com.jdlien.ak820pro.powerlog.plist" 2>/dev/null
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
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-stage4b.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 3
T=$(token); log "token after the flash: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "token mismatch"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 20   # the boot's acquisition settles
log "the clock status pages after the boot"
venv/bin/python hostagent/rtc_phase0.py status 2>&1 | tee "$D/rtc-status-stage4b-0.txt"
venv/bin/python -c "import sys; sys.path.insert(0, 'hostagent'); import ak820health as hp; hp.reset_counters()" && log "health counters reset"
venv/bin/python scripts/overrun_diag.py status 2>&1 | tee "$D/overrun-status-stage4b-0.txt" | grep -i 'kind\|pcf\|span' | head -8
log "a burst of 300 PCF reads (40-80 ms apart, ~18 s) with 200 presses of A1 at 25 ms through it"
venv/bin/python scripts/overrun_diag.py burst 300 --lo 40 --hi 80 2>&1 | tail -2
before=$(venv/bin/python scripts/presser_count.py)
venv/bin/python scripts/presser_repl.py batch A1 200 25 75 2>&1 | grep -v '^BATCH'
sleep 3
after=$(venv/bin/python scripts/presser_count.py)
BEFORE="$before" AFTER="$after" python3 - <<'PY' | tee "$D/burst-presses-stage4b.txt"
import json, os
b, a = json.loads(os.environ["BEFORE"]), json.loads(os.environ["AFTER"])
kp = (a["key_presses"] - b["key_presses"]) & 0xFFFF; re = (a["raw_edges"] - b["raw_edges"]) & 0xFFFFFFFF
print(f"presses through the PCF burst: key_presses +{kp} (want 200), raw_edges +{re} (want 400), row_gap_max {a.get('row_gap_max_ms')} ms -> {'PASS' if kp == 200 and re == 400 else 'FAIL'}")
print("stalls after:", {k: v for k, v in a.items() if 'ge' in k or 'stall' in k or 'gap' in k})
PY
venv/bin/python scripts/overrun_diag.py burst stop >/dev/null 2>&1
venv/bin/python hostagent/rtc_phase0.py status 2>&1 | grep 'page2\|page4' | tee "$D/rtc-status-stage4b-burst.txt"
log "the stuck-bus test (op 23 sub 5): the transfer into its deadline and the restart"
venv/bin/python - <<'PY' | tee "$D/stuck-stage4b.txt"
import sys, time, json
sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp
from overrun_diag import burst
h = hp.open_device()
try:
    s0 = hp.read_stalls(h)
    burst(h, 5)
    time.sleep(1.5)
    s1 = hp.read_stalls(h)
finally:
    h.close()
d = {k: (s1[k] - s0[k]) if isinstance(s1[k], int) and isinstance(s0.get(k), int) else (s0.get(k), s1[k]) for k in s1}
print("stall counters' change across the stuck test:", json.dumps(d))
PY
venv/bin/python hostagent/rtc_phase0.py status 2>&1 | grep 'page2\|page4' | tee "$D/rtc-status-stage4b-stuck.txt"
log "ordinary reads after the stuck test: a burst of 20 (the bus must be back)"
venv/bin/python scripts/overrun_diag.py burst 20 --lo 40 --hi 80 2>&1 | tail -1; sleep 3
venv/bin/python scripts/overrun_diag.py burst stop 2>&1 | tail -1
venv/bin/python hostagent/rtc_phase0.py status 2>&1 | grep 'page2\|page4' | tee "$D/rtc-status-stage4b-after-stuck.txt"
venv/bin/python scripts/overrun_diag.py status 2>&1 | tee "$D/overrun-status-stage4b-after-stuck.txt" | grep -i 'kind\|pcf\|span' | head -8
venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp; from overrun_diag import op
h = hp.open_device()
try:
    op(h, 20, [1]); print("op 22's per-kind spans zeroed after the injection (codex on 6b90f3b821: the healthy soak maxima must not carry the stuck test's 10 ms)")
finally:
    h.close()
PY
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "standing state for the warm windows"
log "three deep sleeps and wakes (the pre-sleep read and the wake's recovery on their 5 ms deadline with the handler running): page 2 before and after"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; sleep 4
venv/bin/python hostagent/rtc_phase0.py status 2>&1 | grep 'page2\|page4' | tee "$D/rtc-status-stage4b-before-wakes.txt"
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1
"$D/deep_wake_presser.sh" 3 stage4b "$WANT" 2>&1 | tee "$D/deep-wake-stage4b.log"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; sleep 4
venv/bin/python hostagent/rtc_phase0.py status 2>&1 | grep 'page2\|page4' | tee "$D/rtc-status-stage4b-after-wakes.txt"
log "the awake soak starts (data on, the daemon syncing; a read every 20 min)"
exec "$D/soak_watch_awake.sh" stage4b "$WANT"
