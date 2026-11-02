#!/bin/bash
# Stage 2's scan-only check on white (11-01 night), in two parts around one
# key from JD. `enter`: the daemon paused, data on, the ladder held at ACTIVE
# for a lit window, light sleep's mask armed with bit 0 (scan-only, op 14
# sub 3, 255 s), the stage forced to LIGHTS_OFF (the RGB dark, so the mask
# applies), the mode read back, a 15 s window (page 7: ~1600 slots/s, no
# pulse), the record; it leaves the board there, data on. Then JD presses a
# key. `exit`: the key count's growth (the scan under scan-only saw it), the
# record, a second window, then the stage forced ACTIVE (scan-only exits by
# the RGB path with the mask still set), a lit window, the record, the
# lighting read back, the mask cleared, the force released, data off, the
# daemon back. The force is RAM: `exit` must run, or the board stays dark.
set -u
cd "$(dirname "$0")/../.." || exit 1
PART="${1:-}"; [[ "$PART" == enter || "$PART" == exit ]] || { echo "usage: $0 enter|exit"; exit 2; }
log() { echo "[$(date +%H:%M:%S)] $*"; }
PL="$HOME/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist"
present() { ioreg -p IOUSB -l -w0 | grep -q '"idProduct" = 32777'; }
if [[ $PART == enter ]]; then
    launchctl bootout "gui/$UID/com.jdlien.ak820pro.agent" 2>&1; log "daemon paused"
    uhubctl -l 3-1.3.4 -p 2 -a on -e >/dev/null; log "data on"
    for i in $(seq 1 30); do present && break; sleep 2; done
    if ! present; then
        log "no board on USB (asleep? one key wakes it); data off, daemon back"
        uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; launchctl bootstrap "gui/$UID" "$PL" 2>&1; exit 1
    fi
    log "board present"; sleep 2
else
    trap 'uhubctl -l 3-1.3.4 -p 2 -a off -e >/dev/null; log "data off"; launchctl bootstrap "gui/$UID" "$PL" 2>&1; log "daemon restarted"' EXIT
    present || { log "no board on USB: the daemon stays paused by the trap's restart; a key, then rerun exit"; exit 1; }
fi
venv/bin/python - "$PART" <<'PY'
import sys, time, json
sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp, ak820lighting as lp, rowisr_diag as rd
from rowisr_baseline import devhook
PART = sys.argv[1]
D = "history/rowisr-stage1-20261101"
OUT = f"{D}/scan-only-{PART}.json"
def log(s): print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
h = hp.open_device()
res = {"part": PART, "t0": time.strftime("%H:%M:%S")}
def power():
    r = devhook(h, 14, [0]); return {"mode": r[4], "stage": r[5], "cap": r[6], "forced": r[7], "battery": r[8]}
def light(mask, ttl):
    r = devhook(h, 14, [3, mask, 2, 0, ttl])
    return {"mask": r[5], "applied": r[6], "wfi": int.from_bytes(r[7:11], "little"), "scan_only": bool(r[11])}
def record():
    r = rd.xfer(h, 5, b"")[4:]
    return {"omit_run_max": r[0] | r[1] << 8, "spurious": r[2], "late_omit": r[3], "epoch_losses": r[4],
            "invalid_services": r[5], "elapsed_min_us": round((r[6] | r[7] << 8) / 48.0, 2),
            "omit_row": list(r[8:26]), "serviced_lo16": r[26] | r[27] << 8}
def status(): return rd.status_dict(rd.xfer(h, 2))
def window(secs):
    A = hp.read_sched(h); tA = time.time(); time.sleep(secs); B = hp.read_sched(h); tB = time.time()
    w = hp.sched_window(A, B, tB - tA); w["page7_after"] = B; return w
def keys(): return hp.read_stalls(h)["key_presses"]
def brief(w): return {k: w[k] for k in ("win_secs", "win_slots_per_s", "win_serviced_valid", "win_missed_slots",
                                       "win_pulses_emitted", "win_pulses_omitted", "win_elapsed_mean_us", "win_cpu_pct") if k in w}
