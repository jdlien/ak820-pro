#!/usr/bin/env python3
"""Where does stage 1's extra 1.3 mA at dark come from? Holds of 40 s on
whatever runs, the INA228's rows from the drain's CSV: Solid at value 0 (the
runner's dark), the same with the key scan skipped (dev op 28 sub 4, re-armed
every 8 s; op 28's status first and a 2 s trial, since the first probe's skip
was refused), the RGB matrix off (VIA effect 0), Solid value 0 again as the
control. The ladder at Always on meanwhile; at the end the lighting back and
the power mode set to Power saver (JD's, as the 16:30 dump recorded; the
runs' earlier failure had left Always on persisted)."""
import json, os, statistics, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, ROOT + "/scripts"); sys.path.insert(0, ROOT + "/hostagent")
import rowisr_baseline as rb
hp, lp = rb.hp, rb.lp
CSV = rb.DEFAULT_CSV
HOLD, SETTLE = 40, 8
POWER_SAVER = 2

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

def op28_status(h):
    r = rb.devhook(h, 28, [2])
    if r is None: return None
    return {"hold_active": r[4], "ms_left": r[5] | r[6] << 8, "irqn": r[14], "line_enabled": r[15], "depth": r[16],
            "prime_timed_out": r[18], "skip_active": r[19], "skip_ms_left": r[20] | r[21] << 8}

skips = {"ok": 0, "refused": 0}
def skip_keep(h):
    if not hasattr(skip_keep, "t") or time.time() - skip_keep.t > 8.0:
        r = rb.devhook(h, 28, [4, 9000 & 0xFF, 9000 >> 8])
        skips["ok" if r is not None else "refused"] += 1
        skip_keep.t = time.time()

h = hp.open_device()
mode0 = None
try:
    before = lp.read_lighting(h)
    pw = rb.devhook(h, 14, [0]); mode0 = pw[4]
    rb.say(f"lighting before {before}; power mode before {mode0} (stage {pw[5]}, cap {pw[6]}, forced {pw[7]})")
    rb.devhook(h, 14, [1, 0])
    for _ in range(20):
        pw = rb.devhook(h, 14, [0])
        if pw[5] == 0 and pw[6] == 255: break
        time.sleep(0.25)
    rb.say(f"op 28 status: {op28_status(h)}")
    r = rb.devhook(h, 28, [4, 2000 & 0xFF, 2000 >> 8])
    rb.say(f"a 2 s skip: {'accepted' if r is not None else 'REFUSED'}; status {op28_status(h)}")
    time.sleep(2.5)
    rb.set_lighting(h, 0, 0, 0)
    r1 = hold(h, "solid, value 0")
    r2 = hold(h, "solid, value 0, key scan skipped", skip_keep)
    rb.say(f"  (skips armed {skips['ok']}, refused {skips['refused']})")
    time.sleep(10)
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, 0])
    rb.say(f"  effect 0 read back {lp.read_lighting(h)}")
    r3 = hold(h, "rgb matrix off (effect 0)")
    rb.set_lighting(h, 0, 0, 0)
    r4 = hold(h, "solid, value 0 (control)")
    rb.say(f"RESULT dark {r1[0]}  scan-skipped {r2[0]} (skips {skips})  rgb-off {r3[0]}  dark-again {r4[0]}")
finally:
    rb.say("restoring: the lighting, then Power saver")
    try:
        lp.write_lighting(h, before)
    finally:
        rb.devhook(h, 14, [1, POWER_SAVER])
        time.sleep(0.5)
        pw = rb.devhook(h, 14, [0])
        rb.say(f"power mode now {pw[4]} (stage {pw[5]}, cap {pw[6]}, forced {pw[7]}); lighting {lp.read_lighting(h)}")
        h.close()
    out = subprocess.run([ROOT + "/venv/bin/python", ROOT + "/hostagent/ak820profiles.py", "dump",
                          ROOT + "/history/rowisr-stage1-20261101/settings-after-probe.json"], capture_output=True, text=True)
    print("\n".join(l for l in out.stdout.splitlines() if l.startswith("live:")))
