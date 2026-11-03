#!/bin/bash
# Waits for a key to wake white by its USB presence, not the power logger
# (the logger goes off the bench for the presser rig's soldering, 23:5x
# 11-02): the daemon paused and the data line on, a sleeping board does not
# enumerate and a woken one does within seconds (the wake's D+ re-attach,
# case 3 of 11-01). Then exit_flash.sh: the flash and its readings (its own
# trap puts data off and the daemon back). Gives up after 90 min. Launched
# detached on JD's go (11-03); its log is exit-on-usb.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
D=history/rowisr-stage1-20261101
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%H:%M:%S)] $*"; }
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on; waiting for white to wake (its USB presence), up to 90 min"
n=0
while ! present; do
    n=$((n + 1))
    if [ "$n" -ge 2700 ]; then
        log "no wake in 90 min: giving up"
        timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"
        launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"
        exit 1
    fi
    sleep 2
done
log "white present on USB (awake); exit_flash.sh starts"
"$D/exit_flash.sh" 2>&1 | tee "$D/flash-exit-run.log"
log "exit_flash.sh exit ${PIPESTATUS[0]}"
