#!/usr/bin/env python3
"""Is the base's lower dark draw a slept-board effect? The base run followed a
deep sleep and a wake; the stage 1 run followed a fresh boot. This holds
Solid value 0 for 40 s on stage 1 after white has deep-slept and woken, the
ladder at Always on for the hold, then the lighting back and Power saver."""
import statistics, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, ROOT + "/scripts"); sys.path.insert(0, ROOT + "/hostagent")
import rowisr_baseline as rb
hp, lp = rb.hp, rb.lp
HOLD, SETTLE, POWER_SAVER = 40, 8, 2

def hold(h, name):
    t0 = time.time(); end = t0 + SETTLE + HOLD
    time.sleep(SETTLE + HOLD)
    rows = rb.power_rows(rb.DEFAULT_CSV, t0 + SETTLE, end)
    cur = [r[1] for r in rows]
    m = (round(statistics.mean(cur), 3), len(cur), round(statistics.pstdev(cur), 3)) if cur else (None, 0, None)
    rb.say(f"  {name:34s} {m[0]} mA over {m[1]} rows (sd {m[2]})")
    return m

h = hp.open_device()
try:
    before = lp.read_lighting(h)
    pw = rb.devhook(h, 14, [0])
    rb.say(f"lighting before {before}; power mode before {pw[4]} (stage {pw[5]}, cap {pw[6]})")
    rb.devhook(h, 14, [1, 0])
    for _ in range(20):
        pw = rb.devhook(h, 14, [0])
        if pw[5] == 0 and pw[6] == 255: break
        time.sleep(0.25)
    rb.set_lighting(h, 0, 0, 0)
    r1 = hold(h, "solid, value 0, after a sleep")
    rb.set_lighting(h, 0, 0, 64)
    r2 = hold(h, "solid white 64, after a sleep")
    rb.say(f"RESULT dark-after-sleep {r1[0]}  white64-after-sleep {r2[0]}  (fresh-boot stage 1: dark 41.94, white 64 45.18; base after a sleep: dark 40.62, white 64 45.18)")
finally:
    rb.say("restoring: the lighting, then Power saver")
    try:
        lp.write_lighting(h, before)
    finally:
        rb.devhook(h, 14, [1, POWER_SAVER]); time.sleep(0.5)
        pw = rb.devhook(h, 14, [0])
        rb.say(f"power mode now {pw[4]}; lighting {lp.read_lighting(h)}")
        h.close()
