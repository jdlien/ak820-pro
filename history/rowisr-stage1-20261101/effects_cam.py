#!/usr/bin/env python3
"""The effects on the wide path, by camera on white, hands-free: Solid, Rainfall,
the Heatmap (the rig's Delete key pressed through the clip) and Drift at values
26, 64 and 128, one clip each. The clip's reading is its brightest spot on the
board, the LCD and the bench beside it cropped out: the maximum over frames of the
frame's maximum at 108 x 192. Two questions: does each
effect's light rise with the value, and does Rainfall or the Heatmap still blaze
over Solid at the same value (they were about 5x over at 50%)? Frames kept per
step for a look. JD's lighting back, the data line off, the daemon on.

    effects_cam.py LABEL
"""
import json, os, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
os.chdir(ROOT); sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
import rowisr_baseline as rb
lp = rb.lp
LABEL = sys.argv[1] if len(sys.argv) > 1 else "effects"
H = "history/rowisr-stage1-20261101/effectscam"; os.makedirs(H, exist_ok=True)
LOG = open(f"{H}/{LABEL}.log", "a")
def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"; print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
def sh(c, **k): return subprocess.run(c, shell=True, capture_output=True, text=True, **k)
def present(): return sh("ioreg -p IOUSB -l -w0 | grep -q '\"idProduct\" = 32777'").returncode == 0
def clip():
    for attempt in range(3):
        before = set(f for f in os.listdir(H) if f.endswith(".mp4"))
        r = sh(f"venv/bin/python scripts/phonecam.py record 2 --out {H}")
        new = [f for f in os.listdir(H) if f.endswith(".mp4") and f not in before]
        if new: return f"{H}/{new[0]}"
        log(f"no clip (attempt {attempt + 1}): {(r.stdout + r.stderr).strip().splitlines()[-1:]}"); time.sleep(3)
    raise SystemExit("the phone made no clip")
def read(path, name):
    W, Hh = 108, 192
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", f"select=gte(n\\,60),crop=iw*0.7:ih*0.93:iw*0.28:ih*0.07,scale={W}:{Hh}",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    if not raw: raise SystemExit(f"no frames read from {path}: the clip is kept")
    fs = W * Hh; n = len(raw) // fs
    peaks = [max(raw[i * fs:(i + 1) * fs]) for i in range(n)]
    sh(f'ffmpeg -loglevel error -y -i "{path}" -vf "select=gte(n\\,120),scale=540:-1" -frames:v 1 -q:v 3 "{H}/{name}.jpg"')
    os.remove(path)
    return {"peak": max(peaks), "mean_peak": round(sum(peaks) / n, 2), "mean": round(sum(raw) / len(raw), 3), "frames": n}
def lighting(effect, val):
    h = open_device()
    try:
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, effect])
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.COLOR, 178, 219])
        lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.BRIGHTNESS, val])
        got = lp.read_lighting(h)
    finally: h.close()
    if got["animation_index"] != effect or got["val"] != val: raise SystemExit(f"the lighting did not take: {got}")
    time.sleep(1.0)
def hook(args):
    h = open_device()
    try: rb.devhook(h, 14, args)
    finally: h.close()
def press_during(fn):
    """The Delete key pressed through the clip: the rig's REPL takes seconds to start, and heat decays in 6 s."""
    p = subprocess.Popen("venv/bin/python scripts/presser_repl.py batch A1 150 40 40", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(10)
    try: return fn()
    finally: p.wait()
EFFECTS = {"solid": 1, "heatmap": 7, "rainfall": 8, "drift": 9}
out = {"label": LABEL, "steps": {}}
SNAP = f"{H}/{LABEL}-lighting-before.json"
sh(f'launchctl bootout "gui/{os.getuid()}/com.jdlien.ak820pro.agent"'); time.sleep(3)
if not present():
    sh("timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on -e")
    for _ in range(8):
        if present(): break
        time.sleep(2)
if not present():
    log("asleep: one rig press"); sh("venv/bin/python scripts/presser_repl.py pulse A1 100")
    for _ in range(15):
        if present(): break
        time.sleep(1)
try:
    if not present(): raise SystemExit("no board")
    r = sh(f"venv/bin/python hostagent/ak820lighting.py dump {SNAP}")
    if r.returncode or not os.path.exists(SNAP): raise SystemExit(f"no lighting snapshot, nothing changed: {r.stdout}{r.stderr}")
    log("JD's lighting: " + sh("venv/bin/python hostagent/ak820lighting.py show").stdout.splitlines()[0])
    t = sh('"$HOME/Library/Application Support/ak820pro/bin/ak820" health --json').stdout
    out["token"] = json.loads(t)["vitals"]["build_token"] if t.strip() else "?"; log(f"token {out['token']}")
    hook([2, 0]); log("the stage held ACTIVE")
    for name, eff in EFFECTS.items():
        for v in (26, 64, 128):
            lighting(eff, v)
            if name == "rainfall": time.sleep(2)   # drops to fall
            path = press_during(clip) if name == "heatmap" else clip()
            got = read(path, f"{LABEL}-{name}-v{v}"); out["steps"][f"{name}-{v}"] = got
            log(f"{name} v={v}: {got}")
finally:
    try: hook([2, 0xFF]); log("the stage released")
    except BaseException as e: log(f"the stage's release failed: {e}")
    sh(f"venv/bin/python hostagent/ak820lighting.py restore {SNAP}")
    log("JD's lighting restored: " + (sh("venv/bin/python hostagent/ak820lighting.py show").stdout.splitlines() or ["?"])[0])
    json.dump(out, open(f"{H}/{LABEL}.json", "w"), indent=1)
    sh("timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e"); time.sleep(3)
    sh(f'launchctl bootstrap "gui/{os.getuid()}" ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist')
    log("the data line off, the daemon back")
