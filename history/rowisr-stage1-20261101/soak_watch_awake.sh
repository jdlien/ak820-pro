#!/bin/bash
# The night's soak on white AWAKE: the data line on and the daemon running
# throughout (the clock synced every 5 min over the data line, the clock
# chip's transactions and the writer's brackets exercised: stage 4's "night
# of syncs"), a read every 20 min with the daemon paused for ~15 s: the
# handler's record, the frame counter's record, the health vitals and
# stalls, the clock status pages (page 2's i2c_max_cycles and failures,
# page 4's bracket width, release and boundary errors, runs and restarts).
# One JSON line per read to soak-LABEL.jsonl, a summary line to the log.
# Runs until killed; the daemon is left running. Usage: soak_watch_awake.sh LABEL [TOKEN].
set -u
cd "$(dirname "$0")/../.." || exit 1
LABEL=${1:-stage4}; WANT=${2:-}
D=history/rowisr-stage1-20261101
OUT="$D/soak-$LABEL.jsonl"
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
launchctl bootstrap "gui/$UID" "$PL" 2>/dev/null
n=0
while true; do
    n=$((n + 1))
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1 >/dev/null
    sleep 2
    for i in $(seq 1 5); do present && break; sleep 2; done
    if ! present; then
        venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1
        for i in $(seq 1 20); do present && break; sleep 1; done
        log "read $n: white was not on USB (asleep?); pressed"
    fi
    if present; then
        sleep 2
        r=$(venv/bin/python scripts/rowisr_diag.py record --json 2>/dev/null); u=$(venv/bin/python scripts/rowisr_diag.py usb --json 2>/dev/null)
        c=$(venv/bin/python scripts/presser_count.py 2>/dev/null); v=$("$A" health --json 2>/dev/null)
        p=$(venv/bin/python hostagent/rtc_phase0.py status 2>/dev/null | grep 'page2\|page4' | tr '\n' ' ')
        R="$r" U="$u" C="$c" V="$v" P="$p" python3 - "$n" >> "$OUT" <<'PY'
import json, os, sys, time, re
r, u, c, v = (json.loads(os.environ[k]) if os.environ.get(k) else {} for k in ("R", "U", "C", "V"))
p = os.environ.get("P", "")
def grab(key):
    m = re.search(r"'" + key + r"': *'?([-\w.]+)", p); return m.group(1) if m else None   # rtc_phase0.py prints a dict: 'key': value
d = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "read": int(sys.argv[1]),
     "key_presses": c.get("key_presses"), "raw_edges": c.get("raw_edges"), "row_gap_max_ms": c.get("row_gap_max_ms"),
     "epoch_losses": r.get("epoch_losses"), "spurious": r.get("spurious"), "invalid_services": r.get("invalid_services"), "late_omit": r.get("late_omit"),
     "usb_checked": u.get("usb_checked"), "usb_rejects": u.get("usb_rejects"), "usb_events": u.get("usb_events"), "usb_last": [u.get("usb_last_dt_ms"), u.get("usb_last_df_ms")],
     "clock": {k: grab(k) for k in ("i2c_fail", "i2c_max_cycles", "stale_count", "release_err_ms", "runs_ok", "restarts", "boundary_err_ms", "d_first_ms", "brk_width_ms", "brk_fails", "slews")},
     "vitals": v.get("vitals") if v else None, "stalls": v.get("stalls") if v else None}
print(json.dumps(d))
ck = d["clock"]
print(f"[{time.strftime('%H:%M:%S')}] read {d['read']}: key_presses {d['key_presses']}, row_gap_max {d['row_gap_max_ms']} ms, losses {d['epoch_losses']}, spurious {d['spurious']}, "
      f"frame counter judged {d['usb_checked']} rejected {d['usb_rejects']} last {d['usb_last']}; clock: i2c_max_cycles {ck['i2c_max_cycles']} fails {ck['i2c_fail']} "
      f"runs_ok {ck['runs_ok']} restarts {ck['restarts']} release_err {ck['release_err_ms']} boundary_err {ck['boundary_err_ms']} bracket width {ck['brk_width_ms']} misses {ck['brk_fails']}", file=sys.stderr)
PY
    else
        log "read $n: white not on USB"
    fi
    launchctl bootstrap "gui/$UID" "$PL" 2>&1 >/dev/null
    sleep 1200
done
