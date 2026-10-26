#!/usr/bin/env python3
"""The knob decoder's state at rest, from op 27 sub 14 byte 17 (dev builds,
P3): A in bit 0, B in bit 1. ENCODER_REST_PINS_EQUAL assumes the knob rests
where its pins agree, 00 or 11 (config.h). Read it with nobody touching the
knob, ideally at two neighbouring detents:

    venv-win/Scripts/python.exe scripts/knob_rest.py [--reads N] < /dev/null

0 or 3 at every read supports the rule; 1 or 2 means the knob rests between
the pins' changes, and the build must go back without the rule. Never
enumerates HID on Windows."""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import open_device, xfer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reads", type=int, default=5)
    a = ap.parse_args()
    h = open_device()
    try:
        states = []
        for _ in range(a.reads):
            r = xfer(h, 14)
            states.append(r[17] & 3)
            time.sleep(0.2)
    finally:
        h.close()
    names = {0: "00", 1: "01 (A high)", 2: "10 (B high)", 3: "11"}
    print("knob state:", ", ".join(names[s] for s in states))
    if len(set(states)) > 1:
        print("MOVING: the reads differ; read again with the knob untouched")
        return 2
    ok = states[0] in (0, 3)
    print("the pins agree at rest: the rule holds" if ok else "the pins DISAGREE at rest: remove ENCODER_REST_PINS_EQUAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
