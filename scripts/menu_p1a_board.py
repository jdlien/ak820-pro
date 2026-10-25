#!/usr/bin/env python3
"""P1a on the board: every screen of the real menu, driven by op 27 (sub 11
opens it; subs 1-3 turn, click and hold), on a dev build. The design's board
gate (plans/CONFIG-MENU-P1-DESIGN.md, "Tests (P1a)").

    venv-win/Scripts/python.exe scripts/menu_p1a_board.py [--out F] < /dev/null

1. Outside the measured interval (it moves the health generation): Reset
   counters' two pages, and a cancel.
2. One measured interval (sub 10 armed): open; moves down and up with wraps;
   Power and Clock committed to another value and back (the board keeps its
   own settings at the end); Help's four topics paged; About; Health and
   Camera handed off and back; a choice cancelled; the hint; the close.
3. Every step: the expected screen id (16 + the node) and cursor, pixels_done
   within 1,000 ms, invariant_fail 0. The interval: no pass over 15 ms, none
   of 340 ms (aliased).
Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

# menu.c's nodes: sub 5 byte 14 is 16 + the node showing.
TOP, POWER, CLOCK, DIAG, HELP, ABOUT, EXIT = 1, 2, 3, 4, 5, 6, 7
RESET, TOPIC0 = 10, 11
SCR = lambda n: 16 + n  # noqa: E731
SETTLE_S = 1.0

log, fails = [], []


def check(ok, what):
    if not ok:
        fails.append(what)
        print("FAIL", what, flush=True)


def settle(h, what):
    t0 = time.perf_counter()
    while True:
        s = read_state(h)
        if s["pixels_done"] and s["owner"] in ("menu", "debug"):
            return s, (time.perf_counter() - t0) * 1000
        if s["owner"] == "debug" and s["debug_done"]:
            return s, (time.perf_counter() - t0) * 1000
        if time.perf_counter() - t0 > 3.0:
            check(False, f"{what}: not settled in 3 s ({s['owner']}, screen {s['screen']})")
            return s, 3000.0
        time.sleep(0.01)


def step(h, sub, args, what, screen=None, cursor=None, owner="menu"):
    st, seq = mutate(h, sub, args)
    check(st == 0, f"{what}: op 27 sub {sub} refused ({st})")
    state, s = wait(h, seq)
    check(state == "done", f"{what}: {state}")
    s, ms = settle(h, what)
    e = {"what": what, "ms": round(ms), "owner": s["owner"], "screen": s["screen"], "cursor": s["cursor"],
         "inv": s["invariant_fail"]}
    log.append(e)
    print(json.dumps(e), flush=True)
    check(s["owner"] == owner, f"{what}: owner {s['owner']}, not {owner}")
    if screen is not None:
        check(s["screen"] == screen, f"{what}: screen {s['screen']}, not {screen}")
    if cursor is not None:
        check(s["cursor"] == cursor, f"{what}: cursor {s['cursor']}, not {cursor}")
    check(ms <= SETTLE_S * 1000 or sub == 3, f"{what}: settled in {ms:.0f} ms")
    check(s["invariant_fail"] & ~0x20 == 0, f"{what}: invariant_fail {s['invariant_fail']:#x}")
    return s


turn = lambda h, n, what, **k: step(h, 1, bytes([n & 0xFF]), what, **k)  # noqa: E731
click = lambda h, what, **k: step(h, 2, b"", what, **k)  # noqa: E731
hold = lambda h, what, **k: step(h, 3, b"", what, **k)  # noqa: E731


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_p1a_board.json")
    a = ap.parse_args()
    h = open_device()
    meas = {}
    try:
        to_dash(h)
        # 1. Reset counters, outside the interval.
        step(h, 11, b"", "open (reset pass)", SCR(TOP), 0)
        turn(h, 2, "to Diagnostics", SCR(TOP), 2)
        click(h, "Diagnostics", SCR(DIAG), 1)
        turn(h, 2, "to Reset counters", SCR(DIAG), 3)
        click(h, "Reset counters", SCR(RESET), 0)
        click(h, "reset", SCR(RESET), 1)
        click(h, "back to Diagnostics", SCR(DIAG), 3)
        click(h, "Reset counters again", SCR(RESET), 0)
        hold(h, "cancel it", SCR(DIAG), 3)
        step(h, 11, b"", "close (reset pass)", owner="dash")
        time.sleep(1.5)   # the restore

        # 2. The measured interval.
        xfer(h, 10, bytes([1]))
        step(h, 11, b"", "open", SCR(TOP), 0)
        for i in range(1, 6):
            turn(h, 1, f"down {i}", SCR(TOP), i)
        turn(h, 1, "wrap down", SCR(TOP), 0)
        turn(h, -1, "wrap up", SCR(TOP), 5)
        turn(h, 1, "back to the top", SCR(TOP), 0)

        # Power: commit the next mode, then the original again.
        s = click(h, "Power", SCR(POWER))
        orig_p = s["cursor"]
        nxt = 1 + (orig_p % 4)
        turn(h, nxt - orig_p, "to another mode", SCR(POWER), nxt)
        click(h, "commit it", SCR(TOP), 0)
        click(h, "Power again", SCR(POWER), nxt)
        turn(h, orig_p - nxt, "to the original", SCR(POWER), orig_p)
        click(h, "commit the original", SCR(TOP), 0)

        # Clock: the same, then a cancel.
        turn(h, 1, "to Clock", SCR(TOP), 1)
        s = click(h, "Clock", SCR(CLOCK))
        orig_c = s["cursor"]
        nxt = 1 + (orig_c % 4)
        turn(h, nxt - orig_c, "to another clock", SCR(CLOCK), nxt)
        click(h, "commit it", SCR(TOP), 1)
        click(h, "Clock again", SCR(CLOCK), nxt)
        turn(h, orig_c - nxt, "to the original", SCR(CLOCK), orig_c)
        click(h, "commit the original", SCR(TOP), 1)
        click(h, "Clock to cancel", SCR(CLOCK), orig_c)
        turn(h, 1, "move", SCR(CLOCK))
        hold(h, "cancelled", SCR(TOP), 1)

        # Help: each topic, paged to its end and back.
        turn(h, 2, "to Help", SCR(TOP), 3)
        click(h, "Help", SCR(HELP), 1)
        for t in range(4):
            if t:
                turn(h, 1, f"to topic {t}", SCR(HELP), 1 + t)
            click(h, f"topic {t}", SCR(TOPIC0 + t), 0)
            turn(h, 1, f"topic {t} page 2", SCR(TOPIC0 + t))
            turn(h, -1, f"topic {t} page 1", SCR(TOPIC0 + t), 0)
            click(h, f"topic {t} back", SCR(HELP), 1 + t)
        hold(h, "Help back", SCR(TOP), 3)

        # About.
        turn(h, 1, "to About", SCR(TOP), 4)
        click(h, "About", SCR(ABOUT), 0)
        click(h, "About back", SCR(TOP), 4)

        # Diagnostics: Health and Camera, handed off and back.
        turn(h, -2, "to Diagnostics", SCR(TOP), 2)
        click(h, "Diagnostics", SCR(DIAG), 1)
        click(h, "Health page", owner="debug")
        click(h, "back from Health", SCR(DIAG), 1, owner="menu")
        turn(h, 1, "to Camera", SCR(DIAG), 2)
        click(h, "Camera page", owner="debug")
        click(h, "back from Camera", SCR(DIAG), 2, owner="menu")
        hold(h, "Diagnostics back", SCR(TOP), 2)

        # The hint: 5 s idle on the top level (the session stays open: 24 s).
        time.sleep(5.0)
        s, _ = settle(h, "after the hint")
        check(s["session"] == "open", "the session closed during the hint")

        step(h, 11, b"", "close", owner="dash")
        time.sleep(1.5)
        meas = decode_meas(xfer(h, 10, bytes([0])))
        check(not meas["aliased"], "a pass of 340 ms or more in the interval")
        check(meas["pass_max_us"] <= 15000, f"the longest pass {meas['pass_max_us']} us")
        check(meas["over15"] == 0, f"{meas['over15']} passes over 15 ms")
        to_dash(h)
    finally:
        h.close()
        with open(a.out, "w") as f:
            json.dump({"steps": log, "meas": meas, "fails": fails}, f, indent=1)
    ms = [e["ms"] for e in log]
    print(f"{len(log)} steps, the slowest settle {max(ms) if ms else 0} ms; "
          f"longest pass {meas.get('pass_max_us')} us, over 15 ms {meas.get('over15')}, piece {meas.get('piece_us')} us")
    print("PASS" if not fails else f"FAILED: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
