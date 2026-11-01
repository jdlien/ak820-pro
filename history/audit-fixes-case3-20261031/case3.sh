#!/bin/bash
# Warren's wake-fix gate, case 3, on white (audit-fixes 67f13f6aaf, token
# 0x1038e774), mid-drain on its pack: relay 2 never touched. Data on, then cut
# with uhubctl while the board is enumerated (the LLD left ACTIVE with PHY_EN
# and ESD_EN off), a deep sleep, JD's key to wake it, data on again: both bits
# must come back, the frame number move, and raw HID answer, with no reset.
set -u
cd /Users/jdlien/code/ak820-pro
OUT=history/audit-fixes-case3-20261031
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
CSV=history/power-bench-2026-10-15/power.csv
log() { echo "[$(date +%T)] $*" | tee -a "$OUT/run.log"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
draw() { tail -1 "$CSV" | cut -d, -f6; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
pause() { launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; log "daemon paused"; }
resume() { launchctl bootstrap "gui/$UID" "$PL" 2>/dev/null; log "daemon restarted"; }
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off (exit)"; resume' EXIT
pause
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for _ in $(seq 1 40); do present && break; sleep 0.5; done
present || { log "white did not enumerate: is it asleep? stopping"; exit 1; }
sleep 1
T=$(token); log "token $T"
[ "$T" = "0x1038e774" ] || { log "not the checkpoint (0x1038e774): stopping"; exit 1; }
"$A" health > "$OUT/health-before.txt" 2>&1
"$A" clock --raw > "$OUT/clock-before.txt" 2>&1
uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data CUT while enumerated (the LLD left ACTIVE)"
resume
log "waiting for the deep sleep (draw under 6 mA for 10 s)"
n=0; for _ in $(seq 1 1800); do d=$(draw); if python3 -c "import sys; sys.exit(0 if float('$d') < 6 else 1)"; then n=$((n+1)); else n=0; fi; [ $n -ge 10 ] && break; sleep 1; done
[ $n -ge 10 ] || { log "no sleep in 30 min: stopping"; exit 1; }
log "asleep (draw $(draw) mA). WAITING FOR JD'S KEY"
w=0; for _ in $(seq 1 3600); do d=$(draw); python3 -c "import sys; sys.exit(0 if float('$d') > 15 else 1)" && { w=1; break; }; sleep 1; done
[ $w = 1 ] || { log "no wake in 60 min: stopping"; exit 1; }
log "woke (draw $(draw) mA); waiting out the recovery"
sleep 6
pause
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on again"
ok=0; for _ in $(seq 1 40); do present && { ok=1; break; }; sleep 0.5; done
log "enumerated: $ok"
sleep 1
T=$(token); log "token after: $T (no reset if 0x1038e774 and uptime continued)"
"$A" health > "$OUT/health-after.txt" 2>&1
"$A" clock --raw > "$OUT/clock-after-1.txt" 2>&1
sleep 2
"$A" clock --raw > "$OUT/clock-after-2.txt" 2>&1
log "done"
