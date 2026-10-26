#!/usr/bin/env python3
"""P5b on the board: the settings profiles' pages through the real menu,
driven by op 27, with their writes, on a dev build; every pass timed
(plans/SETTINGS-PROFILES-PLAN.md, "Tests", the board's).

    venv-win/Scripts/python.exe scripts/menu_p5b_board.py [--out F] < /dev/null

It refuses unless every slot is empty (the keyboard on gremlin's: nothing of
JD's to lose), and leaves them empty and the live settings as they were.

1. One measured interval (op 27 sub 10 armed): open; to Profiles; an empty
   slot saved by a click; its page; the top level's `*` after a change made
   over HC_PROFILES' live apply; Load; Save current here's confirm held, then
   clicked; Delete's confirm clicked; a host restore's Begin popping a slot's
   page; the close.
2. Every step: the screen and cursor (menu_p1a_board's step()); the block
   read back over HC_PROFILES sub 0 where a step writes it; each pass over
   15 ms printed with its scopes. The interval: none of 25 ms or more (a
   press can't be lost below it), none aliased. A save's wear-leveling
   consolidation (~58 ms, every ~16 saves: BACKLOG) is the one exception,
   and is reported, not failed.
Never enumerates HID on Windows."""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
import ak820profiles as ap  # noqa: E402
import menu_p1a_board as g  # noqa: E402
from menu_s0_session import open_device, xfer  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

SCR = g.SCR
TOP, PROFILES, PSLOT0, PSAVE, PDEL = 1, 50, 51, 56, 57
R_PROF, R_HELP = g.R_PROF, g.R_HELP
PR_LCD = 8   # the record's screen level (profiles.h)


def slots(h):
    """Each slot's record, or None, from the block as HC_PROFILES reads it."""
    b = ap.read_block(h)
    if b[0] != ap.MAGIC_V1:
        return [None] * ap.SLOTS, 0xFF
    out = []
    for s in range(ap.SLOTS):
        r = b[2 + s * ap.REC:2 + (s + 1) * ap.REC]
        out.append(r if ap.rec_ok(r) else None)
    return out, b[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="menu_p5b_board.json")
    a = p.parse_args()
    h = open_device()
    meas, live0 = {}, None
    try:
        recs, _ = slots(h)
        if any(recs):
            sys.exit("refused: a slot is saved (this script leaves nothing of the owner's; run it on empty slots)")
        live0 = ap.read_live(h)
        to_dash(h)
        g.read_acct(h, "on")
        g.read_acct(h, "reset")
        xfer(h, 10, bytes([1]))
        g.meas_on["on"] = True
        g.step(h, 11, b"", "open", SCR(TOP), 0)
        g.turn(h, R_PROF, "to Profiles", SCR(TOP), R_PROF)
        g.click(h, "Profiles", SCR(PROFILES), 1)
        g.click(h, "save Profile 1 (empty)", SCR(PROFILES), 1)
        recs, _ = slots(h)
        g.check(recs[0] is not None and not any(recs[1:]), "the save: slot 1 isn't the one saved")
        g.dwell(h, "the save's settle, the active slot's deferred write", 6.0)
        _, active = slots(h)
        g.check(active == 0, f"the active byte {active}, not 0 after the settle")
        g.click(h, "Profile 1's page", SCR(PSLOT0), 1)
        g.dwell(h, "its summary", 2.0)
        g.hold(h, "Profiles back", SCR(PROFILES), 1)
        g.hold(h, "the top level", SCR(TOP), R_PROF)

        # The `*`: the screen level changed over the live apply, the top
        # level's row then comparing each scan; a dwell on it.
        live = bytearray(ap.read_live(h))
        live[PR_LCD] = 7 if live[PR_LCD] != 7 else 8
        live[26] = ap.crc8(live[1:26])
        ap.apply_live(h, bytes(live))
        g.dwell(h, "the top level with its `*`, 3 s", 3.0)

        # Load: the screen level back; Profiles, the check there.
        g.click(h, "Profiles", SCR(PROFILES), 1)
        g.click(h, "Profile 1's page", SCR(PSLOT0), 1)
        g.click(h, "Load", SCR(PROFILES), 1)
        g.check(ap.read_live(h)[PR_LCD] == live0[PR_LCD], "Load: the screen level not back")

        # Save current here: the confirm, a hold, then a click.
        g.click(h, "Profile 1's page", SCR(PSLOT0), 1)
        g.turn(h, 1, "to Save current here", SCR(PSLOT0), 2)
        g.click(h, "Save's confirm", SCR(PSAVE), 0)
        g.hold(h, "cancelled", SCR(PSLOT0), 2)
        g.click(h, "Save's confirm again", SCR(PSAVE), 0)
        g.click(h, "saved", SCR(PSLOT0), 2)

        # Delete: the confirm and a click, back to Profiles; the slot empty.
        g.turn(h, 1, "to Delete", SCR(PSLOT0), 3)
        g.click(h, "Delete's confirm", SCR(PDEL), 0)
        g.click(h, "deleted", SCR(PROFILES), 1)
        recs, _ = slots(h)
        g.check(not any(recs), "Delete: a slot still saved")

        # A host restore's Begin pops a slot's page; its abort, 5 s on, leaves
        # the block unformatted, which the first save formats again.
        g.click(h, "save Profile 1 again", SCR(PROFILES), 1)
        g.click(h, "its page", SCR(PSLOT0), 1)
        tok = random.randint(1, 255)
        r = ap.xfer(h, 1, [0, tok], echo=(5,))
        g.check(r[6] == 0, f"Begin refused ({r[6]})")
        s, _ = g.settle(h, "the restore's pop")
        g.check(s["screen"] == SCR(TOP) and s["cursor"] == R_PROF,
                f"the restore: screen {s['screen']} cursor {s['cursor']}, not the top level on Profiles")
        time.sleep(5.6)   # the abort
        g.click(h, "Profiles after the abort", SCR(PROFILES), 1)
        recs, _ = slots(h)
        g.check(not any(recs), "after the abort: a slot reads saved")
        g.hold(h, "the top level", SCR(TOP), R_PROF)
        g.step(h, 11, b"", "close", owner="dash")
        time.sleep(1.5)
        meas = decode_meas(xfer(h, 10, bytes([0])))
        g.check(not meas["aliased"], "a pass of 340 ms or more in the interval")
        long = [x for x in g.slow if x["pass_ms"] >= 25]
        cons = [x for x in long if "save" in x["step"] or "deleted" in x["step"] or "settle" in x["step"]]
        for x in long:
            if x not in cons:
                g.check(False, f"a pass of {x['pass_ms']} ms at {x['step']}")
        if cons:
            print(f"  {len(cons)} pass(es) >= 25 ms at a write (a consolidation's, BACKLOG): {cons}", flush=True)
        to_dash(h)
    finally:
        try:
            if live0 is not None:
                ap.apply_live(h, live0)   # the live settings as they were
        except SystemExit as e:
            print("restoring the live settings:", e)
        h.close()
        with open(a.out, "w") as f:
            json.dump({"steps": g.log, "meas": meas, "fails": g.fails, "slow": g.slow}, f, indent=1)
    ms = [e["ms"] for e in g.log]
    print(f"{len(g.log)} steps, the slowest settle {max(ms) if ms else 0} ms; "
          f"longest pass {meas.get('pass_max_us')} us, over 15 ms {meas.get('over15')}")
    print("PASS" if not g.fails else f"FAILED: {len(g.fails)}")
    return 1 if g.fails else 0


if __name__ == "__main__":
    sys.exit(main())
