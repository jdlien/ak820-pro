#!/bin/bash
# The silence injections on white (11-02), the frame-counter detector's
# first bench run (D3 case 5, op 28 subs 6 and 7, fdbad7e4a5): over the data
# line with the daemon paused, a set of all-interrupt silences and, after each,
# the record's deltas against the plan's predicted outcome (exact; INVALID by
# the guard; INVALID by the frame counter). Then two with the data cut: armed
# with a 5 s delay, the data off, the silence fires on battery with the bus
# suspended, the data back on, the record read through the reconnection (the
# suspend and the re-enumeration are bus events: each one loss by design, and
# the script subtracts them). No relay. The lights stay as they are; the
# board does not answer during a silence. Data off and the daemon back by the
# trap. Everything to silence-check.json and the log.
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
import sys, time, json, subprocess
sys.path.insert(0, "hostagent"); sys.path.insert(0, "scripts")
import ak820health as hp, rowisr_diag as rd
D = "history/rowisr-stage1-20261101"
def log(s): print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
res = {"t0": time.strftime("%H:%M:%S"), "usb": [], "battery": []}

def record(h):
    r = rd.xfer(h, 5, b"")[4:]
    return {"spurious": r[2], "late_omit": r[3], "epoch_losses": r[4], "invalid_services": r[5], "serviced_lo16": r[26] | r[27] << 8}
def usb(h): return rd.usb_dict(rd.xfer(h, 6))
def status(h): return rd.status_dict(rd.xfer(h, 2))
def silence(h, ms, delay):
    us = int(round(ms * 1000))
    return rd.status_dict(rd.xfer(h, 7, us.to_bytes(4, "little") + bytes([delay & 0xFF, delay >> 8])))
def report(h): return rd.report_dict(rd.xfer(h, 8), rd.xfer(h, 9))
def snap(h):
    return {"record": record(h), "usb": usb(h), "sched": hp.read_sched(h)}
def deltas(a, b):
    d = {k: (b["record"][k] - a["record"][k]) & 0xFF for k in ("spurious", "epoch_losses", "invalid_services", "late_omit")}
    d.update({k: (b["usb"][k] - a["usb"][k]) & 0xFF for k in ("usb_rejects", "usb_events")})
    d["usb_checked"] = (b["usb"]["usb_checked"] - a["usb"]["usb_checked"]) & 0xFFFFFFFF
    d["slots_elapsed"] = (b["sched"]["slots_elapsed"] - a["sched"]["slots_elapsed"]) & 0xFFFFFFFF
    d["missed"] = ((b["sched"]["slots_elapsed"] - b["sched"]["serviced_valid"]) - (a["sched"]["slots_elapsed"] - a["sched"]["serviced_valid"])) & 0xFFFFFFFF
    d["omitted"] = (b["sched"]["pulses_omitted"] - a["sched"]["pulses_omitted"]) & 0xFFFFFFFF
    return d

# (ms, expected losses by the guard, expected rejections by the frame counter), the plan's predictions on USB from
# the length alone; None = the observation gap decides (the near-threshold cases: reported, not gated)
USB_CASES = [(5, 0, 0), (7.5, 0, 0), (7.9, None, 0), (8.1, None, 0), (8.5, 1, 0), (20, 1, 0), (100, 1, 0), (200, 1, 0),
             (350, 0, 1), (700, 0, 1), (1049, 0, 1), (1000, 1, 0), (2048, 1, 0), (7000, 1, 0)]
