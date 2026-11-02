#!/bin/bash
# After JD's key wakes white from a deep sleep entered with the RGB dark
# (11-02 morning): one read over the data line inside the 3 min before it
# sleeps again. The deep-sleep record (op 14 sub 4, read only), HC_POWER
# page 1 (the sleeps since the boot), health, the row handler's record (op 28
# sub 5), a 20 s page-7 window, the ladder's state; then the Rust agent's
# page 7 decode once (Hutch's ae72d2b, a parity check, the handle closed
# first); data off, the daemon back. Nothing on the board changes.
set -u
cd "$(dirname "$0")/../.." || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
for i in $(seq 1 15); do present && break; sleep 2; done
present || { log "no board on USB (asleep? one key wakes it)"; exit 1; }
log "board present"; sleep 2
venv/bin/python - <<'PY'
import sys, time, json
sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp, ak820battery as ba, deep_sleep as ds, rowisr_diag as rd
from rowisr_baseline import devhook
D = "history/rowisr-stage1-20261101"
def log(s): print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
h = hp.open_device()
res = {"t0": time.strftime("%H:%M:%S")}
try:
    res["isr"] = hp.read_isr(h); res["deep"] = ds.deep(h); res["sleep_page"] = ba.sleep_page(h)
    res["health"] = hp.read_health(h); res["stalls"] = hp.read_stalls(h)
    r = rd.xfer(h, 5, b"")[4:]
    res["record"] = {"omit_run_max": r[0] | r[1] << 8, "spurious": r[2], "late_omit": r[3], "epoch_losses": r[4],
                     "invalid_services": r[5], "elapsed_min_us": round((r[6] | r[7] << 8) / 48.0, 2),
                     "omit_row": list(r[8:26]), "serviced_lo16": r[26] | r[27] << 8}
    pw = devhook(h, 14, [0]); res["power"] = {"mode": pw[4], "stage": pw[5], "cap": pw[6], "forced": pw[7], "battery": pw[8]}
    log(f"uptime {res['isr']['uptime_ms'] / 1000:.0f} s; deep-sleep record {res['deep']}")
    log(f"sleep page {res['sleep_page']}")
    log(f"wdt_fired_last_boot {res['health']['wdt_fired_last_boot']} degraded {res['health']['wdt_degraded']}; "
        f"stalls>=25 {res['stalls']['count_ge_25ms']}; key_presses {res['stalls']['key_presses']}")
    log(f"row record {res['record']}; power {res['power']}")
    A = hp.read_sched(h); tA = time.time(); time.sleep(20); B = hp.read_sched(h); tB = time.time()
    res["window"] = hp.sched_window(A, B, tB - tA); res["page7"] = B
    log(f"20 s window {res['window']}")
    log(f"page 7 maxima: latency {B['latency_max_us']} us, elapsed {B['elapsed_max_us']} us")
finally:
    res["t_end"] = time.strftime("%H:%M:%S")
    json.dump(res, open(f"{D}/wake-dark-read.json", "w"), indent=1)
    h.close()
PY
log "the Rust agent's page 7 (ae72d2b):"
ak820-agent/target/debug/ak820 health --sched --window 15 2>&1
log "rust exit $?"
