#!/usr/bin/env python3
"""S1: a real knob spin, measured from the menu's opening (plan S1, "The
encoder drain"; C10). JD opens the menu with Fn+knob and spins; this times
only the menu's session, not whatever the dashboard did before it.

    venv-win/Scripts/python.exe scripts/menu_s1_spin.py STOPFILE OUT.json [--style 16..19] < /dev/null

- Arms the fixture's opener (op 27 sub 6) and HC_ACCT, the loop accounting;
  with --menu (P1a), doesn't arm: Fn+knob opens the real menu.
- When the owner becomes the menu, arms sub 10 (its maxima from there) and,
  with --style, sets F3 in that style (op 27 sub 0).
- Every 250 ms: sub 5 and sub 10. When sub 10's count of passes over 15 ms
  grows, reads HC_ACCT's ring of slow passes (the last 16 of >= 10 ms) and
  keeps those of >= 15 ms, with their per-scope milliseconds.
- Ends at the stop file, or 2 s after the menu closes; disarms both.
Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402
from ak820health import read_acct, read_stalls  # noqa: E402


def mut(h, sub, args=b""):
    st, seq = mutate(h, sub, args)
    if st != 0:
        raise RuntimeError(f"op 27 sub {sub} {list(args)} refused: {st}")
    wait(h, seq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stop")
    ap.add_argument("out")
    ap.add_argument("--style", type=int, default=None, help="op 27 sub 0 pattern, 16-19: F3 once open")
    ap.add_argument("--menu", action="store_true", help="the real menu (P1a): the opener left unarmed")
    a = ap.parse_args()
    if os.path.exists(a.stop):
        os.remove(a.stop)
    h = open_device()
    log, slow, seen = [], [], set()
    res = {"opened": False}
    try:
        read_acct(h, "on")
        read_acct(h, "reset")
        if not a.menu:
            mut(h, 6, bytes([1]))
        print("ready: open the menu with Fn+knob", flush=True)
        t0 = time.perf_counter()
        opened = closed = None
        s0 = over = None
        while not os.path.exists(a.stop):
            s = read_state(h)
            now = time.perf_counter() - t0
            if opened is None and s["owner"] == "menu":
                xfer(h, 10, bytes([1]))
                opened, over = now, 0
                s0 = read_stalls(h)
                if a.style is not None:
                    mut(h, 0, bytes([a.style, 0]))
                print(f"menu open at {now:.1f} s: measuring", flush=True)
            if opened is not None and closed is None:
                m = decode_meas(xfer(h, 10, bytes([0])))
                log.append({"t": round(now - opened, 2), "owner": s["owner"], "screen": s["screen"],
                            "cursor": s["cursor"], "dropped": s["dropped"], "pass_max_us": m["pass_max_us"],
                            "over15": m["over15"], "piece_us": m["piece_us"], "op_us": m["op_us"]})
                if m["over15"] > over:
                    over = m["over15"]
                    for e in read_acct(h)["ring"]:
                        if e["pass_ms"] >= 15 and e["uptime_ms"] not in seen:
                            seen.add(e["uptime_ms"])
                            slow.append(e)
                if s["owner"] != "menu":
                    closed = now
                    res = {"opened": True, "secs": round(closed - opened, 1), "pass_max_us": m["pass_max_us"],
                           "over15": m["over15"], "piece_us": m["piece_us"], "op_us": m["op_us"],
                           "aliased": m["aliased"], "max_dropped": max(x["dropped"] for x in log)}
                    s1 = read_stalls(h)
                    res["ge10"] = s1["count_ge_10ms"] - s0["count_ge_10ms"]
                    res["ge25"] = s1["count_ge_25ms"] - s0["count_ge_25ms"]
                    print("menu closed: " + json.dumps(res), flush=True)
            if closed is not None and now - closed > 2.0:
                break
            time.sleep(0.25)
        if opened is not None and closed is None:   # stopped with the menu still open
            m = decode_meas(xfer(h, 10, bytes([0])))
            res = {"opened": True, "secs": round(time.perf_counter() - t0 - opened, 1), "still_open": True,
                   "pass_max_us": m["pass_max_us"], "over15": m["over15"], "piece_us": m["piece_us"],
                   "op_us": m["op_us"], "aliased": m["aliased"],
                   "max_dropped": max(x["dropped"] for x in log) if log else 0}
        res["slow_passes"] = slow
        print("SUMMARY " + json.dumps(res), flush=True)
    finally:
        try:
            if not a.menu:
                mut(h, 6, bytes([0]))
            read_acct(h, "off")
        finally:
            h.close()
            with open(a.out, "w") as f:
                json.dump({"summary": res, "log": log}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
