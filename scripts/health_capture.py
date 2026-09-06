#!/usr/bin/env python3
"""Capture the raw 32-byte health replies, once per page, as hex.

For building phase-5 fixtures: feed the output to scripts/health_oracle.py
(the Python's decoding of the same bytes) and to ak820-agent's tests (the
Rust's). Page 4 is read twice, WALL seconds apart, because --isr derives
rates from two reads.

⚠️ Uses hidapi through ak820health.open_device(), which ENUMERATES HID -- the
thing the Rust agent exists to avoid, tolerated on steady mains (BACKLOG.md,
"Host tooling still enumerates HID"). A one-off capture, not a tool to loop.

    venv-win\\Scripts\\python.exe scripts\\health_capture.py [WALL]
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
import ak820health  # noqa: E402


def hexline(rep):
    return " ".join(f"{b:02X}" for b in bytes(rep))


def drain(h):
    """Windows delivers HID input reports to EVERY open handle. The first run
    of this script slept two seconds between the page-4 reads, the Rust
    daemon's playback echo landed in this handle's queue meanwhile, and
    ak820health._txn() took it as the reply ("garbled health reply"). So:
    empty the queue before asking, which is what ak820-agent's transport does
    before every request."""
    n = 0
    while h.read(32, 10):
        n += 1
    return n


def txn(h, cmd):
    dropped = drain(h)
    if dropped:
        print(f"# drained {dropped} foreign report(s) before {cmd:#04x}", file=sys.stderr)
    return ak820health._txn(h, cmd)


def main():
    wall = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    h = ak820health.open_device()
    try:
        for name, cmd in (("page1", ak820health.HC_GET), ("page2", ak820health.HC_GET2),
                          ("page3", ak820health.HC_GET3), ("page4", ak820health.HC_GET4)):
            print(f"{name} {hexline(txn(h, cmd))}")
        t0 = time.monotonic()
        time.sleep(wall)
        rep = txn(h, ak820health.HC_GET4)
        t1 = time.monotonic()
        print(f"page4b {hexline(rep)}")
        print(f"wall {t1 - t0:.6f}")
    finally:
        h.close()


if __name__ == "__main__":
    main()
