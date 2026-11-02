#!/bin/bash
# After probe 2 ends and white has deep-slept (the logger under 5 mA for 20 s),
# wake it with relay 2 (the charger edge), bring data on while the relay is on
# so the wake holds, drop relay 2, run dark_after_sleep.py, put the bench back.
set -u
cd /Users/jdlien/code/ak820-pro
L=history/rowisr-stage1-20261101/dark_after_sleep.log
CSV=history/power-bench-2026-10-15/power.csv
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
log() { echo "[$(date +%T)] $*" >> "$L"; }
echo "=== dark after sleep, $(date +%T) ===" > "$L"
while pgrep -f dark_probe2.py > /dev/null; do sleep 5; done
log "probe 2 finished; waiting for the sleep"
deadline=$(( $(date +%s) + 900 ))
while :; do
    low=$(tail -20 "$CSV" | awk -F, '$6 < 5 {n++} END {print n+0}')
    [ "$low" -ge 20 ] && break
    [ "$(date +%s)" -gt "$deadline" ] && { log "white did not sleep within 15 min: giving up"; exit 1; }
    sleep 5
done
log "asleep ($(tail -1 "$CSV" | cut -d, -f6) mA); waking with relay 2"
venv/bin/python scripts/usb_relay.py on power >> "$L" 2>&1
sleep 2
launchctl bootout "gui/$UID/com.jdlien.ap820pro.agent" 2>/dev/null; launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" >> "$L" 2>&1
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" >> "$L" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e > /dev/null
ok=0; for i in $(seq 1 60); do ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' && { ok=1; break; }; sleep 0.5; done
log "board on USB with relay 2 on: $ok"
sleep 3
venv/bin/python scripts/usb_relay.py off power >> "$L" 2>&1
sleep 2
ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777' || { log "gone after relay 2 off"; exit 1; }
log "token $("$HOME/Library/Application Support/ak820pro/bin/ak820" health --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["vitals"]["build_token"])')"
venv/bin/python history/rowisr-stage1-20261101/dark_after_sleep.py >> "$L" 2>&1
log "exit $?"
