#!/usr/bin/env python3
"""Does the fixture's painting cost the RGB its brightness? JD saw the
keyboard's lights dim while A11 flashed the fixture's patterns (10-23).

The row ISR lights one LED row per entry; its period is its own duration plus
~53 us (the counter is re-armed at its end), so anything that delays it
lengthens the dark gaps and dims every row. Health page 4 counts its entries
and their cost. This reads it in 5 s windows:

    dash      the dashboard, now-playing on it
    static    the fixture open, nothing repainting
    toggling  the fixture's patterns A and B toggled back to back, as A11 does
    dash      the dashboard again

    venv-win/Scripts/python.exe scripts/menu_s0_ledrate.py [--out F] < /dev/null

Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402
from menu_s0_accept import op1, to_dash  # noqa: E402
from ak820health import isr_rates, read_isr, read_stalls  # noqa: E402

WINDOW_S = 5.0


def window(h, label, during=None, secs=WINDOW_S, first=None):
    """One page-4 window of `secs`: `first` is called once at its start (a
    transition), `during` repeatedly until it ends."""
    sa = read_stalls(h)
    a = read_isr(h)
    ta = time.monotonic()
    end = ta + secs
    if first:
        first()
    work = 0
    while time.monotonic() < end:
        if during:
            during()
            work += 1
        else:
            time.sleep(0.1)
    b = read_isr(h)
    sb = read_stalls(h)
    r = isr_rates(a, b, time.monotonic() - ta)
    r.update(label=label, work=work, ge10=sb["count_ge_10ms"] - sa["count_ge_10ms"],
             ge25=sb["count_ge_25ms"] - sa["count_ge_25ms"], passes=sb["passes"] - sa["passes"])
    print(f"{label:9s} {r['isr_per_s']:8.1f} ISR/s  mean {r['isr_mean_us']:6.1f} us  "
          f"max {r['isr_max_us']:6.1f} us  cpu {r['isr_cpu_pct']:5.1f}%  "
          f"timebase/wall {r['timebase_vs_wall']}  work {work}  "
          f"ge10 +{r['ge10']}  ge25 +{r['ge25']}  passes/s {r['passes'] / secs:.0f}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_s0_ledrate.json")
    a = ap.parse_args()
    h = open_device()
    out = []
    pattern = [0]

    def toggle():
        pattern[0] ^= 1
        st, seq = mutate(h, 0, bytes([pattern[0], 0]))
        wait(h, seq)
        end = time.monotonic() + 2.0
        while not read_state(h)["pixels_done"] and time.monotonic() < end:
            pass

    try:
        to_dash(h)
        time.sleep(1.0)
        out += [window(h, "dash"), window(h, "dash")]
        st, seq = mutate(h, 4)                     # open the fixture (24 s idle)
        wait(h, seq)
        end = time.monotonic() + 3.0
        while not read_state(h)["pixels_done"] and time.monotonic() < end:
            time.sleep(0.05)
        out.append(window(h, "static"))
        out += [window(h, "toggling", toggle), window(h, "toggling", toggle)]
        to_dash(h)
        time.sleep(1.0)
        out += [window(h, "dash"), window(h, "dash")]
        # The Fn+D page's transitions (op 1), each in a 1 s window from its
        # start: its clear into Health, Camera's, and the staged restore out.
        out.append(window(h, "dash-1s", secs=1.0))
        out.append(window(h, "fnd-enter", secs=1.0, first=lambda: op1(h)))
        time.sleep(2.0)
        out.append(window(h, "health-1s", secs=1.0))
        out.append(window(h, "fnd-camera", secs=1.0, first=lambda: op1(h)))
        time.sleep(2.0)
        out.append(window(h, "fnd-exit", secs=1.0, first=lambda: op1(h)))
        time.sleep(2.0)
        out.append(window(h, "dash-1s", secs=1.0))
    finally:
        h.close()
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
