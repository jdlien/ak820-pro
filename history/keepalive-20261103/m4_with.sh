#!/bin/bash
# The keep-alive's M4 with it (README.md, "The with-run"): does the waking key
# reach the Mac after 30+ min asleep, the link held by the keep-alive alone?
# One trial: the daemon paused (no lock-light frames), the data line off;
# white asleep and no input for 32+ min (checked from power.csv: only the
# keep-alive's ~5 s wakes since); wait (up to 2 h) for Buzz to be unlocked
# and white between wakes; one press of A1 ((0,13), F19, 100 ms); F19's arrival
# from the F19 listener's log within 15 s; white's link events in bluetoothd
# (none expected: the link is up); then the data line on and m4_with_read.py
# (the counts, the wake record with key_gain, the last eight wakes, the sleep
# page). Usage: m4_with.sh [OUT.json]; default m4-with.json.
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/keepalive-20261103
OUT=${1:-$D/m4-with.json}
PCSV=history/power-bench-2026-10-15/power.csv
F19=~/Library/Logs/ak820pro/f19.log
WHITE_BT=EB982520-A7AC-8123-705D-800ADA51BE60   # since the re-pair ~01:10 11-03 (m4_control.sh)
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*" >&2; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
locked() { ioreg -n Root -d1 | grep -q 'CGSSessionScreenIsLocked"=Yes'; }
hub() { timeout 20 uhubctl -l 3-1.3.4 -p 2 -a "$1" -e >/dev/null; }   # port 2 only: port 4 is the UPS
since() { date -r "$1" '+%Y-%m-%d %H:%M:%S'; }
bt() { /usr/bin/log show --start "$(since "$1")" --predicate 'process == "bluetoothd"' --style compact 2>/dev/null; }
asleep_now() { tail -n 3 "$PCSV" | awk -F, '$6 >= 6 {bad=1} END {exit bad}'; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; log "daemon paused (no lock-light frames)"
trap 'hub off; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
hub off; log "data off"
# The last stretch awake longer than a keep-alive wake (> 15 s over 8 mA) is
# the last input's; read again while waiting, since a key on white starts it over.
last_long_end() { tail -n 40000 "$PCSV" | awk -F, '$6 > 8 {if (!s) s = $2; e = $2; next} s {if (e - s > 15) L = e; s = 0} END {print int(L)}'; }
last_long=$(last_long_end)
log "last long awake stretch ended $(date -r "$last_long" '+%m-%d %H:%M:%S')"
# 32 min: past the module's drop (29:53 after the sleep in the control, its
# 30 min from the last traffic) and the first keep-alive wake (~26 min after
# the sleep on the default rate, which a reflash restores).
MIN_IDLE_S=${MIN_IDLE_S:-1920}
w0=$(date +%s)
while [ $(( $(date +%s) - w0 )) -lt 7200 ]; do
    last_long=$(last_long_end)
    ! locked && asleep_now && [ $(( $(date +%s) - last_long )) -ge "$MIN_IDLE_S" ] && break
    sleep 5
done
if locked || [ $(( $(date +%s) - last_long )) -lt "$MIN_IDLE_S" ]; then
    log "not ready after 2 h (Buzz locked, or white's last long wake under $((MIN_IDLE_S / 60)) min ago): no press"; exit 0
fi
lk=no; locked && lk=yes
idle_min=$(( ($(date +%s) - last_long) / 60 ))
log "pressing: Buzz locked=$lk, ${idle_min} min since the last long wake"
n0=$(wc -l < "$F19")
tp0=$(date +%s)
out=$(venv/bin/python scripts/presser_repl.py pulse A1 100 2>&1); echo "$out" >&2
hp=$(echo "$out" | grep 'one press' | head -1 | sed -E 's/^\[([0-9:]+)\].*/\1/')   # the press's own line (~7 s of REPL setup before it)
tp1=$(date -j -f '%Y-%m-%d %H:%M:%S' "$(date +%Y-%m-%d) ${hp:-00:00:00}" +%s)
sleep 15
arr=$(tail -n +$((n0 + 1)) "$F19" | awk '$2 == "down" {print $1}' | head -1)
ev=$(bt "$tp0" | grep "PowerLogger device \"$WHITE_BT\"" | sed -E 's/^(.{23}).* (disconnect|connect)( .*|$)/\1 \2/' | tr '\n' ';')
sleep 3; hub on
for i in $(seq 1 40); do present && break; sleep 0.5; done
sleep 2
board=$(venv/bin/python $D/m4_with_read.py 2>&1) || log "board read failed: $board"
BOARD="$board" python3 - "$lk" "$idle_min" "$tp1" "$arr" "$ev" > "$OUT" <<'PY'
import json, os, sys
lk, idle, tp1, arr, ev = sys.argv[1:]
try:
    b = json.loads(os.environ["BOARD"])
except ValueError:
    b = {"error": os.environ["BOARD"]}
r = b.get("record", {})
d = {"locked_at_press": lk == "yes", "idle_min": int(idle), "press_done_epoch": float(tp1),
     "f19_down_epoch": float(arr) if arr else None,
     "f19_after_press_s": round(float(arr) - float(tp1), 2) if arr else None,
     "white_bt_events": [e for e in ev.split(";") if e], "board": b}
d["verdict"] = ("void (Buzz locked)" if d["locked_at_press"] else
                "void (white not woken by a key)" if r.get("reason") != "key" else
                "ARRIVED" if arr else "LOST")
print(json.dumps(d, indent=1))
PY
log "verdict: $(python3 -c "import json; d=json.load(open('$OUT')); print(d['verdict'], d['f19_after_press_s'], d['white_bt_events'])") -> $OUT"
