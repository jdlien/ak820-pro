#!/bin/bash
# The row ISR rewrite's stage 1 A/B on white (plans/ROW-ISR-PLAN.md, stages 0
# and 1; 11-01), mid-drain on its pack: relay 2 is never touched. As
# audit-fixes-flash2-20261031/flash-white.sh: the daemon paused throughout,
# data on only for the session, the EXIT trap puts both back. Steps:
#   1. the baseline on the v0.3.0 candidate (token 0x6f758b40, the exact base);
#   2. flash.sh with stage 1 (via-dev-a8a567308d-20261101-121551.bin, 0x19884af9);
#   3. the same run on it;
#   4. compare.
# Usage: history/rowisr-stage1-20261101/session.sh [base|stage1|compare|all]
set -u
cd /Users/jdlien/code/ak820-pro
ART=ak820pro-builds/out/via-dev-a8a567308d-20261101-121551.bin
OUT=history/rowisr-stage1-20261101
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
BASE_TOKEN=0x6f758b40
S1_TOKEN=0x19884af9
STEP=${1:-all}
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
log() { echo "[$(date +%T)] $*"; }
wait_board() { for _ in $(seq 1 "${1:-60}"); do present && return 0; sleep 0.5; done; return 1; }

if [ "$STEP" = windows ]; then   # a later check on whatever runs: the windows only, no holds, label from $2
    LABEL=${2:-later}
    log "pausing the daemon"
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
    trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
    uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
    wait_board 60 || { log "no board on USB"; exit 1; }
    sleep 2
    log "board token: $(token)"
    venv/bin/python scripts/rowisr_baseline.py run --label "$LABEL" --out "$OUT" --skip-holds 2>&1 | tee "$OUT/run-$LABEL.log"
    exit "${PIPESTATUS[0]}"
fi

if [ "$STEP" = stage2 ]; then   # stage 2's bring-up: flash $2 (token $3) over whatever runs, the full run as stage2, compare against base
    ART2=$2; TOK2=$3
    log "pausing the daemon"
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
    trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
    uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
    wait_board 60 || { log "no board on USB (asleep? one key wakes it)"; exit 1; }
    sleep 2
    log "board token: $(token)"
    venv/bin/python hostagent/ak820battery.py > "$OUT/battery-before-stage2.txt" 2>&1
    log "flash: $ART2"
    ./flash.sh "$ART2" < /dev/null 2>&1 | tee "$OUT/flash-stage2.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; exit 1; }
    sleep 5
    wait_board 40 || { log "no board after the flash"; exit 1; }
    sleep 2
    T=$(token); log "token after the flash: $T (want $TOK2)"
    [ "$T" = "$TOK2" ] || { log "stage 2 is not what runs: stopping"; exit 1; }
    "$A" health > "$OUT/health-after-stage2-flash.txt" 2>&1
    venv/bin/python hostagent/ak820health.py --sched > "$OUT/sched-after-stage2-flash.txt" 2>&1
    venv/bin/python scripts/rowisr_baseline.py run --label stage2 --out "$OUT" 2>&1 | tee "$OUT/run-stage2.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "the stage 2 run failed"; exit 1; }
    venv/bin/python hostagent/ak820health.py --sched > "$OUT/sched-after-stage2-run.txt" 2>&1
    venv/bin/python scripts/rowisr_diag.py record > "$OUT/record-after-stage2-run.txt" 2>&1
    venv/bin/python scripts/rowisr_baseline.py compare "$OUT/base.json" "$OUT/stage2.json" | tee "$OUT/compare-stage2.txt"
    exit 0
fi

if [ "$STEP" = holds ]; then   # a calibration re-run: flash $2 (token $3), the holds only as label $4, compare against base
    ART2=$2; TOK2=$3; LABEL=${4:-stage2cal}
    log "pausing the daemon"
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
    trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
    uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
    wait_board 60 || { log "no board on USB (asleep? one key wakes it)"; exit 1; }
    sleep 2
    log "board token: $(token)"
    log "flash: $ART2"
    ./flash.sh "$ART2" < /dev/null 2>&1 | tee "$OUT/flash-$LABEL.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; exit 1; }
    sleep 5
    wait_board 40 || { log "no board after the flash"; exit 1; }
    sleep 2
    T=$(token); log "token after the flash: $T (want $TOK2)"
    [ "$T" = "$TOK2" ] || { log "not the expected build: stopping"; exit 1; }
    venv/bin/python scripts/rowisr_baseline.py run --label "$LABEL" --out "$OUT" --skip-windows 2>&1 | tee "$OUT/run-$LABEL.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "the run failed"; exit 1; }
    venv/bin/python hostagent/ak820health.py --sched > "$OUT/sched-after-$LABEL.txt" 2>&1
    venv/bin/python scripts/rowisr_baseline.py compare "$OUT/base.json" "$OUT/$LABEL.json" | tee "$OUT/compare-$LABEL.txt"
    exit 0
fi

if [ "$STEP" = compare ]; then
    venv/bin/python scripts/rowisr_baseline.py compare "$OUT/base.json" "$OUT/stage1.json"
    exit $?
fi

log "pausing the daemon"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
wait_board 60 || { log "no board on USB"; exit 1; }
sleep 2
T=$(token); log "board token: $T"

if [ "$STEP" = base ] || [ "$STEP" = all ]; then
    [ "$T" = "$BASE_TOKEN" ] || { log "not the candidate ($BASE_TOKEN): refusing the baseline"; exit 1; }
    venv/bin/python hostagent/ak820battery.py > "$OUT/battery-before.txt" 2>&1
    log "level: $(awk '/^level/ {print $2}' "$OUT/battery-before.txt") %"
    venv/bin/python scripts/rowisr_baseline.py run --label base --out "$OUT" 2>&1 | tee "$OUT/run-base.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "the baseline run failed"; exit 1; }
fi

if [ "$STEP" = all ]; then
    log "flash: $ART"
    ./flash.sh "$ART" < /dev/null 2>&1 | tee "$OUT/flash.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; exit 1; }
    sleep 5
    wait_board 40 || { log "no board after the flash"; exit 1; }
    sleep 2
    T=$(token); log "token after the flash: $T (want $S1_TOKEN)"
    [ "$T" = "$S1_TOKEN" ] || { log "stage 1 is not what runs: stopping"; exit 1; }
    "$A" health > "$OUT/health-after-flash.txt" 2>&1
fi

if [ "$STEP" = stage1 ] || [ "$STEP" = all ]; then
    T=$(token)
    [ "$T" = "$S1_TOKEN" ] || { log "not stage 1 ($S1_TOKEN): refusing"; exit 1; }
    venv/bin/python scripts/rowisr_baseline.py run --label stage1 --out "$OUT" 2>&1 | tee "$OUT/run-stage1.log"
    [ "${PIPESTATUS[0]}" = 0 ] || { log "the stage 1 run failed"; exit 1; }
    venv/bin/python hostagent/ak820battery.py > "$OUT/battery-after.txt" 2>&1
    venv/bin/python scripts/rowisr_baseline.py compare "$OUT/base.json" "$OUT/stage1.json" | tee "$OUT/compare.txt"
fi
log "done"
