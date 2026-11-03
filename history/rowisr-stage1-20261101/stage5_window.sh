#!/bin/bash
# A lit cost window on the build white runs (stage 5): the board woken onto
# the data line, the ladder held at Always on and READ BACK (5e's first
# window, 13:35, lost its lights at 3 min: the hold had not taken, so page
# 4's pair measured a dark handler and the light read 31 mA), a relight
# press, the lit draw checked at the start and at 200 s (>= 60 mA, else
# the window is void), the counters reset, W s, then page 4, page 7, the
# record, the rows and the logger's mean over the last 120 s; the ladder
# back to Power saver and the standing state. Usage:
# stage5_window.sh TOKEN LABEL [W=300]
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
WANT=${1:?token}; L=${2:?label}; W=${3:-300}
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
power_mean() { tail -"$1" history/power-bench-2026-10-15/power.csv | awk -F, '{s+=$6; n++} END {if (n) printf "%.2f", s/n}'; }
ladder() {   # the mode written and read back, once more if it did not take
    venv/bin/python - "$1" <<'PY'
import sys, time; sys.path.insert(0,'scripts'); sys.path.insert(0,'hostagent')
import ak820health as hp
from rowisr_baseline import devhook
want = int(sys.argv[1]); h = hp.open_device()
try:
    for i in range(3):
        devhook(h, 14, [1, want]); time.sleep(0.5)
        got = devhook(h, 14, [0])[4]
        if got == want: print(f"the ladder at mode {got} (try {i + 1})"); break
        time.sleep(2)
    else: print(f"the ladder did NOT take: mode {got}, wanted {want}"); sys.exit(1)
finally: h.close()
PY
}
standing() { sleep 2; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "the standing state"; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 5); do present && break; sleep 2; done
present || { venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; for i in $(seq 1 15); do present && break; sleep 1; done; }
present || { log "no board"; standing; exit 1; }
sleep 2; T=$(token); log "token $T (want $WANT)"; [ "$T" = "$WANT" ] || { log "token mismatch"; standing; exit 1; }
ladder 0 || { standing; exit 1; }
venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; sleep 12   # the logger pauses around a press: its rows straddle the relight
P0=$(power_mean 2); log "the lit draw at the start: $P0 mA (the last two rows)"
python3 -c "import sys; sys.exit(0 if float('$P0') >= ${LIT_MIN:-60} else 1)" || { log "the board is not lit: the window is void"; ladder 2; standing; exit 1; }
venv/bin/python -c "import sys; sys.path.insert(0, 'hostagent'); import ak820health as hp; hp.reset_counters()" && log "health counters reset"
log "the window: $W s lit"
sleep $((W > 200 ? 200 : W))
P1=$(power_mean 5); log "the lit draw at 200 s: $P1 mA"
python3 -c "import sys; sys.exit(0 if float('$P1') >= ${LIT_MIN:-60} else 1)" || { log "the lights went off inside the window: void"; ladder 2; standing; exit 1; }
[ "$W" -gt 200 ] && sleep $((W - 200))
log "page 4, page 7, the record, the rows, the light after $W s"
"$A" health --isr 2>&1 | tee "$D/health-isr-$L.txt" | grep -E "isr_" | head -5
venv/bin/python hostagent/ak820health.py --sched 2>&1 | tee "$D/health-sched-$L.txt" | grep -E "slots_elapsed|missed|pulses_|latency|elapsed_max"
venv/bin/python scripts/rowisr_diag.py record 2>&1 | tee "$D/record-$L.txt" | head -8
"$A" health --rows 2>&1 | grep -E "row_gap_max|ge_10|ge_25|loop_gap" | tee "$D/rows-$L.txt"
LIT=$(power_mean 120); log "the lit draw over the last 120 s: $LIT mA"; echo "lit_mA $LIT" > "$D/light-$L.txt"
ladder 2; standing
