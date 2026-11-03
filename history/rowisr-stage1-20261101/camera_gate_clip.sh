#!/bin/bash
# The camera gate on stage 4b, filmed from the Mac (plans/ROW-ISR-PLAN.md,
# stage 4: "a forced PCF write filmed shows no dark frame"): one 240 fps clip
# holding the positive control (dev op 23's burst, 20 held reads 100 ms
# apart: a dip a frame, 25 frames apart, the camera's proof it sees a ~3 ms
# dark gap) and then the clock writer's own unmasked write, triggered by the
# daemon's sync as it starts (sync (enumerated) ~2 s after the start), which
# the firmware admits on the data line only once 10 min have passed without
# a key (pcf-unseen) and WITH THE LIGHTS ON, which Power saver's ladder
# turns off 3 min after a key: hold it at Always on (dev op 14 [1,0]) and
# relight with a press at least 10 min before T. White awake on the data
# line, the daemon paused, nothing else on its raw HID (the 11:05 run lost
# its control to "raw HID busy"), nothing in the frame (the 11:05 run had
# an arm in it). Page 4 before and after (runs_ok +1 says the write
# happened); scripts/clip_dips.py on the clip: the control's dips and
# nothing after. The events sit on the wall clock: the clip from T-5 to
# T+17, the burst at T (retried on a busy HID), the daemon at T+6.
# Usage: camera_gate_clip.sh LABEL HH:MM:SS [CROP]
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
L=${1:?label}; T=${2:?the start of the control, HH:MM:SS}; CROP=${3:-1650:670:110:30}
OUT="$HOME/Documents/ak820pro-phonecam/clips"; mkdir -p "$OUT"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S.%N | cut -c1-12)] $*"; }
until_epoch() { local w=$(( $1 - $(date +%s) )); [ "$w" -gt 0 ] && sleep "$w"; }
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' || { log "white not on USB"; exit 1; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 1
tgt=$(date -j -f "%H:%M:%S" "$T" +%s 2>/dev/null); [ -n "$tgt" ] || { log "bad time $T"; exit 1; }
log "T=$T: the clip at T-5, the burst at T, the daemon at T+6, the stop at T+17; waiting"
until_epoch $((tgt - 20))
venv/bin/python hostagent/rtc_phase0.py status 2>/dev/null | grep 'page4' | tee "$D/camera-$L-page4-before.txt"
venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'hostagent')
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try: print("power mode (0 = Always on, needed):", devhook(h, 14, [0])[4])
finally: h.close()
PY
until_epoch $((tgt - 5))
log "T-5: the clip starts (22 s)"
python3 scripts/phonecam.py record 22 --out "$OUT" > "$D/camera-$L-record.log" 2>&1 &
REC=$!
until_epoch "$tgt"
log "T: the control, 20 held reads 100 ms apart (dips expected for 2 s)"
for i in 1 2 3 4 5 6; do
    out=$(venv/bin/python scripts/overrun_diag.py burst 20 --lo 100 --hi 100 2>&1 | tail -1)
    case "$out" in *"'active': True"*) log "the burst armed (try $i): $out"; break;; *) log "the burst refused (try $i): $out"; sleep 0.7;; esac
done
until_epoch $((tgt + 6))
log "T+6: the daemon started; its sync and the writer's unmasked write follow within seconds (no dip expected)"
launchctl bootstrap "gui/$UID" "$PL" 2>&1
venv/bin/python scripts/overrun_diag.py burst stop >/dev/null 2>&1 &
wait $REC; log "the recording's end (rc $?)"
grep -E "mp4|gap|start key" "$D/camera-$L-record.log"
sleep 2
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 2; log "the daemon paused again"
grep -E "^$(date +%Y-%m-%d) " ~/Library/Logs/ak820pro/ak820-agent.log | tail -4 | cut -c1-150
venv/bin/python hostagent/rtc_phase0.py status 2>/dev/null | grep 'page4' | tee "$D/camera-$L-page4-after.txt"
python3 - "$D/camera-$L-page4-before.txt" "$D/camera-$L-page4-after.txt" <<'PY'
import re, sys
def runs(f):
    m = re.search(r"'runs_ok': (\d+)", open(f).read()); return int(m.group(1)) if m else None
b, a = runs(sys.argv[1]), runs(sys.argv[2])
print(f"the writer's runs: {b} -> {a} ({'the write happened' if a is not None and b is not None and a > b else 'NO WRITE: the deferral still held, or the sync did not land'})")
PY
CLIP=$(grep -oE '/[^ ]+\.mp4' "$D/camera-$L-record.log" | head -1)
[ -n "$CLIP" ] && [ -f "$CLIP" ] || { log "no clip pulled"; exit 1; }
python3 scripts/clip_dips.py "$CLIP" --crop "$CROP" --csv "$D/camera-$L-luma.csv" | tee "$D/camera-$L-dips.txt"
