#!/usr/bin/env python3
"""Run hostagent/ak820health.py's protocol-8 decoders over the pages the
firmware's own loop_acct.c and flash_stats.c filled (sim.c prints them), and
check the numbers sim.c drove in. Reads sim output on stdin."""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hostagent"))
sys.modules.setdefault("hid", type(sys)("hid"))      # the decoders need no device
sys.modules.setdefault("venv_bootstrap", type(sys)("venv_bootstrap"))
import ak820health as H

pages = {}
for line in sys.stdin:
    if line.startswith("PAGE "):
        _, cmd, page, hexs = line.split()
        pages[(cmd, int(page))] = bytes.fromhex(hexs)

CMD = {H.HC_ACCT: "ACCT", H.HC_FLASHW: "FLASHW"}


def fake_txn_page(h, cmd, page, arg=0, timeout_ms=500):
    if page in (0xF0, 0xF1):
        page = 0
    body = pages.get((CMD[cmd], page), bytes(28))
    return bytes([H.SET_VALUE, H.HEALTH_CHANNEL, cmd, page]) + body


H._txn_page = fake_txn_page
fails = 0


def check(cond, msg):
    global fails
    if not cond:
        fails += 1
        print("  FAIL", msg)


if ("ACCT", 0) in pages:
    a = H.read_acct(None)
    check(a["passes"] == 104 and a["slow_passes"] == 3, f"passes {a['passes']} slow {a['slow_passes']}")
    check(a["long_passes"] == 0, f"long passes {a['long_passes']}")
    check(a["st_freq"] == 187500, f"st_freq {a['st_freq']}")
    check(abs(a["slow_ms"]["display_hk"] - 8.0) < 0.01, f"display slow ms {a['slow_ms']['display_hk']}")
    check(abs(a["slow_ms"]["battery"] - 3.0) < 0.01, f"battery slow ms {a['slow_ms']['battery']}")
    check(abs(a["slow_ms"]["rtc_task"] - 10.0) < 0.01, f"rtc slow ms {a['slow_ms']['rtc_task']}")
    # unaccounted: 1 ms (the 12 ms pass) + 20 ms (all QMK) + 0 (the 10 ms rtc pass)
    check(abs(a["slow_ms"]["unaccounted"] - 21.0) < 0.05, f"unaccounted {a['slow_ms']['unaccounted']}")
    check(a["slow_top"]["display_hk"] == 1 and a["slow_top"]["unaccounted"] == 1 and a["slow_top"]["rtc_task"] == 1,
          f"largest {a['slow_top']}")
    check(len(a["ring"]) == 3 and a["ring"][0]["pass_ms"] == 12, f"ring {a['ring']}")
    check(a["ring"][0]["scopes_ms"]["display_hk"] == 8 and a["ring"][0]["scopes_ms"]["unaccounted"] == 1,
          f"ring 0 {a['ring'][0]}")
    # all-pass ms: 100 passes of 1 ms ch582
    check(a["all_ms"]["ch582"] == 100, f"ch582 all-pass ms {a['all_ms']['ch582']}")
    print(f"{'FAIL' if fails else 'ok  '} decode acct")

if ("FLASHW", 0) in pages:
    f = H.read_flashw(None)
    check(f["sessions"] == {"other": 1, "kb": 7, "rgb": 1, "via": 1}, f"sessions {f['sessions']}")
    check(f["erases"]["rgb"] == 1 and f["programs"]["rgb"] == 3, f"rgb {f['erases']} {f['programs']}")
    check(f["kb_field_sessions"]["rtc_period"] == 5 and f["kb_field_sessions"]["batt_level"] == 1,
          f"fields {f['kb_field_sessions']}")
    check(f["kb_mixed"] == 1 and f["kb_unknown"] == 0, f"mixed {f['kb_mixed']}")
    check(f["rtc_last_proposed"] == 33300 and f["rtc_last_proposed_path"] == "pcf", f"rtc {f}")
    check(f["rtc_last_stored"] == 33300 and f["rtc_stores"] == {"sof": 0, "pcf": 1}, f"rtc stores {f}")
    check(f["rtc_proposals"] == {"sof": 1, "pcf": 1}, f"proposals {f['rtc_proposals']}")
    check(f["last_erase_uptime_ms"] == 20000, f"last erase {f['last_erase_uptime_ms']}")
    check(f["store_bytes"] == 2048, f"store bytes {f['store_bytes']}")
    print(f"{'FAIL' if fails else 'ok  '} decode flash")

# The reply readers must take only a reply to THEIR request (codex, gate 2).
class FakeDev:
    def __init__(self, replies):
        self.q = list(replies)
    def write(self, b):
        pass
    def read(self, n, t):
        return self.q.pop(0) if self.q else b""

def rep_(cmd, page, fill=0):
    return bytes([H.SET_VALUE, H.HEALTH_CHANNEL, cmd, page] + [fill] * 28)

import importlib
H2 = importlib.reload(H)
d = FakeDev([rep_(H2.HC_FLASHW, 2, 9), rep_(H2.HC_LINK, 8, 7), rep_(H2.HC_FLASHW, 0, 5)])
got = H2._txn_page(d, H2.HC_FLASHW, 0)
check(got[3] == 0 and got[4] == 5, f"page 0 taken, the page-2 and HC_LINK replies discarded: {got[:6]}")
d = FakeDev([rep_(H2.HC_LINK, 8), rep_(H2.HC_GET, 8, 3)])
got = H2._txn(d, H2.HC_GET)
check(got[2] == H2.HC_GET, f"HC_GET's reply, not HC_LINK's: {got[:4]}")
d = FakeDev([rep_(H2.HC_ACCT, 0, 1)])
check(H2._txn_page(d, H2.HC_ACCT, 0xF0, 1)[3] == 0, "0xF0 answers as page 0")
d = FakeDev([rep_(H2.HC_LINK, 0x21, 1), rep_(H2.HC_LINK, 8, 0)])
got = H2.read_link(d)
check(got["sent"] == 0, f"read_link skips another reader's profile page 0x21: {got}")
print(f"{'FAIL' if fails else 'ok  '} reply validation")

sys.exit(1 if fails else 0)
