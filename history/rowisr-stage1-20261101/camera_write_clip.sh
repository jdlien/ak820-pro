#!/bin/bash
# The camera gate on stage 4b with the write forced on cue (plans/ROW-ISR-PLAN.md,
# stage 4: "a forced PCF write filmed shows no dark frame"). The daemon's
# own sync proved a poor trigger (its write needs a whole-second change
# and the 10-min no-key rule, and three runs missed it), so the write is
# forced: with the daemon paused, `ak820ctl clock` (the host's time, the
# protocol-2 transaction the daemon also runs) makes the clock chip's
# write pending (pcf_sync_host_accepted), and a sparse dev op 23 burst
# running meanwhile admits it at once (pcf_start_ok() returns true while a
# burst is active, and the burst steps only between the writer's runs), so
# the writer's transactions run unmasked right after the sync. In the
# clip: the control at T (20 held reads 100 ms apart, dips a frame 25
# frames apart), the marker burst from T+4 (held reads every 250 ms = 60
# frames, dips on that lattice), a sync at T+5.5 and another at T+9, each
# followed by the writer's run: NO dip off the lattice is the gate. White awake on the data line, the lights on (the ladder at
# Always on), the daemon paused, nothing else on the raw HID, nothing in
# the frame. Usage: camera_write_clip.sh LABEL HH:MM:SS [CROP]
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
L=${1:?label}; T=${2:?the start of the control, HH:MM:SS}; CROP=${3:-1650:670:110:30}
OUT="$HOME/Documents/ak820pro-phonecam/clips"; mkdir -p "$OUT"
CTL=time-util-ak820pro/ak820ctl
log() { echo "[$(date +%H:%M:%S.%N | cut -c1-12)] $*"; }
until_epoch() { local w=$(( $1 - $(date +%s) )); [ "$w" -gt 0 ] && sleep "$w"; }
until_ms() { python3 -c "import time,sys; w=float(sys.argv[1])-time.time(); time.sleep(w) if w>0 else None" "$1"; }
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' || { log "white not on USB"; exit 1; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 1
tgt=$(date -j -f "%H:%M:%S" "$T" +%s 2>/dev/null); [ -n "$tgt" ] || { log "bad time $T"; exit 1; }
log "T=$T: the clip at T-5, the control at T, the markers from T+4, a sync at T+5.5 and at T+9 (each the writer's unmasked write), the stop at T+17; waiting"
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
log "T: the control, 20 held reads 100 ms apart"
for i in 1 2 3 4 5 6; do
    out=$(venv/bin/python scripts/overrun_diag.py burst 20 --lo 100 --hi 100 2>&1 | tail -1)
    case "$out" in *"'active': True"*) log "the control armed (try $i)"; break;; *) log "the control refused (try $i): $out"; sleep 0.7;; esac
done
until_ms $((tgt + 3))
venv/bin/python scripts/overrun_diag.py burst stop >/dev/null 2>&1
until_ms $((tgt + 4))
log "T+4: the markers, 40 held reads 250 ms apart (10 s)"
out=$(venv/bin/python scripts/overrun_diag.py burst 40 --lo 250 --hi 250 2>&1 | tail -1); log "markers: $out"
until_ms $(python3 -c "print($tgt + 5.5)")
log "T+5.5: the first sync (ak820ctl's transaction, the host's time): the clock chip's write pending, admitted at once by the burst, unmasked"
$CTL clock 2>&1 | tail -1
until_ms $(python3 -c "print($tgt + 9)")
log "T+9: the second sync: a second write"
$CTL clock 2>&1 | tail -1
until_ms $((tgt + 15))
venv/bin/python scripts/overrun_diag.py burst stop >/dev/null 2>&1
wait $REC; log "the recording's end (rc $?)"
grep -E "mp4|gap|start key" "$D/camera-$L-record.log"
sleep 1
venv/bin/python hostagent/rtc_phase0.py status 2>/dev/null | grep 'page4' | tee "$D/camera-$L-page4-after.txt"
python3 - "$D/camera-$L-page4-before.txt" "$D/camera-$L-page4-after.txt" <<'PY'
import re, sys
def runs(f):
    m = re.search(r"'runs_ok': (\d+)", open(f).read()); return int(m.group(1)) if m else None
b, a = runs(sys.argv[1]), runs(sys.argv[2])
print(f"the writer's runs: {b} -> {a} ({'the writes happened' if a is not None and b is not None and a >= b + 2 else ('ONE write' if a == b + 1 else 'NO WRITE')})")
PY
$CTL clock --read 2>&1 | tail -2
CLIP=$(grep -oE '/[^ ]+\.mp4' "$D/camera-$L-record.log" | head -1)
[ -n "$CLIP" ] && [ -f "$CLIP" ] || { log "no clip pulled"; exit 1; }
python3 scripts/clip_dips.py "$CLIP" --crop "$CROP" --csv "$D/camera-$L-luma.csv" | tee "$D/camera-$L-dips.txt"
