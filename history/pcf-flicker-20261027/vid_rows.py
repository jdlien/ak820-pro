"""Per-frame brightness of each key row in JD's 240 fps clip of the keyboard on
gremlin (19:15:16-19:15:19 by its clock): ffmpeg decodes to 960x540 RGB, and
each row band's mean R, G, B is taken per frame. Frames whose overall level
or any row's level departs from its rolling median are listed. Writes the
per-frame table as CSV beside the clip's frames."""
import csv
import subprocess
import sys

import numpy as np

SRC = sys.argv[1]
OUT = sys.argv[2]
FF = "ffmpeg"
W, H = 960, 540
# Key row bands at 960x540 (from the first frame), x 0-760 (the LCD is right of it).
ROWS = {"F": (80, 135), "num": (150, 200), "qwer": (205, 252), "asdf": (262, 310),
        "zxcv": (318, 370), "bottom": (375, 432)}
X0, X1 = 0, 760

p = subprocess.Popen([FF, "-v", "error", "-i", SRC, "-vf", f"scale={W}:{H}", "-f", "rawvideo",
                      "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
recs = []
n = 0
while True:
    buf = p.stdout.read(W * H * 3)
    if len(buf) < W * H * 3:
        break
    f = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32)
    r = {"frame": n}
    tot = []
    for k, (y0, y1) in ROWS.items():
        m = f[y0:y1, X0:X1].reshape(-1, 3).mean(axis=0)
        r[f"{k}_r"], r[f"{k}_g"], r[f"{k}_b"] = (round(float(v), 2) for v in m)
        r[k] = round(float(m.mean()), 2)
        tot.append(m.mean())
    r["all"] = round(float(np.mean(tot)), 2)
    recs.append(r)
    n += 1
p.wait()

with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(recs[0].keys()))
    w.writeheader()
    w.writerows(recs)

keys = ["all"] + list(ROWS)
arr = {k: np.array([r[k] for r in recs]) for k in keys}
print(f"{n} frames; overall level median {np.median(arr['all']):.2f}, "
      f"min {arr['all'].min():.2f} (frame {arr['all'].argmin()}), max {arr['all'].max():.2f}")
for k in keys:
    a = arr[k]
    med = np.array([np.median(a[max(0, i - 24):i + 25]) for i in range(len(a))])
    dev = (a - med) / med * 100
    hits = np.where(np.abs(dev) > 4)[0]
    print(f"  {k:7s} median {np.median(a):6.2f}  frame-to-frame sd {np.std(np.diff(a)):.2f}  "
          f"frames off >4%: {len(hits)}")
    if len(hits):
        # group consecutive frames
        groups, start = [], hits[0]
        for a0, a1 in zip(hits, hits[1:]):
            if a1 != a0 + 1:
                groups.append((start, a0)); start = a1
        groups.append((start, hits[-1]))
        print("          " + ", ".join(f"{g0}-{g1} ({dev[g0:g1 + 1].min():+.0f}..{dev[g0:g1 + 1].max():+.0f}%)"
                                       for g0, g1 in groups[:20]))
