#!/usr/bin/env python3
"""The first transition run found single-frame dips and had no control, so: the same
clips beside steady ones, with each LED's series kept. A dip is judged against the
steady clip's rate and by its distance from the nearest step in the series. The last
clip's reading also tests whether a dark LED reads dark at this exposure.

    transition_cam2.py LABEL     (the caller owns the data line, the daemon and the lighting)
"""
import json, os, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
os.chdir(ROOT); sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
import rowisr_baseline as rb
lp = rb.lp
LABEL = sys.argv[1] if len(sys.argv) > 1 else "transition2"
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
        out[name] = [round(sum(raw[i * fs:(i + 1) * fs]) / (16 * 16), 1) for i in range(len(raw) // fs)]
    return out
def judge(v):
    """Levels by the outer eighths; the steps where the series crosses their middle; a dip
    a frame under 0.6 of the lower level; its distance in frames from the nearest step."""
    w = v[40:]; s = sorted(w); n = len(s)
    low, high = s[n // 8], s[n - n // 8 - 1]
    mid = (low + high) / 2
    two = high > low * 1.5 + 8
    edges = [i for i in range(1, len(w)) if (w[i - 1] < mid) != (w[i] < mid)] if two else []
    dips = [i for i, x in enumerate(w) if x < low * 0.6 - 3]
    over = [i for i, x in enumerate(w) if x > high * 1.35 + 8]
    near = [min((abs(d - e) for e in edges), default=None) for d in dips]
    # frame to frame noise on the level, away from any step
    return {"low": low, "high": high, "floor": s[0], "peak": s[-1], "edges": len(edges), "dips": len(dips), "dips_at": dips[:10],
            "from_step": near[:10], "over": len(over), "over_at": over[:10]}
def clip(name, setup, a=None, b=None):
    h = open_device()
    try: setup(h)
    finally: h.close()
    time.sleep(1.5)
    before = set(f for f in os.listdir(H) if f.endswith(".mp4"))
    p = subprocess.Popen(["venv/bin/python", "scripts/phonecam.py", "record", "4", "--out", H], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.2)
    if a:
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
    tag = name.split(",")[0].replace(" ", "-") + "-" + str(len(os.listdir(H)))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", "select=eq(n\\,500),scale=540:-1", "-frames:v", "1", "-q:v", "3", f"{H}/{LABEL}-{tag}.jpg"])
    os.remove(path)
    rows = {k: judge(v) for k, v in s.items()}
    log(f"{name}: {len(next(iter(s.values())))} frames ({tag})")
    for k, r in rows.items():
        log(f"  {k:8s} levels {r['low']:6.1f} to {r['high']:6.1f}, extremes {r['floor']:6.1f} to {r['peak']:6.1f}, {r['edges']} steps: {r['dips']} dips {r['dips_at']} {r['from_step']}, {r['over']} over {r['over_at']}")
    return {"name": name, "leds": rows, "series": s}
HUE, SAT = 178, 219
def solid(v):
    def f(h):
        setv(h, lp.EFFECT, 1); setv(h, lp.COLOR, HUE, SAT); setv(h, lp.BRIGHTNESS, v); setv(h, lp.SPEED, 0)
    return f
bri = lambda v: (lambda h: setv(h, lp.BRIGHTNESS, v))
out = [
    clip("steady 25%, no change", solid(64)),
    clip("steps 25% and 50%", solid(64), bri(128), bri(64)),
    clip("steady 25%, again", solid(64)),
    clip("steady 50%, no change", solid(128)),
    clip("steps 10% and 75%", solid(26), bri(191), bri(26)),
    clip("steady 10%, no change", solid(26)),
    clip("RGB off and on at 50%", solid(128), lambda h: setv(h, lp.EFFECT, 0), lambda h: setv(h, lp.EFFECT, 1)),
    clip("steps 25% and 50%, again", solid(64), bri(128), bri(64)),
]
json.dump(out, open(f"{H}/{LABEL}.json", "w"))
