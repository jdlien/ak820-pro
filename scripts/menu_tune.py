#!/usr/bin/env python3
"""Hold the real menu open for JD and change its colours live (dev builds:
op 27 sub 13). The screen stays as it is unless JD turns the knob; the menu's
24 s idle close is held off by a step down and back only when the knob has
been idle 18 s.

    venv-win/Scripts/python.exe scripts/menu_tune.py CMDFILE < /dev/null

CMDFILE is read once a second; each new line is a command:
    leave FF9A9A     a colour by name, as RGB888 hex: lit, dim, leave, white, grey, track, cursor
    stop             close the menu and exit
The palette's names are menu.h's MP_* order. Never enumerates HID on Windows."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402

NAMES = ["lit", "dim", "leave", "white", "grey", "track", "cursor"]


def rgb565(hexstr):
    v = int(hexstr, 16)
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def mut(h, sub, args=b""):
    st, seq = mutate(h, sub, args)
    if st == 0:
        wait(h, seq, poll=0.1)
    return st


def main():
    cmdfile = sys.argv[1]
    done = 0
    h = open_device()
    try:
        last_cur, last_t = None, time.monotonic()
        while True:
            s = read_state(h)
            if s["session"] != "open":
                mut(h, 11)                   # the menu, its top level
                print("opened", flush=True)
                last_t = time.monotonic()
            if s["cursor"] != last_cur:      # JD turned: the board's idle clock restarted too
                last_cur, last_t = s["cursor"], time.monotonic()
            elif time.monotonic() - last_t > 18:
                mut(h, 1, bytes([1]))        # a step down and straight back keeps it open
                mut(h, 1, bytes([0xFF]))
                last_t = time.monotonic()
            lines = open(cmdfile).read().splitlines() if os.path.exists(cmdfile) else []
            for line in lines[done:]:
                done += 1
                w = line.split()
                if not w:
                    continue
                if w[0] == "stop":
                    mut(h, 11)
                    return 0
                if w[0] in NAMES and len(w) == 2:
                    c = rgb565(w[1])
                    r = xfer(h, 13, bytes([NAMES.index(w[0]), c & 255, c >> 8]))
                    print(f"{w[0]} = #{w[1]} (RGB565 {c:#06x}): status {r[5]}", flush=True)
            time.sleep(1.0)
    finally:
        h.close()


if __name__ == "__main__":
    sys.exit(main())
