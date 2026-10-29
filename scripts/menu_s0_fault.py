#!/usr/bin/env python3
"""The configuration menu's S0, acceptance case A7 (plans/CONFIG-MENU-S0-BOARD-
TESTS.md): a real lost DMA completion, retried (N=1) and given up (N=2), under
the dashboard, the fixture and the Health page (the Camera page too, until it
was removed on 10-28). Needs the `devfault` build, whose HC_BLITFAULT ([0x07,
0x13, 0x77, N]) drops the next N completions. Each fault is triggered by a
known DMA within 3 s.

    venv-win/Scripts/python.exe scripts/menu_s0_fault.py [--out F] < /dev/null

The evidence: `ak820 health --json`'s blit_timeouts and
vitals.blit_retry_successes, op 27's losses, and the owner's recovery. The
animation's case is recorded as not run unless its slot has frames (no host
op starts it). Never enumerates HID on Windows."""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402
from menu_s0_accept import dash_done, op1, to_dash, until  # noqa: E402

SET_VALUE, CH, HC_BLITFAULT = 0x07, 0x13, 0x77
AK820 = os.path.join(os.path.dirname(__file__), "..", "ak820-agent", "target", "release", "ak820.exe")


def blitfault(h, n):
    h.write(bytes([0, SET_VALUE, CH, HC_BLITFAULT, n]) + bytes(28))
    end = time.monotonic() + 3.0   # a deadline, not a count: other handles' replies land here too
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and r[1] == CH and r[2] == HC_BLITFAULT:
            if r[0] != SET_VALUE:
                raise RuntimeError("HC_BLITFAULT unhandled: not a devfault build?")
            return r[3]
    raise RuntimeError("HC_BLITFAULT: no reply")


def counters():
    out = subprocess.run([AK820, "health", "--json"], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=30)
    j = json.loads(out.stdout)
    v = j.get("vitals", {})
    return {"timeouts": j.get("blit_timeouts"), "retry_ok": v.get("blit_retry_successes"),
            "irq_lost": j.get("blit_irq_lost", v.get("blit_irq_lost"))}


def settle(h, owner):
    if owner == "menu":
        until(h, lambda s: s["pixels_done"], timeout=5)
    time.sleep(1.5 if owner in ("dash", "debug") else 0.2)


def one(h, owner, n, pattern=None):
    """One fault of N under `owner`. The trigger is a known DMA: under the
    fixture, sub 0 setting `pattern` (its title's glyphs); under the dashboard
    and the debug page, the next clock second."""
    before = counters()
    s0 = read_state(h)
    blitfault(h, n)
    if owner == "menu":
        mutate(h, 0, bytes([pattern, 0]))
    t_end = time.monotonic() + 3.0
    while time.monotonic() < t_end:
        c = counters()
        if c["timeouts"] - before["timeouts"] >= n:
            break
        time.sleep(0.25)
    time.sleep(0.5)
    after = counters()
    s1 = read_state(h)
    dt = after["timeouts"] - before["timeouts"]
    dr = after["retry_ok"] - before["retry_ok"]
    dl = s1["losses"] - s0["losses"]
    ev = {"owner": owner, "n": n, "timeouts": dt, "retry_ok": dr, "losses": dl,
          "irq_lost": [before["irq_lost"], after["irq_lost"]]}
    if n == 1:
        ok = dt == 1 and dr == 1 and dl == 0
    else:
        ok = dt == 2 and dl == 1
        if owner == "dash":
            okr, s2 = until(h, dash_done, timeout=10)
            ev["repaired"] = okr
            ev["gen"] = [s0["restore_gen"], s2["restore_gen"]]
            ok = ok and okr and s2["restore_gen"] == s0["restore_gen"] + 1
        elif owner == "menu":
            okr, s2 = until(h, lambda s: s["pixels_done"], timeout=10)
            ev["repainted"] = okr
            ok = ok and okr
        else:
            time.sleep(3)   # the page's clear and its cells
            s2 = read_state(h)
            ev["still_debug"] = s2["owner"] == "debug"
            ok = ok and ev["still_debug"]
        ev["invariant_fail"] = s2["invariant_fail"]
        ok = ok and s2["invariant_fail"] == 0
    return ok, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_s0_fault.json")
    a = ap.parse_args()
    h = open_device()
    results = []
    try:
        for owner in ("dash", "menu", "health"):
            to_dash(h)
            if owner == "menu":
                st, seq = mutate(h, 4)
                wait(h, seq)
            elif owner == "health":
                op1(h)
            kind = "debug" if owner == "health" else owner
            for n in (1, 2):
                settle(h, kind)
                ok, ev = one(h, kind, n, pattern=1 if n == 1 else 0)   # A to B, then back
                ev["page"] = owner
                results.append({"pass": ok, **ev})
                print(("PASS " if ok else "FAIL ") + json.dumps(ev))
        to_dash(h)
    finally:
        h.close()
    results.append({"pass": None, "owner": "anim", "note": "not run: no host op starts the animation"})
    with open(a.out, "w") as f:
        json.dump(results, f, indent=1)
    return 0 if all(r["pass"] for r in results if r["pass"] is not None) else 1


if __name__ == "__main__":
    sys.exit(main())
