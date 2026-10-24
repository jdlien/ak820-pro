"""S1: where the menu's slow passes go (HC_ACCT), with and without HID polling. scripts/menu_s1_acct_toggle.py [poll|quiet] < /dev/null
poll: toggle A/B and poll sub 5 flat out (as menu_s0_ledrate does);
quiet: toggle every 1.5 s with no polling between."""
import json
import os
import sys
import time

sys.path.insert(0, "scripts")
sys.path.insert(0, "hostagent")
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from ak820health import read_acct, read_stalls  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "poll"
h = open_device()
try:
    to_dash(h)
    st, seq = mutate(h, 4)
    wait(h, seq)
    time.sleep(1.5)
    read_acct(h, "on")
    read_acct(h, "reset")
    s0 = read_stalls(h)
    p = 0
    end = time.monotonic() + 8.0
    n = 0
    while time.monotonic() < end:
        p ^= 1
        st, seq = mutate(h, 0, bytes([p, 0]))
        n += 1
        if mode == "poll":
            wait(h, seq)
            e2 = time.monotonic() + 2
            while not read_state(h)["pixels_done"] and time.monotonic() < e2:
                pass
        else:
            time.sleep(1.5)
    s1 = read_stalls(h)
    a = read_acct(h)
    print(mode, "toggles", n, "ge10", s1["count_ge_10ms"] - s0["count_ge_10ms"],
          "ge25", s1["count_ge_25ms"] - s0["count_ge_25ms"])
    print("passes", a["passes"], "slow", a["slow_passes"])
    print("slow_ms by scope:", {k: v for k, v in a["slow_ms"].items() if v})
    print("slow_top:", {k: v for k, v in a["slow_top"].items() if v})
    for e in a["ring"][-8:]:
        print("  ring", e["pass_ms"], "ms:", {k: v for k, v in e["scopes_ms"].items() if v})
    to_dash(h)
finally:
    h.close()
