#!/bin/bash
# Warren's ds-phase (fcb7ae00b4, as on white) onto black, gremlin's board, on
# Buzz's relay cable (hub 3-1.3.4 port 2). Relay 2 never touched (white's
# drain). The daemon paused throughout; the flash starts at once so flash.sh's
# clock step defers to the daemon (status < 2 min old) and never runs
# ak820ctl, which enumerates HID. Black's backups go to their own files, so
# white's (~/Documents/ak820pro-{keymap,lighting,profiles}.json) stay as they are.
set -u
cd /Users/jdlien/code/ak820-pro
ART=ak820pro-builds/out/via-dev-fcb7ae00b4-20261029-000229.bin
OUT=history/ds-phase-black-20261030
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
SLOTS=/private/tmp/claude-501/-Users-jdlien-code-ak820-pro/ae231e7d-be57-4a63-8869-e3b131136e11/scratchpad/ds_slots.py
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
echo "[$(date +%T)] pausing the daemon"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; echo "[$(date +%T)] data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; echo "[$(date +%T)] daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; echo "[$(date +%T)] data on"
for _ in $(seq 1 60); do present && break; sleep 0.5; done
sleep 1
T=$(token); echo "[$(date +%T)] board token: $T"
[ "$T" = "0xb5f2fdab" ] || { echo "not black's 8ec0c8b9b4 (0xb5f2fdab): refusing"; exit 1; }
echo "[$(date +%T)] flash: $ART"
KEYMAP="$HOME/Documents/ak820pro-black-keymap.json" \
LIGHTING="$HOME/Documents/ak820pro-black-lighting.json" \
PROFILES="$HOME/Documents/ak820pro-black-profiles.json" \
BATTLOG_DIR="$HOME/Documents/ak820pro-battlogs/black" \
    ./flash.sh "$ART" < /dev/null || { echo "[$(date +%T)] flash FAILED"; exit 1; }
sleep 5
for _ in $(seq 1 30); do present && break; sleep 0.5; done
T=$(token); echo "[$(date +%T)] token after: $T (want 0xf2a645a7)"
venv/bin/python "$SLOTS" > "$OUT/slots-after-flash.json"; echo "[$(date +%T)] slots rc=$?"
"$A" health > "$OUT/health-after-flash.txt" 2>&1
echo "[$(date +%T)] done"
