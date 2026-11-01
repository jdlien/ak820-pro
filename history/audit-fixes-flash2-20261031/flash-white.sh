#!/bin/bash
# The audit fixes, second checkpoint (57d1368f17, dev, token 0x191986cf: all five batches) onto
# white, JD's board, on Buzz's relay cable (hub 3-1.3.4 port 2), mid-drain on
# its pack: relay 2 is never touched. As icon-only-20261030/flash-white.sh:
# the daemon paused throughout, the token and the mid-drain level checked.
set -u
cd /Users/jdlien/code/ak820-pro
ART=ak820pro-builds/out/via-dev-57d1368f17-20261031-161116.bin
OUT=history/audit-fixes-flash2-20261031
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
echo "[$(date +%T)] pausing the daemon"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; echo "[$(date +%T)] data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; echo "[$(date +%T)] daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; echo "[$(date +%T)] data on"
for _ in $(seq 1 60); do present && break; sleep 0.5; done
sleep 1
T=$(token); echo "[$(date +%T)] board token: $T"
[ "$T" = "0x1038e774" ] || { echo "not the first checkpoint (0x1038e774): refusing"; exit 1; }
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-before.txt" 2>&1
LVL=$(awk '/^level/ {print $2}' "$OUT/battery-before.txt")
echo "[$(date +%T)] level: $LVL %; $(grep '^power mode' "$OUT/battery-before.txt")"
python3 -c 'import sys; v=sys.argv[1]; sys.exit(0 if v.replace(".","",1).isdigit() and float(v) < 75 else 1)' "$LVL" ||
    { echo "the level ($LVL) isn't white's mid-drain one: refusing"; exit 1; }
echo "[$(date +%T)] flash: $ART"
./flash.sh "$ART" < /dev/null || { echo "[$(date +%T)] flash FAILED"; exit 1; }
sleep 5
for _ in $(seq 1 30); do present && break; sleep 0.5; done
T=$(token); echo "[$(date +%T)] token after: $T (want 0x191986cf)"
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-after.txt" 2>&1
"$A" health > "$OUT/health-after-flash.txt" 2>&1
echo "[$(date +%T)] done"
