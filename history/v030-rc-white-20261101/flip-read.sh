#!/bin/bash
# After JD's Win/Mac flip to Mac and back on the candidate: the profiles and
# the level read off white, data on for the read only, the daemon paused.
set -u
cd /Users/jdlien/code/ak820-pro
OUT=history/v030-rc-white-20261101
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
echo "[$(date +%T)] pausing the daemon"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; echo "[$(date +%T)] data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; echo "[$(date +%T)] daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; echo "[$(date +%T)] data on"
for _ in $(seq 1 60); do present && break; sleep 0.5; done
present || { echo "[$(date +%T)] white is not on USB (asleep?)"; exit 1; }
sleep 1
T=$(token); echo "[$(date +%T)] board token: $T"
[ "$T" = "0x6f758b40" ] || { echo "not the candidate (0x6f758b40)"; exit 1; }
venv/bin/python hostagent/ak820profiles.py show > "$OUT/profiles-after-flip.txt" 2>&1
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-after-flip.txt" 2>&1
grep -E '^(level|power mode|time left)' "$OUT/battery-after-flip.txt"
grep -E 'backup \(' "$OUT/profiles-after-flip.txt"
echo "[$(date +%T)] done"
