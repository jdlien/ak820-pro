#!/bin/bash
# Warren's ds-phase (fcb7ae00, slot 10) onto JD's board, then his check that slot 9's
# no-init RAM survives a reset through the bootloader: flash; a 30 s fed
# armed sleep; read slot 9 (magic, secs 30, flags 0xc0); re-flash the same
# .bin; read slot 9 again ([26] = 1 with the same seconds: it survives).
# Relay 2 never touched (the drain). The daemon paused throughout.
set -u
cd /Users/jdlien/code/ak820-pro
ART=ak820pro-builds/out/via-dev-fcb7ae00b4-20261029-000229.bin
OUT=history/ds-phase-check-$(date +%Y%m%d-%H%M)
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
mkdir -p "$OUT"
echo "[$(date +%T)] pausing the daemon"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1
trap 'echo "[$(date +%T)] restarting the daemon"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; launchctl print "gui/$UID/com.jdlien.ak820pro.agent" | grep -m1 "state ="' EXIT
sleep 2
echo "[$(date +%T)] flash 1: $ART"
./flash.sh "$ART" < /dev/null || { echo "flash 1 failed"; exit 1; }
sleep 5
echo "[$(date +%T)] slots after flash 1"
venv/bin/python /private/tmp/claude-501/-Users-jdlien-code-ak820-pro/ae231e7d-be57-4a63-8869-e3b131136e11/scratchpad/ds_slots.py | tee "$OUT/slots-0-after-flash.json"
echo "[$(date +%T)] a 30 s fed armed sleep"
venv/bin/python /private/tmp/claude-501/-Users-jdlien-code-ak820-pro/ae231e7d-be57-4a63-8869-e3b131136e11/scratchpad/wdt_asleep.py --fed --caps 30 --out "$OUT/sleep"
echo "[$(date +%T)] slots after the sleep"
venv/bin/python /private/tmp/claude-501/-Users-jdlien-code-ak820-pro/ae231e7d-be57-4a63-8869-e3b131136e11/scratchpad/ds_slots.py | tee "$OUT/slots-1-after-sleep.json"
echo "[$(date +%T)] flash 2, the same .bin (a software reset through the bootloader)"
./flash.sh "$ART" < /dev/null || { echo "flash 2 failed"; exit 1; }
sleep 5
echo "[$(date +%T)] slots after flash 2"
venv/bin/python /private/tmp/claude-501/-Users-jdlien-code-ak820-pro/ae231e7d-be57-4a63-8869-e3b131136e11/scratchpad/ds_slots.py | tee "$OUT/slots-2-after-reflash.json"
echo "[$(date +%T)] done: $OUT"
