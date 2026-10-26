#!/usr/bin/env python3
"""The configuration menu's S0: the photographed cases, A13 and A2
(plans/CONFIG-MENU-S0-BOARD-TESTS.md). Steps the board through each frame
and holds it until the file named by --next appears (then deletes it), so a
person can photograph each one at their own pace.

    A13: fixture-A; fixture-B-stop13; fixture-A-again; fixture-F2
    A2:  the Camera page settled (photo 1); after sub 8 and 30 s (photo 2)

The fixture closes after 60 s with no input (24 s until 10-26), so while a fixture frame is held
the knob is turned one notch and back every 15 s (op 27 sub 1). That blinks
the cursor's row and the next one for a moment; under the stop, the paint
stays held. The state after each frame is logged, with the stop and
`invariant_fail` checked.

    venv-win/Scripts/python.exe scripts/menu_s0_photos.py --next F [--out J] < /dev/null

Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402
from menu_s0_accept import op1, to_dash, until  # noqa: E402

KEEPALIVE_S = 15.0
# The last input the board counted. One clock across every frame: sub 0 (the
# pattern changes) isn't input, so a timer restarted at each frame let the
# fixture's 24 s idle run out in the second frame (the first run, 08:09).
last_input = [time.monotonic()]


def say(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def keepalive(h):
    """A notch and back, if 15 s have passed since the last input."""
    if time.monotonic() - last_input[0] < KEEPALIVE_S:
        return
    for t in (1, -1):
        st, seq = mutate(h, 1, bytes([t & 0xFF]))
        if st != 0:
            say(f"keep-alive turn refused: status {st}")
            return
        last_input[0] = time.monotonic()
        state, s = wait(h, seq)
        if state != "done":
            say(f"keep-alive turn {state}: session={s['session']} stopped={s['stopped']}")


def hold(h, trigger, keep):
    """Wait for the trigger file; keep the fixture open meanwhile."""
    while not os.path.exists(trigger):
        time.sleep(0.2)
        if keep:
            keepalive(h)
    os.remove(trigger)


def frame(h, name, trigger, keepalive, log, check=None):
    s = read_state(h)
    ok = check(s) if check else True
    entry = {"frame": name, "ok": ok, "state": s}
    log.append(entry)
    say(f"READY {name} ok={ok} owner={s['owner']} screen={s['screen']} cursor={s['cursor']} "
        f"pixels_done={s['pixels_done']} stopped={s['stopped']} invariant_fail={s['invariant_fail']}")
    hold(h, trigger, keepalive)
    s2 = read_state(h)
    entry["after"] = s2
    if check and not check(s2):
        entry["ok"] = False
    say(f"SHOT {name} ok={entry['ok']} (after: stopped={s2['stopped']} session={s2['session']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", required=True, help="the trigger file: its appearance ends a frame's hold")
    ap.add_argument("--out", default="menu_s0_photos.json")
    ap.add_argument("--skip-a", action="store_true", help="fixture-A already photographed: don't hold it")
    a = ap.parse_args()
    if os.path.exists(a.next):
        os.remove(a.next)
    h = open_device()
    log = []
    try:
        to_dash(h)
        # A13
        st, seq = mutate(h, 4)
        wait(h, seq)
        last_input[0] = time.monotonic()         # the opening is input
        until(h, lambda s: s["pixels_done"], timeout=5)
        if not a.skip_a:
            frame(h, "fixture-A", a.next, True, log,
                  lambda s: s["session"] == "open" and s["screen"] == 1 and s["pixels_done"])
        st, seq = mutate(h, 0, bytes([2, 13]))
        say(f"pattern B stopping after 13: status {st}")
        wait(h, seq)
        until(h, lambda s: s["stopped"], timeout=5)
        frame(h, "fixture-B-stop13", a.next, True, log,
              lambda s: s["session"] == "open" and s["stopped"])
        st, seq = mutate(h, 0, bytes([0, 0]))
        wait(h, seq)
        until(h, lambda s: s["pixels_done"], timeout=5)
        frame(h, "fixture-A-again", a.next, True, log,
              lambda s: s["session"] == "open" and s["pixels_done"])
        st, seq = mutate(h, 0, bytes([3, 0]))
        wait(h, seq)
        until(h, lambda s: s["pixels_done"], timeout=5)
        frame(h, "fixture-F2", a.next, True, log,
              lambda s: s["session"] == "open" and s["pixels_done"])
        # A2
        to_dash(h)
        op1(h)
        op1(h)                                   # Health, then Camera
        time.sleep(10)
        s = read_state(h)
        losses0 = s["losses"]
        frame(h, "camera-1", a.next, False, log, lambda s: s["owner"] == "debug")
        st, seq = mutate(h, 8)                   # an injected loss under Camera
        wait(h, seq)
        time.sleep(30)
        frame(h, "camera-2", a.next, False, log,
              lambda s: s["owner"] == "debug" and s["losses"] == losses0 + 1)
        op1(h)                                   # Camera to the dashboard
        ok, s = until(h, lambda s: s["owner"] == "dash" and s["phase"] == "done")
        log.append({"frame": "dashboard-restored", "ok": ok and s["invariant_fail"] == 0, "state": s})
        say(f"DONE restored={ok} invariant_fail={s['invariant_fail']}")
    finally:
        h.close()
        with open(a.out, "w") as f:
            json.dump(log, f, indent=1, default=str)
    return 0 if all(e["ok"] for e in log) else 1


if __name__ == "__main__":
    sys.exit(main())
