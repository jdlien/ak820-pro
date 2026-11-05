#!/usr/bin/env python3
"""The precision path's arithmetic on the host (D9 revised): rowisr.c's
wide_width() over every (chroma, value) at the three scales (the 125 us
cadence's 300, the devprobe's 64, the 267 us cadence's 640): every width
strictly below the cadence's terminal, monotonic in the value and in the
chroma, the top exact (255 x k / 64), the dither buckets where the light is
under a tick, and the intermediate ranges inside 32 bits."""
import sys
H = "qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/curve12.h"
t = [int(x) for l in open(H) if l.startswith("    ") for x in l.strip().rstrip(",").split(",")]
assert len(t) == 256 and t[0] == 0 and t[255] == 16320 and all(t[i] <= t[i + 1] for i in range(255))
FLAG, BASE, PSHIFT = 0x8000, 0x07FF, 11
PAT = [0, 0x1, 0x5, 0x7]
def wide(chroma, v, K):
    full_q8 = (t[v] * K) >> 4; assert full_q8 * 256 < 2**32
    recip = (full_q8 * 256 + 127) // 255; assert chroma * recip < 2**32
    q8 = (chroma * recip + 128) >> 8; w, frac = q8 >> 8, q8 & 0xFF
    if w >= 16: return w + (1 if frac >= 128 else 0)
    q = (frac + 32) >> 6
    if q == 4: w += 1; q = 0
    if q == 0: return w
    return FLAG | (PAT[q] << PSHIFT) | w
def light(w):   # the mean ticks a field a coded width means
    if w & FLAG: return (w & BASE) + bin((w >> PSHIFT) & 0xF).count("1") / 4
    return w
def worst(w):   # the most ticks one field of it drives (the terminal rule)
    return (w & BASE) + 1 if w & FLAG else w
bad = 0
for K, term in ((300, 1535), (64, 1535), (640, 4095)):
    top = (255 * K + 32) >> 6
    for chroma in range(256):
        prev = -1
        for v in range(256):
            w = wide(chroma, v, K)
            if not (worst(w) < term): bad += 1; print("over the terminal", K, chroma, v, w)
            l = light(w)
            if l < prev: bad += 1; print("not monotonic in v", K, chroma, v, w, prev)
            prev = l
    for v in range(256):
        prev = -1
        for chroma in range(256):
            l = light(wide(chroma, v, K))
            if l < prev: bad += 1; print("not monotonic in chroma", K, chroma, v)
            prev = l
    assert wide(255, 255, K) == top, (K, wide(255, 255, K), top)
    print(f"K={K}: top {top} ticks exact; v=1 {light(wide(255,1,K))}, v=2 {light(wide(255,2,K))}, v=13 {wide(255,13,K)}, v=128 {wide(255,128,K)}; purple at v=13: r {light(wide(77,13,K))} g {light(wide(35,13,K))} b {light(wide(255,13,K))}; the first v with every purple channel lit: " + str(next(v for v in range(256) if all(light(wide(c, v, K)) > 0 for c in (77, 35, 255)))))
print("exhaustive checks:", "all pass" if bad == 0 else f"{bad} FAILED"); sys.exit(1 if bad else 0)
