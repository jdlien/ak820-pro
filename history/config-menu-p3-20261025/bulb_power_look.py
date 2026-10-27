"""The Power page's bulbs on the board (a5d9171c): open, to Power, the cursor
through every row and around once more, a dwell on each; held back, nothing
committed; every pass timed (op 27 sub 10). Never enumerates HID."""
import json
import sys
import time

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
import menu_p1a_board as g  # noqa: E402
from menu_s0_session import open_device, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

TOP, POWER = 1, 2
OUT = sys.argv[1] if len(sys.argv) > 1 else "bulb-look.json"
h = open_device()
meas = {}
try:
    to_dash(h)
    xfer(h, 10, bytes([1]))
    g.step(h, 11, b"", "open", g.SCR(TOP), 0)
    g.turn(h, g.R_POWER, "to Power", g.SCR(TOP), g.R_POWER)
    s = g.click(h, "Power", g.SCR(POWER))
    c0 = s["cursor"]
    g.dwell(h, "the page, its four bulbs, 2 s", 2.0)
    for k in range(1, 11):
        g.turn(h, 1, f"row {(c0 + k) % 5}", g.SCR(POWER), (c0 + k) % 5)
        g.dwell(h, "1.5 s", 1.5)
    g.hold(h, "Power back, nothing committed", g.SCR(TOP), g.R_POWER)
    g.step(h, 11, b"", "close", owner="dash")
    time.sleep(1.5)
    meas = decode_meas(xfer(h, 10, bytes([0])))
    g.check(not meas["aliased"], "no pass of 340 ms or more")
    g.check(meas["pass_max_us"] < 25000, f"the longest pass {meas['pass_max_us']} us")
    print(f"  longest pass {meas['pass_max_us']} us, over 15 ms {meas['over15']}", flush=True)
    to_dash(h)
finally:
    h.close()
    with open(OUT, "w") as f:
        json.dump({"steps": g.log, "meas": meas, "fails": g.fails, "slow": g.slow}, f, indent=1)
print("PASS" if not g.fails else f"FAILED: {len(g.fails)}")
sys.exit(1 if g.fails else 0)
