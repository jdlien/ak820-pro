#!/bin/bash
# The trim's flash on white (11-02 evening, a47c134079, token 0x1a291156) and
# the warm windows after it: the daemon paused, data on, the token read
# (the detector build, 0x60d4a06b, expected before), flash.sh with its
# backups and restores, the board back, then warm_windows.sh trim 0x1a291156
# (its own trap puts data off and the daemon back). One key from JD wakes
# white first; his go here starts it.
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-a47c134079-20261102-205641.bin
A="$HOME/Library/Application Support/ak820pro/bin/ak820"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
token() { "$A" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])' 2>/dev/null; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 15); do present && break; sleep 2; done
present || { log "no board on USB (asleep? one key wakes it)"; uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist" 2>&1; exit 1; }
sleep 2; log "board present, token before: $(token)"
log "flash: $ART"
./flash.sh "$ART" < /dev/null 2>&1 | tee "$D/flash-trim.log"
[ "${PIPESTATUS[0]}" = 0 ] || { log "flash FAILED"; exit 1; }
sleep 5
for i in $(seq 1 40); do present && break; sleep 1; done
present || { log "no board after the flash"; exit 1; }
sleep 2
exec "$D/warm_windows.sh" trim 0x1a291156
