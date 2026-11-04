#!/bin/bash
# One guarded lit window on 5g at the full-white reference (val 255, the
# afternoon's state), with JD's own lighting choice saved first and put back
# after: the flash restored his val 141 (set while he judged the rainbow on
# 5e), which the window's lit guard refused at 56 mA. Usage: the token and
# the label are fixed; run from the repo root.
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
on_data() {
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
    for i in $(seq 1 8); do present && return 0; sleep 2; done
    return 1
}
standing() { sleep 2; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "the standing state"; }
on_data || { log "no board"; standing; exit 1; }
venv/bin/python hostagent/ak820lighting.py restore "$D/lighting-before-holds-stage5e.json" 2>&1 | tail -1
log "the full-white reference restored (val 255); the window"
"$D/stage5_window.sh" 0x34d7c5fb stage5g 300
log "the window done; JD's lighting choice back"
on_data || { log "no board for the restore"; standing; exit 1; }
venv/bin/python hostagent/ak820lighting.py restore "$D/lighting-5g-jd-choice.json" 2>&1 | tail -1
standing
log "all done"
