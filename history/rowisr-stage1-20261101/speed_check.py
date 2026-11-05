#!/usr/bin/env python3
"""Does a Cycle keep its place when the speed changes? On white, by camera: Cycle
All at a low value, the speed stepped, one clip a step, the bare LEDs' mean colour
read as a hue angle. Time x speed would move the colour by a large part of the wheel
at each step. A running clock moves it only by what the time between clips earns,
which is what the log prints beside each reading. JD's lighting back after; the
caller owns the data line and the daemon.

    speed_check.py LABEL
"""
import json, math, os, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
os.chdir(ROOT); sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
import rowisr_baseline as rb
lp = rb.lp
LABEL = sys.argv[1] if len(sys.argv) > 1 else "speed"
H = "history/rowisr-stage1-20261101/speedcam"; os.makedirs(H, exist_ok=True)
LOG = open(f"{H}/{LABEL}.log", "a")
PTS = [(408, 180), (408, 804), (432, 900), (960, 1692)]
VAL = 40
def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"; print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)
def clip():
    for attempt in range(3):
        before = set(f for f in os.listdir(H) if f.endswith(".mp4"))
        sh(f"venv/bin/python scripts/phonecam.py record 2 --out {H}")
        new = [f for f in os.listdir(H) if f.endswith(".mp4") and f not in before]
        if new: return f"{H}/{new[0]}"
        time.sleep(3)
    raise SystemExit("the phone made no clip")
def read(path):
    leds = []
    for x, y in PTS:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", f"select=gte(n\\,60),crop=16:16:{x-8}:{y-8}",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if not raw: raise SystemExit(f"no frames read from {path}: the clip is kept")
        n = len(raw) // 3
        leds.append([sum(raw[i::3]) / n for i in range(3)])
    os.remove(path)
    return leds
def hue(rgb):
    r, g, b = rgb
    return math.degrees(math.atan2(math.sqrt(3) * (g - b), 2 * r - g - b)) % 360
def dev(fn):
    h = open_device()
    try: return fn(h)
    finally: h.close()
SNAP = f"{H}/{LABEL}-lighting-before.json"
r = sh(f"venv/bin/python hostagent/ak820lighting.py dump {SNAP}")
if r.returncode or not os.path.exists(SNAP): raise SystemExit(f"no lighting snapshot, nothing changed: {r.stdout}{r.stderr}")
out = []
try:
    dev(lambda h: rb.devhook(h, 14, [2, 0]))
    def setup(h):
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, 3])
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.COLOR, 0, 255])
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.BRIGHTNESS, VAL])
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.SPEED, 0])
    dev(setup); time.sleep(1.0)
    last_t = None
    for sp in (0, 0, 40, 80, 120, 0):
        dev(lambda h: lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.SPEED, sp]))
        t = time.time()
        leds = read(clip())
        hs = [round(hue(c), 1) for c in leds]
        cycle = 600.0 / 60 ** (sp / 255)
        log(f"speed {sp:3d} (a cycle in {cycle:5.0f} s, {360 / cycle:4.1f} deg/s): hue by LED {hs}"
            + (f"; {t - last_t:.0f} s since the last" if last_t else ""))
        out.append({"speed": sp, "t": t, "hues": hs, "leds": leds})
        last_t = t
finally:
    try: dev(lambda h: rb.devhook(h, 14, [2, 0xFF]))
    except BaseException as e: log(f"the stage's release failed: {e}")
    sh(f"venv/bin/python hostagent/ak820lighting.py restore {SNAP}")
    log("JD's lighting restored: " + (sh("venv/bin/python hostagent/ak820lighting.py show").stdout.splitlines() or ["?"])[0])
    json.dump(out, open(f"{H}/{LABEL}.json", "w"), indent=1)
