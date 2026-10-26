#!/usr/bin/env python3
"""S1: the mono text's cost per style, on F3 (op 27 sub 0 patterns 16-19:
lit/half, lit/full, inverted/half, inverted/full). Plan "Open" 2 (half or
full rows) is decided by these numbers, "Open" 1 (the cursor) by JD's eye.

    venv-win/Scripts/python.exe scripts/menu_s1_styles.py [--out F] [--moves N] < /dev/null

For each style, two intervals of sub 10 (its maxima re-armed at each start):
  style    switching into it from the previous style: the title and the
           eight rows repaint (no clear)
  moves    N selection changes (sub 1, alternately +1 and -1), each waited
           out to pixels_done: two rows each
and the wall time from each mutation to pixels_done. Opens the fixture
itself and closes it after. Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s0_accept import to_dash, until  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

STYLES = ["lit, half rows", "lit, full rows", "inverted, half rows", "inverted, full rows"]
MONO_FIRST = 16


def mut(h, sub, args=b""):
    st, seq = mutate(h, sub, args)
    if st != 0:
        raise RuntimeError(f"op 27 sub {sub} {list(args)} refused: {st}")
    state, _ = wait(h, seq)
    if state != "done":
        raise RuntimeError(f"op 27 sub {sub}: {state}")


def settle(h, what):
    t0 = time.perf_counter()
    ok, s = until(h, lambda s: s["pixels_done"], timeout=5.0)
    if not ok:
        raise RuntimeError(f"{what}: no pixels_done in 5 s")
    return (time.perf_counter() - t0) * 1000.0


def interval(h, fn):
    xfer(h, 10, bytes([1]))   # re-arm: the maxima from here
    walls = fn()
    m = decode_meas(xfer(h, 10, bytes([0])))
    if m["aliased"]:
        raise RuntimeError("a pass of 340 ms or more in the interval")
    return {"piece_us": m["piece_us"], "op_us": m["op_us"], "pass_max_us": m["pass_max_us"],
            "over15": m["over15"], "repaint_ms": m["repaint_ms"],
            "wall_ms_max": round(max(walls), 1), "wall_ms_mean": round(sum(walls) / len(walls), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_s1_styles.json")
    ap.add_argument("--moves", type=int, default=10)
    a = ap.parse_args()
    h = open_device()
    out = []
    try:
        to_dash(h)
        mut(h, 4)                                   # open: F1
        settle(h, "open")
        mut(h, 0, bytes([MONO_FIRST + 3, 0]))       # F3, so the first style is a retarget
        settle(h, "F3")
        for st in range(4):
            def style():
                mut(h, 0, bytes([MONO_FIRST + st, 0]))
                return [settle(h, STYLES[st])]

            def moves():
                walls = []
                for i in range(a.moves):
                    mut(h, 1, bytes([1 if i % 2 == 0 else 0xFF]))
                    walls.append(settle(h, "a move"))
                return walls

            s = read_state(h)
            if s["session"] != "open":
                raise RuntimeError("the fixture closed")
            r = {"style": STYLES[st], "pattern": MONO_FIRST + st,
                 "switch": interval(h, style), "moves": interval(h, moves)}
            out.append(r)
            print(json.dumps(r), flush=True)
        mut(h, 4)                                   # close
        to_dash(h)
    finally:
        h.close()
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
    print(f"{'style':22} {'what':7} {'piece':>7} {'op':>7} {'pass':>7} {'>15':>4} {'repaint':>8} {'wall max':>9}")
    for r in out:
        for k in ("switch", "moves"):
            m = r[k]
            print(f"{r['style']:22} {k:7} {m['piece_us']:6}u {m['op_us']:6}u {m['pass_max_us']:6}u "
                  f"{m['over15']:4} {m['repaint_ms']:6}ms {m['wall_ms_max']:8}ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
