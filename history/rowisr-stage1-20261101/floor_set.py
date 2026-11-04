#!/Users/jdlien/code/ak820-pro/venv/bin/python
"""Stage 6's floor by hand: every LED on one colour at N ticks on the devprobe
build (dev op 28 sub 3, index 254; a byte is its pulse width in ticks), the
level on the LCD's text line, left on until the next call. JD drives it from
the session's prompt: `! venv/bin/python history/rowisr-stage1-20261101/floor_set.py red 3`.
Usage: floor_set.py red|green|blue N | dark | off      (off: the effect back, the label cleared)"""
import sys, time
ROOT = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, ROOT + "/scripts"); sys.path.insert(0, ROOT + "/hostagent"); sys.path.insert(0, ROOT + "/history/rowisr-stage1-20261101")
from ak820health import open_device   # noqa: E402
from floor_eye import pattern, label, clear_label, ALL, OFF   # noqa: E402

def main():
    a = sys.argv[1:]
    ok = a in (["dark"], ["off"]) or (len(a) == 2 and a[0] in ("red", "green", "blue") and a[1].isdigit() and int(a[1]) <= 255)
    if not ok: sys.exit(__doc__)
    h = open_device()
    try:
        if a == ["off"]:
            pattern(h, OFF, 0, 0, 0); clear_label(h); msg = "pattern off: the effect back"
        elif a == ["dark"]:
            pattern(h, ALL, 0, 0, 0); label(h, "dark"); msg = "every LED dark"
        else:
            n = int(a[1]); rgb = [0, 0, 0]; rgb[("red", "green", "blue").index(a[0])] = n
            pattern(h, ALL, *rgb); label(h, f"{a[0][0].upper()} N={n}"); msg = f"every LED {a[0]} at {n} ticks"
    finally:
        h.close()
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(ROOT + "/history/rowisr-stage1-20261101/floor-eye.log", "a") as f: f.write(line + "\n")

if __name__ == "__main__":
    main()
