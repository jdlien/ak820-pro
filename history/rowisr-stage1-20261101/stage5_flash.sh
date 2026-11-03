#!/bin/bash
# Stage 5's flash on white and the hands-free gates (plans/ROW-ISR-PLAN.md,
# "Stage 5: the cadence"): the flash (white woken by the presser if asleep),
# the token check, the counters reset, a warm window for the handler's cost
# (page 4's mean and CPU share, page 7's elapsed, the record's omissions and
# late_omit and spurious, row_gap_max), the light at JD's full white against
# the logger (the lit draw on the data line; 4b read 92.1 mA lit, 31.1 dark,
# so 61.0 mA incremental is the reference; the gate is within 5%), the
# presser's short-tap gate, then the standing state (data off, the daemon
# up). Usage: stage5_flash.sh ART WANT LABEL [WINDOW_S] [PRESSER yes|no]
# (no: the presser's batches skipped, since on an unlocked Buzz their 1,900
# F19/F20 presses land in whatever is in front, 12:54 11-03; the ladder is
# put back and the standing state restored before the gate, whose own trap
# restores it again, the 12:56 run's lesson: its restore found no board).
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=${1:?artifact}; WANT=${2:?token}; L=${3:?label}; W=${4:-300}; PRESSER=${5:-yes}
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
power_mean() {   # the logger's mean mA over the last N rows
    tail -"$1" history/power-bench-2026-10-15/power.csv | awk -F, '{s+=$6; n++} END {if (n) printf "%.2f", s/n}'
}
pkill -f "soak_watch" 2>/dev/null; sleep 1; pkill -f presser_repl.py 2>/dev/null
launchctl bootstrap "gui/$UID" "$HOME/Library/LaunchAgents/com.jdlien.ak820pro.powerlog.plist" 2>/dev/null
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
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-$L.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 3
T=$(token); log "token after the flash: $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "token mismatch"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1; }
sleep 15
log "the ladder held at Always on (the lights stay on for the window and the light gate); a relight press"
venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'hostagent')
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try: devhook(h, 14, [1, 0])
finally: h.close()
PY
venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1
sleep 5
venv/bin/python -c "import sys; sys.path.insert(0, 'hostagent'); import ak820health as hp; hp.reset_counters()" && log "health counters reset"
venv/bin/python scripts/rowisr_diag.py record --json 2>/dev/null > /dev/null   # the record's own reset is with the counters
log "the warm window: $W s, white lit at JD's full white, nothing touching it"
sleep "$W"
log "page 4 (the handler) and page 7 (the scheduler) after $W s"
"$A" health --isr 2>&1 | tee "$D/health-isr-$L.txt" | grep -iE "isr|entries|mean|cpu|max" | head -8
venv/bin/python hostagent/ak820health.py --sched 2>&1 | tee "$D/health-sched-$L.txt" | head -14
venv/bin/python scripts/rowisr_diag.py record 2>&1 | tee "$D/record-$L.txt" | head -12
"$A" health --rows 2>&1 | grep -E "row_gap_max|ge_10|ge_25|loop_gap" | tee "$D/rows-$L.txt"
LIT=$(power_mean 120); log "the light: the lit draw over the last 120 s at full white: $LIT mA (4b: 92.1 lit, 31.1 dark, 61.0 incremental; within 5% is 58.0-64.1 incremental, 89.1-95.2 lit)"
echo "lit_mA $LIT" > "$D/light-$L.txt"
log "the ladder back to Power saver; the standing state"
venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'hostagent')
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try: devhook(h, 14, [1, 2])
finally: h.close()
PY
sleep 2; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"
launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon back: the standing state"
if [ "$PRESSER" = yes ]; then
    log "the presser's short-tap gate (its own trap leaves the standing state)"
    "$D/presser_gate.sh" "$L" "$WANT" 2>&1 | tail -6
else
    log "the presser's gate skipped (PRESSER=no): run presser_gate.sh $L $WANT with Buzz locked"
fi
