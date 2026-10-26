#!/usr/bin/env python3
"""P1a on the board: every screen of the real menu, driven by op 27 (sub 11
opens it; subs 1-3 turn, click and hold), on a dev build. The design's board
gate (plans/CONFIG-MENU-P1-DESIGN.md, "Tests (P1a)").

    venv-win/Scripts/python.exe scripts/menu_p1a_board.py [--out F] < /dev/null

1. Outside the measured interval (it moves the health generation): Reset
   counters' two pages, and a cancel.
2. One measured interval (sub 10 armed): open; moves down and up with wraps;
   Power and Clock committed to another value and back (the board keeps its
   own settings at the end); Help's four topics paged; About; Health and
   Camera handed off and back; a choice cancelled; the hint; the close.
3. Every step: the expected screen id (16 + the node) and cursor, pixels_done
   within 1,000 ms, invariant_fail 0. The interval: no pass over 17 ms (JD's
   (b), 10-24: menu painting passes of ~16-17 ms accepted; those over 15 are
   counted and printed, not failed), none
   of 340 ms (aliased).
Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from ak820health import read_acct  # noqa: E402
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s0_accept import dash_done, to_dash  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

# menu.c's nodes: sub 5 byte 14 is 16 + the node showing.
TOP, POWER, CLOCK, DIAG, HELP, ABOUT, EXIT = 1, 2, 3, 4, 5, 6, 7
RESET, TOPIC0 = 10, 11
LIGHT, SCREEN, EFFECT, BRIGHT, HUE = 24, 25, 26, 27, 28   # P1b's nodes
IND, CONN, LOCKS, CHGL = 35, 36, 37, 38                   # P2a's
CONNINFO, PAIRING = 39, 44                                 # P3's (Pair a device: the current slot's)
BATT = 45                                                  # P4's Battery
PROFILES, PSLOT0 = 50, 51                                  # P5b's Profiles page and slot pages
# P3's link byte (menu_env.h's ENV_LINK_*: transport bits 1-0, slot 3-2,
# state 6-4) and the pairing facts, for op 27 sub 16's stand-in.
L_USB, L_BT = 0, 1
S_IDLE, S_LINKING, S_PAIRING, S_CONNECTED, S_REJECTED = range(5)
PF_WAITING, PF_RETRYING, PF_CONFIRMED, PF_SEL_LOST = 1, 2, 4, 8
P_START, P_OPEN, P_DONE, P_ENDED, P_FAILED, P_UNSURE = range(6)
LINK = lambda slot, st: L_BT | slot << 2 | st << 4  # noqa: E731
# The top level since P5b (JD, 10-25): Lighting, Screen, Connection, Power,
# Indicators, Clock, Battery, Profiles; Bootloader, Diagnostics, Help, About,
# Exit on page two.
R_CONN, R_POWER, R_IND, R_CLOCK, R_BATT, R_PROF, R_BOOT, R_DIAG, R_HELP, R_ABOUT, R_EXIT = 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
SCR = lambda n: 16 + n  # noqa: E731
SETTLE_S = 1.0

log, fails = [], []
slow, seen = [], set()   # HC_ACCT's passes of >= 15 ms, with their scopes
meas_on = {"on": False, "over": 0}   # in the measured interval: each step's over-15 count


def check(ok, what):
    if not ok:
        fails.append(what)
        print("FAIL", what, flush=True)


def settle(h, what):
    t0 = time.perf_counter()
    while True:
        s = read_state(h)
        if s["owner"] == "dash" and s["session"] == "none" and dash_done(s):   # a close: the restore done
            return s, (time.perf_counter() - t0) * 1000
        if s["pixels_done"] and s["owner"] in ("menu", "debug"):
            return s, (time.perf_counter() - t0) * 1000
        if s["owner"] == "debug" and s["debug_done"]:
            return s, (time.perf_counter() - t0) * 1000
        if time.perf_counter() - t0 > 3.0:
            check(False, f"{what}: not settled in 3 s ({s['owner']}, screen {s['screen']})")
            return s, 3000.0
        time.sleep(0.1)   # the gate's rate (POLL_S): this script's own traffic is load too


def step(h, sub, args, what, screen=None, cursor=None, owner="menu"):
    st, seq = mutate(h, sub, args)
    check(st == 0, f"{what}: op 27 sub {sub} refused ({st})")
    state, s = wait(h, seq, poll=0.1)
    check(state == "done", f"{what}: {state}")
    s, ms = settle(h, what)
    e = {"what": what, "ms": round(ms), "owner": s["owner"], "screen": s["screen"], "cursor": s["cursor"],
         "inv": s["invariant_fail"]}
    note_meas(h, what, e)
    log.append(e)
    print(json.dumps(e), flush=True)
    check(s["owner"] == owner, f"{what}: owner {s['owner']}, not {owner}")
    if screen is not None:
        check(s["screen"] == screen, f"{what}: screen {s['screen']}, not {screen}")
    if cursor is not None:
        check(s["cursor"] == cursor, f"{what}: cursor {s['cursor']}, not {cursor}")
    check(ms <= SETTLE_S * 1000 or sub == 3 or owner == "dash", f"{what}: settled in {ms:.0f} ms")
    check(s["invariant_fail"] & ~0x20 == 0, f"{what}: invariant_fail {s['invariant_fail']:#x}")
    return s


def dwell(h, what, secs):
    """Stay on the screen, touching nothing, then the interval's passes (the
    Clock's live examples tick meanwhile)."""
    time.sleep(secs)
    s, _ = settle(h, what)
    e = {"what": what, "ms": 0, "owner": s["owner"], "screen": s["screen"], "cursor": s["cursor"],
         "inv": s["invariant_fail"]}
    note_meas(h, what, e)
    log.append(e)
    print(json.dumps(e), flush=True)
    check(s["invariant_fail"] & ~0x20 == 0, f"{what}: invariant_fail {s['invariant_fail']:#x}")
    return s


