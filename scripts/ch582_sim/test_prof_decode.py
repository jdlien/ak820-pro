#!/usr/bin/env python3
"""Run hostagent/ak820health.py's read_link_prof over the HC_LINK profile pages
the driver's own ch582_prof_fill filled (harness.c's `profile` case prints
them), through a fake device that answers each request with its page. Also:
firmware without the profile (page 0's layout, the version in the page byte)
must read as None, not be decoded."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hostagent"))
sys.modules.setdefault("hid", type(sys)("hid"))
sys.modules.setdefault("venv_bootstrap", type(sys)("venv_bootstrap"))
import ak820health as H

pages = {}
for line in sys.stdin:
    if line.startswith("PAGE "):
        _, pg, hexs = line.split()
        pages[int(pg)] = bytes.fromhex(hexs)


class Dev:
    def __init__(self, answer):
        self.answer, self.q = answer, []
    def write(self, b):
        self.q.append(self.answer(b[4]))
    def read(self, n, t):
        return self.q.pop(0) if self.q else b""


fails = 0
def check(c, m):
    global fails
    if not c:
        fails += 1
        print("  FAIL", m)

new = Dev(lambda pg: bytes([H.SET_VALUE, H.HEALTH_CHANNEL, H.HC_LINK, pg]) + pages.get(pg, bytes(28)))
p = H.read_link_prof(new)
check(p is not None, "decoded")
if p:
    check(p["slow_calls"] == 1 and p["slow_threshold_ms"] == 4.0, f"slow calls {p['slow_calls']}")
    check(p["slow_ms"]["c5_hook"] == 9.6 and p["slow_ms"]["rx"] == 0, f"sections {p['slow_ms']}")
    check(p["c5_reports"] == 3 and p["c5_hook_max_ms"] == 4.8, f"5C {p['c5_reports']} {p['c5_hook_max_ms']}")
    check(len(p["ring"]) == 1 and p["ring"][0]["c5_reports"] == 2 and p["ring"][0]["rx_bytes"] == 6
          and p["ring"][0]["total_ms"] == 9.6, f"ring {p['ring']}")
old = Dev(lambda pg: bytes([H.SET_VALUE, H.HEALTH_CHANNEL, H.HC_LINK, 8]) + bytes(28))
check(H.read_link_prof(old) is None, "flash 1b's firmware (no profile) reads as None")
print(f"{'FAIL' if fails else 'ok  '} profile decode")
sys.exit(1 if fails else 0)
