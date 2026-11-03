#!/bin/bash
# Stage 5's load and light holds after the presser gates (plans/ROW-ISR-PLAN.md,
# "Stage 5: the cadence"; codex's judgment of 13:21): (1) a mixed-load window
# with the daemon running (its syncs and the LCD's text), a burst of 300
# clock-chip reads (dev op 23) and a presser batch through it, then the
# omissions and the UART kinds (the gate: under 0.1%); (2) the dark hold on
# this build (the lights off by Power saver's ladder 3 min after the last
# key, the board held awake by the data line), the logger's mean, against
# 4b's 31.1 mA; (3) the per-colour and value-64 holds through VIA's lighting
# channel (hostagent/ak820lighting.py restore from a temporary backup: red,
# green, blue at full, white at 64, the logger's mean each, JD's lighting
# restored from ~/Documents/ak820pro-lighting.json after). Usage:
# stage5_loads.sh TOKEN [LABEL] [STEPS=123]
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
WANT=${1:?token}; L=${2:-stage5d}; STEPS=${3:-123}
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
power_mean() { tail -"$1" history/power-bench-2026-10-15/power.csv | awk -F, '{s+=$6; n++} END {if (n) printf "%.2f", s/n}'; }
wake_on_data() {
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
    for i in $(seq 1 5); do present && return 0; sleep 2; done
    venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1
    for i in $(seq 1 15); do present && return 0; sleep 1; done
    return 1
}
ladder() {   # the mode written and read back, once more if it did not take (5e's first window, 13:35)
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
    else: print(f"the ladder did NOT take: mode {got}, wanted {want}")
finally: h.close()
PY
}
standing() { sleep 2; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "the standing state"; }
reset_counters() { venv/bin/python -c "import sys; sys.path.insert(0, 'hostagent'); import ak820health as hp; hp.reset_counters()"; }

case "$STEPS" in *1*)
log "1. the mixed-load window: the daemon up, a 300-read burst, 200 presses, 120 s"
wake_on_data || { log "no board"; standing; exit 1; }
sleep 3; ladder 0; venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; sleep 3
reset_counters; venv/bin/python scripts/overrun_diag.py reset >/dev/null 2>&1
launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "the daemon up (its sync, the text)"
sleep 20
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 2   # the HID is exclusive on macOS: the burst and the presser need it
venv/bin/python scripts/overrun_diag.py burst 300 --lo 40 --hi 80 2>&1 | tail -1
venv/bin/python scripts/presser_repl.py batch A1 200 25 75 2>&1 | grep -v '^BATCH' | tail -1
launchctl bootstrap "gui/$UID" "$PL" 2>&1; sleep 60
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 2
log "the window's end: page 7, the record, the UART kinds"
venv/bin/python hostagent/ak820health.py --sched 2>&1 | grep -E "slots_elapsed|pulses_|latency|missed" | tee "$D/mixed-sched-$L.txt"
venv/bin/python scripts/rowisr_diag.py record 2>&1 | tee "$D/mixed-record-$L.txt" | head -3
venv/bin/python scripts/overrun_diag.py status 2>&1 | tee "$D/mixed-overrun-$L.txt" | grep -iE "OE total|overrun|kind|ack|timeout" | head -10
"$A" health 2>&1 | grep -iE "tx_|ack|stall|ge_25|ge_10" | tee "$D/mixed-health-$L.txt"
ladder 2; standing
;; esac
case "$STEPS" in *2*)
log "2. the dark hold: Power saver's lights off at 3 min idle, the board awake on the data line; 240 s"
wake_on_data || { log "no board"; standing; exit 1; }
sleep 3; ladder 2; venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1
sleep 240
DARK=$(power_mean 60); log "the dark draw on this build: $DARK mA (4b: 31.1); lit at full white 92.32: incremental $(python3 -c "print(round(92.32 - $DARK, 2))")"
echo "dark_mA $DARK" > "$D/dark-$L.txt"
standing
;; esac
case "$STEPS" in *3*)
log "3. the per-colour and value-64 holds through the lighting channel (JD's lighting restored after)"
wake_on_data || { log "no board"; standing; exit 1; }
sleep 3; ladder 0; venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; sleep 2
venv/bin/python hostagent/ak820lighting.py dump "$D/lighting-before-holds-$L.json" >/dev/null 2>&1 || cp ~/Documents/ak820pro-lighting.json "$D/lighting-before-holds-$L.json"
for spec in "red 0 255 255" "green 85 255 255" "blue 170 255 255" "white64 0 0 64" "white255 0 0 255"; do
    set -- $spec; name=$1; hue=$2; sat=$3; val=$4
    python3 - "$D/lighting-before-holds-$L.json" "$hue" "$sat" "$val" "/tmp/hold-$name.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d['hue'], d['sat'], d['val'] = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
