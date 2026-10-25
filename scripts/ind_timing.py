"""The indicator tick's cost (plans/CONFIG-MENU-P1-DESIGN.md, "P2a"; codex on
its design, point 2): the main loop's pass rate (health page 2) and the row
ISR's rate and CPU share (page 4) over an interval, under a named indicator
state. With --set (P2a firmware, dev builds: op 27 sub 15) the groups are
forced at a level first, and put back after; without it the board is
measured as it is (the old firmware's baseline, Caps from the host).

    venv-win/Scripts/python.exe scripts/ind_timing.py LABEL [--set FORCE,LOCKS,CHG]
        [--secs 10] [--out FILE.jsonl] < /dev/null"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ak820health as H  # noqa: E402
from menu_s0_session import xfer  # noqa: E402
from menu_p1b_gates import devop  # noqa: E402


def sample(h):
    return H.read_stalls(h), H.read_isr(h)


def ind_state(h):
    r = xfer(h, 14)
    return {"open": r[6], "locks": r[12], "charging": r[13], "force": r[14]}


def ind_set(h, force, locks, chg):
    r = xfer(h, 15, bytes([force, locks, chg]))
    if r[5] != 0:
        raise SystemExit(f"op 27 sub 15 refused ({r[5]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--set", help="FORCE,LOCKS,CHG: the force bits (1 locks, 2 charging) and the levels 0-100")
    ap.add_argument("--lcd", type=int, help="the LCD level for the run (dev op 4, RAM only; put back after)")
    ap.add_argument("--secs", type=float, default=10.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    h = H.open_device()
    before, lcd0, lcd_eff = None, None, None
    try:
        if a.set or a.lcd is not None:
            # An open edit's live value is a preview: sub 15 or op 4 cancels
            # it, and restoring the value read before would keep the preview
            # (codex, P2a's and P2b's code reviews).
            if ind_state(h)["open"]:
                raise SystemExit("an edit is open in the menu: close it first")
        if a.set:
            force, locks, chg = (int(x) for x in a.set.split(","))
            before = ind_state(h)
            ind_set(h, force, locks, chg)
        if a.lcd is not None:
            lcd0 = devop(h, 6)
            st = devop(h, 4, a.lcd)
            # The workload is the effective level: powered, uncapped (codex).
            if st["level"] != a.lcd or not st["on"] or st["effective"] != a.lcd:
                raise SystemExit(f"the LCD isn't lit at {a.lcd}: {st}")
            lcd_eff = st["effective"]
        time.sleep(1.0)
        s2a, s4a = sample(h)
        t0 = time.monotonic()
        time.sleep(a.secs)
        s2b, s4b = sample(h)
        wall = time.monotonic() - t0
    finally:
        if before is not None:
            ind_set(h, before["force"], before["locks"], before["charging"])
        if lcd0 is not None:
            devop(h, 4, lcd0["level"])
        h.close()
    rates = H.isr_rates(s4a, s4b, wall)
    dt = rates["isr_dt_s"]
    passes = (s2b["passes"] - s2a["passes"]) & 0xFFFFFFFF
    row = {"label": a.label, "set": a.set, "lcd": a.lcd, "lcd_effective": lcd_eff, "secs": round(wall, 2), "passes_per_s": round(passes / dt, 1) if dt else None,
           "count_ge_10ms": (s2b["count_ge_10ms"] - s2a["count_ge_10ms"]) & 0xFFFFFFFF,
           "count_ge_25ms": (s2b["count_ge_25ms"] - s2a["count_ge_25ms"]) & 0xFFFFFFFF, **rates}
    print(json.dumps(row))
    if a.out:
        with open(a.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
