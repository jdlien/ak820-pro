#!/bin/bash
# The warm windows on the detector build (11-02 20:41, 5c0e6249d0): the
# runner's three health windows (idle, repaint, pcf; page 4's handler mean
# and the link counters) without the holds, compared against stage 2's
# (stage2.json, 11-01), to separate the handler's 63.3 us page-7 mean seen
# after the 19:06 wake from the lighting's content; a page-7 window and the
# row record before and after, and the USB record after. Over the data line
# with the daemon paused, no relay; the runner holds the ladder and puts the
# mode back (checked here: Power saver, 2). Data off and the daemon back by
# the trap. Everything to warm-windows.log, detector.json, compare-detector.txt.
# Usage: warm_windows.sh [LABEL] [TOKEN]: the label names the runner's JSON and the
# compare (detector, 0x60d4a06b by default; the trim's run is `trim 0x1a291156`,
# compared against stage 2's and the detector's windows).
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
D=history/rowisr-stage1-20261101
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
LABEL=${1:-detector}; WANT=${2:-0x60d4a06b}
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
trap 'timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"   # the pause: an on right after another script's off hung uhubctl twice on 11-03 (26 and 22 min)
for i in $(seq 1 5); do present && break; sleep 2; done
if ! present; then   # asleep: one press of the presser wakes it (11-03)
    log "white not on USB: asleep, one press to wake it"
    venv/bin/python scripts/presser_repl.py pulse A1 100 || exit 1
    for i in $(seq 1 15); do present && break; sleep 1; done
    present || { log "no board on USB after the wake press"; exit 1; }
fi
log "board present"; sleep 2
T=$(token); log "token $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "not the expected build: stopping"; exit 1; }
log "page-7 window before (20 s)"
venv/bin/python hostagent/ak820health.py --sched --window 20 > "$D/sched-window-$LABEL-before.txt" 2>&1
grep -E 'win_(slots_per_s|elapsed_mean_us|cpu_pct|missed_slots|pulses_omitted)' "$D/sched-window-$LABEL-before.txt"
venv/bin/python scripts/rowisr_diag.py record > "$D/record-$LABEL-before.txt" 2>&1; log "record before: $(tr '\n' ' ' < "$D/record-$LABEL-before.txt" | cut -c1-300)"
log "the runner's windows (idle, repaint, pcf), holds skipped"
venv/bin/python scripts/rowisr_baseline.py run --label "$LABEL" --out "$D" --skip-holds --cleanup skip 2>&1 | tee "$D/run-$LABEL.log"
rc=${PIPESTATUS[0]}; log "runner exit $rc"
venv/bin/python scripts/rowisr_baseline.py compare "$D/stage2.json" "$D/$LABEL.json" 2>&1 | tee "$D/compare-$LABEL.txt"
[ "$LABEL" = detector ] || venv/bin/python scripts/rowisr_baseline.py compare "$D/detector.json" "$D/$LABEL.json" 2>&1 | tee "$D/compare-$LABEL-vs-detector.txt"
log "page-7 window after (20 s)"
venv/bin/python hostagent/ak820health.py --sched --window 20 > "$D/sched-window-$LABEL-after.txt" 2>&1
grep -E 'win_(slots_per_s|elapsed_mean_us|cpu_pct|missed_slots|pulses_omitted)' "$D/sched-window-$LABEL-after.txt"
venv/bin/python scripts/rowisr_diag.py record > "$D/record-$LABEL-after.txt" 2>&1; log "record after: $(tr '\n' ' ' < "$D/record-$LABEL-after.txt" | cut -c1-300)"
venv/bin/python scripts/rowisr_diag.py usb > "$D/usb-$LABEL-after.txt" 2>&1; log "usb after: $(tr '\n' ' ' < "$D/usb-$LABEL-after.txt" | cut -c1-400)"
venv/bin/python - <<'PY'
import sys, time
sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try:
    pw = devhook(h, 14, [0]); print(f"[{time.strftime('%H:%M:%S')}] power after the run: mode {pw[4]} stage {pw[5]} cap {pw[6]} forced {pw[7]}")
    if pw[7] not in (0xFF, 0): devhook(h, 14, [2, 0xFF]); print("  the forced stage released")
    if pw[4] != 2:
        devhook(h, 14, [1, 2]); time.sleep(0.5); pw = devhook(h, 14, [0]); print(f"  Power saver put back: mode {pw[4]}")
finally:
    h.close()
PY
log "done"