def note_meas(h, what, e):
    if meas_on["on"]:
        m = decode_meas(xfer(h, 10, bytes([0])))
        e["over15"], e["pass_max_us"] = m["over15"], m["pass_max_us"]
        if m["over15"] != meas_on["over"]:
            print(f"  ^ {m['over15'] - meas_on['over']} pass(es) over 15 ms in this step "
                  f"(the interval's longest {m['pass_max_us']} us)", flush=True)
            meas_on["over"] = m["over15"]
            for r in read_acct(h)["ring"]:
                if r["pass_ms"] >= 15 and r["uptime_ms"] not in seen:
                    seen.add(r["uptime_ms"])
                    top = {k: v for k, v in r["scopes_ms"].items() if v}
                    slow.append({"step": what, "pass_ms": r["pass_ms"], "scopes": top})
                    print(f"    {r['pass_ms']} ms: {top}", flush=True)


def turn(h, n, what, *a, **k):
    return step(h, 1, bytes([n & 0xFF]), what, *a, **k)


def click(h, what, *a, **k):
    return step(h, 2, b"", what, *a, **k)


def hold(h, what, *a, **k):
    return step(h, 3, b"", what, *a, **k)


def ind_editors(h, ind_state):
    """P2a: Indicators' two editors, each cancelled: sub 14 says the edit
    closed, the level restored and the preview's force gone."""
    click(h, "Indicators", SCR(IND), 1)
    _, locks0, chg0, _ = ind_state()
    click(h, "Lock lights", SCR(LOCKS))
    check(ind_state()[3] == 1, f"Lock lights: the force bits {ind_state()[3]}, not 1")
    turn(h, 1, "lock lights up", SCR(LOCKS))
    turn(h, 3, "lock lights up, fast", SCR(LOCKS))
    check(ind_state()[1] == min(100, locks0 + 25), f"Lock lights: {ind_state()[1]}, not {locks0} + 25")
    hold(h, "Lock lights cancelled", SCR(IND), 1)
    check(ind_state() == (0, locks0, chg0, 0), f"Lock lights: after the cancel {ind_state()}")
    turn(h, 1, "to Charging light", SCR(IND), 2)
    click(h, "Charging light", SCR(CHGL))
    check(ind_state()[3] == 2, f"Charging light: the force bits {ind_state()[3]}, not 2")
    turn(h, 2, "charging light up, fast", SCR(CHGL))
    hold(h, "Charging light cancelled", SCR(IND), 2)
    check(ind_state() == (0, locks0, chg0, 0), f"Charging light: after the cancel {ind_state()}")
    hold(h, "Indicators back", SCR(TOP), R_IND)


def standin(h, link, pf=0):
    """Op 27 sub 16: the menu's link and pairing facts (0xFF: the live ones).
    While it's set the menu's calls go nowhere."""
    r = xfer(h, 16, bytes([link, pf]))
    check(r[5] == 0, f"op 27 sub 16 ({link:#x}, {pf}) refused ({r[5]})")


