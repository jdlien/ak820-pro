#!/bin/bash
# The v0.3.0 release candidate (audit-fixes 4c7395a4c6, dev, token 0x6f758b40) onto
# white, JD's board, on Buzz's relay cable (hub 3-1.3.4 port 2), mid-drain on
# its pack: relay 2 is never touched. As audit-fixes-flash2-20261031/flash-white.sh:
# the daemon paused throughout, the artifact's hash, the token and the
# mid-drain level checked. The first flash onto a firmware with the new
# profiles restore (the commit's [7], the live record applied and flushed
# before it), so the profiles are read off the board before and after.
set -u
cd /Users/jdlien/code/ak820-pro
ART=ak820pro-builds/out/via-dev-4c7395a4c6-20261031-224044.bin
SHA=d67746165d164cbd33c4dbcc0afaadeb7f840c1f8f3bb9235b9ad80307bdbd2e
OUT=history/v030-rc-white-20261101
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
[ "$(shasum -a 256 "$ART" | cut -d' ' -f1)" = "$SHA" ] || { echo "$ART is not the candidate's build: refusing"; exit 1; }
echo "[$(date +%T)] pausing the daemon"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; echo "[$(date +%T)] data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; echo "[$(date +%T)] daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; echo "[$(date +%T)] data on"
for _ in $(seq 1 60); do present && break; sleep 0.5; done
present || { echo "[$(date +%T)] white is not on USB (asleep?): refusing"; exit 1; }
sleep 1
T=$(token); echo "[$(date +%T)] board token: $T"
[ "$T" = "0x191986cf" ] || { echo "not the second checkpoint (0x191986cf): refusing"; exit 1; }
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-before.txt" 2>&1
LVL=$(awk '/^level/ {print $2}' "$OUT/battery-before.txt")
echo "[$(date +%T)] level: $LVL %; $(grep '^power mode' "$OUT/battery-before.txt")"
python3 -c 'import sys; v=sys.argv[1]; sys.exit(0 if v.replace(".","",1).isdigit() and float(v) < 75 else 1)' "$LVL" ||
    { echo "the level ($LVL) isn't white's mid-drain one: refusing"; exit 1; }
venv/bin/python hostagent/ak820profiles.py show > "$OUT/profiles-before.txt" 2>&1
echo "[$(date +%T)] flash: $ART"
./flash.sh "$ART" < /dev/null || { echo "[$(date +%T)] flash FAILED (exit $?)"; exit 1; }
sleep 5
for _ in $(seq 1 30); do present && break; sleep 0.5; done
T=$(token); echo "[$(date +%T)] token after: $T (want 0x6f758b40)"
venv/bin/python hostagent/ak820battery.py > "$OUT/battery-after.txt" 2>&1
venv/bin/python hostagent/ak820profiles.py show > "$OUT/profiles-after.txt" 2>&1
"$A" health > "$OUT/health-after-flash.txt" 2>&1
echo "[$(date +%T)] done"
