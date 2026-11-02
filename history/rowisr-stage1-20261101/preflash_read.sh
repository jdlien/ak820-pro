#!/bin/bash
# Before the detector flash (11-02): one read of white over the data line,
# while the RAM still holds the night's record. The deep sleep's wake ring
# (op 24 slots 0-7: the last eight wakes with their reasons, pins and stray
# counts), the stray diagnostic (slot 8), the sleep page, health, the row
# handler's record and its USB fields. Nothing changes on the board. Data
# off and the daemon back by the trap. For Hutch's 11:31 self-wake question.
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
U16 = lambda b, o: int.from_bytes(b[o:o + 2], "little")
U32 = lambda b, o: int.from_bytes(b[o:o + 4], "little")
WAKES = ["none", "key", "backstop", "strays", "blocked", "knob", "charge"]
h = hp.open_device()
res = {"t0": time.strftime("%H:%M:%S")}
try:
    res["isr"] = hp.read_isr(h); res["health"] = hp.read_health(h); res["stalls"] = hp.read_stalls(h)
    res["deep"] = ds.deep(h); res["sleep_page"] = ba.sleep_page(h)
    # The wake ring: slot n is the n-th entry; every reply's [26..27] is the next sleep's number.
    for _ in range(3):
        ring = []
        for slot in range(8):
            b = devhook(h, 24, [slot])[4:32]
            ring.append({"slot": slot, "seq": U16(b, 0), "reason": WAKES[b[2]] if b[2] < len(WAKES) else b[2], "flags": b[3],
                         "counted_s": U32(b, 4), "p0": hex(U32(b, 8)), "p1": hex(U32(b, 12)), "p2": hex(U32(b, 16)),
                         "ms": U32(b, 20), "strays": U16(b, 24), "next": U16(b, 26)})
        if len({w["next"] for w in ring}) == 1: break
    res["wake_ring"] = sorted(ring, key=lambda w: w["seq"])
    b = devhook(h, 24, [8])[4:32]
    f = U16(b, 16)
    icsr = lambda v: {"icsr": hex(v), "vectpending": (v >> 12) & 0x3F, "pendsv": bool(v & (1 << 28)), "pendst": bool(v & (1 << 26))}
    res["stray_diag"] = {"seq": U16(b, 0), "same_s": U16(b, 2), "first_s": U32(b, 4), "ispr": hex(U32(b, 8)), **icsr(U32(b, 12)),
                         "ie_outside": [p for p in range(3) if f & (1 << p)], "mis_outside": [p for p in range(3) if f & (8 << p)],
                         "iser_not_wake_set": bool(f & 64), "last_n": U16(b, 18), "last_ispr": hex(U32(b, 20)), "last": icsr(U32(b, 24))}
    r = rd.xfer(h, 5, b"")[4:]
    res["record"] = {"omit_run_max": r[0] | r[1] << 8, "spurious": r[2], "late_omit": r[3], "epoch_losses": r[4],
                     "invalid_services": r[5], "serviced_lo16": r[26] | r[27] << 8}
    res["sched"] = hp.read_sched(h)
    log(f"uptime {res['isr']['uptime_ms'] / 1000:.0f} s, timer ms {res['isr']['uptime_ms']}; sleep page {res['sleep_page']}")
    log(f"deep-sleep record {res['deep']}")
    now = res["isr"]["uptime_ms"]
    for w in res["wake_ring"]:
        age = (now - w["ms"]) & 0xFFFFFFFF
        log(f"wake #{w['seq']}: {w['reason']}, flags 0x{w['flags']:02x}, slept {w['counted_s']} counted s, strays {w['strays']}, "
            f"pins p0 {w['p0']} p1 {w['p1']} p2 {w['p2']}, at timer ms {w['ms']} ({age / 1000:.0f} s of awake time ago)")
    log(f"stray diag {res['stray_diag']}")
    log(f"row record {res['record']}; page 7 losses/spurious as above; wdt_fired {res['health']['wdt_fired_last_boot']}")
finally:
    res["t_end"] = time.strftime("%H:%M:%S")
    json.dump(res, open(f"{D}/preflash-read.json", "w"), indent=1)
    h.close()
PY
