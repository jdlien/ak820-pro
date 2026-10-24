#!/usr/bin/env python3
"""The deep-sleep experiment on the bench (plans/SLEEP-PLAN.md): does a key
wake it, what does it draw asleep, and is the waking key itself lost.

    venv/bin/python scripts/deep_sleep.py [--wait 20] [--no-press] [--no-feed] [--cap 120] [--preset N] [--out DIR]

In order: relay 2 off (the pack); the stage forced to SCREEN_OFF and light
sleep off; arm (op 14 sub 4: a 15 s delay, the cap); USB data off
(`uhubctl`, so USB is not configured, one of the sleep's preconditions);
watch the logger for the current to fall (asleep: entry confirmed, or the
run stops there); --wait s after that the wake rig presses F19 once (unless
--no-press: the cap wakes it); --hold-after s later (5 by default; longer
to watch the daemon's --radio pick the board back up, its status file's
radio fields logged while asleep and after the press) data back on, wait for the board, and
read the record: why it woke, which column pins, seconds asleep, stray
wakes, the PLL's lock loops, whether the waking key registered, and the USB
transceiver after the wake.

--no-feed leaves the watchdog unfed while asleep: a reset ~12 s in means it
counts in Deep-sleep (the record is then gone with the RAM; the retained
watchdog record, `ak820 health --json`, names site 27); the cap reached
unfed means it does not. Measured 19:16 10-18: it does not.

--preset N (with --no-press) is the 32-bit widths' test
(plans/DEEP-SLEEP-BUILD-PLAN.md, validation 7): the counted seconds start
at N and the cap is N + --cap, so with N near 65,535 the count crosses 16
bits asleep. A 16-bit count would wrap and never reach the cap. Pass: it
woke on the cap with exactly --cap seconds counted past the preset (the
clocks take only those).

Pass: entry seen in the logger; the record says it slept and why (a key on a
press run, the cap on a --no-press run, a reset in the deep-sleep site on a
--no-feed run); on a press run the waking key registered. Needs JD at hand:
if it never wakes, the slider brings it back. Restored in a `finally`, each
step on its own: relay 1 open, relay 2 on, data on, the board back on USB (a
rig tap if not), the arm cancelled, the stage released.
"""
import argparse, json, os, subprocess, sys, time

import hid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sleep_baseline as sb  # noqa: E402

cm = sb.cm
HUB, PORT = "3-1.3.4", "2"   # docs/test-bench.md: the relay cable's port (the Acasis, from 10-23; 0-1.4 before)
REASONS = {0: "none", 1: "key", 2: "cap", 3: "strays", 4: "blocked", 5: "knob", 6: "charge"}   # SLEEP_WAKE_*; 2 is the cap or the backstop
# The record's flags (SLEEP_V_* in sleep.h)
V_PCF, V_ACQ_DONE, V_USB_SOF, V_REATTACH, V_USB_20S, V_PLL_CEIL, V_SLEPT, V_BOUND = (1 << i for i in range(8))
# The recovery's steps (SLEEP_RC_*): the record's last byte names those that timed out
RC_STEPS = ["input", "clock", "gauge", "radio", "supply", "usb", "display"]
AK820 = os.path.expanduser("~/Library/Application Support/ak820pro/bin/ak820")
STATUS = os.path.expanduser("~/Library/Application Support/ak820pro/ak820-agent.status")
DELAY_S = 15


def watch_radio(secs, log):
    """Wait secs, noting each change in the daemon's radio fields (its --radio
    runs on its own media tick, so this only reads the status file)."""
    end, last = time.time() + secs, None
    while True:
        try:
            with open(STATUS) as f:
                kv = dict(ln.rstrip("\n").split("=", 1) for ln in f if "=" in ln)
        except OSError:
            kv = {}
        cur = {k: kv.get(k) for k in ("transport", "radio", "radio_pushes", "radio_silent")}
        if cur != last:
            log.append({"t": round(time.time(), 2), **cur})
            last = cur
        if time.time() >= end:
            return
        time.sleep(min(0.5, max(0.0, end - time.time())))