json.dump(d, open(sys.argv[5], 'w'))
PY
    venv/bin/python hostagent/ak820lighting.py restore "/tmp/hold-$name.json" >/dev/null 2>&1 || log "the hold $name's restore failed"
    sleep 45
    M=$(power_mean 30); DRV=$(venv/bin/python hostagent/ak820battery.py 2>/dev/null | grep -oE "led drive +[0-9.]+ %" | grep -oE "[0-9.]+ %" | head -1)
    log "hold $name (h$hue s$sat v$val): $M mA; the drive accounting (D8, led_pm): $DRV of maximum (expect white255 100, red/green/blue 33.3, white64 25.1)"
    echo "$name $M ${DRV:-?}" >> "$D/holds-$L.txt"
done
venv/bin/python hostagent/ak820lighting.py restore "$D/lighting-before-holds-$L.json" >/dev/null 2>&1; log "JD's lighting restored from the dump taken before the holds"
venv/bin/python hostagent/ak820lighting.py show 2>&1 | head -5
ladder 2; standing
;; esac
case "$STEPS" in *4*)
log "4. the value ladder on the logger: the Solid colour effect (JD's Alphas/Mods keeps the mods lit at their own colour, so its value 0 drew 41.9 mA, 14:12), white at 0, 32, 64, 96, 128 (the low cap's ceiling), a keep-lit press before each (below 15% the dim comes at 1 min and the lights off at 3), 40 s each; the gate: the incremental current linear in the drive accounting's share (the bytes are the CIE curve of the value, so the accounting is the byte, not the value)"
wake_on_data || { log "no board"; standing; exit 1; }
sleep 3; ladder 0; venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; sleep 2
venv/bin/python hostagent/ak820lighting.py dump "$D/lighting-before-ladder-$L.json" >/dev/null 2>&1 || cp ~/Documents/ak820pro-lighting.json "$D/lighting-before-ladder-$L.json"
: > "$D/valueladder-$L.txt"
for val in 0 32 64 96 128; do
    python3 - "$D/lighting-before-ladder-$L.json" "$val" "/tmp/ladder-$val.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d['animation_index'], d['hue'], d['sat'], d['val'] = 1, 0, 0, int(sys.argv[2])   # 1: Solid colour
json.dump(d, open(sys.argv[3], 'w'))
PY
    venv/bin/python hostagent/ak820lighting.py restore "/tmp/ladder-$val.json" >/dev/null 2>&1 || log "value $val: the restore failed"
    venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1   # keep-lit: the dim at 1 min under the cap
    sleep 40
    M=$(power_mean 25); DRV=$(venv/bin/python hostagent/ak820battery.py 2>/dev/null | grep -oE "led drive +[0-9.]+ %" | grep -oE "[0-9.]+" | head -1)
    log "value $val: $M mA, the drive accounting ${DRV:-?} % of maximum"; echo "$val $M ${DRV:-?}" >> "$D/valueladder-$L.txt"
done
venv/bin/python hostagent/ak820lighting.py restore "$D/lighting-before-ladder-$L.json" >/dev/null 2>&1; log "JD's lighting restored"
python3 - "$D/valueladder-$L.txt" <<'PY'
import sys
rows=[l.split() for l in open(sys.argv[1]) if l.strip()]
pts=[(int(r[0]), float(r[1]), r[2]) for r in rows]
dark=next((m for v,m,_ in pts if v==0), None)
print("value -> mA over the dark base against the drive accounting's share (the byte's), the mA per % of full (61 mA at 100% is the full-white reference):")
for v,m,d in pts:
    if v==0: print(f"  {v:3d}: {m:6.2f} (dark)"); continue
    inc=m-dark
    try: pct=float(d); per=inc/pct if pct else float('nan'); print(f"  {v:3d}: {m:6.2f}  +{inc:5.2f} mA  drive {pct:5.1f} %  -> {per*100:6.1f} mA at 100% by this step")
    except ValueError: print(f"  {v:3d}: {m:6.2f}  +{inc:5.2f} mA  drive ?")
PY
ladder 2; standing
;; esac
log "stage 5's load and light holds done ($STEPS)"
