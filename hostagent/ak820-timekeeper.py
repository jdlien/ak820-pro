#!/usr/bin/env python3
"""AK820 Pro timekeeper agent (clock-sync plan 3.8). Replaces the 3-hourly
ak820-clocksync.sh job.

Loop every 15 s:
  * sync when the raw-HID interface (re)appears (a slider flip reboots the
    board; a replug too);
  * sync when the loop's own wall-clock gap exceeds 60 s (the Mac slept);
  * sync every SYNC_INTERVAL s regardless;
  * every BIAS_INTERVAL s of continuous USB continuity, re-measure this Mac's
    SOF bias from the board's sof_frames_total vs the wall clock and cache it
    for ak820ctl (`clock --bias`), keyed by the USB controller the board is on.

Every transaction shells out to ak820ctl so exactly one process owns the
raw-HID interface at a time; failures (VIA holding it, no reply) are logged
and retried next round. Log: ~/Library/Logs/ak820pro-timekeeper.log
"""
import json, os, re, subprocess, sys, time

AK820_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTL  = os.environ.get("AK820_CTL") or os.path.join(AK820_ROOT, "time-util-ak820pro", "ak820ctl")
LOG  = os.path.expanduser("~/Library/Logs/ak820pro-timekeeper.log")
BIAS_STATE = os.path.expanduser("~/.ak820ctl-bias.json")
SYNC_INTERVAL = 300      # s (5 min: keeps |offset| < 20 ms even during the ILRC warm-up drift)
BIAS_INTERVAL = 900      # s of continuity before a bias re-measurement (>= 600 for +-3 ppm)
LOOP = 15
SLEEP_GAP = 60

VID, PID = 0x0C45, 0x8009


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def hid_present():
    try:
        import hid
        return any(d.get("usage_page") == 0xFF60 and d.get("usage") == 0x61
                   for d in hid.enumerate(VID, PID))
    except Exception:
        return False


def controller_id():
    """Something that changes when the board moves to another USB controller/hub."""
    try:
        out = subprocess.run(["ioreg", "-p", "IOUSB", "-w0", "-l"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r'"idProduct" = 32777.*?"locationID" = (\d+)', out, re.S)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def run_ctl(*args, timeout=30):
    r = subprocess.run([CTL, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def read_status():
    rc, out = run_ctl("clock", "--read")
    if rc != 0:
        return None
    d = {}
    m = re.search(r"offset board-host ([-+\d.]+) ms", out);     d["offset"] = float(m.group(1)) if m else None
    m = re.search(r"ref_state (\d+)", out);                       d["ref_state"] = int(m.group(1)) if m else None
    m = re.search(r"sof_epoch (\d+)\s+sof_frames_total (\d+)", out)
    if m:
        d["epoch"] = int(m.group(1)); d["frames"] = int(m.group(2))
    m = re.search(r"flags 0x([0-9a-f]+)", out);                  d["flags"] = int(m.group(1), 16) if m else None
    return d


def sync(reason):
    rc, out = run_ctl("clock")
    log(f"sync ({reason}): {out.splitlines()[-1] if out else 'no output'}" + ("" if rc == 0 else f" [rc={rc}]"))
    return rc == 0


def bias_step(state):
    """Accumulate continuity; when BIAS_INTERVAL of unbroken epoch has elapsed, compute b."""
    st = read_status()
    now = time.time()
    if not st or "epoch" not in st:
        state.clear(); return
    cid = controller_id()
    if state.get("cid") != cid or state.get("epoch") != st["epoch"]:
        state.clear()
        state.update(cid=cid, epoch=st["epoch"], t0=now, f0=st["frames"])
        return
    H = now - state["t0"]
    if H >= BIAS_INTERVAL:
        F = (st["frames"] - state["f0"]) & 0xFFFFFFFF
        b = (F / (1000.0 * H) - 1.0) * 1e6
        if -600 < b < 600:
            run_ctl("clock", "--bias", str(int(round(b))))
            log(f"bias: F={F} H={H:.1f}s b={b:+.1f} ppm (controller {cid}) cached")
            try:
                json.dump({"cid": cid, "b_ppm": b, "t": now}, open(BIAS_STATE, "w"))
            except Exception:
                pass
        state.clear()   # start the next measurement


def main():
    log("timekeeper start")
    last_loop = time.time()
    last_sync = 0.0
    was_present = False
    bias_state = {}
    while True:
        now = time.time()
        present = hid_present()
        reason = None
        if present and not was_present:
            reason = "enumerated"
        elif now - last_loop > SLEEP_GAP:
            reason = "wake"
        elif now - last_sync >= SYNC_INTERVAL:
            reason = "periodic"
        if present and reason:
            time.sleep(2 if reason == "enumerated" else 0)   # let the board settle after boot
            if sync(reason):
                last_sync = time.time()
        if present:
            try:
                bias_step(bias_state)
            except Exception as e:
                log(f"bias step error: {e}")
        else:
            bias_state.clear()
        was_present = present
        last_loop = time.time()
        time.sleep(LOOP)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
