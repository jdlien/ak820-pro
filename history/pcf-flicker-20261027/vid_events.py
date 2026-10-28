"""From rows.csv (vid_rows.py): each frame's hottest row-colour (its level over
that row-colour's median) and the board's level against its rolling median,
for the frames where the board dims; and from the clip itself, the frames
where the LCD's seconds digits change (the keyboard's clock, synced to
gremlin), to put the events on the wall clock."""
import csv
import subprocess
import sys

import numpy as np

SRC, CSV = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(CSV)))
bands = ["F", "num", "qwer", "asdf", "zxcv", "bottom"]
ch = ["r", "g", "b"]
M = np.array([[[float(r[f"{b}_{c}"]) for c in ch] for b in bands] for r in rows])   # frame, band, channel
allv = np.array([float(r["all"]) for r in rows])
med_bc = np.median(M, axis=0)
p99_bc = np.percentile(M, 99, axis=0)
roll = np.array([np.median(allv[max(0, i - 24):i + 25]) for i in range(len(allv))])
dip = (allv - roll) / roll * 100

# The LCD's seconds digits, full resolution (x 1640-1676, y 692-722).
W, H, X, Y = 36, 30, 1640, 692
p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", SRC, "-vf", f"crop={W}:{H}:{X}:{Y}", "-f", "rawvideo",
                      "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
sig = []
while True:
    b = p.stdout.read(W * H)
    if len(b) < W * H:
        break
    sig.append(np.frombuffer(b, np.uint8).astype(np.float32))
p.wait()
sig = np.array(sig)
d = np.abs(np.diff(sig, axis=0)).mean(axis=1)
base = np.median(d)
steps = [i + 1 for i in np.argsort(d)[::-1][:12] if d[i] > 6 * base]
print(f"LCD seconds: frame-to-frame change median {base:.2f}; biggest changes at frames "
      + ", ".join(f"{i} ({d[i - 1]:.1f})" for i in sorted(steps)))

print("\nframes where the board dims >= 4%: the board's dip, and the hottest row-colour (x its median, x its 99th pct)")
for i in np.where(dip <= -4)[0]:
    ratio = M[i] / med_bc
    b, c = np.unravel_index(np.argmax(ratio), ratio.shape)
    print(f"  frame {i:4d} ({i / 240:.3f} s): board {dip[i]:+.1f}%, hottest {bands[b]}-{ch[c]} "
          f"x{ratio[b, c]:.2f} median, x{M[i, b, c] / p99_bc[b, c]:.2f} p99; "
          f"others' mean x{np.delete(ratio.reshape(-1), b * 3 + c).mean():.2f}")
