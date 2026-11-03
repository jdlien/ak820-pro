#!/usr/bin/env python3
"""Find dark frames in a slow-motion clip of the keyboard's lights.

The camera gate (plans/ROW-ISR-PLAN.md, stage 4) asks whether the clock
chip's unmasked write shows a dark frame on the LEDs. Judging that by eye
in a 240 fps clip is unreliable, so this measures it: ffprobe's signalstats
gives every frame's mean luma (YAVG), and a frame well below the clip's
median is a dip. The positive control (dev op 23's burst: 20 held reads
100 ms apart, each a ~3 ms dark gap) should show 20 dips 24 frames apart at
240 fps; the write under test should show none.

Measured 11-03 (docs/test-bench.md, "The camera"): from the tripod, the
keys cropped (990:410:260:100), the room lit, a held read's ~3 ms gap is a
5-7% dip in one frame, or 3-4% in each of two when it straddles a frame
boundary, against a frame-to-frame noise of 0.3%; so the default depth is
3%. A dark board shows nothing: Power saver's ladder turns the lights off
3 min after the last key, so relight it (and hold the ladder) first.

Usage: clip_dips.py CLIP [--fps 240] [--crop W:H:X:Y] [--depth 0.03]
                    [--mad 4] [--csv OUT]
  --fps    the capture rate: a Pixel's "1/8" slow motion is 240 fps (its file
           may say 30 fps, with every captured frame kept)
  --crop   restrict to the keys (ffmpeg crop syntax), when the frame holds more
  --depth  a dip is at least this fraction below the median (default 0.03)
  --mad    ... and at least this many scaled MADs below it (default 4)
Needs ffmpeg/ffprobe on PATH; nothing else.
"""
import argparse, json, statistics, subprocess, sys

def ffprobe_stream(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_frames,width,height,duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]

def lavfi_escape(path):
    # a filter-graph argument: escape the characters the graph parser eats
    return path.replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,").replace("'", "\\'").replace("[", "\\[").replace("]", "\\]")

def per_frame_yavg(path, crop=None):
    graph = "movie=" + lavfi_escape(path)
    if crop:
        graph += ",crop=" + crop
    graph += ",signalstats"
    out = subprocess.run(["ffprobe", "-v", "error", "-f", "lavfi", "-i", graph,
                          "-show_entries", "frame=pts_time:frame_tags=lavfi.signalstats.YAVG",
                          "-of", "csv=p=0"], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(",")
        if len(parts) < 2 or not parts[1]:
            continue
        rows.append((float(parts[0]), float(parts[1])))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--fps", type=float, default=240.0)
    ap.add_argument("--crop")
    ap.add_argument("--depth", type=float, default=0.03)
    ap.add_argument("--mad", type=float, default=4.0)
    ap.add_argument("--csv")
    a = ap.parse_args()
    st = ffprobe_stream(a.clip)
    rows = per_frame_yavg(a.clip, a.crop)
    if len(rows) < 10:
        sys.exit(f"only {len(rows)} frames read")
    y = [v for _, v in rows]
    med = statistics.median(y)
    mad = 1.4826 * statistics.median([abs(v - med) for v in y]) or 1e-9
    thr = med - max(a.depth * med, a.mad * mad)
    print(f"{a.clip}: {len(rows)} frames, {st.get('width')}x{st.get('height')}, file rate {st.get('r_frame_rate')} (avg {st.get('avg_frame_rate')}), "
          f"duration {float(st.get('duration', 0)):.2f} s in the file; at {a.fps:g} fps captured that is {len(rows)/a.fps:.2f} s of real time")
    print(f"YAVG median {med:.1f}, scaled MAD {mad:.2f}, min {min(y):.1f}, max {max(y):.1f}; a dip is below {thr:.1f} "
          f"({(1-thr/med)*100:.0f}% under the median)")
    # events: runs of consecutive dip frames
    events, i = [], 0
    while i < len(y):
        if y[i] < thr:
            j = i
            while j + 1 < len(y) and y[j + 1] < thr:
                j += 1
            lo = min(y[i:j + 1])
            events.append((i, j - i + 1, lo))
            i = j + 1
        else:
            i += 1
    # the camera settles its exposure over the clip's first quarter second
    # (six false dips in the first 60 frames of a 2x clip, 11-03): listed, not counted
    settle = int(0.5 * a.fps)
    early = [e for e in events if e[0] < settle]
    events = [e for e in events if e[0] >= settle]
    print(f"dips: {len(events)}" + (f" (+{len(early)} in the clip's first 0.5 s, the camera settling, not counted)" if early else ""))
    prev = None
    for (f, n, lo) in early + events:
        gap = "" if prev is None else f"  +{(f - prev)/a.fps*1000:.1f} ms after the previous"
        tag = "  [settling]" if f < settle else ""
        print(f"  frame {f:5d} ({f/a.fps:7.3f} s real, {rows[f][0]:7.3f} s in the file): {n} frame(s), min YAVG {lo:.1f} = {(1-lo/med)*100:.0f}% under the median{gap}{tag}")
        prev = f
    # a coarse profile: the minimum in each of 100 bins across the clip
    nb = min(100, len(y))
    per = len(y) / nb
    print("profile (each column the darkest frame in its slice; '#' at the median, '.' a dip):")
    cols = []
    for b in range(nb):
        seg = y[int(b * per):int((b + 1) * per)] or [med]
        m = min(seg)
        cols.append("." if m < thr else ("#" if m >= med * 0.97 else "+"))
    print("  " + "".join(cols))
    if a.csv:
        with open(a.csv, "w") as fh:
            fh.write("frame,pts_s,real_s,yavg,dip\n")
            for k, (t, v) in enumerate(rows):
                fh.write(f"{k},{t:.6f},{k/a.fps:.6f},{v:.3f},{int(v < thr)}\n")
        print(f"wrote {a.csv}")

if __name__ == "__main__":
    main()
