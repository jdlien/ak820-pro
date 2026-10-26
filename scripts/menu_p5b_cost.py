"""Usage: venv-win/Scripts/python.exe scripts/menu_p5b_cost.py < /dev/null

The `*` compare's cost on the board: the menu open and settled on the top
level, page one (the Profiles row showing), with no active profile and with
one, alternating, three windows each. Per pass: the menu's two scopes
(unaccounted holds menu_task, the blit pump menu_pump) and the passes >= 10
ms. A turn down and back before each window keeps the session open (24 s
idle closes it). Leaves the slots empty and the menu closed."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
import ak820profiles as ap  # noqa: E402
from ak820health import read_acct  # noqa: E402
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402

SECS = 8.0


def settle(h):
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5:
        s = read_state(h)
        if s["pixels_done"] and s["owner"] == "menu":
            return s
        time.sleep(0.1)
    raise SystemExit(f"not settled: {s['owner']} {s['session']}")


def turn(h, n):
    st, seq = mutate(h, 1, bytes([n & 0xFF]))
    if st != 0:
        raise SystemExit(f"turn refused {st}")
    wait(h, seq, poll=0.1)


def window(h, what):
    turn(h, 1)
    turn(h, -1)
    settle(h)
    time.sleep(0.8)
    read_acct(h, "reset")
    time.sleep(SECS)
    a = read_acct(h)
    s = read_state(h)
    n = a["passes"]
    r = {"what": what, "passes": n, "unacc": a["all_ms"]["unaccounted"] / n, "pump": a["all_ms"]["blit_pump"] / n,
         "slow": a["slow_passes"], "owner": s["owner"], "screen": s["screen"], "cursor": s["cursor"]}
    print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}), flush=True)
    return r


def main():
    h = open_device()
    out = []
    try:
        b = ap.read_block(h)
        if b[0] == ap.MAGIC_V1 and any(ap.rec_ok(b[2 + s * 27:29 + s * 27]) for s in range(4)):
            raise SystemExit("refused: a slot is saved")
        to_dash(h)
        read_acct(h, "on")
        xfer(h, 11)   # open: the top level, row 0
        settle(h)
        for k in range(3):
            out.append(window(h, "none"))
            if ap.xfer(h, 0x40, [0])[5] != 0:
                raise SystemExit("dev save refused")
            out.append(window(h, "active"))
            if ap.xfer(h, 0x41, [0])[5] != 0:
                raise SystemExit("dev delete refused")
        xfer(h, 11)   # close
        time.sleep(1.5)
        to_dash(h)
    finally:
        h.close()
    for w in ("none", "active"):
        rs = [r for r in out if r["what"] == w]
        print(w, "means: unacc %.4f pump %.4f slow %.1f passes %.0f" % (
            sum(r["unacc"] for r in rs) / len(rs), sum(r["pump"] for r in rs) / len(rs),
            sum(r["slow"] for r in rs) / len(rs), sum(r["passes"] for r in rs) / len(rs)))


if __name__ == "__main__":
    main()
