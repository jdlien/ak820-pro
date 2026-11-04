#!/usr/bin/env python3
"""Stage 6's floor by eye (plans/ROW-ISR-PLAN.md, "The floor is measured first,
per colour"): every LED on one colour at N ticks, on the devprobe build where
a byte is its pulse width in ticks (dev op 28 sub 3, index 254), stepping N up
the list with "R N=3" on the LCD's text line, each level held HOLD seconds;
dark (every LED at 0) before the first level and after the last, then the
pattern released to the effect. JD watches the keys in the dark and reports
the first N he sees at all and the first N from which each step up is a
visible step. The log has the time of each level, so the power logger's rows
(history/power-bench-2026-10-15/power.csv) pair with a long hold for the
current's slope.

Usage: floor_eye.py red|green|blue [--hold S] [--steps 1,2,3,...] [--gap S]
                    [--no-label] [--log FILE]
  --gap S    dark for S seconds between levels (an onset at each level,
             for "shows at all"); default 0, a staircase (for "each step")."""
import argparse, os, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, ROOT + "/scripts"); sys.path.insert(0, ROOT + "/hostagent")
from ak820health import open_device   # noqa: E402
from rowisr_diag import xfer          # noqa: E402

STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50]
SET_VALUE, TEXT_CHANNEL, TEXT_SET, TEXT_CLEAR = 0x07, 0x12, 0x01, 0x02
ALL, OFF = 0xFE, 0xFF

def label(h, text):
    body = text.encode("ascii", "replace")[:20]
    p = bytes([0, SET_VALUE, TEXT_CHANNEL, TEXT_SET, 0]) + body
    h.write(p + bytes(33 - len(p))); h.read(32, 300)

def clear_label(h):
    p = bytes([0, SET_VALUE, TEXT_CHANNEL, TEXT_CLEAR])
    h.write(p + bytes(33 - len(p))); h.read(32, 300)

def pattern(h, idx, r, g, b):
    rep = xfer(h, 3, bytes([idx, r, g, b]))
    assert rep[4] == idx and rep[5:8] == bytes([r, g, b]), rep[:8].hex()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("colour", choices=["red", "green", "blue"])
    ap.add_argument("--hold", type=float, default=4.0)
    ap.add_argument("--gap", type=float, default=0.0)
    ap.add_argument("--steps", default=",".join(map(str, STEPS)))
    ap.add_argument("--no-label", action="store_true")
    ap.add_argument("--log", default=None)
    a = ap.parse_args()
    steps = [int(s) for s in a.steps.split(",")]
    assert all(0 <= s <= 255 for s in steps)
    ch = {"red": 0, "green": 1, "blue": 2}[a.colour]
    tag = a.colour[0].upper()
    logf = open(a.log, "a") if a.log else None
    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        if logf: logf.write(line + "\n"); logf.flush()
    h = open_device()
    try:
        log(f"{a.colour}: every LED at N ticks, {len(steps)} levels {steps}, {a.hold} s each" + (f", {a.gap} s dark between" if a.gap else ", a staircase"))
        pattern(h, ALL, 0, 0, 0)
        if not a.no_label: label(h, f"{tag} dark")
        log("dark"); time.sleep(3)
        for n in steps:
            rgb = [0, 0, 0]; rgb[ch] = n
            if a.gap and n != steps[0]:
                pattern(h, ALL, 0, 0, 0)
                if not a.no_label: label(h, f"{tag} dark")
                time.sleep(a.gap)
            pattern(h, ALL, *rgb)
            if not a.no_label: label(h, f"{tag} N={n}")
            log(f"N={n}"); time.sleep(a.hold)
        pattern(h, ALL, 0, 0, 0)
        if not a.no_label: label(h, f"{tag} dark")
        log("dark"); time.sleep(2)
    finally:
        try:
            pattern(h, OFF, 0, 0, 0); clear_label(h)
        finally:
            h.close()
    log("pattern released to the effect, the label cleared")

if __name__ == "__main__":
    main()
