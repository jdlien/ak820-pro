#!/bin/bash
# Stage 2's scan-only check, the key half in one run (11-02): data on, the
# stage forced LIGHTS_OFF and light sleep's mask bit 0 armed (scan-only), a
# window, then the key count polled every 0.5 s for up to 300 s with the
# mask re-armed every 200 s (its TTL is a byte of seconds: the 11-01 run's
# handshake outlived it). At the first key: the mask read back (the reply
# carries the state BEFORE the set, so it says whether scan-only was in
# force as the key was seen), the record, a second window; then forced
# ACTIVE (the exit by the RGB path), a lit window, the record, the lighting;
# the mask cleared and the force released in a finally; data off and the
# daemon back by the trap. The lights are dark on purpose throughout.
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
import ak820health as hp, ak820lighting as lp, rowisr_diag as rd
from rowisr_baseline import devhook
D = "history/rowisr-stage1-20261101"
OUT = f"{D}/scan-only-key.json"
def log(s): print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
h = hp.open_device()
res = {"t0": time.strftime("%H:%M:%S")}
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
def window(secs):
    A = hp.read_sched(h); tA = time.time(); time.sleep(secs); B = hp.read_sched(h); tB = time.time()
    w = hp.sched_window(A, B, tB - tA); w["page7_after"] = B; return w
def keys(): return hp.read_stalls(h)["key_presses"]
def brief(w): return {k: w[k] for k in ("win_secs", "win_slots_per_s", "win_serviced_valid", "win_missed_slots",
                                       "win_pulses_emitted", "win_pulses_omitted", "win_elapsed_mean_us", "win_cpu_pct") if k in w}
def rec_brief(r): return {k: r[k] for k in ("spurious", "epoch_losses", "invalid_services", "late_omit", "omit_run_max", "serviced_lo16")}
try:
    res["power_before"] = power(); res["lighting_before"] = lp.read_lighting(h); res["record_before"] = record()
    log(f"power {res['power_before']} lighting {res['lighting_before']} record {rec_brief(res['record_before'])}")
    devhook(h, 14, [2, 2]); res["arm"] = light(1, 255); time.sleep(1.5)
    res["armed_dark"] = light(1, 255); res["power_dark"] = power()
    log(f"forced LIGHTS_OFF, armed: {res['armed_dark']} {res['power_dark']}")
    res["window_scan_only"] = window(10); log(f"scan-only window {brief(res['window_scan_only'])}")
    k0 = keys(); res["keys_start"] = k0
    t_start = t_arm = time.time(); seen = None
    log(f"PRESS NOW: key count {k0}; watching for 300 s")
    while time.time() - t_start < 300:
        if time.time() - t_arm > 200:
            res.setdefault("rearms", []).append({"t": time.strftime("%H:%M:%S"), "light": light(1, 255)}); t_arm = time.time()
        k = keys()
        if k != k0:
            st = light(1, 255)
            seen = {"t": time.strftime("%H:%M:%S"), "after_s": round(time.time() - t_start, 1), "keys_delta": (k - k0) & 0xFFFF,
                    "light_at_key": st, "power_at_key": power()}
            log(f"KEY SEEN {seen}")
            break
        time.sleep(0.5)
    res["key"] = seen
    if seen is None: log("no key in 300 s")
    res["record_after_key"] = record(); log(f"record {rec_brief(res['record_after_key'])}")
    res["window_scan_only_2"] = window(10); log(f"scan-only window {brief(res['window_scan_only_2'])}")
    devhook(h, 14, [2, 0]); time.sleep(1.5)
    res["after_force_active"] = {"light": light(1, 255), "power": power()}; log(f"forced ACTIVE: {res['after_force_active']}")
    res["window_exit"] = window(15); log(f"lit window after the exit {brief(res['window_exit'])}")
    res["record_exit"] = record(); res["lighting_after"] = lp.read_lighting(h)
    log(f"record {rec_brief(res['record_exit'])} lighting {res['lighting_after']}")
    w1, w2, wx = res["window_scan_only"], res["window_scan_only_2"], res["window_exit"]
    r0, r2 = res["record_before"], res["record_exit"]
    checks = {"scan_only_in_force": res["armed_dark"]["scan_only"] and (res["armed_dark"]["applied"] & 1) == 1,
              "slot_rate_1600": abs(w1["win_slots_per_s"] - 1600) / 1600 < 0.05 and abs(w2["win_slots_per_s"] - 1600) / 1600 < 0.05,
              "no_pulse": w1["win_pulses_emitted"] + w1["win_pulses_omitted"] + w2["win_pulses_emitted"] + w2["win_pulses_omitted"] == 0,
              "key_seen_in_scan_only": seen is not None and seen["light_at_key"]["scan_only"] and (seen["light_at_key"]["applied"] & 1) == 1,
              "exit_leaves_scan_only": not res["after_force_active"]["light"]["scan_only"],
              "lit_rate_back": abs(wx["win_slots_per_s"] - 3744) / 3744 < 0.03 and wx["win_pulses_emitted"] > 0,
              "record_clean": all(r2[k] == r0[k] for k in ("spurious", "epoch_losses", "invalid_services")),
              "lighting_unchanged": res["lighting_after"] == res["lighting_before"]}
    res["checks"] = checks
    log(("PASS" if all(checks.values()) else "FAIL") + f" {checks}")
finally:
    try:
        res["mask_off"] = light(0, 0); devhook(h, 14, [2, 0xFF]); time.sleep(0.5); res["power_final"] = power()
        log(f"released: {res['power_final']}")
    except Exception as e:
        res["release_error"] = repr(e); log(f"RELEASE FAILED: {e!r}")
    res["t_end"] = time.strftime("%H:%M:%S")
    json.dump(res, open(OUT, "w"), indent=1)
    h.close()
PY
