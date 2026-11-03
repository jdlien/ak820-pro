#!/bin/bash
# The keep-alive's M4, the control (today's firmware, no keep-alive): does the
# waking key reach the Mac after the module has dropped the link? N trials of:
# white asleep on battery, the data line off and the daemon paused (no
# lock-light frames to hold the link); the module's drop seen in bluetoothd
# (reason 719, ~30:00 after the sleep, docs/wireless.md "The module ends the
# link"); one press of A1 ((0,13), F19, 100 ms) by the presser; F19's arrival
# read from the F19 listener's log (it logs F19/F20 only) within 15 s; then the
# data line on and the board's own key_presses read, which separates a lost key
# from a failed press. Buzz must be unlocked at the press (the listener sees
# nothing on a locked Mac): the trial waits up to 30 min for it, then records
# the press as void. Usage: m4_control.sh N; results in m4-control.json/.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
N=${1:-4}
D=history/keepalive-20261103
OUT="$D/m4-control.json"
PCSV=history/power-bench-2026-10-15/power.csv
F19=~/Library/Logs/ak820pro/f19.log
# White's BLE device in bluetoothd's PowerLogger lines (EB982520 since the re-pair ~01:10 11-03, 0E7229B8 before; a re-pair changes it). A bare
# "reason 719" is not enough: the iPhone's link drops with 719 too (11:53 and 11:57 11-03).
WHITE_BT=EB982520-A7AC-8123-705D-800ADA51BE60
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*" >&2; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
locked() { ioreg -n Root -d1 | grep -q 'CGSSessionScreenIsLocked"=Yes'; }
hub() { timeout 20 uhubctl -l 3-1.3.4 -p 2 -a "$1" -e >/dev/null; }   # port 2 only: port 4 is the UPS
since() { date -r "$1" '+%Y-%m-%d %H:%M:%S'; }
bt() { /usr/bin/log show --start "$(since "$1")" --predicate 'process == "bluetoothd"' --style compact 2>/dev/null; }
counts() { venv/bin/python scripts/presser_count.py; }
read_counts() {   # data on (3 s after the last off), white present, the counts, data off
    sleep 3; hub on
    for i in $(seq 1 40); do present && break; sleep 0.5; done
    present || { log "white NOT present 20 s after the data line came on"; hub off; return 1; }
    sleep 2; local c; c=$(counts); local rc=$?; hub off; [ $rc = 0 ] && echo "$c"
}
wait_asleep() {   # three fresh rows under 6 mA, up to 10 min; prints the first row's epoch
    local t0 n=0 last="" first=""; t0=$(date +%s)
    while [ $(( $(date +%s) - t0 )) -lt 600 ]; do
        local row; row=$(tail -1 "$PCSV")
        if [ "$row" != "$last" ]; then
            last=$row
            local ma ep; ma=$(echo "$row" | cut -d, -f6); ep=$(echo "$row" | cut -d, -f2)
            if awk -v m="$ma" 'BEGIN{exit !(m < 6)}'; then n=$((n + 1)); [ $n = 1 ] && first=$ep; else n=0; fi
            [ $n -ge 3 ] && { log "white asleep ($ma mA)"; echo "${first%.*}"; return 0; }
        fi
        sleep 2
    done
    log "white not asleep after 10 min (last row: $last)"; return 1
}
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; log "daemon paused (no lock-light frames)"
trap 'hub off; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
hub off; log "data off"
log "baseline: one press to wake white (a sleeping board does not wake on the data line), then the counts"
venv/bin/python scripts/presser_repl.py pulse A1 100 2>&1 | tee -a "$D/m4-control.log" >&2
prev=$(read_counts) || exit 1
log "baseline: $prev"
echo "[" > "$OUT"
for k in $(seq 1 "$N"); do
    ts=$(wait_asleep) || break
    log "trial $k: asleep since $(date -r "$ts" +%H:%M:%S); waiting for the module's drop (reason 719, up to 40 min)"
    tdrop=""
    while [ $(( $(date +%s) - ts )) -lt 2400 ]; do
        woke=$(tail -n 3000 "$PCSV" | awk -F, -v t="$ts" '$2 > t + 5 && $6 > 8 {print $1; exit}')
        if [ -n "$woke" ]; then   # a key on white (or a stray) restarts the link's 30 min: start over
            log "trial $k: white woke at $woke (a key on white?); waiting for it to sleep again"
            ts=$(wait_asleep) || break 2
            log "trial $k: asleep again since $(date -r "$ts" +%H:%M:%S)"
            continue
        fi
        tdrop=$(bt "$ts" | grep "PowerLogger device \"$WHITE_BT\" disconnect" | head -1 | cut -c1-23)
        [ -n "$tdrop" ] && break
        sleep 30
    done
    log "trial $k: drop ${tdrop:-NOT SEEN in 40 min}"
    sleep 60
    w0=$(date +%s)
    while locked && [ $(( $(date +%s) - w0 )) -lt 1800 ]; do sleep 20; done
    lk=no; locked && lk=yes
    n0=$(wc -l < "$F19")
    tp0=$(date +%s)
    out=$(venv/bin/python scripts/presser_repl.py pulse A1 100 2>&1); echo "$out" | tee -a "$D/m4-control.log" >&2
    hp=$(echo "$out" | grep 'one press' | head -1 | sed -E 's/^\[([0-9:]+)\].*/\1/')   # the press's own line, not the command's start (~7 s of REPL setup)
    tp1=$(date -j -f '%Y-%m-%d %H:%M:%S' "$(date +%Y-%m-%d) ${hp:-00:00:00}" +%s)
    sleep 15
    arr=$(tail -n +$((n0 + 1)) "$F19" | awk '$2 == "down" {print $1}' | head -1)
    rdy=$(bt "$tp0" | grep "PowerLogger device \"$WHITE_BT\" connect" | head -1 | cut -c1-23)
    cur=$(read_counts) || break
    PREV="$prev" CUR="$cur" python3 - "$k" "$ts" "$tdrop" "$lk" "$tp1" "$arr" "$rdy" >> "$OUT" <<'PY'
import json, os, sys
k, ts, tdrop, lk, tp1, arr, rdy = sys.argv[1:]
p, c = json.loads(os.environ["PREV"]), json.loads(os.environ["CUR"])
d = {"trial": int(k), "asleep_epoch": int(ts), "drop": tdrop or None, "locked_at_press": lk == "yes",
     "press_done_epoch": float(tp1), "f19_down_epoch": float(arr) if arr else None,
     "f19_after_press_s": round(float(arr) - float(tp1), 2) if arr else None, "bt_ready": rdy or None,
     "key_presses_delta": (c["key_presses"] - p["key_presses"]) & 0xFFFF}
d["verdict"] = ("void (Buzz locked)" if d["locked_at_press"] else "void (no press at the board)" if d["key_presses_delta"] < 1
                else "ARRIVED" if arr else "LOST")
print(("," if int(k) > 1 else "") + json.dumps(d))
PY
    log "trial $k: $(tail -1 "$OUT")"
    prev=$cur
done
echo "]" >> "$OUT"
log "done -> $OUT"
