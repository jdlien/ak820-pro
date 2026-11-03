#!/bin/bash
# Waits for a key to wake white (the power logger: two samples over 20 mA,
# above the Mac's lock-light bursts into the sleeping module at ~14 mA and
# below any wake, dark ~28 mA or lit ~46), then runs trim_flash.sh: the
# trim's flash and its warm windows. Launched detached on JD's go (23:03
# 11-02); its log is trim-on-wake.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
CSV=history/power-bench-2026-10-15/power.csv
log() { echo "[$(date +%H:%M:%S)] $*"; }
log "waiting for white to wake (two logger samples over 20 mA); last: $(tail -1 "$CSV" | cut -d, -f1,6)"
n=0
while :; do
    ma=$(tail -1 "$CSV" | cut -d, -f6)
    if awk -v m="$ma" 'BEGIN{exit !(m+0 > 20)}'; then n=$((n+1)); else n=0; fi
    [ "$n" -ge 2 ] && break
    sleep 1
done
log "white awake ($ma mA); trim_flash.sh starts"
"$D/trim_flash.sh" 2>&1 | tee "$D/trim-flash.log"
log "trim_flash.sh exit ${PIPESTATUS[0]}"