def rec_brief(r): return {k: r[k] for k in ("spurious", "epoch_losses", "invalid_services", "late_omit", "omit_run_max", "serviced_lo16")}
try:
    if PART == "enter":
        res["power_before"] = power(); log(f"power {res['power_before']}")
        res["lighting_before"] = lp.read_lighting(h); log(f"lighting {res['lighting_before']}")
        res["keys_before"] = keys(); res["record_before"] = record(); log(f"record {rec_brief(res['record_before'])}")
        devhook(h, 14, [2, 0]); time.sleep(1.0)
        res["power_active"] = power(); log(f"held ACTIVE {res['power_active']}")
        res["window_lit"] = window(15); log(f"lit window {brief(res['window_lit'])}")
        res["arm"] = light(1, 255); log(f"mask armed (RGB lit, so not applied yet) {res['arm']}")
        devhook(h, 14, [2, 2]); time.sleep(1.5)
        res["power_dark"] = power(); res["armed_dark"] = light(1, 255)
        log(f"forced LIGHTS_OFF {res['power_dark']}; light {res['armed_dark']}")
        res["status_scan_only"] = status(); log(f"status {res['status_scan_only']}")
        res["window_scan_only"] = window(15); log(f"scan-only window {brief(res['window_scan_only'])}")
        res["record_scan_only"] = record(); log(f"record {rec_brief(res['record_scan_only'])}")
        res["keys_after"] = keys()
        w, r0, r1 = res["window_scan_only"], res["record_before"], res["record_scan_only"]
        checks = {"scan_only_in_force": res["armed_dark"]["scan_only"] and (res["armed_dark"]["applied"] & 1) == 1,
                  "slot_rate_1600": w["win_slots_per_s"] is not None and abs(w["win_slots_per_s"] - 1600) / 1600 < 0.05,
                  "no_pulse": w["win_pulses_emitted"] == 0 and w["win_pulses_omitted"] == 0,
                  "record_clean": all(r1[k] == r0[k] for k in ("spurious", "epoch_losses", "invalid_services"))}
        res["checks"] = checks
        log(("ENTER PASS" if all(checks.values()) else "ENTER FAIL") + f" {checks}; the board left in scan-only, data on; JD's key next, then exit")
    else:
        prev = json.load(open(f"{D}/scan-only-enter.json"))
        res["armed_check"] = light(1, 255); res["power_check"] = power()
        log(f"still in force? light {res['armed_check']} power {res['power_check']}")
        res["keys_after_key"] = keys(); res["keys_delta"] = (res["keys_after_key"] - prev["keys_after"]) & 0xFFFF
        log(f"key presses since enter: {res['keys_delta']}")
        res["record_after_key"] = record(); log(f"record {rec_brief(res['record_after_key'])}")
        res["window_scan_only_2"] = window(10); log(f"scan-only window {brief(res['window_scan_only_2'])}")
        devhook(h, 14, [2, 0]); time.sleep(1.5)
        res["after_force_active"] = {"light": light(1, 255), "power": power()}
        log(f"forced ACTIVE: {res['after_force_active']}")
        res["window_exit"] = window(15); log(f"lit window after the exit {brief(res['window_exit'])}")
        res["record_exit"] = record(); res["status_exit"] = status()
        log(f"record {rec_brief(res['record_exit'])}; status {res['status_exit']}")
        res["lighting_after"] = lp.read_lighting(h); log(f"lighting {res['lighting_after']}")
        res["mask_off"] = light(0, 0)
        devhook(h, 14, [2, 0xFF]); time.sleep(0.5)
        res["power_final"] = power(); log(f"released: {res['power_final']}")
        w2, wx, wl = res["window_scan_only_2"], res["window_exit"], prev["window_lit"]
        r0, r1, r2 = prev["record_before"], res["record_after_key"], res["record_exit"]
        checks = {"still_scan_only_at_key": res["armed_check"]["scan_only"],
                  "key_seen": res["keys_delta"] >= 1,
                  "scan_only_window_clean": w2["win_pulses_emitted"] == 0 and abs(w2["win_slots_per_s"] - 1600) / 1600 < 0.05,
                  "exit_leaves_scan_only": not res["after_force_active"]["light"]["scan_only"],
                  "lit_rate_back": abs(wx["win_slots_per_s"] - wl["win_slots_per_s"]) / wl["win_slots_per_s"] < 0.03 and wx["win_pulses_emitted"] > 0,
                  "record_clean": all(r2[k] == r0[k] for k in ("spurious", "epoch_losses", "invalid_services")),
                  "lighting_unchanged": res["lighting_after"] == prev["lighting_before"],
                  "released": res["power_final"]["forced"] == 0xFF and res["mask_off"]["mask"] == 0}
        res["checks"] = checks
        log(("EXIT PASS" if all(checks.values()) else "EXIT FAIL") + f" {checks}")
finally:
    res["t_end"] = time.strftime("%H:%M:%S")
    json.dump(res, open(OUT, "w"), indent=1)
    h.close()
PY
