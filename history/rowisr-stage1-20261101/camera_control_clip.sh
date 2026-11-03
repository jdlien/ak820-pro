#!/bin/bash
# The camera's visibility check: one 240 fps clip of white's lights from the
# tripod with the positive control in it (dev op 23's burst: 20 held 7-byte
# clock-chip reads 100 ms apart, the row ISR held off through each, so a
# ~3 ms dark gap every 100 ms for 2 s), then scripts/clip_dips.py on the
# clip: the control should show as 20 dips 24 frames apart. White must be
# awake on the data line WITH ITS LIGHTS ON (Power saver turns them off 3 min
# after the last key: hold the ladder at Always on, dev op 14 [1,0], and press
# a key). Usage: camera_control_clip.sh [LABEL] [SECONDS] [CROP] (the clip's
# length, default 8, the burst 3 s after the start key; CROP an ffmpeg
# W:H:X:Y to measure the keys alone, 990:410:260:100 for the 11-03 framing).
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
L=${1:-control}; S=${2:-8}; CROP=${3:-}
OUT="$HOME/Documents/ak820pro-phonecam/clips"; mkdir -p "$OUT"
log() { echo "[$(date +%H:%M:%S.%N | cut -c1-12)] $*"; }
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' || { log "white not on USB"; exit 1; }
python3 scripts/phonecam.py record "$S" --out "$OUT" > "$D/camera-$L-record.log" 2>&1 &
REC=$!
sleep 3
log "the burst: 20 held reads 100 ms apart (dark gaps expected for 2 s)"
venv/bin/python scripts/overrun_diag.py burst 20 --lo 100 --hi 100 2>&1 | tail -1
sleep 2.5
venv/bin/python scripts/overrun_diag.py burst stop >/dev/null 2>&1
log "the burst done"
wait $REC; log "the recording's end (rc $?)"; cat "$D/camera-$L-record.log"
CLIP=$(grep -oE '/[^ ]+\.mp4' "$D/camera-$L-record.log" | head -1)
[ -n "$CLIP" ] && [ -f "$CLIP" ] || { log "no clip pulled"; exit 1; }
python3 scripts/clip_dips.py "$CLIP" ${CROP:+--crop "$CROP"} --csv "$D/camera-$L-luma.csv" | tee "$D/camera-$L-dips.txt"
