#!/usr/bin/env python3
"""S1: which dashboard paths make passes over 15 ms (C10's target). The gate
(§16) passed on a8b98bc0 but failed on cbb51ac1 with a 20.3 ms pass that
F1, its only menu screen, doesn't explain; a real spin's record showed a
17.7 ms pass on the dashboard before the menu opened.

    venv-win/Scripts/python.exe scripts/menu_s1_dashwatch.py SECS OUT.json < /dev/null

Arms sub 10 and HC_ACCT; every 250 ms reads sub 10 and the daemon's
now-playing text; when sub 10's count over 15 ms grows, reads HC_ACCT's
ring (the last 16 passes of >= 10 ms) and keeps the new ones of >= 15 ms
with their per-scope milliseconds and the track text at the time. Touches
nothing else. Never enumerates HID on Windows."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from menu_s0_session import media_text, open_device, read_state, xfer  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402
from ak820health import read_acct  # noqa: E402


def main():
    secs, out = float(sys.argv[1]), sys.argv[2]
    h = open_device()
    slow, seen, events = [], set(), []
    m = {}
    try:
        read_acct(h, "on")
        read_acct(h, "reset")
        xfer(h, 10, bytes([1]))
        t0 = time.perf_counter()
        over, track = 0, media_text()
        while time.perf_counter() - t0 < secs:
            m = decode_meas(xfer(h, 10, bytes([0])))
            tr = media_text()
            if tr != track:
                events.append({"t": round(time.perf_counter() - t0, 2), "track": tr})
                track = tr
            if m["over15"] > over:
                over = m["over15"]
                s = read_state(h)
                for e in read_acct(h)["ring"]:
                    if e["pass_ms"] >= 15 and e["uptime_ms"] not in seen:
                        seen.add(e["uptime_ms"])
                        e = dict(e, t=round(time.perf_counter() - t0, 2), owner=s["owner"], track=tr,
                                 top={k: v for k, v in e["scopes_ms"].items() if v})
                        slow.append(e)
                        print(json.dumps({k: e[k] for k in ("t", "pass_ms", "owner", "top")}), flush=True)
            time.sleep(0.25)
        print("SUMMARY " + json.dumps({"secs": secs, "pass_max_us": m.get("pass_max_us"), "over15": m.get("over15"),
                                       "aliased": m.get("aliased"), "track_changes": len(events)}), flush=True)
    finally:
        try:
            read_acct(h, "off")
        finally:
            h.close()
            with open(out, "w") as f:
                json.dump({"summary": m, "slow": slow, "tracks": events}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
