#!/usr/bin/env python3
"""Where does stage 1's extra 1.3 mA at dark come from? Four 40 s holds on
whatever runs, the INA228's rows from the drain's CSV: Solid at value 0 (the
runner's dark), the same with the key scan skipped (dev op 28 sub 4, re-armed
every 8.5 s), the RGB matrix off (VIA effect 0), and Solid value 0 again as
the control. The ladder held at Always on; everything put back after."""
import os, statistics, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, ROOT + "/scripts"); sys.path.insert(0, ROOT + "/hostagent")
import rowisr_baseline as rb
hp, lp = rb.hp, rb.lp
CSV = rb.DEFAULT_CSV
HOLD, SETTLE = 40, 8

def mean_ma(t_from, t_to):
    rows = rb.power_rows(CSV, t_from, t_to)
    cur = [r[1] for r in rows]
    return (round(statistics.mean(cur), 3), len(cur), round(statistics.pstdev(cur), 3)) if cur else (None, 0, None)

def hold(h, name, keep=None):
    t0 = time.time()
    end = t0 + SETTLE + HOLD
    while time.time() < end:
        if keep: keep(h)
        time.sleep(0.5)
    m = mean_ma(t0 + SETTLE, end)
    rb.say(f"  {name:34s} {m[0]} mA over {m[1]} rows (sd {m[2]})")
    return m

def skip_keep(h):
    if not hasattr(skip_keep, "t") or time.time() - skip_keep.t > 8.5:
        r = rb.devhook(h, 28, [4, 9000 & 0xFF, 9000 >> 8])
        if r is None:
            raise SystemExit("the scan skip was refused")
        skip_keep.t = time.time()

h = hp.open_device()
try:
    before = lp.read_lighting(h)
    pw = rb.devhook(h, 14, [0]); mode0 = pw[4]
    rb.devhook(h, 14, [1, 0])
    for _ in range(20):
        pw = rb.devhook(h, 14, [0])
        if pw[5] == 0 and pw[6] == 255: break
        time.sleep(0.25)
    rb.say(f"token {rb.token_from_cli() if False else '(see session log)'}; lighting before {before}; mode {mode0} -> Always on (stage {pw[5]}, cap {pw[6]})")
    rb.set_lighting(h, 0, 0, 0)
    r1 = hold(h, "solid, value 0")
    r2 = hold(h, "solid, value 0, key scan skipped", skip_keep)
    time.sleep(10)   # the last skip runs out
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, 0])
    rb.say(f"  effect set to 0 (off); read back {lp.read_lighting(h)}")
    r3 = hold(h, "rgb matrix off (effect 0)")
    rb.set_lighting(h, 0, 0, 0)
    r4 = hold(h, "solid, value 0 (control)")
    rb.say(f"RESULT dark {r1[0]}  scan-skipped {r2[0]}  rgb-off {r3[0]}  dark-again {r4[0]}")
finally:
    rb.say("restoring")
    try:
        rb.devhook(h, 14, [1, mode0])
    finally:
        lp.write_lighting(h, before)
        h.close()
