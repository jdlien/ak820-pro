#!/bin/bash
# Stage 5h's three clean builds from the row-isr HEAD (the worktree, row-isr): dev
# (the candidate for white), daily (the detector out: the check and the heap
# gap), devprobe (the floor probe's flavour proven to build). The logs beside.
cd "$(dirname "$0")/../.." || exit 1
export AK820_QMK_HOME=/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr
D=history/rowisr-stage1-20261101
for f in dev daily devprobe; do
    echo "[$(date +%H:%M:%S)] build $f"
    ./build.sh "$f" > "$D/build-stage5h-$f.log" 2>&1
    echo "[$(date +%H:%M:%S)] $f: $(tail -3 "$D/build-stage5h-$f.log" | grep -E 'BUILD OK|FAIL|RAM:' | tr '\n' ' ')"
done
echo "[$(date +%H:%M:%S)] builds done"