def uhub(state):
    try:
        rc = subprocess.run(["uhubctl", "-l", HUB, "-p", PORT, "-a", state, "-e"],
                            capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"uhubctl {state} timed out")
    if rc.returncode:
        raise SystemExit(f"uhubctl {state} failed: {rc.stdout}{rc.stderr}")


def on_bus():
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-w0"], capture_output=True, text=True, timeout=10).stdout
    return "AK820 PRO@" in out


def deep(h, arg=0, delay=DELAY_S, cap=120, no_feed=False, preset=0):
    """op 14 sub 4: arg 0 reads, 1 arms, 2 cancels; returns the record (v2,
    sleep.h: 32-bit counts, the knob's and the charger's P1 bits, a sequence
    number). cap is counted seconds, 0 the 24 h backstop; preset starts the
    count there (the 32-bit widths' test)."""
    r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, cm.HC_DEVHOOK, 14, 4, arg, delay]
                + list(cap.to_bytes(4, "little")) + [1 if no_feed else 0]
                + list(preset.to_bytes(4, "little")) + [0] * 16)
    if len(r) < 32 or r[3] != 14 or r[4] != 4:
        raise SystemExit(f"a reply to another op: {r[:12].hex()}")
    o = r[5:32]
    if o[0] != 2:
        raise SystemExit(f"record version {o[0]}, not 2: an older firmware")
    u16 = lambda i: o[i] | o[i + 1] << 8
    u32 = lambda i: int.from_bytes(o[i:i + 4], "little")
    f = o[5]
    return {"state": o[1], "reason": REASONS.get(o[2], o[2]), "blocked": u16(3), "flags": f,
            "slept": bool(f & V_SLEPT), "pcf": bool(f & V_PCF), "usb_back_20s": bool(f & V_USB_20S),
            "pll_ceiling": bool(f & V_PLL_CEIL), "bound": bool(f & V_BOUND), "reattach": bool(f & V_REATTACH),
            "secs": u32(6), "strays": u16(10), "p0": u16(12), "p2": u16(14), "p1": u32(16),
            "pll_loops": u16(20), "key_gain": u16(22), "seq": u16(24),
            "timed_out": [nm for i, nm in enumerate(RC_STEPS) if o[26] & (1 << i)]}


def bench_sleep(h, ms):
    """op 14 sub 5: the ladder's sleep time for the bench (ms, at least 30 s;
    0 clears it). Not persisted."""
    r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, cm.HC_DEVHOOK, 14, 5, 0] + list(ms.to_bytes(4, "little")) + [0] * 22)
    if len(r) < 5 or r[3] != 14 or r[4] != 5:
        raise SystemExit(f"a reply to another op: {r[:12].hex()}")


def need_bus(wait_s=30.0):
    """Back on USB, waiting up to wait_s for it to enumerate (codex)."""
    deadline = time.time() + wait_s
    while not on_bus():
        if time.time() > deadline:
            raise SystemExit(f"not on USB after {wait_s:.0f} s")
        time.sleep(0.5)
    time.sleep(2)


_good_path = None   # the last path open_dev opened


def open_dev(wait_s=30.0):
    """The board's raw HID, retried: on macOS it opens exclusively, and the
    now-playing daemon reopens it the moment USB comes back (the cycle run's
    seventh cycle, 20:14 10-18: "raw HID interface busy"). 30 s, not 8: the
    daemon's clock sync on enumeration held it 11 s (05:43:24-35 10-19) and
    stopped the 300-cycle soak at cycle 248."""
    global _good_path
    deadline = time.time() + wait_s
    while True:
        try:
            h = cm.ak820text.open_device()
            _good_path = cm.ak820text._cached_path or _good_path
            return h
        except SystemExit:
            # One collision with another opener at the wrong moment clears
            # ak820text's cached path and starts its enumeration backoff (60 s
            # and up), though the board never moved: two scripts opening the
            # cable by turns (overrun_diag.py and its load, 00:07 10-20) gave
            # up here. So the last path that opened goes back, and the next
            # try opens it directly. A board that re-enumerated has a new
            # path; the old one just fails, as the cleared one would have.
            if cm.ak820text._cached_path is None and _good_path is not None:
                cm.ak820text._cached_path = _good_path
            if time.time() > deadline:
                raise
            time.sleep(0.3)


