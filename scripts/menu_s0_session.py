#!/usr/bin/env python3
"""The configuration menu's S0 workload (plans/CONFIG-MENU-BUILD-PLAN.md, S0's
proof): a fixed 50-step array of op 27 mutations, run ten times, each sent when
the last is terminal, polling sub 5 every 20 ms. It records every outcome and
every transition seen, and the stall counters before and after, with no reset
inside the measured span. Dev builds only (HC_DEVHOOK).

    venv-win/Scripts/python.exe scripts/menu_s0_session.py [--repeats N] [--out results.json] < /dev/null

Also the op 27 codec the S0 tests use: `read_state`, `mutate`, `wait`.
Never enumerates HID on Windows (ak820health.open_device)."""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from ak820health import open_device  # noqa: E402

SET_VALUE, CH, HC, OP = 0x07, 0x13, 0x76, 27
OK, BUSY, BAD = 0, 1, 2
STATES = ["none", "pending", "done", "cancelled", "superseded", "refused"]
OWNERS = ["dash", "debug", "menu", "anim"]
SESSIONS = ["none", "pending", "open"]
PHASES = ["splash", "waiting", "clear", "stages", "residual", "done"]
LATCHES = ["none", "click", "back", "close"]
TERMINAL = {2, 3, 4, 5}


def xfer(h, sub, args=b""):
    """One op 27 report; the reply matched by channel, command, op and sub,
    since Windows delivers every input report to every open handle."""
    h.write(bytes([0, SET_VALUE, CH, HC, OP, sub]) + args + bytes(27 - len(args)))
    for _ in range(8):
        r = h.read(32, 1000)
        if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == OP and r[4] == sub:
            if r[0] != SET_VALUE:
                raise RuntimeError(f"op 27 sub {sub}: unhandled (byte 0 = {r[0]:#x})")
            return bytes(r)
    raise RuntimeError(f"op 27 sub {sub}: no reply")


def u16(b, i):
    return b[i] | (b[i + 1] << 8)


def read_state(h):
    r = xfer(h, 5)
    f = r[16]
    return {
        "last_seq": r[6], "last_state": STATES[r[7]] if r[7] < len(STATES) else r[7],
        "owner": OWNERS[r[8]], "session": SESSIONS[r[9]],
        "restore_gen": u16(r, 10), "phase": PHASES[r[12]], "damaged": bool(r[13]),
        "screen": r[14], "cursor": r[15],
        "armed": bool(f & 1), "edit": bool(f & 2), "pixels_done": bool(f & 4),
        "dma_busy": bool(f & 8), "clearing": bool(f & 16), "wake_hold": bool(f & 32),
        "batt_dirty": bool(f & 64), "logo_stale": bool(f & 128),
        "gq": r[17] & 15, "lq": r[17] >> 4,
        "turns": r[18] - 256 if r[18] > 127 else r[18], "latch": LATCHES[r[19]],
        "dropped": r[20], "unsettled": r[21], "losses": r[22], "capture": r[23],
        "invariant_fail": u16(r, 24), "paint_us": u16(r, 26), "pairing": r[28],
        "ops": r[29], "stopped": bool(r[30] & 1),
    }


def mutate(h, sub, args=b""):
    """(status, seq): 0 accepted, 1 busy, 2 a bad argument or state."""
    r = xfer(h, sub, args)
    return r[5], r[6]


def wait(h, seq, timeout=5.0, poll=0.02):
    """Until the outstanding mutation `seq` is terminal; its state, and the
    board's state as last read."""
    end = time.monotonic() + timeout
    while True:
        s = read_state(h)
        if s["last_seq"] == seq and STATES.index(s["last_state"]) in TERMINAL:
            return s["last_state"], s
        if time.monotonic() > end:
            return "timeout", s
        time.sleep(poll)


