#!/bin/bash
# The presser's short-tap gate on white, counted at the board (the plan's
# "The key-press rig": the delivery gate is commanded closures against
# key_presses, after debounce, and raw_edges, before it; a press is one
# key_press and two raw edges, so a phantom or a miss shows as a count off by
# one). Each batch is pressed from the logger's REPL (scripts/presser_repl.py:
# the logger paused for the batch and checked logging again after), the
# counts read before and after over the data line with the daemon paused.
# The batches: 200 at 25 ms and 200 at 15 ms dwell on A1 ((0,13), F19), 200
# at 25 ms on A0 ((3,14), F20); the debounce boundary 12, 10 and 8 ms, 100
# each on A1 (sym_defer_pk, 5 ms: the old rig put the boundary near 10 ms);
# then 100 at 25 ms on A1 with A0 held throughout (the cross-row chord: A0
# counts one press of its own). The dwell is the board's clock, ~1 ms
# resolution, the actual min/max/mean reported. Data off and the daemon back
# by the trap. Usage: presser_gate.sh LABEL [TOKEN]; results in
# presser-gate-LABEL.json and presser-gate-LABEL.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
LABEL=${1:-exit}; WANT=${2:-0x9e2d894a}
D=history/rowisr-stage1-20261101
OUT="$D/presser-gate-$LABEL.json"
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 5); do present && break; sleep 2; done
if ! present; then   # asleep: one press of A1 wakes it (the Power saver ladder sleeps 3 min after the last key)
    log "white not on USB: asleep, one press to wake it"
    venv/bin/python scripts/presser_repl.py pulse A1 100 || { log "the wake press failed"; exit 1; }
    for i in $(seq 1 15); do present && break; sleep 1; done
    present || { log "no board on USB after the wake press"; exit 1; }
    log "white awake"
fi
sleep 2
T=$(token); log "token $T (want $WANT)"
[ "$T" = "$WANT" ] || { log "not the expected build: stopping"; exit 1; }
echo "[" > "$OUT"; first=1
run() {   # pin n dwell gap [--hold PIN]
    local pin=$1 n=$2 dwell=$3 gap=$4; shift 4
    local before after batch rc
    before=$(venv/bin/python scripts/presser_count.py) || { log "count failed"; return 1; }
    batch=$(venv/bin/python scripts/presser_repl.py batch "$pin" "$n" "$dwell" "$gap" "$@" 2>&1); rc=$?
    echo "$batch" | grep -v '^BATCH' 
    [ $rc = 0 ] || { log "presser run failed (rc $rc): stopping"; echo "]" >> "$OUT"; exit 2; }
    sleep 1.5
    after=$(venv/bin/python scripts/presser_count.py) || { log "count failed"; return 1; }
    [ $first = 1 ] || echo "," >> "$OUT"; first=0
    BEFORE="$before" AFTER="$after" BATCH="$(echo "$batch" | grep '^BATCH')" python3 - "$pin" "$n" "$dwell" "$gap" "$*" >> "$OUT" <<'PY'
import json, os, sys, time
pin, n, dwell, gap, extra = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
b, a = json.loads(os.environ["BEFORE"]), json.loads(os.environ["AFTER"])
kv = dict(t.split("=") for t in os.environ["BATCH"].split()[1:])
hold = "--hold" in extra
exp_kp, exp_re = n + (1 if hold else 0), 2 * n + (2 if hold else 0)
d = {k: (a[k] - b[k]) & 0xFFFF for k in ("key_presses",)}
d.update({k: (a[k] - b[k]) & 0xFFFFFFFF for k in ("raw_edges", "consumes", "cooked_changes")})
r = {"pin": pin, "n": n, "dwell_ms": dwell, "gap_ms": gap, "hold": extra.split()[-1] if hold else None,
     "dwell_us": {k[6:-3]: int(kv[k]) for k in ("dwell_min_us", "dwell_max_us", "dwell_mean_us")},
     "deltas": d, "expected": {"key_presses": exp_kp, "raw_edges": exp_re},
     "row_gap_max_ms_after": a.get("row_gap_max_ms"), "t": time.strftime("%H:%M:%S")}
r["pass"] = d["key_presses"] == exp_kp and d["raw_edges"] == exp_re
print(json.dumps(r))
verdict = "PASS" if r["pass"] else ("MISSING" if d["key_presses"] < exp_kp else "PHANTOM")
print(f"[{r['t']}] {pin} x{n} at {dwell} ms{' with ' + r['hold'] + ' held' if hold else ''}: key_presses {d['key_presses']:+d} "
      f"(expected {exp_kp}), raw_edges {d['raw_edges']:+d} (expected {exp_re}), dwell actual "
      f"{r['dwell_us']['min']}-{r['dwell_us']['max']} us, row_gap_max {a.get('row_gap_max_ms')} ms -> {verdict}", file=sys.stderr)
PY
}
run A1 200 25 75
run A1 200 15 85
run A0 200 25 75
run A1 100 12 88
run A1 100 10 90
run A1 100 8 92
run A1 100 25 75 --hold A0
echo "]" >> "$OUT"
python3 - "$OUT" <<'PY'
import json, sys
rs = json.load(open(sys.argv[1]))
print(f"RESULT: {sum(1 for r in rs if r['pass'])} of {len(rs)} batches exact")
PY
log "done -> $OUT"
