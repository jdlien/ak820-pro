"""The PCF write waits for nobody watching (65f86da5) on the keyboard on gremlin,
on USB with the daemon owning the clock. HC_RTC page 4: ps_state, runs_ok,
pending, stale.

1. A daemon sync makes a write pending (waits up to 6 min for one).
2. Lit, it stays pending: 60 s, runs_ok unchanged.
3. The lights held dark (op 14 sub 2, stage 2): the write runs within ~5 s,
   pending and stale clear, runs_ok + 1. Released.
4. Lit again: the next sync's write waits until 10 min pass without input
   (from the last key, or the boot), checked every 20 s for up to 17 min;
   the board's key count says whether JD typed meanwhile.
Never enumerates HID; the stage is released in every case."""
import json
import sys
import time

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
from menu_s0_session import open_device  # noqa: E402
import ak820health as H  # noqa: E402

HC_RTC = 0x03
OUT = sys.argv[1] if len(sys.argv) > 1 else "pcf-unseen-board.json"
rec = {"events": []}
fails = []


def now():
    return time.strftime("%H:%M:%S")


def log(msg):
    line = f"{now()}  {msg}"
    print(line, flush=True)
    rec["events"].append(line)


def check(ok, what):
    log(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        fails.append(what)


def ps(h):
    b = H._txn_page(h, HC_RTC, 4)[4:]
    return {"ps_state": b[0], "runs_ok": b[3] | b[4] << 8, "restarts": b[5] | b[6] << 8,
            "pending": b[14], "stale": b[24], "maybe_stopped": b[7]}


def stage(h, s):
    """Op 14 sub 2: hold the ladder at stage s, or release it (None)."""
    h.write(bytes([0, H.SET_VALUE, H.HEALTH_CHANNEL, 0x76, 14, 2, 0xFF if s is None else s]) + bytes(26))
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and r[1] == H.HEALTH_CHANNEL and r[2] == 0x76 and r[3] == 14:
            return
    raise RuntimeError("op 14: no reply")


def wait_pending(h, limit_s, why):
    end = time.monotonic() + limit_s
    while time.monotonic() < end:
        p = ps(h)
        if p["pending"]:
            log(f"pending ({why}): {p}")
            return p
        time.sleep(5.0)
    return None


h = open_device()
held = False
try:
    p0 = ps(h)
    log(f"start: {p0}")
    rec["start"] = p0
    p = p0 if p0["pending"] else wait_pending(h, 6 * 60, "the first sync")
    check(p is not None, "a sync left a write pending")
    if p is not None:
        runs = p["runs_ok"]
        time.sleep(60.0)
        p = ps(h)
        log(f"after 60 s lit: {p}")
        check(p["pending"] == 1 and p["runs_ok"] == runs and p["ps_state"] == 0,
              "lit: still pending, nothing run")
        stage(h, 2)
        held = True
        t0 = time.monotonic()
        while time.monotonic() - t0 < 10.0:
            time.sleep(0.5)
            p = ps(h)
            if p["runs_ok"] > runs and not p["pending"] and p["ps_state"] == 0:
                break
        rec["dark_s"] = round(time.monotonic() - t0, 1)
        log(f"dark after {rec['dark_s']} s: {p}")
        check(p["runs_ok"] == runs + 1 and not p["pending"] and not p["stale"] and p["ps_state"] == 0,
              "dark: the write ran once, not stale")
        stage(h, None)
        held = False

        # The lit path: the next sync, then 10 min from the last input.
        p = wait_pending(h, 6 * 60, "the next sync")
        check(p is not None, "the next sync left a write pending")
        if p is not None:
            runs = p["runs_ok"]
            k0 = H.read_stalls(h)["key_presses"]
            t0 = time.monotonic()
            while time.monotonic() - t0 < 17 * 60:
                time.sleep(20.0)
                p = ps(h)
                k = H.read_stalls(h)["key_presses"] - k0
                log(f"{round(time.monotonic() - t0):4d} s lit: pending {p['pending']}, runs_ok {p['runs_ok']}, "
                    f"stale {p['stale']}, keys since {k}")
                if p["runs_ok"] > runs:
                    break
            rec["lit_s"] = round(time.monotonic() - t0)
            check(p["runs_ok"] == runs + 1 and not p["pending"] and not p["stale"],
                  f"lit: the write ran after {rec['lit_s']} s pending (10 min from the last input)")
    s = H.read_stalls(h)
    rec["end"] = {"ge25": s.get("count_ge_25ms"), "ge25_nonflash": s.get("count_ge_25ms_nonflash"),
                  "key_presses": s["key_presses"]}
    log(f"health: {rec['end']}")
finally:
    if held:
        stage(h, None)
    h.close()
    rec["fails"] = fails
    with open(OUT, "w") as f:
        json.dump(rec, f, indent=1)
print("PASS" if not fails else f"FAILED: {len(fails)}")
sys.exit(1 if fails else 0)
