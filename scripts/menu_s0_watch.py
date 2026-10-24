#!/usr/bin/env python3
"""The configuration menu's S0, A10's companion (plans/CONFIG-MENU-S0-BOARD-
TESTS.md): arms the physical opener (op 27 sub 6), then logs every change to
the owner, the session, the screen, the cursor, the capture bits, the latch,
the dropped count and `invariant_fail` while a person works the knob. Stops
when the file named by --stop appears, and disarms unless --stay-armed.

    venv-win/Scripts/python.exe -u scripts/menu_s0_watch.py --stop F [--out J] < /dev/null

Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402

FIELDS = ("owner", "session", "screen", "cursor", "capture", "latch", "dropped", "armed", "invariant_fail")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", required=True)
    ap.add_argument("--out", default="menu_s0_watch.json")
    ap.add_argument("--stay-armed", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.stop):
        os.remove(a.stop)
    h = open_device()
    log = []
    try:
        st, seq = mutate(h, 6, bytes([1]))
        state, s = wait(h, seq)
        print(time.strftime("%H:%M:%S"), f"armed: {state}", flush=True)
        prev = None
        while not os.path.exists(a.stop):
            s = read_state(h)
            cur = {k: s[k] for k in FIELDS}
            if cur != prev:
                cur["t"] = time.strftime("%H:%M:%S")
                log.append(cur)
                print(cur["t"], " ".join(f"{k}={cur[k]}" for k in FIELDS), flush=True)
                prev = {k: s[k] for k in FIELDS}
            time.sleep(0.05)
        if not a.stay_armed:
            st, seq = mutate(h, 6, bytes([0]))
            wait(h, seq)
            print(time.strftime("%H:%M:%S"), "disarmed", flush=True)
    finally:
        h.close()
        with open(a.out, "w") as f:
            json.dump(log, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
