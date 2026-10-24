#!/usr/bin/env python3
"""The configuration menu's S0: the board's acceptance cases that need no
hands (plans/CONFIG-MENU-S0-BOARD-TESTS.md: A1, A3, A5, A6, A8). Dev builds.

    venv-win/Scripts/python.exe scripts/menu_s0_accept.py [a1 a3 a5 a6 a8] [--out F] < /dev/null

Each case prints PASS, FAIL or INCONCLUSIVE with its evidence, and the run
writes them all to a JSON file. Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import OK, open_device, read_state, wait, mutate, xfer  # noqa: E402

SET_VALUE, CH, HC = 0x07, 0x13, 0x76
UNHANDLED = 0xFF


def devhook(h, op, args=b""):
    """An HC_DEVHOOK report other than op 27; the reply matched by op."""
    h.write(bytes([0, SET_VALUE, CH, HC, op]) + args + bytes(27 - len(args)))
    end = time.monotonic() + 3.0   # a deadline, not a count: other handles' replies land here too
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == op:
            return bytes(r)
    raise RuntimeError(f"op {op}: no reply")


def op1(h):
    devhook(h, 1)


def arm_record(h, arg, delay=1):
    """Op 14 sub 4: arg 1 arms (delay s), 2 disarms, 0 reads. The record:
    version, state, reason, then the blockers it sampled (u16)."""
    args = bytes([4, arg, delay]) if arg == 1 else bytes([4, arg])
    r = devhook(h, 14, args)
    if r[0] != SET_VALUE or r[4] != 4:
        raise RuntimeError(f"op 14 sub 4: unhandled ({r[0]:#x})")
    return {"version": r[5], "state": r[6], "reason": r[7], "blocked": r[8] | (r[9] << 8)}


def until(h, pred, timeout=10.0, poll=0.02):
    end = time.monotonic() + timeout
    while True:
        s = read_state(h)
        if pred(s):
            return True, s
        if time.monotonic() > end:
            return False, s
        time.sleep(poll)


def dash_done(s):
    return s["owner"] == "dash" and s["session"] == "none" and s["phase"] == "done"


def to_dash(h):
    """Close whatever is open, and wait for the dashboard restored."""
    s = read_state(h)
    if s["session"] != "none":
        st, seq = mutate(h, 4)
        wait(h, seq)
    elif s["owner"] == "debug":
        while read_state(h)["owner"] == "debug":
            op1(h)
            time.sleep(0.05)
    return until(h, dash_done)


def a1(h):
    r = xfer_raw(h, 31)   # S1's C10 took sub 10; 31 is unknown
    ok_unknown = r[0] == UNHANDLED
    s5 = xfer(h, 5)
    ok_framing = s5[0] == SET_VALUE and s5[5] == OK
    return ("PASS" if ok_unknown and ok_framing else "FAIL",
            {"unknown_sub_byte0": r[0], "sub5_byte0": s5[0], "sub5_status": s5[5],
             "short_report": "source inspection: raw_hid_task() always passes 32 bytes"})


def xfer_raw(h, sub):
    """An op 27 report whose reply may be unhandled (byte 0 0xFF)."""
    h.write(bytes([0, SET_VALUE, CH, HC, 27, sub]) + bytes(26))
    end = time.monotonic() + 3.0   # a deadline, not a count: other handles' replies land here too
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == 27 and r[4] == sub:
            return bytes(r)
    raise RuntimeError("no reply")


def a3(h):
    ok, s = to_dash(h)
    if not ok:
        return "INCONCLUSIVE", {"why": "the dashboard isn't DONE", "state": s}
    g0 = s["restore_gen"]
    r = xfer(h, 9)
    seq = r[6]
    before, after = (r[7], r[8]), (r[9], r[10])
    s = read_state(h)
    if s["last_seq"] != seq or s["last_state"] != "done":
        return "INCONCLUSIVE", {"why": f"the probe was {s['last_state']}", "state": s}
    owner = s["owner"]
    op1(h)
    op1(h)   # Health to Camera, Camera to the dashboard
    ok, s2 = until(h, dash_done)
    good = before[0] > 0 and before[1] > 0 and after == (0, 0) and owner == "debug" and ok \
        and s2["restore_gen"] == g0 + 1 and s2["invariant_fail"] == 0
    return ("PASS" if good else "FAIL",
            {"gq_lq_before": before, "gq_lq_after": after, "owner_after_probe": owner,
             "restored": ok, "gen": [g0, s2["restore_gen"]], "invariant_fail": s2["invariant_fail"]})


def a5(h):
    to_dash(h)
    st, seq = mutate(h, 4)                     # open the fixture
    wait(h, seq)
    arm_record(h, 1, delay=1)
    time.sleep(2.5)                            # past the delay: sampling every pass
    rec_open = arm_record(h, 0)
    s_open = read_state(h)
    arm_record(h, 2)                           # cancel
    st, seq = mutate(h, 4)                     # close
    wait(h, seq)
    until(h, dash_done)
    arm_record(h, 1, delay=1)
    time.sleep(2.5)
    rec_closed = arm_record(h, 0)
    arm_record(h, 2)
    menu_open = bool(rec_open["blocked"] & 0x4000)
    menu_closed = bool(rec_closed["blocked"] & 0x4000)
    good = rec_open["state"] == 1 and s_open["session"] == "open" and menu_open and \
        rec_closed["state"] == 1 and not menu_closed
    return ("PASS" if good else "FAIL",
            {"open": {"record": rec_open, "session": s_open["session"]},
             "closed": {"record": rec_closed}, "dsb_menu": [menu_open, menu_closed]})


def a6(h, tries=20):
    trials = []
    for i in range(tries):
        to_dash(h)
        st, seq = mutate(h, 4)                 # open
        wait(h, seq)
        until(h, lambda s: s["pixels_done"], timeout=5)
        # sub 8 and op 1 in consecutive reports, the replies read after.
        h.write(bytes([0, SET_VALUE, CH, HC, 27, 8]) + bytes(26))
        h.write(bytes([0, SET_VALUE, CH, HC, 1]) + bytes(27))
        seq8 = None
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            r = h.read(32, 250)
            if r and r[1] == CH and r[2] == HC and r[3] == 27 and r[4] == 8:
                seq8 = r[6]
            if r and r[1] == CH and r[2] == HC and r[3] == 1:
                break
        state, s = wait(h, seq8) if seq8 else ("no reply", read_state(h))
        trials.append(state)
        if state == "superseded":
            ok, s2 = until(h, lambda s: s["owner"] == "debug", timeout=3)
            return ("PASS" if s2["invariant_fail"] == 0 else "FAIL",
                    {"trials": trials, "owner": s2["owner"], "invariant_fail": s2["invariant_fail"]})
    return "INCONCLUSIVE", {"trials": trials, "why": "no superseded in the tries"}


def a8(h):
    ok, s = to_dash(h)
    g0 = s["restore_gen"]
    st, seq = mutate(h, 7)                     # a restore requested, as the startup callback does
    wait(h, seq)
    ok_clear, s = until(h, lambda s: s["phase"] == "clear", timeout=1)
    op1(h)                                     # Fn+D during its CLEAR
    s_wait = read_state(h)
    op1(h)
    op1(h)
    ok, s2 = until(h, dash_done)
    good = ok_clear and s_wait["owner"] == "debug" and s_wait["phase"] == "waiting" and ok and \
        s2["restore_gen"] == g0 + 2 and s2["invariant_fail"] == 0
    return ("PASS" if good else ("INCONCLUSIVE" if not ok_clear else "FAIL"),
            {"saw_clear": ok_clear, "under_debug": [s_wait["owner"], s_wait["phase"]],
             "gen": [g0, s2["restore_gen"]], "restored": ok, "invariant_fail": s2["invariant_fail"]})


CASES = {"a1": a1, "a3": a3, "a5": a5, "a6": a6, "a8": a8}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", default=list(CASES))
    ap.add_argument("--out", default="menu_s0_accept.json")
    a = ap.parse_args()
    h = open_device()
    results = {}
    try:
        for name in a.cases:
            verdict, ev = CASES[name](h)
            results[name] = {"verdict": verdict, "evidence": ev}
            print(f"{name.upper()}: {verdict}  {json.dumps(ev, default=str)}")
        to_dash(h)
    finally:
        h.close()
    with open(a.out, "w") as f:
        json.dump(results, f, indent=1, default=str)
    return 0 if all(r["verdict"] == "PASS" for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