h = hp.open_device()
try:
    res["before"] = snap(h); res["status_before"] = status(h)
    log(f"before: record {res['before']['record']} usb {res['before']['usb']}")
    if not res["before"]["usb"]["usb_trusted_now"]:
        log("the frame counter is NOT trusted now (USB not active?): the USB set would judge nothing"); 
    for ms, g, f in USB_CASES:
        a = snap(h)
        st = silence(h, ms, 300)
        if not st["silence_armed"]:
            log(f"{ms} ms: REFUSED"); res["usb"].append({"ms": ms, "refused": True}); continue
        time.sleep(0.3 + ms / 1000.0 + 0.6)
        b = snap(h); st2 = status(h); rp = report(h)
        d = deltas(a, b)
        meas = rp["measured_ms"]
        exp_losses = None if g is None else g + f
        ok = ((exp_losses is None and d["epoch_losses"] <= 1) or d["epoch_losses"] == exp_losses) and d["usb_rejects"] == f \
             and d["usb_events"] == 0 and d["spurious"] == 0 and rp["run"] == (st["silences_run"] + 1) & 0xFF and abs(meas - ms) < 0.2
        res["usb"].append({"ms": ms, "measured_ms": meas, "expected": {"guard": g, "frames": f}, "deltas": d, "report": rp,
                           "usb_after": b["usb"], "pass": ok})
        log(f"{ms} ms: measured {meas} ms; losses {d['epoch_losses']} (expected {'the gap decides' if exp_losses is None else exp_losses}), "
            f"frame rejects {d['usb_rejects']} (expected {f}), bus-event rejects {d['usb_events']}, invalid {d['invalid_services']}, "
            f"spurious {d['spurious']}, missed slots {d['missed']}, omitted {d['omitted']}, judged {d['usb_checked']}; "
            f"the extension read {rp['ext_delta_ms']} ms across it, generation +{rp['gen_delta']}"
            f"{' (the guard: its gap ' + str(rp['guard_gap1_ms']) + ' ms)' if rp['guard_rejected'] else ''}; last rejection spans {b['usb']['usb_last_dt_ms']}/{b['usb']['usb_last_df_ms']} ms "
            f"-> {'PASS' if ok else 'FAIL'}")
    res["after_usb"] = snap(h)
finally:
    h.close()

# The data cut: armed with the 5 s delay, data off at once, the silence on battery with the bus suspended, data on, read back.
def uhub(state): subprocess.run(["uhubctl", "-l", "3-1.3.4", "-p", "2", "-a", state, "-e"], capture_output=True)
def present():
    return subprocess.run("ioreg -p IOUSB -l -w0 | grep -q '\"idProduct\" = 32777'", shell=True).returncode == 0
BATT_CASES = [(20, 1), (350, 0)]   # (ms, the silence's own expected losses: the guard's; the bus events' are subtracted)
for ms, g in BATT_CASES:
    h = hp.open_device()
    try:
        a = snap(h); st = silence(h, ms, 5000)
    finally:
        h.close()
    if not st["silence_armed"]:
        log(f"battery {ms} ms: REFUSED"); res["battery"].append({"ms": ms, "refused": True}); continue
    uhub("off"); t_off = time.time(); log(f"data off; the {ms} ms silence fires in 5 s on battery")
    time.sleep(8.0)
    uhub("on"); log("data on")
    for _ in range(15):
        if present(): break
        time.sleep(2)
    if not present():
        log("no board after the data on"); res["battery"].append({"ms": ms, "lost": True}); continue
    time.sleep(2)
    h = hp.open_device()
    try:
        b = snap(h); st2 = status(h)
    finally:
        h.close()
    rp = None
    h = hp.open_device()
    try:
        rp = report(h)
    finally:
        h.close()
    d = deltas(a, b); meas = rp["measured_ms"]
    own = (d["epoch_losses"] - d["usb_events"]) & 0xFF
    ok = own == g and d["usb_rejects"] == 0 and rp["run"] == (st["silences_run"] + 1) & 0xFF and abs(meas - ms) < 0.2
    res["battery"].append({"ms": ms, "measured_ms": meas, "expected_own_losses": g, "deltas": d, "own_losses": own, "report": rp,
                           "usb_after": b["usb"], "pass": ok})
    log(f"battery {ms} ms: measured {meas} ms; losses {d['epoch_losses']}, of them bus events {d['usb_events']}, the silence's own {own} "
        f"(expected {g}), frame rejects {d['usb_rejects']}, spurious {d['spurious']}; usb now {b['usb']['usb_state']} -> {'PASS' if ok else 'FAIL'}")
res["t_end"] = time.strftime("%H:%M:%S")
res["pass"] = all(c.get("pass") for c in res["usb"]) and all(c.get("pass") for c in res["battery"])
json.dump(res, open(f"{D}/silence-check.json", "w"), indent=1)
log("ALL PASS" if res["pass"] else "SOME FAIL")
PY