# The fixed 50 steps (CONFIG-MENU-BUILD-PLAN, S0): 28 turns, 10 clicks (two
# A/B toggles, two trips to F2 and back, two Diagnostics handoffs and
# returns), 4 holds of 650 ms, 4 Fn plus a click, 2 restores, 2 losses. Each
# starts and ends with the fixture open on F1 at row 0. A step is (kind, arg,
# the owner, screen and cursor expected after it; None: not checked).
F1, F2 = 1, 2
STEPS = [
    ("turns", 3, ("menu", F1, 3)), ("turns", -3, ("menu", F1, 0)),
    ("click", 0, ("menu", F1, 0)), ("click", 0, ("menu", F1, 0)),              # A to B, B to A
    ("turns", 4, ("menu", F1, 4)), ("turns", 2, ("menu", F1, 6)),
    ("click", 0, ("menu", F2, None)), ("click", 0, ("menu", F1, 6)),           # F2 and back
    ("turns", 1, ("menu", F1, 7)),
    ("click", 0, ("debug", None, None)), ("click", 0, ("menu", F1, 7)),        # Diagnostics and back
    ("turns", 1, ("menu", F1, 0)),
    ("restore", 0, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),          # Back closes; Fn+click opens
    ("turns", 2, ("menu", F1, 2)), ("turns", -4, ("menu", F1, 6)),
    ("click", 0, ("menu", F2, None)), ("click", 0, ("menu", F1, 6)),
    ("turns", 1, ("menu", F1, 7)),
    ("click", 0, ("debug", None, None)), ("click", 0, ("menu", F1, 7)),
    ("loss", 0, ("menu", F1, 7)),
    ("turns", -3, ("menu", F1, 4)), ("turns", -4, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),
    ("turns", 1, ("menu", F1, 1)), ("turns", 1, ("menu", F1, 2)), ("turns", -2, ("menu", F1, 0)),
    ("turns", 3, ("menu", F1, 3)), ("turns", -3, ("menu", F1, 0)),
    ("loss", 0, ("menu", F1, 0)),
    ("turns", 4, ("menu", F1, 4)), ("turns", -4, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),
    ("turns", 2, ("menu", F1, 2)), ("turns", 2, ("menu", F1, 4)),
    ("turns", -2, ("menu", F1, 2)), ("turns", -2, ("menu", F1, 0)),
    ("restore", 0, ("menu", F1, 0)),
    ("turns", 1, ("menu", F1, 1)), ("turns", -1, ("menu", F1, 0)),
    ("turns", 4, ("menu", F1, 4)), ("turns", -4, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),
    ("turns", 3, ("menu", F1, 3)), ("turns", -3, ("menu", F1, 0)),
]
assert len(STEPS) == 50
_mix = [k for k, _, _ in STEPS]
assert (_mix.count("turns"), _mix.count("click"), _mix.count("hold"), _mix.count("fn"),
        _mix.count("restore"), _mix.count("loss")) == (28, 10, 4, 4, 2, 2)


def send(h, kind, arg):
    if kind == "turns":
        return mutate(h, 1, bytes([arg & 0xFF]))
    if kind == "click":
        return mutate(h, 2)
    if kind == "hold":
        return mutate(h, 3, bytes([arg & 0xFF, arg >> 8]))
    if kind == "fn":
        return mutate(h, 4)
    if kind == "restore":
        return mutate(h, 7)
    if kind == "loss":
        return mutate(h, 8)
    raise ValueError(kind)


def health_json():
    py = sys.executable
    tool = os.path.join(os.path.dirname(__file__), "..", "hostagent", "ak820health.py")
    out = subprocess.run([py, tool, "--stalls", "--json"], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=30)
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--out", default="menu_s0_session.json")
    a = ap.parse_args()

    before = health_json()
    h = open_device()
    log, mismatches, outcomes = [], 0, {}
    t0 = time.monotonic()
    try:
        s = read_state(h)
        if s["session"] != "none":
            st, seq = mutate(h, 4)   # close whatever is open
            wait(h, seq)
        st, seq = mutate(h, 4)       # open the fixture
        state, s = wait(h, seq)
        if (s["owner"], s["screen"], s["cursor"]) != ("menu", F1, 0):
            sys.exit(f"the fixture didn't open: {s}")
        for rep in range(a.repeats):
            for i, (kind, arg, want) in enumerate(STEPS):
                st, seq = send(h, kind, arg)
                if st != OK:
                    log.append({"rep": rep, "step": i, "kind": kind, "status": st})
                    mismatches += 1
                    continue
                state, s = wait(h, seq)
                outcomes[state] = outcomes.get(state, 0) + 1
                seen = (s["owner"], s["screen"], s["cursor"])
                ok = all(w is None or w == g for w, g in zip(want, seen))
                if not ok:
                    mismatches += 1
                log.append({"rep": rep, "step": i, "kind": kind, "arg": arg, "state": state,
                            "seen": seen, "want": want, "ok": ok, "phase": s["phase"],
                            "gen": s["restore_gen"], "invariant_fail": s["invariant_fail"],
                            "dropped": s["dropped"], "losses": s["losses"]})
        st, seq = mutate(h, 4)       # the last returns to the dashboard
        wait(h, seq)
        final = read_state(h)
    finally:
        h.close()
    elapsed = time.monotonic() - t0
    after = health_json()
    result = {
        "repeats": a.repeats, "elapsed_s": round(elapsed, 1), "mismatches": mismatches,
        "outcomes": outcomes, "final": final,
        "count_ge_10ms": [before.get("count_ge_10ms"), after.get("count_ge_10ms")],
        "count_ge_25ms": [before.get("count_ge_25ms"), after.get("count_ge_25ms")],
        "loop_gap_max_ms": after.get("loop_gap_max_ms"),
        "acct_after": after.get("acct"),
        "log": log,
    }
    with open(a.out, "w") as f:
        json.dump(result, f, indent=1)
    print(f"{a.repeats} x 50 steps in {elapsed:.0f} s: {mismatches} mismatches, outcomes {outcomes}")
    print(f"ge10 {before.get('count_ge_10ms')} -> {after.get('count_ge_10ms')}, "
          f"ge25 {before.get('count_ge_25ms')} -> {after.get('count_ge_25ms')}, "
          f"invariant_fail {final['invariant_fail']:#x}, final {final['owner']}/{final['session']}/{final['phase']}")
    return 1 if mismatches or final["invariant_fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