def with_dev(fn, *args, **kw):
    h = open_dev()
    try:
        return fn(h, *args, **kw)
    finally:
        h.close()


def light_off(h):
    cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, cm.HC_DEVHOOK, 14, 3, 0, 2, 0, 0] + [0] * 23)


_restored = None   # restore()'s result, once it has run


def restore(dev, *controls):
    """Put the bench back, power first, each step on its own: relay 1 open,
    relay 2 on (on USB power the ladder never sleeps, and a charge start wakes
    a sleeping board), data on, the board back on USB (one rig tap if not: a
    full pack gives no charge edge), then `controls`, each (what, fn, *args)
    run through the retrying open. Shared by a run's `finally` and its
    deadline guard, which exits without one (codex, deep-sleep build review 8
    and its verifies): once, under sb.cleanup_lock, so the two never run it
    together or twice. True if every step went."""
    global _restored
    with sb.cleanup_lock:
        if _restored is None:
            _restored = _restore(dev, *controls)
        return _restored


def _restore(dev, *controls):
    done = [sb.attempt("relay 1 open", sb.bounded, sb.relay1, dev, False),
            sb.attempt("relay 2 on", sb.relay2, "on"),
            sb.attempt("data on", uhub, "on")]
    back = sb.attempt("the board on USB", need_bus, 30)
    if not back:
        sb.attempt("a wake tap", sb.bounded, sb.press, dev, 40, 200)
        back = sb.attempt("the board on USB after the tap", need_bus, 30)
    if not back:
        return False
    done += [sb.attempt(what, with_dev, fn, *args) for what, fn, *args in controls]
    return all(done)


def power_op(h, sub=0, arg=0):
    """op 14 sub 0 (read), 1 (set the mode to arg) or 2 (hold the stage at
    arg, 0xFF releases): returns (mode, stage). Sub 1 persists the mode."""
    r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, cm.HC_DEVHOOK, 14, sub, arg] + [0] * 26)
    if len(r) < 6 or r[3] != 14:
        raise SystemExit(f"a reply to another op: {r[:12].hex()}")
    return r[4], r[5]


