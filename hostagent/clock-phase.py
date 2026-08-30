#!/usr/bin/env python3
"""Measure the AK820 Pro's clock phase error in milliseconds.

The wire protocol carries WHOLE SECONDS both ways, so the sub-second offset is
recovered by polling fast and catching the instant the device's seconds value
increments. At that edge a perfectly-synced device would have the host at
fraction .000, so the host's fraction AT THE EDGE is the error.

Polls over raw HID directly rather than spawning ak820ctl per sample -- process
spawn is tens of ms, which would swamp the thing being measured.
"""
import sys, time
import hid

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61
SET_VALUE, RTC_CHANNEL, RTC_GET_TIME = 0x07, 0x10, 0x02

def open_raw():
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
            return hid.Device(path=d["path"])
    sys.exit("raw HID interface not found (cable in? bootloader?)")

def read_secs(h):
    h.write(bytes([0x00, SET_VALUE, RTC_CHANNEL, RTC_GET_TIME] + [0]*29))
    r = h.read(32, timeout=200)
    if not r or not r[3]:
        return None
    return r[10], (r[8], r[9], r[10])

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    h = open_raw()
    errs = []
    for i in range(n):
        prev = None
        deadline = time.time() + 3.0
        while time.time() < deadline:
            got = read_secs(h)
            t = time.time()
            if got is None:
                continue
            sec, hms = got
            if prev is not None and sec != prev:
                frac = t - int(t)
                # SIGN: frac is the host's fraction when the DEVICE ticked. If the
                # device ticks at host .08 its boundary came LATE, so the device
                # is BEHIND by 80 ms. Positive = behind, negative = ahead.
                err = frac if frac < 0.5 else frac - 1.0   # signed, nearest boundary
                errs.append(err * 1000)
                print(f"sample {i+1}: device ticked to {hms[0]:02d}:{hms[1]:02d}:{hms[2]:02d} "
                      f"at host .{frac*1000:06.1f}ms  ->  {err*1000:+7.1f} ms "
                      f"({'behind' if err > 0 else 'ahead'})")
                break
            prev = sec
        else:
            print(f"sample {i+1}: no tick within 3 s")
    if errs:
        errs.sort()
        mean = sum(errs)/len(errs)
        print(f"\nn={len(errs)}  mean {mean:+.1f} ms  median {errs[len(errs)//2]:+.1f} ms  "
              f"spread {max(errs)-min(errs):.1f} ms")
        print("device BEHIND host" if mean > 0 else "device AHEAD of host")

main()
