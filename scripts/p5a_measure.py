#!/usr/bin/env python3
"""P5a's first board measure (plans/SETTINGS-PROFILES-PLAN.md, "When"): a
complete main-loop pass that includes one profile save, with and without a
wear-leveling consolidation, against C10's 15 ms ceiling. Dev builds only:
HC_PROFILES' 0x40 (save) and 0x41 (delete), and op 27 sub 10 (the pass
measure: armed, then read).

Each save first moves the live hue by one through VIA's lighting channel,
which is _noeeprom (via.c), so the save writes the whole 26 B body and no
RGB flush lands in the interval. Baseline intervals, the same timing with no
save, come first. The hue is put back at the end, and slot 0 deleted.

    venv-win/Scripts/python.exe scripts/p5a_measure.py --out history/.../p5a-measure-<sha>.json < /dev/null

Never enumerates HID on Windows (ak820health.open_device()).
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from ak820health import open_device  # noqa: E402

SET_VALUE, GET_VALUE, CH, HC_DEVHOOK, HC_PROFILES = 0x07, 0x08, 0x13, 0x76, 0x10
RGB_CHANNEL, COLOR = 3, 4


def read_match(h, want, n, what):
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and bytes(r[1:n]) == bytes(want[1:n]):
            if r[0] == 0xFF:
                raise SystemExit(f"{what}: unhandled -- is this a dev build with P5a?")
            return bytes(r)
    raise SystemExit(f"{what}: no reply")


def meas(h, arm):
    req = bytes([SET_VALUE, CH, HC_DEVHOOK, 27, 10, 1 if arm else 0]) + bytes(26)
    h.write(bytes([0]) + req)
    r = read_match(h, req, 5, "op 27 sub 10")
    return {"pass_max_us": r[10] | r[11] << 8, "over15": r[12] | r[13] << 8, "passes": r[24] | r[25] << 8}


def prof(h, sub, slot):
    req = bytes([SET_VALUE, CH, HC_PROFILES, sub, slot]) + bytes(27)
    h.write(bytes([0]) + req)
    r = read_match(h, req, 5, f"HC_PROFILES {sub:#x}")
    return r[5], bool(r[6])


def hue_get(h):
    req = bytes([GET_VALUE, RGB_CHANNEL, COLOR]) + bytes(29)
    h.write(bytes([0]) + req)
    r = read_match(h, req, 3, "VIA colour read")
    return r[3], r[4]


def hue_set(h, hue, sat):
    req = bytes([SET_VALUE, RGB_CHANNEL, COLOR, hue, sat]) + bytes(27)
    h.write(bytes([0]) + req)
    read_match(h, req, 3, "VIA colour set")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline", type=int, default=20)
    ap.add_argument("--max-saves", type=int, default=250)
    ap.add_argument("--after-consolidations", type=int, default=2)
    a = ap.parse_args()
    h = open_device()
    hue0, sat0 = hue_get(h)
    base, saves = [], []
    try:
        for _ in range(a.baseline):
            meas(h, True)
            time.sleep(0.05)
            base.append(meas(h, False))
            time.sleep(0.2)
        cons = 0
        for i in range(a.max_saves):
            hue_set(h, (hue0 + 1 + (i & 1)) & 0xFF, sat0)
            time.sleep(0.05)
            meas(h, True)
            st, c = prof(h, 0x40, 0)
            m = meas(h, False)
            m.update(status=st, consolidated=c, i=i)
            saves.append(m)
            if st != 0:
                print(f"save {i}: status {st}")
            if c:
                cons += 1
                print(f"save {i}: consolidated, the pass {m['pass_max_us']} us")
                if cons >= a.after_consolidations:
                    break
            time.sleep(0.2)
    finally:
        hue_set(h, hue0, sat0)
        prof(h, 0x41, 0)
        h.close()

    def summary(rows):
        v = [r["pass_max_us"] for r in rows]
        return {"n": len(v), "median_us": statistics.median(v) if v else None, "max_us": max(v) if v else None,
                "over15": sum(1 for x in v if x > 15000)}
    plain = [s for s in saves if not s["consolidated"] and s["status"] == 0]
    cons_rows = [s for s in saves if s["consolidated"]]
    out = {"baseline": summary(base), "saves": summary(plain), "consolidating": summary(cons_rows),
           "rows": {"baseline": base, "saves": saves}}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    for k in ("baseline", "saves", "consolidating"):
        print(f"{k:13s} {out[k]}")
    print(f"-> {a.out}")
    worst = max([s["pass_max_us"] for s in plain] + [0])
    return 0 if worst <= 15000 else 1


if __name__ == "__main__":
    sys.exit(main())
