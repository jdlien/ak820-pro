#!/bin/bash
# Deep sleep's wakes with the waking key kept, by the presser (the gate stage 1
# and stage 2 still owed; plans/ROW-ISR-PLAN.md): N cycles of: white asleep
# (the power logger's current under 6 mA on three rows in a row; it sleeps
# 3 min after the last key on Power saver with the data line off), one press
# of A1 ((0,13), 100 ms), the data line on, white present within 20 s (the
# wake), the counts read: key_presses must have grown by exactly 1 since the
# previous cycle's read (the waking key kept, judged at the board: the Mac
# loses the first key after a 30 min sleep anyway), the handler's record
# (losses, spurious) and the frame counter's record, then the data line off
# again. A cycle 0 wakes and reads without a verdict (the baseline count).
# The daemon paused throughout and put back by the trap. Usage:
# deep_wake_presser.sh N LABEL [TOKEN]; results in deep-wake-LABEL.json/.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
N=${1:-5}; LABEL=${2:-exit}; WANT=${3:-0x9e2d894a}
D=history/rowisr-stage1-20261101
OUT="$D/deep-wake-$LABEL.json"
PCSV=history/power-bench-2026-10-15/power.csv
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
counts() { venv/bin/python scripts/presser_count.py; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
trap 'timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
wait_asleep() {   # three fresh rows under 6 mA; up to 7 min
    local t0=$(date +%s) n=0 last=""
    while [ $(( $(date +%s) - t0 )) -lt 420 ]; do
        local row; row=$(tail -1 "$PCSV")
        if [ "$row" != "$last" ]; then
            last=$row
            local ma; ma=$(echo "$row" | awk -F, '{print $6}')
            if awk -v m="$ma" 'BEGIN{exit !(m < 6)}'; then n=$((n + 1)); else n=0; fi
            [ $n -ge 3 ] && { log "white asleep ($ma mA)"; return 0; }
        fi
        sleep 2
    done
    log "white not asleep after 7 min (last row: $last)"; return 1
}
wake_and_read() {   # prints the cycle's JSON on stdout, one line; everything else to stderr
    local t_press t_up delay before="$1"
    t_press=$(python3 -c 'import time; print(time.time())')
    venv/bin/python scripts/presser_repl.py pulse A1 100 >&2 || { log "the press failed"; return 1; }   # its log to stderr: this function's stdout is the cycle's JSON
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
    for i in $(seq 1 40); do present && break; sleep 0.5; done
    present || { log "white NOT present 20 s after the press: no wake"; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; return 2; }
    t_up=$(python3 -c 'import time; print(time.time())')
    sleep 2
    local c r u
    c=$(counts) || return 3
    r=$(venv/bin/python scripts/rowisr_diag.py record --json) || return 3
    u=$(venv/bin/python scripts/rowisr_diag.py usb --json) || return 3
    BEFORE="$before" python3 - "$t_press" "$t_up" "$c" "$r" "$u" <<'PY'
import json, os, sys, time
tp, tu = float(sys.argv[1]), float(sys.argv[2])
c, r, u = json.loads(sys.argv[3]), json.loads(sys.argv[4]), json.loads(sys.argv[5])
b = json.loads(os.environ["BEFORE"]) if os.environ["BEFORE"] else None
d = {"t": time.strftime("%H:%M:%S"), "press_to_present_s": round(tu - tp, 1), "key_presses": c["key_presses"],
     "raw_edges": c["raw_edges"], "epoch_losses": r["epoch_losses"], "spurious": r["spurious"], "invalid_services": r["invalid_services"],
     "usb_rejects": u["usb_rejects"], "usb_events": u["usb_events"], "loss_gen": u["loss_gen"]}
if b:
    d["key_presses_delta"] = (c["key_presses"] - b["key_presses"]) & 0xFFFF
    d["losses_delta"] = (r["epoch_losses"] - b["epoch_losses"]) & 0xFF
    d["spurious_delta"] = (r["spurious"] - b["spurious"]) & 0xFF
    d["pass"] = d["key_presses_delta"] == 1 and d["spurious_delta"] == 0
print(json.dumps(d))
PY
}
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null
echo "[" > "$OUT"
log "cycle 0: the baseline wake and read (no verdict)"
present && log "white awake already (data was on?)"
if ! present; then wait_asleep || exit 1; fi
prev=$(wake_and_read "") || exit 1
T=$(token); log "token $T (want $WANT)"; [ "$T" = "$WANT" ] || { log "not the expected build: stopping"; exit 1; }
log "cycle 0: $prev"
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off; white sleeps in ~3 min"
pass=0
for k in $(seq 1 "$N"); do
    wait_asleep || break
    cur=$(wake_and_read "$prev") || break
    [ $k = 1 ] || echo "," >> "$OUT"
    echo "$cur" >> "$OUT"
    ok=$(echo "$cur" | python3 -c 'import json,sys; print("PASS" if json.load(sys.stdin)["pass"] else "FAIL")')
    [ "$ok" = PASS ] && pass=$((pass + 1))
    summ=$(echo "$cur" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("woke %.1f s after the press command (the REPL setup inside); key_presses %+d (want +1), losses %+d, spurious %+d, frame rejects %d, bus events %d" % (d["press_to_present_s"], d["key_presses_delta"], d["losses_delta"], d["spurious_delta"], d["usb_rejects"], d["usb_events"]))')
    log "cycle $k: $summ -> $ok"
    prev=$cur
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"
done
echo "]" >> "$OUT"
log "RESULT: $pass of $N wakes kept the key -> $OUT"
