#!/usr/bin/env python3
"""P5b and P5d on the board: the settings profiles' pages through the real
menu, driven by op 27, with their writes, on a dev build; every pass timed
(plans/SETTINGS-PROFILES-PLAN.md, "Tests", the board's).

    venv-win/Scripts/python.exe scripts/menu_p5b_board.py [--out F] < /dev/null

It refuses unless every slot is empty (the keyboard on gremlin's: nothing of
JD's to lose), and leaves them empty and the live settings as they were.

1. One measured interval (op 27 sub 10 armed): open; to Profiles; Save new
   (P5d: the list shows the saved slots and Save new); its page; the top
   level's `*` after a change made over HC_PROFILES' live apply; Load; Save
   current here's confirm held, then clicked; Delete's confirm clicked; all
   eight saved by Save new, the list paged, a dwell on it and on the top
   level, Save new's "Full" clicked; a host restore's Begin popping a slot's
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
TOP, PROFILES, PSLOT, PSAVE, PDEL = 1, 50, 51, 54, 55   # P5d: one slot node; its cursor is the slot << 4 | the row
R_PROF, R_HELP = g.R_PROF, g.R_HELP
PR_LCD = 8   # the record's screen level (profiles.h)
ME_PROFILE = 10   # menu_edit.h: P5e's preview edit
# P5e: each of the eight saved from its own look: an effect id (rgb_effects.c)
# and a screen level, so every preview switches both.
LOOKS = [(1, 20), (4, 90), (12, 40), (9, 100), (5, 30), (11, 70), (2, 50), (10, 60)]


def live_with(live, effect, lcd):
    r = bytearray(live)
    r[3], r[PR_LCD], r[2] = effect, lcd, 1
    r[26] = ap.crc8(r[1:26])
    return bytes(r)


def edit(h):
    """op 27 sub 14: the menu's edit, (open, field); never cancels one,
    as HC_PROFILES' and VIA's lighting reads do."""
    r = xfer(h, 14)
    return r[6], r[7]


def slots(h):
    """Each slot's record, or None, from the block as HC_PROFILES reads it."""
    gp = ap.geometry(h)
    b = ap.read_block(h, gp)
    if b[0] != gp.magic:
        return [None] * gp.slots, 0xFF
    out = []
    for s in range(gp.slots):
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
        g.click(h, "Save new: Profile 1", SCR(PROFILES), 1)
        recs, _ = slots(h)
        g.check(len(recs) == 8 and recs[0] is not None and not any(recs[1:]), "the save: slot 1 isn't the one saved")
        g.dwell(h, "the save's settle, the active slot's deferred write", 6.0)
        _, active = slots(h)
        g.check(active == 0, f"the active byte {active}, not 0 after the settle")
        g.click(h, "Profile 1's page", SCR(PSLOT), 0x01)
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
        g.click(h, "Profile 1's page", SCR(PSLOT), 0x01)
        g.click(h, "Load", SCR(PROFILES), 1)
        g.check(ap.read_live(h)[PR_LCD] == live0[PR_LCD], "Load: the screen level not back")

        # Save current here: the confirm, a hold, then a click.
        g.click(h, "Profile 1's page", SCR(PSLOT), 0x01)
        g.turn(h, 1, "to Save current here", SCR(PSLOT), 0x02)
        g.click(h, "Save's confirm", SCR(PSAVE), 0)
        g.hold(h, "cancelled", SCR(PSLOT), 0x02)
        g.click(h, "Save's confirm again", SCR(PSAVE), 0)
        g.click(h, "saved", SCR(PSLOT), 0x02)

        # Delete: the confirm and a click, back to Profiles, the cursor's
        # row now Save new; the slot empty.
        g.turn(h, 1, "to Delete", SCR(PSLOT), 0x03)
        g.click(h, "Delete's confirm", SCR(PDEL), 0)
        g.click(h, "deleted", SCR(PROFILES), 1)
        recs, _ = slots(h)
        g.check(not any(recs), "Delete: a slot still saved")

        # P5d: all eight by Save new, each on its new row, each from other
        # live settings (P5e: an effect and a screen level of its own, set
        # over HC_PROFILES' live apply, so each preview switches both); the
        # list (ten rows, two pages) turned through; a dwell on it and on the
        # top level, the snapshot reading eight records every 128 ms; Save
        # new's "Full" clicked, nothing written.
        for k in range(1, 9):
            ap.apply_live(h, live_with(live0, *LOOKS[k - 1]))
            g.click(h, f"Save new: Profile {k}", SCR(PROFILES), k)
            if k < 8:
                g.turn(h, 1, "to Save new", SCR(PROFILES), k + 1)
        recs, _ = slots(h)
        g.check(all(recs), "eight: a slot not saved")
        g.dwell(h, "the eight's settle", 6.0)
        g.turn(h, 1, "to Save new, Full", SCR(PROFILES), 9)
        before = slots(h)
        g.click(h, "Full: nothing written", SCR(PROFILES), 9)
        g.check(slots(h) == before, "Full: the block changed")
        g.check(edit(h) == (0, 0), f"on Save new: an edit open {edit(h)}")
        # P5e: each row rested on 1.2 s: a profile's preview open (ME_PROFILE)
        # from 0.6 s, Back's and Save new's none; the passes as the effects
        # and the screen levels switch.
        for k in range(10):
            g.turn(h, 1, f"the list, row {k}", SCR(PROFILES), k)
            g.dwell(h, f"a rest on row {k}, 1.2 s", 1.2)
            want = (1, ME_PROFILE) if 1 <= k <= 8 else (0, 0)
            g.check(edit(h) == want, f"row {k}: the edit {edit(h)}, not {want}")
        g.turn(h, -2, "to Profile 7, a fast turn", SCR(PROFILES), 7)
        g.dwell(h, "the list of eight, Profile 7 previewed, 3 s", 3.0)
        g.check(edit(h) == (1, ME_PROFILE), "Profile 7: no preview")
        # Its page keeps the preview; Save's confirm shows the live settings;
        # back, the profile's again; Back to the list, then out: none.
        g.click(h, "Profile 7's page", SCR(PSLOT), 0x61)
        g.check(edit(h) == (1, ME_PROFILE), "Profile 7's page: no preview")
        g.turn(h, 1, "to Save current here", SCR(PSLOT), 0x62)
        g.click(h, "Save's confirm, the live settings", SCR(PSAVE), 6)
        g.check(edit(h) == (0, 0), "Save's confirm: a preview open")
        g.hold(h, "cancelled, Profile 7's again", SCR(PSLOT), 0x62)
        g.check(edit(h) == (1, ME_PROFILE), "back from the confirm: no preview")
        g.hold(h, "the list", SCR(PROFILES), 7)
        g.hold(h, "the top level", SCR(TOP), R_PROF)
        g.check(edit(h) == (0, 0), "out of Profiles: a preview open")
        g.check(ap.read_live(h)[3] == LOOKS[7][0], "out of Profiles: the live effect isn't Profile 8's")
        g.dwell(h, "the top level, Profile 8 active, 3 s", 3.0)
        # Load over a preview: Profile 3 becomes the live settings, saved.
        g.click(h, "Profiles", SCR(PROFILES), 8)
        g.turn(h, -5, "to Profile 3", SCR(PROFILES), 3)
        g.dwell(h, "Profile 3 previewed", 1.0)
        g.click(h, "Profile 3's page", SCR(PSLOT), 0x21)
        g.click(h, "Load", SCR(PROFILES), 3)
        g.check(edit(h) == (0, 0), "Load: the preview's edit still open")
        lv = ap.read_live(h)
        g.check(lv[3] == LOOKS[2][0] and lv[PR_LCD] == LOOKS[2][1], f"Load: live effect {lv[3]} screen {lv[PR_LCD]}")
        g.hold(h, "the top level", SCR(TOP), R_PROF)
        for s in range(8):
            g.check(ap.xfer(h, 0x41, [s])[5] == 0, f"the dev delete of slot {s} refused")
        g.settle(h, "the deletes' repaint")
        g.click(h, "Profiles, nothing saved", SCR(PROFILES), 1)

        # A host restore's Begin pops a slot's page; its abort, 5 s on, leaves
        # the block unformatted, which the first save formats again.
        g.click(h, "Save new: Profile 1 again", SCR(PROFILES), 1)
        g.click(h, "its page", SCR(PSLOT), 0x01)
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
        cons = [x for x in long if any(w in x["step"].lower() for w in ("save", "deleted", "delete of", "settle"))]
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
