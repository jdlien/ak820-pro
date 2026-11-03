#!/bin/bash
# The night's soak on white, read every 20 min with no key pressed (the board
# sleeps 3 min after the last key and the data line off; each read wakes it
# with one press of the presser, reads the record, the frame counter's
# record and the health vitals over the data line, and leaves it to sleep
# again; the sleeps and wakes are the soak's own cycles). Appends one JSON
# line per read to soak-LABEL.jsonl and a summary line to the log. Runs
# until killed. Usage: soak_watch.sh LABEL [TOKEN].
set -u
cd "$(dirname "$0")/../.." || exit 1
LABEL=${1:-stage3b}; WANT=${2:-}
D=history/rowisr-stage1-20261101
OUT="$D/soak-$LABEL.jsonl"
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
n=0
while true; do
    n=$((n + 1))
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1 >/dev/null
    sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
    for i in $(seq 1 5); do present && break; sleep 2; done
    woke=0
    if ! present; then
        venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1 || { log "read $n: the press failed"; }
        for i in $(seq 1 20); do present && break; sleep 1; done
        woke=1
    fi
    if present; then
        sleep 3
        r=$(venv/bin/python scripts/rowisr_diag.py record --json 2>/dev/null); u=$(venv/bin/python scripts/rowisr_diag.py usb --json 2>/dev/null)
        c=$(venv/bin/python scripts/presser_count.py 2>/dev/null); v=$("$A" health --json 2>/dev/null)
        R="$r" U="$u" C="$c" V="$v" python3 - "$n" "$woke" >> "$OUT" <<'PY'
import json, os, sys, time
r, u, c, v = (json.loads(os.environ[k]) if os.environ.get(k) else {} for k in ("R", "U", "C", "V"))
d = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "read": int(sys.argv[1]), "woke": bool(int(sys.argv[2])),
     "key_presses": c.get("key_presses"), "raw_edges": c.get("raw_edges"), "row_gap_max_ms": c.get("row_gap_max_ms"),
     "epoch_losses": r.get("epoch_losses"), "spurious": r.get("spurious"), "invalid_services": r.get("invalid_services"), "late_omit": r.get("late_omit"),
     "usb_checked": u.get("usb_checked"), "usb_rejects": u.get("usb_rejects"), "usb_events": u.get("usb_events"), "usb_last": [u.get("usb_last_dt_ms"), u.get("usb_last_df_ms")],
     "vitals": {k: v.get("vitals", {}).get(k) for k in ("build_token", "uptime_s", "resets", "wdt_resets")} if v else None,
     "stalls": v.get("stalls") if v else None}
print(json.dumps(d))
print(f"[{time.strftime('%H:%M:%S')}] read {d['read']}{' (woke it)' if d['woke'] else ''}: key_presses {d['key_presses']}, raw_edges {d['raw_edges']}, row_gap_max {d['row_gap_max_ms']} ms, "
      f"losses {d['epoch_losses']}, spurious {d['spurious']}, invalid {d['invalid_services']}, late omits {d['late_omit']}, "
      f"frame counter judged {d['usb_checked']} rejected {d['usb_rejects']} events {d['usb_events']} last {d['usb_last']}", file=sys.stderr)
PY
    else
        log "read $n: white not on USB after the press"
    fi
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null
    launchctl bootstrap "gui/$UID" "$PL" 2>&1 >/dev/null
    sleep 1200
done
