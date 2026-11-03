#!/bin/bash
# The presser's contact check (scripts/presser_repl_check.py): the daemon and
# the power logger's LaunchAgent paused, white's data line on (port 2 of
# 3-1.3.4, never port 4: the UPS), all three undone by the trap.
set -u
cd "$(dirname "$0")/.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
AG="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
PLG="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.powerlog.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
launchctl bootout "gui/$UID/com.jdlien.ak820pro.powerlog" 2>&1; log "logger paused"
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$AG" 2>&1; log "daemon back"; launchctl bootstrap "gui/$UID" "$PLG" 2>&1; log "logger back"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 15); do present && break; sleep 2; done
present || { log "white not on USB (asleep? a key wakes it)"; exit 1; }
sleep 2
venv/bin/python scripts/presser_repl_check.py "$@"