def tail_rows(path, kb=48):
    """The logger's rows in the file's last `kb` KB (~400 rows at 48), as
    (epoch, mA)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - kb * 1024))
            lines = f.read().decode(errors="replace").splitlines()[1:]
    except OSError:
        return []
    out = []
    for ln in lines:
        p = ln.split(",")
        try:
            out.append((float(p[1]), float(p[5])))
        except (IndexError, ValueError):
            pass
    return out


# Between awake and dark (27-30 mA) and the 2.4G module's tail: in 2.4G the
# draw falls to ~15 mA for ~5 s after the MCU stops, then to ~3.2 mA, and a
# 15 mA edge timed the fall at the tail's end (PCF 4-6 s long on 10-19). The
# tail is the module's, not the MCU's: counted/PCF is 0.842 in both modes.
SLEEP_EDGE_MA = 22.0


def edges(rows, t_lo, t_hi, thr=SLEEP_EDGE_MA):
    """The sleep's fall and rise in the logger, each the midpoint between
    the last sample on one side of `thr` and the first on the other (the
    logger samples ~1 s apart, so each is within ~0.5 s): the first fall
    after t_lo and the rise after it, both before t_hi. None if either is
    missing."""
    rows = [r for r in rows if t_lo <= r[0] <= t_hi]
    fall = None
    for (t0, c0), (t1, c1) in zip(rows, rows[1:]):
        if fall is None:
            if c0 >= thr > c1:
                fall = (t0 + t1) / 2
        elif c1 >= thr > c0:
            return fall, (t0 + t1) / 2
    return None


def tail_ma(path, n=8):
    """The logger's last n rows (n <= ~35), (epoch, mA), read from the file's end (it is large)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode(errors="replace").splitlines()[1:]
    except OSError:
        return []
    out = []
    for ln in lines[-n:]:
        p = ln.split(",")
        try:
            out.append((float(p[1]), float(p[5])))
        except (IndexError, ValueError):
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=float, default=20.0, help="s asleep before the press")
    ap.add_argument("--no-press", action="store_true")
    ap.add_argument("--no-feed", action="store_true")
    ap.add_argument("--cap", type=int, default=120)
    ap.add_argument("--preset", type=int, default=0, help="counted seconds to start from (the widths' test)")
    ap.add_argument("--hold-after", type=float, default=5.0,
                    help="s the data stays off after the press (the daemon's radio picking the board back up)")
    ap.add_argument("--log", default=os.path.join(HERE, "..", "history", "power-bench-2026-10-15", "power.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "history", "deep-sleep-" + time.strftime("%Y%m%d-%H%M")))
    a = ap.parse_args()
    if not 10 <= a.cap <= 7200:
        sys.exit("--cap: 10-7200 s")
    if not 0 <= a.preset <= 0xFFFFFFFF - 7200 or (a.preset and not a.no_press):
        sys.exit("--preset: 0 to 2^32 less 7200, and with --no-press")
    if not a.no_press and not 5 <= a.wait <= a.cap - 5:
        sys.exit("--wait: 5 s to the cap less 5")
    if not cm.relay_on():
        sys.exit("relay 2 is off: start from the charging state")
    if not os.path.exists(a.log):
        sys.exit("the power logger's CSV is missing: entry cannot be confirmed")
    res = {"args": vars(a), "before": with_dev(deep)}
    devs = hid.enumerate(sb.VID, sb.PID)
    if len(devs) != 1:
        sys.exit(f"expected one USB relay, found {len(devs)}")
    ok = False
    controls = [("arm cancelled", deep, 2), ("stage released", cm.force_stage, None)]
    with hid.Device(path=devs[0]["path"]) as dev:
        sb.hold_relay(dev)   # relay 2 goes through this handle too (macOS opens it exclusively)
        guard = sb.deadline_guard(DELAY_S + a.cap + 300, lambda: restore(dev, *controls))
        try:
            cm.say("relay 2 off; light sleep off; stage forced to SCREEN_OFF")
            sb.relay2("off")
            deadline = time.time() + 30
            while not sb.on_battery():
                if time.time() > deadline:
                    raise SystemExit("the board never reported the pack")
                time.sleep(1)
            with_dev(light_off)
            with_dev(cm.force_stage, sb.SCREEN_OFF)
            time.sleep(8)
            base = [c for _, c in tail_ma(a.log, 8)]
            res["awake_ma"] = sum(base) / len(base) if base else None
            kp0 = sb.counts()["presses"]
            l0 = with_dev(lambda h: sb.health.read_link(h))
            with_dev(deep, 1, DELAY_S, a.preset + a.cap, a.no_feed, a.preset)
            t_arm = time.time()
            cm.say(f"armed ({DELAY_S} s delay, cap {a.cap} s); awake {res['awake_ma']:.2f} mA with data; data off")
            uhub("off")
            # The awake draw with the data off (the USB data itself costs ~1.7
            # mA), from the samples before the delay ends; then entry: three
            # samples after it, 2 mA under that (codex).
            time.sleep(max(0.0, t_arm + DELAY_S - 1 - time.time()))
            off = [c for t, c in tail_ma(a.log, 12) if t_arm + 5 < t < t_arm + DELAY_S - 1]
            res["awake_dataoff_ma"] = sum(off) / len(off) if off else None
            t_asleep = None
            if res["awake_dataoff_ma"] is not None:
                while time.time() < t_arm + DELAY_S + 30:
                    cur = [c for t, c in tail_ma(a.log, 3) if t > t_arm + DELAY_S + 1]
                    if len(cur) == 3 and all(c < res["awake_dataoff_ma"] - 2.0 for c in cur):
                        t_asleep = time.time()
                        break
                    time.sleep(1)
            res["asleep_seen_at"] = t_asleep
            if t_asleep is None:
                cm.say("no fall in the current: it did not go to sleep (the record will say why)")
            elif a.no_press or a.no_feed:
                cm.say("asleep (the current fell)")
                time.sleep(a.cap + 10 if a.no_press and not a.no_feed else 25)
            else:
                cm.say(f"asleep (the current fell); pressing F19 in {a.wait:.0f} s")
                res["radio_asleep"] = []
                watch_radio(a.wait, res["radio_asleep"])
                asleep = [c for t, c in tail_ma(a.log, int(a.wait) - 2) if t > t_asleep]
                res["asleep_ma"] = sum(asleep) / len(asleep) if asleep else None
                res["press_at"] = time.time()
                sb.press(dev, 40, 200)   # a realistic tap, not a long hold (codex)
                res["radio_after_press"] = []
                watch_radio(a.hold_after, res["radio_after_press"])
            cm.say("data on")
            uhub("on")
            need_bus(30)
            rec = with_dev(deep)
            res["record"] = rec
            l1 = with_dev(lambda h: sb.health.read_link(h))
            res["link"] = {k: l1[k] - l0[k] for k in ("sent", "timeouts", "giveups", "queue_full", "uart_overrun",
                                                      "uart_framing", "uart_parity")}
            cm.say(f"link across the run: {res['link']}")
            res["key_presses_gained"] = (sb.counts()["presses"] - kp0) & 0xFFFF
            res["logger"] = [(float(r["epoch"]), float(r["current_ma"])) for r in cm.log_rows(a.log, t_arm - 10, time.time())]
            cm.say(f"record: {rec}")
            if res.get("asleep_ma") is not None:
                cm.say(f"asleep: {res['asleep_ma']:.2f} mA (awake {res['awake_ma']:.2f})")
            if a.no_feed:
                try:
                    hj = json.loads(subprocess.run([AK820, "health", "--json"], capture_output=True, text=True,
                                                   timeout=10).stdout)
                    res["watchdog_record"] = hj.get("watchdog_record")
                except (OSError, ValueError, subprocess.TimeoutExpired) as e:
                    res["watchdog_record"] = f"unread: {e}"
                wr = res["watchdog_record"] if isinstance(res["watchdog_record"], dict) else {}
                # Either answer settles it: a reset recorded in site 27 (the
                # watchdog counts asleep), or the cap reached unfed (it does
                # not: 19:16 10-18, 30 s unfed, no reset).
                reset_asleep = rec["state"] == 0 and wr.get("valid") and wr.get("site_id") == 27
                slept_through = rec["slept"] and rec["reason"] == "cap"
                res["watchdog_counts_asleep"] = True if reset_asleep else (False if slept_through else None)
                ok = t_asleep is not None and (reset_asleep or slept_through)
            elif a.no_press:
                ok = t_asleep is not None and rec["slept"] and rec["reason"] == "cap" and rec["secs"] == a.cap
            else:
                ok = (t_asleep is not None and rec["slept"] and rec["reason"] == "key" and rec["key_gain"] >= 1
                      and res["link"]["giveups"] == 0)
        finally:
            done = restore(dev, *controls)
            guard.cancel()
            if done:
                cm.say("restored: relay 1 open, relay 2 on, data on, the arm cancelled, stage released")
            else:
                ok = False
                cm.say("⚠️ cleanup incomplete: see above")
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "deep-sleep.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("deep sleep:", "PASS" if ok else "FAIL", json.dumps(res.get("record", {})))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
