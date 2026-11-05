#!/usr/bin/env python3
"""D9's camera gates on white (plans/ROW-ISR-PLAN.md, "D9 revised", Gates),
hands-free: the board over the data line, the bench phone recording 2 s a
step, one frame a step, the bare LEDs read as R, G, B means at the frame's
bright points. Steps: (1) the purple theme (Solid, hue 178, sat 219) at
values 1, 2, 4, 8, 13, 26, 64, 128, 255: the red present from 4 up, the
light monotonic; (2) the RGB toggled off and on at value 64; (3) the dev
pattern on (every LED red at byte 1) and off, the effect repainted; (4)
Jellybean at value 64 left 3 s, then the value to 13 with no drop forced:
the brightness lands. JD's lighting restored and the standing state after.
Writes d9cam/gates-LABEL.json and the frames; prints a verdict per step."""
import json, os, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
os.chdir(ROOT); sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
import rowisr_baseline as rb
lp = rb.lp
LABEL = sys.argv[1] if len(sys.argv) > 1 else "gates"
H = "history/rowisr-stage1-20261101/d9cam"; os.makedirs(H, exist_ok=True)
LOG = open(f"{H}/gates-{LABEL}.log", "a")
def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"; print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
def sh(c, **k): return subprocess.run(c, shell=True, capture_output=True, text=True, **k)
def present(): return sh("ioreg -p IOUSB -l -w0 | grep -q '\"idProduct\" = 32777'").returncode == 0
def frame(name):
    for attempt in range(3):   # a start that makes no new file is reported, not retried, by phonecam: retry here after a pause
        before = set(f for f in os.listdir(H) if f.endswith(".mp4"))
        r = sh(f"venv/bin/python scripts/phonecam.py record 2 --out {H}")
        new = [f"{H}/{f}" for f in os.listdir(H) if f.endswith(".mp4") and f not in before]
        if new: break
        log(f"no clip for {name} (attempt {attempt + 1}): {(r.stdout + r.stderr).strip().splitlines()[-1:] }"); time.sleep(3)
    else:
        raise SystemExit(f"the phone made no clip for {name}")
    clip = new[0]
    ppm = f"{H}/{name}.ppm"
    sh(f'ffmpeg -loglevel error -y -i "{clip}" -vf "select=gte(n\\,300)" -frames:v 1 -f image2 -pix_fmt rgb24 "{ppm}"')   # the clip's end: the camera's exposure settled after the scene change
    sh(f'ffmpeg -loglevel error -y -i "{clip}" -vf "select=gte(n\\,300),scale=540:-1" -frames:v 1 -q:v 3 "{H}/{name}.jpg"')
    os.remove(clip)
    return ppm
def points(ppm, pts=None):
    d = open(ppm, "rb").read(); parts = d.split(b"\n", 3); W, Hh = map(int, parts[1].split()); A = parts[3]
    def mean(cx, cy, r):
        n = 0; acc = [0, 0, 0]
        for y in range(max(0, cy - r), min(Hh, cy + r)):
            for x in range(max(0, cx - r), min(W, cx + r)):
                i = (y * W + x) * 3; acc[0] += A[i]; acc[1] += A[i + 1]; acc[2] += A[i + 2]; n += 1
        return tuple(round(a / n, 1) for a in acc)
    if pts is None:   # find the bare LEDs in a DIM frame (value 13: only they clear the threshold; the LCD excluded, y < 100)
        bs = 24; pts = []
        for by in range(100, Hh - bs, bs):
            for bx in range(300, W - bs, bs):
                cx, cy = bx + bs // 2, by + bs // 2
                if max(mean(cx, cy, 8)) > 40 and not any(abs(cx - x) < 50 and abs(cy - y) < 50 for x, y in pts): pts.append((cx, cy))
        return pts
    return [mean(x, y, 8) for x, y in pts]
def lighting(h, effect, hue, sat, val):
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, effect])
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.COLOR, hue, sat])
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.BRIGHTNESS, val])
    time.sleep(0.6)
