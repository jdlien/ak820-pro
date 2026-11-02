#!/bin/bash
# The base plus the fix (the audit session's f033-noled build) on white, between
# two flashes: the same four holds, then stage 1 plus the fix back. Usage:
#   base_fix_check.sh BASE_ART BASE_TOKEN BACK_ART BACK_TOKEN FROM_TOKEN
set -u
cd /Users/jdlien/code/ak820-pro
ART=$1; WANT=$2; BACK=$3; BACKTOKEN=$4; FROM=$5
OUT=history/rowisr-stage1-20261101
L=$OUT/base_fix_check.log
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
log() { echo "[$(date +%T)] $*" | tee -a "$L"; }
echo "=== base + fix check $(date +%T): $ART, then back to $BACK ===" >> "$L"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" >> "$L" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" >> "$L" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for _ in $(seq 1 60); do present && break; sleep 0.5; done
present || { log "no board on USB (asleep? one key wakes it)"; exit 1; }
sleep 2
T=$(token); log "board token: $T"
[ "$T" = "$FROM" ] || { log "not the expected build ($FROM): refusing"; exit 1; }
log "flash: $ART"
./flash.sh "$ART" < /dev/null >> "$L" 2>&1 || { log "flash FAILED"; exit 1; }
sleep 5
for _ in $(seq 1 40); do present && break; sleep 0.5; done
sleep 2
T=$(token); log "token after: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "wrong token after the flash: stopping"; exit 1; }
venv/bin/python - >> "$L" 2>&1 <<'PY'
import statistics, sys, time
sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
import rowisr_baseline as rb
hp, lp = rb.hp, rb.lp
HOLD, SETTLE, POWER_SAVER = 40, 8, 2
def hold(name):
    t0 = time.time(); time.sleep(SETTLE + HOLD); end = time.time()
    cur = [r[1] for r in rb.power_rows(rb.DEFAULT_CSV, t0 + SETTLE, end)]
    m = (round(statistics.mean(cur), 3), len(cur), round(statistics.pstdev(cur), 3)) if cur else (None, 0, None)
    rb.say(f"  {name:22s} {m[0]} mA over {m[1]} rows (sd {m[2]})"); return m[0]
h = hp.open_device()
try:
    before = lp.read_lighting(h); pw = rb.devhook(h, 14, [0])
    rb.say(f"lighting before {before}; power mode {pw[4]}")
    rb.devhook(h, 14, [1, 0])
    for _ in range(20):
        pw = rb.devhook(h, 14, [0])
        if pw[5] == 0 and pw[6] == 255: break
        time.sleep(0.25)
    rb.set_lighting(h, 0, 0, 0);   d1 = hold("dark")
    rb.set_lighting(h, 0, 0, 64);  w64 = hold("white 64")
    rb.set_lighting(h, 0, 0, 255); w255 = hold("white 255")
    rb.set_lighting(h, 0, 0, 0);   d2 = hold("dark again")
    rb.say(f"RESULT base + fix: dark {d1}/{d2}, white 64 {w64}, white 255 {w255}; base unfixed: dark 40.62, white 64 45.18, white 255 88.73")
finally:
    rb.say("restoring the lighting, then Power saver")
    try:
        lp.write_lighting(h, before)
    finally:
        rb.devhook(h, 14, [1, POWER_SAVER]); time.sleep(0.5)
        pw = rb.devhook(h, 14, [0]); rb.say(f"power mode now {pw[4]}; lighting {lp.read_lighting(h)}")
        h.close()
PY
log "flash back: $BACK"
./flash.sh "$BACK" < /dev/null >> "$L" 2>&1 || { log "flash back FAILED: white is on the base + fix build"; exit 1; }
sleep 5
for _ in $(seq 1 40); do present && break; sleep 0.5; done
sleep 2
T=$(token); log "token after the flash back: $T (want $BACKTOKEN)"
[ "$T" = "$BACKTOKEN" ] || { log "wrong token after the flash back"; exit 1; }
venv/bin/python - >> "$L" 2>&1 <<'PY'
import sys, time
sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
import rowisr_baseline as rb
h = rb.hp.open_device()
try:
    pw = rb.devhook(h, 14, [0]); rb.say(f"after the flash back: power mode {pw[4]}, lighting {rb.lp.read_lighting(h)}")
finally:
    h.close()
PY
log "done"