def connection(h):
    """P3, all on op 27 sub 16's stand-in, whatever the slider says (its
    calls go nowhere, so a real link is never touched; codex: with the
    slider on BT the real screens' clicks would re-select): the page off BT,
    the slot list in each state, a click on each slot, Pair a device (the
    current slot's), the Pairing page in each phase, a stop, and the screens
    following the slider. The stand-in is cleared at the end, and by
    main()'s finally."""
    standin(h, L_USB)
    settle(h, "the stand-in off BT")
    click(h, "Connection, off BT", SCR(CONNINFO), 0)
    click(h, "Connection back", SCR(TOP), R_CONN)
    standin(h, LINK(1, S_CONNECTED))
    click(h, "Connection, on BT 2", SCR(CONN), 2)
    for st in (S_IDLE, S_LINKING, S_PAIRING, S_REJECTED, S_CONNECTED):
        standin(h, LINK(1, st))
        settle(h, f"BT 2's word, state {st}")
    click(h, "BT 2 again: nothing", SCR(CONN), 2)
    turn(h, 1, "to BT 3", SCR(CONN), 3)
    click(h, "BT 3: a select (not sent: the stand-in)", SCR(CONN), 3)
    turn(h, -2, "to BT 1", SCR(CONN), 1)
    click(h, "BT 1", SCR(CONN), 1)
    turn(h, 3, "to Pair a device", SCR(CONN), 4)
    standin(h, LINK(1, S_CONNECTED), PF_WAITING)   # the stand-in's slot (BT 2) is the current one
    click(h, "Pair a device (BT 2)", SCR(PAIRING), 1 << 4 | P_START)
    for link, pf, ph, what in (
            (LINK(1, S_PAIRING), PF_RETRYING, P_START, "resending"),
            (LINK(1, S_PAIRING), PF_CONFIRMED, P_OPEN, "advertising"),
            (LINK(1, S_CONNECTED), PF_CONFIRMED, P_DONE, "connected"),
            (LINK(1, S_REJECTED), PF_CONFIRMED, P_ENDED, "ended"),
            (LINK(1, S_LINKING), PF_SEL_LOST, P_FAILED, "failed"),
            (LINK(1, S_PAIRING), 0, P_UNSURE, "unsure"),
            (LINK(1, S_PAIRING), PF_CONFIRMED, P_OPEN, "advertising again")):
        standin(h, link, pf)
        s, _ = settle(h, f"Pairing: {what}")
        check(s["screen"] == SCR(PAIRING) and s["cursor"] == (1 << 4 | ph),
              f"Pairing {what}: screen {s['screen']} cursor {s['cursor']:#x}, not {1 << 4 | ph:#x}")
    click(h, "stop it", SCR(CONN), 2)
    turn(h, 2, "to Pair a device again", SCR(CONN), 4)
    click(h, "Pair a device again", SCR(PAIRING))
    standin(h, L_USB)
    s, _ = settle(h, "the slider to the cable, under the Pairing page")
    check(s["screen"] == SCR(TOP) and s["cursor"] == R_CONN, f"off BT: screen {s['screen']} cursor {s['cursor']}")
    standin(h, 0xFF)
    settle(h, "the stand-in cleared")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_p1a_board.json")
    ap.add_argument("--no-ind", action="store_true",
                    help="skip the indicator editors (they clear the bench's force bits): the timing run with "
                         "the indicators forced by op 27 sub 15 (codex, P2a's code review)")
    ap.add_argument("--no-conn", action="store_true", help="skip P3's Connection screens (and op 27 sub 16)")
    a = ap.parse_args()
    h = open_device()
    meas = {}
    try:
        to_dash(h)
        # 1. Reset counters, outside the interval.
        step(h, 11, b"", "open (reset pass)", SCR(TOP), 0)
        turn(h, R_DIAG, "to Diagnostics", SCR(TOP), R_DIAG)
        click(h, "Diagnostics", SCR(DIAG), 1)
        turn(h, 2, "to Reset counters", SCR(DIAG), 3)
        click(h, "Reset counters", SCR(RESET), 0)
        click(h, "reset", SCR(RESET), 1)
        click(h, "back to Diagnostics", SCR(DIAG), 3)
        click(h, "Reset counters again", SCR(RESET), 0)
        hold(h, "cancel it", SCR(DIAG), 3)
        step(h, 11, b"", "close (reset pass)", owner="dash")
        time.sleep(1.5)   # the restore

        # 2. The measured interval.
        read_acct(h, "on")
        read_acct(h, "reset")
        xfer(h, 10, bytes([1]))
        meas_on["on"] = True
        step(h, 11, b"", "open", SCR(TOP), 0)
        for i in range(1, R_EXIT + 1):
            turn(h, 1, f"down {i}", SCR(TOP), i)
        turn(h, 1, "wrap down", SCR(TOP), 0)
        turn(h, -1, "wrap up", SCR(TOP), R_EXIT)
        turn(h, 1, "back to the top", SCR(TOP), 0)

        # Power: commit the next mode, then the original again.
        turn(h, R_POWER, "to Power", SCR(TOP), R_POWER)
        s = click(h, "Power", SCR(POWER))
        orig_p = s["cursor"]
        nxt = 1 + (orig_p % 4)
        turn(h, nxt - orig_p, "to another mode", SCR(POWER), nxt)
        click(h, "commit it", SCR(TOP), R_POWER)
        click(h, "Power again", SCR(POWER), nxt)
        turn(h, orig_p - nxt, "to the original", SCR(POWER), orig_p)
        click(h, "commit the original", SCR(TOP), R_POWER)

        # Clock: the same over its six rows (10-25), a dwell while its examples
        # tick, then a cancel.
        turn(h, R_CLOCK - R_POWER, "to Clock", SCR(TOP), R_CLOCK)
        s = click(h, "Clock", SCR(CLOCK))
        orig_c = s["cursor"]
        dwell(h, "Clock ticking, 5 s", 5.0)
        nxt = 1 + (orig_c % 6)
        turn(h, nxt - orig_c, "to another clock", SCR(CLOCK), nxt)
        click(h, "commit it", SCR(TOP), R_CLOCK)
        click(h, "Clock again", SCR(CLOCK), nxt)
        turn(h, orig_c - nxt, "to the original", SCR(CLOCK), orig_c)
        click(h, "commit the original", SCR(TOP), R_CLOCK)
        click(h, "Clock to cancel", SCR(CLOCK), orig_c)
        turn(h, 1, "move", SCR(CLOCK))
        hold(h, "cancelled", SCR(TOP), R_CLOCK)

        # Battery (P4): the other readout, then the original again; a dwell on
        # its live preview.
        turn(h, R_BATT - R_CLOCK, "to Battery", SCR(TOP), R_BATT)
        s = click(h, "Battery", SCR(BATT))
        orig_b = s["cursor"]
        dwell(h, "Battery's preview, 3 s", 3.0)
        nxt = 3 - orig_b
        turn(h, nxt - orig_b, "to the other readout", SCR(BATT), nxt)
        click(h, "commit it", SCR(TOP), R_BATT)
        click(h, "Battery again", SCR(BATT), nxt)
        turn(h, orig_b - nxt, "to the original", SCR(BATT), orig_b)
        click(h, "commit the original", SCR(TOP), R_BATT)

        # Profiles (P5b): the page and each row, nothing written; a dwell on
        # the top level, whose row compares the live settings each scan.
        turn(h, R_PROF - R_BATT, "to Profiles", SCR(TOP), R_PROF)
        dwell(h, "Profiles' row, its compare, 3 s", 3.0)
        s = click(h, "Profiles", SCR(PROFILES))
        c0 = s["cursor"]
        for k in range(1, 6):
            turn(h, 1, f"Profiles row {(c0 + k) % 5}", SCR(PROFILES), (c0 + k) % 5)
        hold(h, "Profiles back", SCR(TOP), R_PROF)

        # Help: each topic, paged to its end and back.
        turn(h, R_HELP - R_PROF, "to Help", SCR(TOP), R_HELP)
        click(h, "Help", SCR(HELP), 1)
        for t in range(4):
            if t:
                turn(h, 1, f"to topic {t}", SCR(HELP), 1 + t)
            click(h, f"topic {t}", SCR(TOPIC0 + t), 0)
            turn(h, 1, f"topic {t} page 2", SCR(TOPIC0 + t))
            turn(h, -1, f"topic {t} page 1", SCR(TOPIC0 + t), 0)
            click(h, f"topic {t} back", SCR(HELP), 1 + t)
        hold(h, "Help back", SCR(TOP), R_HELP)

        # About.
        turn(h, 1, "to About", SCR(TOP), R_ABOUT)
        click(h, "About", SCR(ABOUT), 0)
        click(h, "About back", SCR(TOP), R_ABOUT)

        # Diagnostics: Health and Camera, handed off and back.
        turn(h, R_DIAG - R_ABOUT, "to Diagnostics", SCR(TOP), R_DIAG)
        click(h, "Diagnostics", SCR(DIAG), 1)
        click(h, "Health page", owner="debug")
        click(h, "back from Health", SCR(DIAG), 1, owner="menu")
        turn(h, 1, "to Camera", SCR(DIAG), 2)
        click(h, "Camera page", owner="debug")
        click(h, "back from Camera", SCR(DIAG), 2, owner="menu")
        hold(h, "Diagnostics back", SCR(TOP), R_DIAG)

        # P1b: Lighting's list, a choice and the editors, each cancelled (the
        # board keeps its settings); sub 14 says the edit closed, restored.
        def edit_state():
            r = xfer(h, 14)
            return r[6], r[8], r[9]

        turn(h, -R_DIAG, "to Lighting", SCR(TOP), 0)
        click(h, "Lighting", SCR(LIGHT), 1)
        click(h, "Effect", SCR(EFFECT))
        _, _, saved = edit_state()
        turn(h, 1, "preview the next effect", SCR(EFFECT))
        hold(h, "Effect cancelled", SCR(LIGHT), 1)
        check(edit_state()[0] == 0, "Effect: the edit still open")
        turn(h, 1, "to Brightness", SCR(LIGHT), 2)
        click(h, "Brightness", SCR(BRIGHT))
        _, v0, _ = edit_state()
        turn(h, 1, "brightness up", SCR(BRIGHT))
        turn(h, -2, "brightness down", SCR(BRIGHT))
        hold(h, "Brightness cancelled", SCR(LIGHT), 2)
        check(edit_state()[0] == 0, "Brightness: the edit still open")
        click(h, "Brightness again", SCR(BRIGHT))
        check(edit_state()[1] == v0, f"Brightness: {edit_state()[1]} after the cancel, not {v0}")
        hold(h, "Brightness cancelled again", SCR(LIGHT), 2)
        turn(h, 1, "to Hue", SCR(LIGHT), 3)
        click(h, "Hue", SCR(HUE))
        for i in range(4):
            turn(h, 1, f"hue up {i + 1}", SCR(HUE))
        turn(h, -6, "hue down, fast", SCR(HUE))
        hold(h, "Hue cancelled", SCR(LIGHT), 3)
        hold(h, "Lighting back", SCR(TOP), 0)
        turn(h, 1, "to Screen", SCR(TOP), 1)
        click(h, "Screen", SCR(SCREEN))
        turn(h, 1, "screen up", SCR(SCREEN))
        hold(h, "Screen cancelled", SCR(TOP), 1)
        check(edit_state()[0] == 0, "Screen: the edit still open")

        # P3: Connection, every screen (the stand-in for BT); P2a: Indicators'
        # two editors, each cancelled; sub 14 says the edit closed, the level
        # restored and the preview's force gone.
        def ind_state():
            r = xfer(h, 14)
            return r[6], r[12], r[13], r[14]   # open, the lock lights, the charging light, the force bits

        turn(h, R_CONN - 1, "to Connection", SCR(TOP), R_CONN)
        if not a.no_conn:
            connection(h)
        turn(h, R_IND - R_CONN, "to Indicators", SCR(TOP), R_IND)
        if not a.no_ind:
            ind_editors(h, ind_state)

        # The hint: 5 s idle on the top level (the session stays open: 24 s).
        time.sleep(5.0)
        s, _ = settle(h, "after the hint")
        check(s["session"] == "open", "the session closed during the hint")

        step(h, 11, b"", "close", owner="dash")
        time.sleep(1.5)
        meas = decode_meas(xfer(h, 10, bytes([0])))
        check(not meas["aliased"], "a pass of 340 ms or more in the interval")
        check(meas["pass_max_us"] <= 17000, f"the longest pass {meas['pass_max_us']} us")   # JD's (b)
        to_dash(h)
    finally:
        try:
            xfer(h, 16, bytes([0xFF, 0]))   # never leave the stand-in set
        except Exception as e:   # noqa: BLE001
            print("clearing the stand-in:", e)
        h.close()
        with open(a.out, "w") as f:
            json.dump({"steps": log, "meas": meas, "fails": fails, "slow": slow}, f, indent=1)
    ms = [e["ms"] for e in log]
    print(f"{len(log)} steps, the slowest settle {max(ms) if ms else 0} ms; "
          f"longest pass {meas.get('pass_max_us')} us, over 15 ms {meas.get('over15')}, piece {meas.get('piece_us')} us")
    print("PASS" if not fails else f"FAILED: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
