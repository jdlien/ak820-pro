#!/bin/bash
# Stage 5's remaining hands-free gates after stage5_flash.sh (plans/ROW-ISR-PLAN.md,
# "Stage 5: the cadence"; Warren's two asks for the keep-alive's with-run):
# the UART and ACK counts awake at the new cadence (overrun_diag status
# before and after a presser batch), five ladder sleeps with presser wakes
# (deep_wake_presser.sh: the ring clean, no strays, the restart at 6,000
# ticks), the silence set (silence_check.sh: the detector at the new slot),
# and the camera gate at this cadence (camera_write_clip.sh: the lights on,
# the ladder held, a forced write filmed, nothing in the writer's windows).
# Each script leaves white in the standing state; this one ends there too.
# Usage: stage5_gates.sh TOKEN [LABEL] [STEPS] (STEPS the digits of the steps to
# run, default 1234: 1 the UART counts with a presser batch, 2 the five wakes,
# 3 the silence set, 4 the camera gate; 1-3 press keys into whatever is in
# front on an unlocked Buzz, so they run with Buzz locked; 4 presses once).
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
D=history/rowisr-stage1-20261101
WANT=${1:?token}; L=${2:-stage5}; STEPS=${3:-1234}
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
wake_on_data() {
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>/dev/null; sleep 3
    timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null
    for i in $(seq 1 5); do present && return 0; sleep 2; done
    venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1
    for i in $(seq 1 15); do present && return 0; sleep 1; done
    return 1
}
standing() { sleep 2; timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "the standing state"; }

case "$STEPS" in *1*)
log "1. the UART and ACK counts awake at the new cadence: status, 200 presses at 25 ms, status"
wake_on_data || { log "no board"; standing; exit 1; }
sleep 3
venv/bin/python scripts/overrun_diag.py status 2>&1 | tee "$D/overrun-$L-before.txt" | grep -iE "OE total|overrun|ack|timeout" | head -6
venv/bin/python scripts/presser_repl.py batch A1 200 25 75 2>&1 | grep -v '^BATCH' | tail -2
sleep 3
venv/bin/python scripts/overrun_diag.py status 2>&1 | tee "$D/overrun-$L-after.txt" | grep -iE "OE total|overrun|ack|timeout" | head -6
"$HOME/Library/Application Support/ak820pro/bin/ak820" health 2>&1 | grep -iE "ack|overrun|uart|stall|ge_25" | head -8 | tee "$D/health-uart-$L.txt"
standing
;; esac
case "$STEPS" in *2*)
log "2. five ladder sleeps with presser wakes"
"$D/deep_wake_presser.sh" 5 "$L" "$WANT" 2>&1 | tail -8
;; esac
case "$STEPS" in *3*)
log "3. the silence set"
"$D/silence_check.sh" 2>&1 | tail -20
for f in silence-check.json silence-check.log; do [ -f "$D/$f" ] && cp "$D/$f" "$D/${f%.*}-$L.${f##*.}"; done
;; esac
case "$STEPS" in *4*)
log "4. the camera gate at this cadence: the lights on, the ladder held, the write forced, filmed"
wake_on_data || { log "no board for the camera"; standing; exit 1; }
sleep 3
venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'hostagent')
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try: devhook(h, 14, [1, 0]); print("the ladder held at Always on")
finally: h.close()
PY
venv/bin/python scripts/presser_repl.py pulse A1 100 >/dev/null 2>&1; sleep 2
python3 scripts/studio_lights.py off 2>&1 | tail -1
T=$(date -v+75S +%H:%M:%S); log "the clip at T-5, T=$T"
"$D/camera_write_clip.sh" "write-$L" "$T" 2>&1 | grep -vE "^phone - mac|^deleted|^page4|^power mode" | tail -30
python3 scripts/studio_lights.py restore 2>&1 | tail -1
venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'hostagent')
import ak820health as hp
from rowisr_baseline import devhook
h = hp.open_device()
try: devhook(h, 14, [1, 2]); print("Power saver back")
finally: h.close()
PY
standing
;; esac
log "stage 5's gates done ($STEPS)"
