#!/bin/bash
# Icon only (5c8c5f5ea8, dev, token 0x5b880dd4) onto white, JD's board, on
# Buzz's relay cable (hub 3-1.3.4 port 2), mid-drain on its pack: relay 2 is
# never touched. The daemon paused throughout; the flash starts at once so
# flash.sh's clock step defers to the daemon (status < 2 min old) and never
# runs ak820ctl, which enumerates HID. Both boards ran fcb7ae00b4 (token
# 0xf2a645a7), so the level tells white (mid-drain, under 75%) from black.
# White's backups are the default files.
set -u
cd /Users/jdlien/code/ak820-pro
ART=ak820pro-builds/out/via-dev-5c8c5f5ea8-20261030-172709.bin
OUT=history/icon-only-20261030
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
[ "$T" = "0xf2a645a7" ] || { echo "not fcb7ae00b4 (0xf2a645a7): refusing"; exit 1; }
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-before.txt" 2>&1
LVL=$(awk '/^level/ {print $2}' "$OUT/battery-before.txt")
echo "[$(date +%T)] level: $LVL %; $(grep '^power mode' "$OUT/battery-before.txt")"
python3 -c 'import sys; v=sys.argv[1]; sys.exit(0 if v.replace(".","",1).isdigit() and float(v) < 75 else 1)' "$LVL" ||
    { echo "the level ($LVL) isn't white's mid-drain one: refusing"; exit 1; }
echo "[$(date +%T)] flash: $ART"
./flash.sh "$ART" < /dev/null || { echo "[$(date +%T)] flash FAILED"; exit 1; }
sleep 5
for _ in $(seq 1 30); do present && break; sleep 0.5; done
T=$(token); echo "[$(date +%T)] token after: $T (want 0x5b880dd4)"
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-after.txt" 2>&1
"$A" health > "$OUT/health-after-flash.txt" 2>&1
echo "[$(date +%T)] done"