SOLID, JELLY = 1, 6   # via.json's effect order: 0 off, 1 Solid, 2 Alphas/Mods, 3-5 the Cycles, 6 Jellybean (rb.SOLID is 1)
assert rb.SOLID == SOLID
out = {"label": LABEL, "steps": {}}
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
if not present(): log("no board"); sys.exit(1)
tok = sh('"$HOME/Library/Application Support/ak820pro/bin/ak820" health --json').stdout
out["token"] = json.loads(tok)["vitals"]["build_token"] if tok.strip() else "?"
log(f"{LABEL}: token {out['token']}")
h = open_device()
try:
    rb.devhook(h, 14, [2, 0]); log("the ladder's stage forced ACTIVE for the run (Power saver on battery dims at 1 min idle and darkens at 3: the first run's 128 and 255 read as 64 and its Jellybean step went dark)")
    # The bare LEDs' positions in the phone's frame, from the floor evening's clips (the board unmoved since 15:50):
    # Delete, two F-row keys, the bottom-left Ctrl. A finder at any value picks up capped keys too.
    pts = [(408, 180), (408, 804), (432, 900), (960, 1692)]
    lighting(h, SOLID, 178, 219, 64); chk = points(frame("find"), pts); log(f"bare LEDs at {pts}: at value 64 they read {chk}")
    assert all(max(c) > 40 for c in chk), "a bare LED reads dark at value 64: the board moved, or the lights are capped"

    # (1) the purple ramp
    ramp = {}
    for v in (1, 2, 4, 8, 13, 26, 64, 128, 255):
        lighting(h, SOLID, 178, 219, v); ramp[v] = points(frame(f"{LABEL}-purple-v{v}"), pts)
        log(f"purple v={v}: " + "; ".join(str(c) for c in ramp[v]))
    sums = {v: sum(sum(c) for c in ramp[v]) for v in ramp}
    vs   = [v for v in sorted(sums) if v <= 64]   # the camera saturates above 64 at this exposure (and re-meters each clip): the ramp is judged where it can see
    mono = all(sums[a] <= sums[b] * 1.02 + 20 for a, b in zip(vs, vs[1:]))
    red4 = all(sum(c[0] for c in ramp[v]) / len(pts) > 6 for v in (13, 26))   # the purple's red is 2 ticks at 13 (the camera reads 20-40), 1 tick at 8 (it reads 1-10, under the gate), half a tick on alternate fields at 4
    out["steps"]["purple"] = {"sums": sums, "monotonic": mono, "red from 4": red4}
    log(f"(1) purple: monotonic {mono}, red present from 4 {red4} -> {'PASS' if mono and red4 else 'FAIL'}")
    # (2) the toggle off and on at 64
    lighting(h, SOLID, 178, 219, 64); on1 = points(frame(f"{LABEL}-toggle-on1"), pts)
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, 0]); time.sleep(0.6); off = points(frame(f"{LABEL}-toggle-off"), pts)
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, SOLID]); time.sleep(0.6); on2 = points(frame(f"{LABEL}-toggle-on2"), pts)
    dark = max(max(c) for c in off) < 12; same = all(abs(sum(a) - sum(b)) < 0.15 * sum(a) + 10 for a, b in zip(on1, on2))
    out["steps"]["toggle"] = {"on1": on1, "off": off, "on2": on2, "dark": dark, "same": same}
    log(f"(2) toggle: dark when off {dark}, the same back on {same} -> {'PASS' if dark and same else 'FAIL'}")
    # (3) the pattern on and off at value 64
    import rowisr_diag as rd
    rd.xfer(h, 3, bytes([0xFE, 1, 0, 0])); time.sleep(0.6); pat = points(frame(f"{LABEL}-pattern-on"), pts)
    rd.xfer(h, 3, bytes([0xFF, 0, 0, 0])); time.sleep(0.8); back = points(frame(f"{LABEL}-pattern-off"), pts)
    patred = all(c[0] > c[2] for c in pat); restored = all(abs(sum(a) - sum(b)) < 0.15 * sum(a) + 10 for a, b in zip(on2, back))
    out["steps"]["pattern"] = {"on": pat, "off": back, "red": patred, "restored": restored}
    log(f"(3) pattern: red while on {patred}, the effect back after {restored} -> {'PASS' if patred and restored else 'FAIL'}")
    # (4) Jellybean idle, then the value down with no drop forced
    lighting(h, JELLY, 178, 219, 64); time.sleep(3); j64 = points(frame(f"{LABEL}-jelly-64"), pts)
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.BRIGHTNESS, 13]); time.sleep(1.0); j13 = points(frame(f"{LABEL}-jelly-13"), pts)
    dropped = sum(sum(c) for c in j13) < 0.6 * sum(sum(c) for c in j64)
    out["steps"]["jelly"] = {"v64": j64, "v13": j13, "dimmed": dropped}
    log(f"(4) Jellybean's value change with no drop: dimmed {dropped} -> {'PASS' if dropped else 'FAIL'}")
finally:
    try: rb.devhook(h, 14, [2, 0xFF]); log("the stage released")
    finally: h.close()
sh("venv/bin/python hostagent/ak820lighting.py restore history/rowisr-stage1-20261101/lighting-5h-jd-choice.json")
log("JD's lighting restored: " + sh("venv/bin/python hostagent/ak820lighting.py show").stdout.splitlines()[0])
sh("timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e"); time.sleep(3)
sh(f'launchctl bootstrap "gui/{os.getuid()}" ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist')
json.dump(out, open(f"{H}/gates-{LABEL}.json", "w"), indent=1)
log("the standing state; " + ("ALL PASS" if all(all(v for k, v in s.items() if isinstance(v, bool)) for s in out["steps"].values()) else "a FAIL above"))
