#!/bin/bash
# The end of 11-03's bench day on white: relay 2 off (the charge done, the
# board back on battery), 5e flashed back over the SRAM trial (the night's
# build), a 120 s lit window on battery (the full-white draw as a third
# point, the handler as a check), the per-colour and value-64 holds
# (stage5_loads.sh step 3), then the standing state for the hand-over to
# Hutch (asleep and dark on 5e). Usage: stage5_evening.sh
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
ART=ak820pro-builds/out/via-dev-739fe1b635-20261103-132623.bin; WANT=0xf222e31c
log "relay 2 off: the board on battery again"
venv/bin/python scripts/usb_relay.py off 2 2>&1 | tail -1
sleep 15; log "the pack: $(tail -1 history/power-bench-2026-10-15/power.csv | cut -d, -f1,4,6,9)"
log "5e back on white"
"$D/stage5_flash.sh" "$ART" "$WANT" stage5e-night 120 no 2>&1 | grep -E "^\[|isr_mean|isr_cpu|pulses_omitted|lit_mA|the light" | cut -c1-160
log "the battery page"; launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; sleep 6
venv/bin/python hostagent/ak820battery.py 2>/dev/null | grep -iE "level|supply|led drive" | head -3
timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist" 2>&1
log "the per-colour and value-64 holds"
"$D/stage5_loads.sh" "$WANT" stage5e 3 2>&1 | grep -E "^\[|hold|drive" | cut -c1-200
log "the evening's bench done: white in the standing state on 5e"
