#!/bin/bash
# d9_cam.sh LABEL VAL [HUE SAT]: JD's theme (Alphas/Mods, hue 178, sat 219) at value VAL
# on white over the data line, a 3 s clip from the bench phone, one frame kept and its
# bright points (the capless LEDs) read as R, G, B means; the value put back to 125 and
# the standing state restored. The D9 gate: the purple's red at the dim end, before/after.
set -u
cd /Users/jdlien/code/ak820-pro
L=${1:?label}; V=${2:?value}; HUE=${3:-178}; SAT=${4:-219}
H=history/rowisr-stage1-20261101/d9cam; mkdir -p $H
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a $H/d9cam.log; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3
present || { timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; for i in $(seq 1 8); do present && break; sleep 2; done; }
present || { log "asleep: one rig press"; venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; for i in $(seq 1 15); do present && break; sleep 1; done; }
present || { log "no board"; exit 1; }
TOK=$("$HOME/Library/Application Support/ak820pro/bin/ak820" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])')
venv/bin/python - "$HUE" "$SAT" "$V" <<'PY'
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
from rowisr_baseline import set_lighting
h = open_device()
try: set_lighting(h, int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
finally: h.close()
PY
sleep 2
log "$L: token $TOK, hue $HUE sat $SAT val $V: a 3 s clip"
venv/bin/python scripts/phonecam.py record 3 --out $H 2>&1 | sed -n 1p | tee -a $H/d9cam.log
C=$(ls -t $H/*.mp4 | head -1); F=$H/frame-$L-v$V.ppm
ffmpeg -loglevel error -y -i "$C" -vf "select=eq(n\,300)" -frames:v 1 -f image2 -pix_fmt rgb24 "$F"
ffmpeg -loglevel error -y -i "$C" -vf "select=eq(n\,300),scale=540:-1" -frames:v 1 -q:v 3 $H/frame-$L-v$V.jpg
python3 - "$F" "$L" <<'PY' | tee -a $H/d9cam.log
import sys
d = open(sys.argv[1], "rb").read(); parts = d.split(b"\n", 3); W, H = map(int, parts[1].split()); A = parts[3]
def mean(cx, cy, r):
    n = 0; acc = [0, 0, 0]
    for y in range(max(0, cy - r), min(H, cy + r)):
        for x in range(max(0, cx - r), min(W, cx + r)):
            i = (y * W + x) * 3; acc[0] += A[i]; acc[1] += A[i + 1]; acc[2] += A[i + 2]; n += 1
    return tuple(round(a / n, 1) for a in acc)
bs = 24; pts = []
for by in range(0, H - bs, bs):
    for bx in range(300, W - bs, bs):
        cx, cy = bx + bs // 2, by + bs // 2
        r, g, b = mean(cx, cy, 8)
        if max(r, g, b) > 60 and not any(abs(cx - x) < 50 and abs(cy - y) < 50 for x, y, _ in pts): pts.append((cx, cy, (r, g, b)))
print(f"{sys.argv[2]}: bright points (x, y): R, G, B in a 16 px window: " + "; ".join(f"({x},{y}): {c}" for x, y, c in pts[:8]))
PY
venv/bin/python hostagent/ak820lighting.py restore history/rowisr-stage1-20261101/lighting-5h-jd-choice.json >/dev/null 2>&1   # his Alphas/Mods at 125 back (set_lighting is Solid)
venv/bin/python hostagent/ak820lighting.py show 2>/dev/null | head -1 | tee -a $H/d9cam.log
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; sleep 3
launchctl bootstrap "gui/$UID" ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist 2>/dev/null
log "$L done; the standing state"
