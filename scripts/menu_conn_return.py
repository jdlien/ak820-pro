#!/usr/bin/env python3
"""P3 on the board: the slider-follow return alone, measured. With op 27 sub
16's stand-in on BT, open the Pairing page, arm C10's interval (sub 10), move
the stand-in off BT (the menu goes back to the top level from the confirm
geometry: a layout change), and read the interval's longest pass. Then the
same return from the slot list (a list to a list). The stand-in is cleared at
the end, whatever happens.

    venv-win/Scripts/python.exe scripts/menu_conn_return.py [--runs 3] [--out F] < /dev/null

Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import menu_p1a_board as B  # noqa: E402
from menu_s0_session import open_device, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402


def measure(h, link, what):
    xfer(h, 10, bytes([1]))   # a new interval
    B.standin(h, link)
    s, ms = B.settle(h, what)
    time.sleep(0.3)
    m = decode_meas(xfer(h, 10, bytes([0])))
    return {"what": what, "screen": s["screen"], "cursor": s["cursor"], "settle_ms": round(ms),
            "pass_max_us": m["pass_max_us"], "over15": m["over15"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default="menu_conn_return.json")
    a = ap.parse_args()
    h = open_device()
    out = []
    try:
        to_dash(h)
        for r in range(a.runs):
            B.standin(h, B.LINK(1, B.S_CONNECTED))
            B.step(h, 11, b"", f"open {r}", B.SCR(B.TOP), 0)
            B.turn(h, B.R_CONN, "to Connection", B.SCR(B.TOP), B.R_CONN)
            B.click(h, "Connection", B.SCR(B.CONN), 2)
            B.turn(h, 2, "to Pair a device", B.SCR(B.CONN), 4)
            B.standin(h, B.LINK(1, B.S_CONNECTED), B.PF_WAITING)
            B.click(h, "Pair a device", B.SCR(B.PAIRING))
            out.append(measure(h, B.L_USB, f"run {r}: off BT under the Pairing page"))
            B.standin(h, B.LINK(1, B.S_CONNECTED))
            B.settle(h, "back on BT")
            B.click(h, "Connection again", B.SCR(B.CONN), 2)
            out.append(measure(h, B.L_USB, f"run {r}: off BT under the slot list"))
            B.standin(h, 0xFF)
            B.step(h, 11, b"", f"close {r}", owner="dash")
            time.sleep(1.5)
            print(json.dumps(out[-2]), json.dumps(out[-1]), flush=True)
    finally:
        try:
            xfer(h, 16, bytes([0xFF, 0]))
        except Exception as e:   # noqa: BLE001
            print("clearing the stand-in:", e)
        h.close()
        with open(a.out, "w") as f:
            json.dump({"runs": out, "fails": B.fails}, f, indent=1)
    worst = max((o["pass_max_us"] for o in out), default=0)
    print(f"the longest pass across the returns: {worst} us; fails: {B.fails}")
    return 1 if B.fails else 0


if __name__ == "__main__":
    sys.exit(main())
