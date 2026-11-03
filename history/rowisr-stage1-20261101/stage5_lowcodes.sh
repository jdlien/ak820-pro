#!/bin/bash
# Stage 5's low-code gate by camera (plans/ROW-ISR-PLAN.md, "Stage 5: the
# cadence": the lowest codes, values 1-16, monotonic): the room dark from
# the Mac, the ladder held, white's lighting set through VIA's channel to
# solid white at each value (ak820lighting.py restore of a temporary file),
# a 3 s clip of each from the tripod (phonecam.py record), the keys' mean
# luma over the clip's middle second (clip_dips.py's CSV); then JD's
# lighting restored from the dump taken first. The gate: the luma
# monotonic in the value with no plateau at the bottom, and the ratios
# against the value compared with the model (a linear scale: 1, 2, 4, 8,
# 16 should sit on a line through the dark level). Usage:
# stage5_lowcodes.sh TOKEN [LABEL] [VALUES="0 1 2 4 8 16 32 64"]
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
WANT=${1:?token}; L=${2:-stage5d}; VALUES=${3:-"0 1 2 4 8 16 32 64"}
OUT="$HOME/Documents/ak820pro-phonecam/clips"; CROP=1650:670:110:30
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
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
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
for i in $(seq 1 5); do present && break; sleep 2; done
present || { venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; for i in $(seq 1 15); do present && break; sleep 1; done; }
present || { log "no board"; exit 1; }
sleep 2; ladder 0; venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; sleep 2
venv/bin/python hostagent/ak820lighting.py dump "$D/lighting-before-lowcodes-$L.json" >/dev/null 2>&1 || cp ~/Documents/ak820pro-lighting.json "$D/lighting-before-lowcodes-$L.json"
python3 scripts/studio_lights.py off 2>&1 | tail -1
: > "$D/lowcodes-$L.txt"
for v in $VALUES; do
    python3 - "$D/lighting-before-lowcodes-$L.json" "$v" "/tmp/lowcode-$v.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d['hue'], d['sat'], d['val'] = 0, 0, int(sys.argv[2])
json.dump(d, open(sys.argv[3], 'w'))
PY
    venv/bin/python hostagent/ak820lighting.py restore "/tmp/lowcode-$v.json" >/dev/null 2>&1 || log "value $v: the restore failed"
    sleep 2
    python3 scripts/phonecam.py record 3 --out "$OUT" > "/tmp/lowcode-rec-$v.log" 2>&1
    CLIP=$(grep -oE '/[^ ]+\.mp4' "/tmp/lowcode-rec-$v.log" | head -1)
    if [ -n "$CLIP" ] && [ -f "$CLIP" ]; then
        python3 scripts/clip_dips.py "$CLIP" --crop "$CROP" --csv "/tmp/lowcode-$v.csv" >/dev/null 2>&1
        M=$(awk -F, 'NR>1 && $1>=240 && $1<480 {s+=$4; n++} END {if (n) printf "%.3f", s/n}' "/tmp/lowcode-$v.csv")
        log "value $v: mean luma $M (the clip's second second)"; echo "$v $M $CLIP" >> "$D/lowcodes-$L.txt"
    else
        log "value $v: no clip"; echo "$v - -" >> "$D/lowcodes-$L.txt"
    fi
done
python3 scripts/studio_lights.py restore 2>&1 | tail -1
venv/bin/python hostagent/ak820lighting.py restore "$D/lighting-before-lowcodes-$L.json" >/dev/null 2>&1; log "JD's lighting restored"
ladder 2; sleep 2; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "the standing state"
python3 - "$D/lowcodes-$L.txt" <<'PY'
import sys
rows=[l.split() for l in open(sys.argv[1]) if l.strip() and l.split()[1] != '-']
pts=[(int(r[0]), float(r[1])) for r in rows]
dark=next((m for v,m in pts if v==0), None)
print("value -> luma (minus the dark level):")
prev=None; mono=True
for v,m in pts:
    d = m - dark if dark is not None else m
    if prev is not None and v>0 and d <= prev: mono=False
    print(f"  {v:3d}: {m:7.3f}  {'' if dark is None else f'{d:+7.3f}'}  {'' if v==0 or dark is None or d<=0 else f'per unit {d/v:.3f}'}")
    if v>0: prev=d
print("monotonic:", mono)
PY
