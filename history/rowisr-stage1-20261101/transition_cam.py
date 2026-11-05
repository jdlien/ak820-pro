#!/usr/bin/env python3
"""Do the wide path's changes show on the LEDs? D9's flush converts unmasked, so a
frame can mix old and new LEDs (plans/ROW-ISR-PLAN.md, "D9 revised"), which is fine
if a change only passes between its two levels. The failure to look for is a blaze
or a dark frame: chroma driven as raw bytes, or a frame with nothing committed. On
white, on USB: a clip per transition (brightness, hue, effect, RGB off and on), the
change made four times inside the clip, each capless LED's R+G+B read per frame, and
the frames outside its two levels counted. A frame is 4.2 ms, a field 2.25 ms.

    transition_cam.py LABEL      (the caller owns the data line, the daemon and the lighting)
"""
import json, os, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
os.chdir(ROOT); sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
import rowisr_baseline as rb
lp = rb.lp
LABEL = sys.argv[1] if len(sys.argv) > 1 else "transition"
H = "history/rowisr-stage1-20261101/transitioncam"; os.makedirs(H, exist_ok=True)
LOG = open(f"{H}/{LABEL}.log", "a")
PTS = {"Delete": (408, 180), "F-row a": (408, 804), "F-row b": (432, 900), "Ctrl": (960, 1692)}
def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"; print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
def setv(h, ch, *vals): lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, ch, *vals])
def series(path):
    out = {}
    for name, (x, y) in PTS.items():
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", f"crop=16:16:{x-8}:{y-8}",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if not raw: raise SystemExit(f"no frames read from {path}: the clip is kept")
        fs = 16 * 16 * 3
        out[name] = [sum(raw[i * fs:(i + 1) * fs]) / (16 * 16) for i in range(len(raw) // fs)]
    return out
def judge(vals, check_dark):
    v = sorted(vals[40:]); n = len(v)
    low, high = v[n // 8], v[n - n // 8 - 1]
    over = [i for i, x in enumerate(vals) if i >= 40 and x > high * 1.35 + 8]
    under = [i for i, x in enumerate(vals) if i >= 40 and x < low * 0.6 - 3] if check_dark else []
    return {"low": round(low, 1), "high": round(high, 1), "peak": round(v[-1], 1), "floor": round(v[0], 1), "over": len(over), "under": len(under), "over_at": over[:6], "under_at": under[:6]}
def clip(name, setup, a, b, check_dark=True):
    h = open_device()
    try: setup(h)
    finally: h.close()
    time.sleep(1.5)
    before = set(f for f in os.listdir(H) if f.endswith(".mp4"))
    p = subprocess.Popen(["venv/bin/python", "scripts/phonecam.py", "record", "4", "--out", H], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.2)
    h = open_device()
    try:
        for i in range(4):
            a(h); time.sleep(0.35); b(h); time.sleep(0.35)
    finally: h.close()
    p.wait()
    new = [f for f in os.listdir(H) if f.endswith(".mp4") and f not in before]
    if not new: raise SystemExit(f"{name}: the phone made no clip")
    path = f"{H}/{new[0]}"
    s = series(path)
    rows = {k: judge(v, check_dark) for k, v in s.items()}
    frames = len(next(iter(s.values())))
    os.remove(path)
    log(f"{name}: {frames} frames")
    for k, r in rows.items():
        log(f"  {k:8s} levels {r['low']:6.1f} to {r['high']:6.1f}, extremes {r['floor']:6.1f} to {r['peak']:6.1f}: {r['over']} over, {r['under']} under {r['over_at']}{r['under_at']}")
    return {"name": name, "frames": frames, "leds": rows}
HUE, SAT = 178, 219
def solid(v, hue=HUE):
    def f(h):
        setv(h, lp.EFFECT, 1); setv(h, lp.COLOR, hue, SAT); setv(h, lp.BRIGHTNESS, v); setv(h, lp.SPEED, 0)
    return f
out = [
    clip("brightness, 25% and 50%", solid(64), lambda h: setv(h, lp.BRIGHTNESS, 128), lambda h: setv(h, lp.BRIGHTNESS, 64)),
    clip("brightness, 10% and 75%", solid(26), lambda h: setv(h, lp.BRIGHTNESS, 191), lambda h: setv(h, lp.BRIGHTNESS, 26)),
    clip("hue, purple and red at 25%", solid(64), lambda h: setv(h, lp.COLOR, 0, SAT), lambda h: setv(h, lp.COLOR, HUE, SAT)),
    clip("effect, Solid and Cycle All at 25%", solid(64), lambda h: setv(h, lp.EFFECT, 3), lambda h: setv(h, lp.EFFECT, 1)),
    clip("RGB off and on at 25%", solid(64), lambda h: setv(h, lp.EFFECT, 0), lambda h: setv(h, lp.EFFECT, 1), check_dark=False),
]
json.dump(out, open(f"{H}/{LABEL}.json", "w"), indent=1)
bad = sum(r["over"] + r["under"] for c in out for r in c["leds"].values())
log(f"frames outside the levels, all clips: {bad}")
sys.exit(1 if bad else 0)
