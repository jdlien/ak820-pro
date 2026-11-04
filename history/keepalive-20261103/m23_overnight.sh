#!/bin/bash
# The keep-alive's M2 and M3 overnight on white (README.md, "The with-run"):
# the daemon paused (no lock-light frames to hold the link instead), the data
# line off, one presser press (input, so the absence starts from it), then
# white left alone on the ladder's own sleeps until END; every 30 min a line
# from m23_read.py (the wakes from power.csv, white's link in bluetoothd). No
# board traffic after the press. The trap puts the daemon back at the end.
# Usage: m23_overnight.sh [END as HH:MM, tomorrow's; default 08:00]
set -u
cd "$(dirname "$0")/../.." || exit 1
END=${1:-08:00}
D=history/keepalive-20261103
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }
end_ep=$(date -j -v+1d -f '%H:%M:%S' "$END:00" +%s)
[ $(( end_ep - $(date +%s) )) -gt 86400 ] && end_ep=$(( end_ep - 86400 ))
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; log "daemon paused until $(date -r $end_ep '+%m-%d %H:%M')"
trap 'launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"   # port 2 only: port 4 is the UPS
venv/bin/python scripts/presser_repl.py pulse A1 100 2>&1 | grep -v 'logger\|QT Py'
t0=$(date +%s); log "start $t0: white sleeps on its ladder ~3 min after that press"
while [ "$(date +%s)" -lt "$end_ep" ]; do
    sleep 1800
    log "$(venv/bin/python $D/m23_read.py "$t0" 2>&1)"
done
venv/bin/python $D/m23_read.py "$t0" --json > "$D/m23-overnight.json"
log "end: $(venv/bin/python $D/m23_read.py "$t0" 2>&1) -> $D/m23-overnight.json"
