#!/usr/bin/env python3
"""Does the same pulse width give the same light on USB power and on battery?
On USB in the BT position the board's rail runs through a diode (4.12-4.47 V,
docs/battery.md) and on battery it is the buck-boost's 3.90 V, and nobody has
filmed the difference. Hands-free: Solid in JD's purple at a fixed value, relay 2
alternated, a clip per state from the bench phone, the bare LEDs' R, G, B means
over the clip's frames (a frame is 4.2 ms and a field 2.25, so one frame beats).
Then a ramp around two values on USB, so a difference can be read as slider
percent. The stage held ACTIVE and the values at or under Power saver's 128, so
the only thing that moves is the supply. Relay 2 goes back ON, JD's lighting and
the stage back, the data line off and the daemon on, whatever happens.

    usb_light.py LABEL
"""
import json, os, statistics, subprocess, sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
os.chdir(ROOT); sys.path.insert(0, "scripts"); sys.path.insert(0, "hostagent")
from ak820health import open_device
import rowisr_baseline as rb
lp = rb.lp
LABEL = sys.argv[1] if len(sys.argv) > 1 else "usb-light"
H = "history/rowisr-stage1-20261101/usbcam"; os.makedirs(H, exist_ok=True)
LOG = open(f"{H}/{LABEL}.log", "a")
PTS = [(408, 180), (408, 804), (432, 900), (960, 1692)]
AK = '"$HOME/Library/Application Support/ak820pro/bin/ak820"'
def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"; print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
def sh(c, **k): return subprocess.run(c, shell=True, capture_output=True, text=True, **k)
def present(): return sh("ioreg -p IOUSB -l -w0 | grep -q '\"idProduct\" = 32777'").returncode == 0
def relay(on):
    r = sh(f"venv/bin/python scripts/usb_relay.py {'on' if on else 'off'} power")
    if r.returncode: raise SystemExit(f"the relay did not switch: {r.stdout}{r.stderr}")
def clip():
    for attempt in range(3):
        before = set(f for f in os.listdir(H) if f.endswith(".mp4"))
        r = sh(f"venv/bin/python scripts/phonecam.py record 2 --out {H}")
        new = [f for f in os.listdir(H) if f.endswith(".mp4") and f not in before]
        if new: return f"{H}/{new[0]}"
        log(f"no clip (attempt {attempt + 1}): {(r.stdout + r.stderr).strip().splitlines()[-1:]}"); time.sleep(3)
    raise SystemExit("the phone made no clip")
def read(path):
    """The bare LEDs' R, G, B over the clip's frames past the first 60, and the whole frame's mean."""
    leds = []
    for x, y in PTS:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", f"select=gte(n\\,60),crop=16:16:{x-8}:{y-8}",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        n = len(raw) // 3
        leds.append([round(sum(raw[i::3]) / max(n, 1), 2) for i in range(3)])
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", "select=gte(n\\,60),scale=108:192",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    whole = round(sum(raw) / max(len(raw), 1), 3)
    if not raw or whole == 0: raise SystemExit(f"no frames read from {path}: the clip is kept")   # ffmpeg 9 removed -vsync, and an empty read looked like darkness
    os.remove(path)
    return {"leds": leds, "whole": whole}
def set_val(val):
    h = open_device()
    try: rb.set_lighting(h, 178, 219, val)
    finally: h.close()
    time.sleep(0.8)
def hook(args):
    h = open_device()
    try: rb.devhook(h, 14, args)
    finally: h.close()
def health():
    r = sh(f"{AK} health --json")
    try: return json.loads(r.stdout)
    except Exception: return {}
out = {"label": LABEL, "started": time.strftime("%H:%M:%S"), "pairs": [], "ramp": {}}
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
restored = False
try:
    if not present(): raise SystemExit("no board")
    r = sh(f"venv/bin/python hostagent/ak820lighting.py dump {SNAP}")
    if r.returncode or not os.path.exists(SNAP): raise SystemExit(f"no lighting snapshot, nothing changed: {r.stdout}{r.stderr}")
    log("JD's lighting: " + sh("venv/bin/python hostagent/ak820lighting.py show").stdout.splitlines()[0])
    v0 = health().get("vitals", {}); out["token"] = v0.get("build_token"); out["vitals_before"] = v0
    log(f"token {out['token']}; vitals keys {sorted(v0)[:30]}")
    hook([2, 0]); log("the stage held ACTIVE")
    relay(True)
    for rep in range(2):
        for v in (26, 64, 128):
            pair = {"val": v, "rep": rep}
            for on in ((True, False) if rep == 0 else (False, True)):   # A B then B A
                relay(on); time.sleep(5)
                if not present(): raise SystemExit(f"the board left the data line with relay 2 {'on' if on else 'off'}")
                set_val(v)
                got = read(clip()); pair["usb" if on else "batt"] = got
                log(f"v={v} rep {rep} {'USB ' if on else 'batt'}: LEDs {got['leds']} whole {got['whole']}")
            out["pairs"].append(pair)
    relay(True); time.sleep(5)
    for v in (23, 28, 59, 61, 66, 69):
        set_val(v); out["ramp"][v] = read(clip()); log(f"ramp on USB v={v}: LEDs {out['ramp'][v]['leds']} whole {out['ramp'][v]['whole']}")
    v1 = health().get("vitals", {}); out["vitals_after"] = v1
finally:
    relay(True); log("relay 2 back ON: " + sh("venv/bin/python scripts/usb_relay.py status").stdout.strip())
    try: hook([2, 0xFF]); log("the stage released")
    except BaseException as e: log(f"the stage's release failed: {e}")
    sh(f"venv/bin/python hostagent/ak820lighting.py restore {SNAP}")
    log("JD's lighting restored: " + (sh("venv/bin/python hostagent/ak820lighting.py show").stdout.splitlines() or ["?"])[0])
    json.dump(out, open(f"{H}/{LABEL}.json", "w"), indent=1)
    sh("timeout 20 uhubctl -l 3-1.3.4 -p 2 -a off -e"); time.sleep(3)
    sh(f'launchctl bootstrap "gui/{os.getuid()}" ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist')
    log("the data line off, the daemon back")
