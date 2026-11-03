#!/bin/bash
# Q1's delay sweep on stage 3 (plans/ROW-ISR-PLAN.md, Q1; stage 3's first
# gate): the column settle after the row select (op 28 sub 13, HCLK ticks at
# 48 MHz) swept down from 96 (2 us) to 0 with a cross-row chord held and each
# colour active. Per setting: A0 ((3,14)) held through 100 presses of A1
# ((0,13)) at 15 ms dwell; the counts at the scan (sub 12: the rig's keys'
# presses and releases, every other key's presses) and after debounce
# (key_presses) read around each batch; exact means key0 100/100, key1 1/1,
# nothing elsewhere, key_presses +101. First with the lighting as JD has it
# at every setting, then Solid red, green and blue at full (VIA's lighting
# channel, hue 0, 85, 170, sat and val 255) at 96, 24, 6 and 0; JD's
# lighting restored from ~/Documents/ak820pro-lighting.json and the settle
# put back to 96 by the trap. Daemon paused, data on, both undone by the
# trap. Usage: settle_sweep.sh LABEL [TOKEN]; results settle-sweep-LABEL.json/.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
LABEL=${1:-stage3}; WANT=${2:-}
D=history/rowisr-stage1-20261101
OUT="$D/settle-sweep-$LABEL.json"
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
TMPL=/private/tmp/claude-501/-Users-jdlien-code-ak820-pro/2a31fef6-0933-442c-8d0e-4cfef52909e2/scratchpad/lighting-sweep.json
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
restore_all() {
    venv/bin/python scripts/rowisr_diag.py settle 96 >/dev/null 2>&1 && log "settle back to 96"
    venv/bin/python hostagent/ak820lighting.py restore "$HOME/Documents/ak820pro-lighting.json" >/dev/null 2>&1 && log "JD's lighting restored"
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"
}
trap restore_all EXIT
sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"   # the pause: an on right after another script's off hung uhubctl twice on 11-03 (26 and 22 min)
for i in $(seq 1 5); do present && break; sleep 2; done
if ! present; then
    log "white not on USB: asleep, one press to wake it"
    venv/bin/python scripts/presser_repl.py pulse A1 100 || exit 1
    for i in $(seq 1 15); do present && break; sleep 1; done
    present || { log "no board after the wake press"; exit 1; }
fi
sleep 2
T=$(token); log "token $T${WANT:+ (want $WANT)}"
[ -z "$WANT" ] || [ "$T" = "$WANT" ] || { log "not the expected build: stopping"; exit 1; }
venv/bin/python scripts/rowisr_diag.py rig --json >/dev/null || { log "no rig counters: not a stage 3 build"; exit 1; }
echo "[" > "$OUT"; first=1
one() {   # colour settle
    local colour=$1 settle=$2 before after rig batch rc
    venv/bin/python scripts/rowisr_diag.py settle "$settle" >/dev/null || return 1
    venv/bin/python scripts/rowisr_diag.py rig --json >/dev/null
    sleep 1.5
    idle=$(venv/bin/python scripts/rowisr_diag.py rig --json)   # 1.5 s with nothing pressed: phantoms at this setting?
    before=$(venv/bin/python scripts/presser_count.py) || return 1
    venv/bin/python scripts/rowisr_diag.py rig --json >/dev/null
    batch=$(venv/bin/python scripts/presser_repl.py batch A1 100 15 85 --hold A0 2>&1); rc=$?
    echo "$batch" | grep -v '^BATCH' | grep -v 'logger\|REPL\|held\|released' 
    [ $rc = 0 ] || { log "presser run failed (rc $rc)"; return 2; }
    sleep 1.5
    after=$(venv/bin/python scripts/presser_count.py) || return 1
    rig=$(venv/bin/python scripts/rowisr_diag.py rig --json)
    [ $first = 1 ] || echo "," >> "$OUT"; first=0
    BEFORE="$before" AFTER="$after" RIG="$rig" IDLE="$idle" python3 - "$colour" "$settle" >> "$OUT" <<'PY'
import json, os, sys, time
colour, settle = sys.argv[1], int(sys.argv[2])
b, a, rig, idle = (json.loads(os.environ[k]) for k in ("BEFORE", "AFTER", "RIG", "IDLE"))
kp = (a["key_presses"] - b["key_presses"]) & 0xFFFF
got = {k: [rig[k]["presses"], rig[k]["releases"]] for k in ("key0", "key1")}
idle_any = idle["key0"]["presses"] + idle["key1"]["presses"] + idle["other_presses"]
r = {"t": time.strftime("%H:%M:%S"), "colour": colour, "settle_ticks": settle, "settle_us": round(settle / 48, 3), "key_presses": kp,
     "scan": got, "other_presses": rig["other_presses"], "idle_presses": idle_any,
     "pass": kp == 101 and got == {"key0": [100, 100], "key1": [1, 1]} and rig["other_presses"] == 0 and idle_any == 0}
print(json.dumps(r))
print(f"[{r['t']}] {colour}, settle {settle} ticks ({r['settle_us']} us): key_presses +{kp} (want 101); at the scan (0,13) {got['key0'][0]}/{got['key0'][1]}, "
      f"(3,14) held {got['key1'][0]}/{got['key1'][1]}, elsewhere {rig['other_presses']}, idle {idle_any} -> {'PASS' if r['pass'] else 'FAIL'}", file=sys.stderr)
PY
}
for st in 96 48 24 12 6 3 0; do one "JD's lighting" $st || break; done
for hue in 0 85 170; do
    name=$([ $hue = 0 ] && echo red || ([ $hue = 85 ] && echo green || echo blue))
    printf '{"animation_index": 1, "hue": %d, "sat": 255, "val": 255, "speed": 231}\n' "$hue" > "$TMPL"
    venv/bin/python hostagent/ak820lighting.py restore "$TMPL" >/dev/null 2>&1 && log "lighting: Solid $name at full" || { log "lighting set failed"; break; }
    sleep 1
    for st in 96 24 6 0; do one "solid $name" $st || break; done
done
echo "]" >> "$OUT"
python3 - "$OUT" <<'PY'
import json, sys
rs = json.load(open(sys.argv[1]))
fails = [r for r in rs if not r["pass"]]
print(f"RESULT: {len(rs) - len(fails)} of {len(rs)} exact; the shortest exact setting per colour: " +
      ", ".join(f"{c} {min((r['settle_ticks'] for r in rs if r['colour'] == c and r['pass']), default='none')}" for c in dict.fromkeys(r['colour'] for r in rs)))
PY
log "done -> $OUT"
