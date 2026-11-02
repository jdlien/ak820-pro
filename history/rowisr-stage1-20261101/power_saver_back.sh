#!/bin/bash
# Put white's power mode back to Power saver (2) after a runner step that
# read Always on as the mode to restore (the dump-order fault of 11-01), and
# leave the bench in its standing state. Run right after the step's EXIT
# trap: the idle board sleeps within a minute of data going off.
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 30); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' && break; sleep 2; done
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' || { log "no board on USB (asleep? one key wakes it)"; exit 1; }
sleep 2
venv/bin/python - <<'PY'
import sys, time
sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try:
    pw = devhook(h, 14, [0]); print(f"before: mode {pw[4]} stage {pw[5]} cap {pw[6]} forced {pw[7]}")
    if pw[7] != 0xFF and pw[7] != 0: devhook(h, 14, [2, 0xFF])
    devhook(h, 14, [1, 2])
    time.sleep(0.5)
    pw = devhook(h, 14, [0]); print(f"after:  mode {pw[4]} stage {pw[5]} cap {pw[6]} forced {pw[7]}")
    assert pw[4] == 2, "the mode did not take"
finally:
    h.close()
PY
venv/bin/python hostagent/ak820profiles.py dump history/rowisr-stage1-20261101/settings-after-mode.json 2>&1 | grep -i "live:"
