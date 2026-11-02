#!/usr/bin/env python3
"""The wake fixes' gate, case 3 (plans/review-codex-wake-fixes-2026-10-31.md,
item 4): a `uhubctl` reconnection across a deep sleep, on white, with relay
2 off throughout (the drain). Codex asks for both USB bits back, a host's
frames after the wake and HID working, with no reset.

    venv/bin/python history/wake-case3-20261101/case3.py a [--wait-key 900]
    venv/bin/python history/wake-case3-20261101/case3.py b [--after 30] [--wait-key 900]

a: white asleep with the data off; the data comes on while it sleeps. Does
   the attach wake it and enumerate? If not within 30 s, it waits for a key
   (JD), with the data left on: the wake then meets a host that tried and
   failed, and the recovery's re-attach (3 s without frames) is the path.
b: the data off; wait for the sleep (Power saver: ~3 min idle); a key (JD)
   wakes it; --after s later (past the 3 s re-attach and the 20 s window)
   the data comes on.

Both read, once it is on USB: uptime (page 4) against the flash's boot, the
sleep record (op 14 sub 4: why it woke, the flags: a host's frames after the
wake, within 20 s, the re-attach), the health flags. The bits themselves are
not readable on this build (black's census is ds-phase only): enumeration
and HID after the wake need the driver's reset, resume or wakeup handler,
each of which sets both, as case 1 read them.

The daemon is paused for the run (macOS raw HID is exclusive) and restarted
at the end; the data goes off at the end (the standing state). Never relay
2, never port 4. Never enumerates HID: ioreg and the board's own open.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "hostagent"))
import deep_sleep as ds  # noqa: E402  (uhub, deep, open_dev, tail_ma)
import ak820health as health  # noqa: E402
import ak820battery as ba  # noqa: E402  (sleep_page: HC_POWER page 1)

LOG = os.path.join(REPO, "history", "power-bench-2026-10-15", "power.csv")
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist")
LABEL = "com.jdlien.ak820pro.agent"
ASLEEP_MA, AWAKE_MA = 6.0, 10.0


def say(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def bus():
    """Three looks, logged apart (the 20:06 11-01 miss: an enumerated board
    an ioreg grep did not see for 64 s)."""
    def run(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
        except subprocess.TimeoutExpired:
            return ""
    plane = run(["ioreg", "-p", "IOUSB", "-w0"])
    plane_l = run(["ioreg", "-p", "IOUSB", "-l", "-w0"])
    cls = run(["ioreg", "-r", "-c", "IOUSBHostDevice", "-l", "-w0"])
    return {"plane_name": "AK820 PRO@" in plane,
            "plane_pid": '"idProduct" = 32777' in plane_l,
            "class_pid": '"idProduct" = 32777' in cls and '"idVendor" = 3141' in cls}


def on_bus():
    b = bus()
    return any(b.values()), b


def current():
    rows = ds.tail_ma(LOG, 3)
    return rows[-1][1] if rows else None


def wait_state(asleep, secs, need=4):
    """`need` consecutive logger rows asleep (< 6 mA) or awake (> 10 mA)."""
    deadline = time.time() + secs
    seen = set()
    run = 0
    while time.time() < deadline:
        rows = ds.tail_ma(LOG, 2)
        for t, c in rows:
            if t in seen:
                continue
            seen.add(t)
            ok = (0 < c < ASLEEP_MA) if asleep else (c > AWAKE_MA)
            run = run + 1 if ok else 0
            if run >= need:
                return t, c
        time.sleep(0.5)
    return None


def daemon(on):
    if on:
        r = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", PLIST], capture_output=True, text=True)
    else:
        r = subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, text=True)
    say("daemon", "restarted" if on else "paused", (r.stderr or "").strip())


def read_board():
    h = ds.open_dev(30)
    try:
        isr = health.read_isr(h)
        rec = ds.deep(h)
        page = ba.sleep_page(h)
        hl = health.read_health(h)
    finally:
        h.close()
    return {"uptime_s": isr["uptime_ms"] / 1000.0, "record": rec, "sleep_page": page,
            "wdt_fired_last_boot": hl["wdt_fired_last_boot"], "wdt_degraded": hl["wdt_degraded"]}


def asleep_since(t0, t1):
    """Seconds the logger read white asleep (< 6 mA) between t0 and t1:
    page 4's uptime is the system timer's, which stops in Deep-sleep (3a, 21:03
    11-01: 1562 s awake + 3219 s asleep = the 4797 s since the flash, less its
    ~16 s), so no reset means uptime + this = the time since the boot."""
    asleep, prev = 0.0, None
    for t, c in ds.tail_rows(LOG, kb=int((t1 - t0) / 400 * 48) + 64):
        if t < t0 or t > t1:
            continue
        if prev is not None and 0 < prev[1] < ASLEEP_MA:
            asleep += t - prev[0]
        prev = (t, c)
    return asleep


def wait_bus(secs, out):
    t0 = time.time()
    first = {}
    while time.time() - t0 < secs:
        ok, b = on_bus()
        for k, v in b.items():
            if v and k not in first:
                first[k] = round(time.time() - t0, 2)
        if ok:
            time.sleep(1.0)
            ok2, b2 = on_bus()
            for k, v in b2.items():
                if v and k not in first:
                    first[k] = round(time.time() - t0, 2)
            out["bus_first_seen_s"] = first
            out["bus_looks"] = b2
            return True
        time.sleep(0.5)
    out["bus_first_seen_s"] = first
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=["a", "b"])
    ap.add_argument("--after", type=float, default=30.0, help="b: s from the wake to the data on")
    ap.add_argument("--wait-key", type=float, default=900.0, help="s to wait for JD's key")
    ap.add_argument("--boot", default="2026-11-01 19:44:00", help="the flash's boot, local time (uptime check)")
    a = ap.parse_args()
    res = {"variant": a.variant, "start": time.strftime("%Y-%m-%d %H:%M:%S")}
    c = current()
    if c is None or c < 0:
        sys.exit(f"the logger reads {c} mA: charging or missing (relay 2 must be off)")
    daemon(False)
    try:
        if a.variant == "a":
            say("waiting for white asleep (< 6 mA, 4 rows)")
            if not wait_state(True, 300):
                raise SystemExit("not asleep within 5 min")
            say("asleep; data on")
            res["data_on"] = time.time()
            ds.uhub("on")
            if wait_bus(30, res):
                res["woke_by"] = "the attach"
                say(f"on USB without a key: {res['bus_first_seen_s']}")
            else:
                say(f"not on USB in 30 s ({current()} mA); WAITING FOR A KEY on white (data left on)")
                w = wait_state(False, a.wait_key, need=2)
                if not w:
                    raise SystemExit("no key within the wait")
                res["woke_at"] = w[0]
                say(f"awake at {time.strftime('%H:%M:%S', time.localtime(w[0]))} ({w[1]} mA); waiting for USB")
                if not wait_bus(60, res):
                    raise SystemExit(f"awake but not on USB in 60 s: {res['bus_first_seen_s']}")
                res["woke_by"] = "a key"
                say(f"on USB {time.time() - w[0]:.1f} s after the wake: {res['bus_first_seen_s']}")
        else:
            ds.uhub("off")
            res["data_off"] = time.time()
            say("data off; waiting for the sleep (Power saver, ~3 min idle)")
            s = wait_state(True, 600)
            if not s:
                raise SystemExit("not asleep within 10 min")
            say(f"ASLEEP at {time.strftime('%H:%M:%S', time.localtime(s[0]))}; WAITING FOR A KEY on white")
            w = wait_state(False, a.wait_key, need=2)
            if not w:
                raise SystemExit("no key within the wait")
            res["woke_at"] = w[0]
            say(f"awake at {time.strftime('%H:%M:%S', time.localtime(w[0]))} ({w[1]} mA); data on in {a.after:.0f} s")
            time.sleep(max(0.0, w[0] + a.after - time.time()))
            res["data_on"] = time.time()
            ds.uhub("on")
            say("data on")
            if not wait_bus(60, res):
                raise SystemExit(f"not on USB in 60 s after the data on: {res['bus_first_seen_s']}")
            say(f"on USB: {res['bus_first_seen_s']}")
        time.sleep(2)
        b = read_board()
        res["board"] = b
        boot = time.mktime(time.strptime(a.boot, "%Y-%m-%d %H:%M:%S"))
        now = time.time()
        res["asleep_since_boot_s"] = round(asleep_since(boot, now), 1)
        res["uptime_vs_flash_s"] = round(b["uptime_s"] + res["asleep_since_boot_s"] - (now - boot), 1)
        say(f"uptime {b['uptime_s']:.0f} s awake + {res['asleep_since_boot_s']:.0f} s asleep "
            f"({res['uptime_vs_flash_s']:+.0f} s against a boot at {a.boot}); "
            f"wdt fired last boot {b['wdt_fired_last_boot']}")
        say(f"record: {json.dumps(b['record'])}")
        say(f"sleep page: {json.dumps(b['sleep_page'])}")
        r = b["record"]
        # A host's frames after the wake: 0x04 latches only inside the
        # recovery's USB step, which a re-attach closes before the frames come
        # back; 0x10 watches 20 s (sleep.c, recovery_task). b's data comes on
        # past both windows, so there the frames are the enumeration and the
        # HID reads above (3b, 21:13 11-01: flags 0x4B, by design).
        frames = bool(r["flags"] & (ds.V_USB_SOF | ds.V_USB_20S)) or a.variant == "b"
        res["pass"] = bool(r["slept"] and r["reason"] == "key" and frames and abs(res["uptime_vs_flash_s"]) < 60
                           and not b["wdt_fired_last_boot"])
        say("case 3", a.variant, "PASS" if res["pass"] else "FAIL",
            "(slept, woke on the key, a host's frames after the wake, no reset since the flash, HID read)")
    except SystemExit as e:
        res["error"] = str(e)
        say("STOPPED:", e)
    finally:
        try:
            ds.uhub("off")
            say("data off")
        except SystemExit as e:
            say("⚠️ data off failed:", e)
        daemon(True)
        out = os.path.join(HERE, f"case3{a.variant}-{time.strftime('%H%M%S')}.json")
        with open(out, "w") as f:
            json.dump(res, f, indent=1, default=str)
        say("wrote", out)


if __name__ == "__main__":
    main()
