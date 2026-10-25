"""Wait until nobody is using the keyboard on gremlin: no key press (health
page 2's key_presses) and no menu session (op 27 sub 5) for QUIET minutes,
read once a minute. Exits 0 then, or 1 after MAX hours. For the board tests
that take the panel or need a steady load (scripts/ind_timing.py,
menu_p1a_board.py), so they don't run under JD's hands.

    venv-win/Scripts/python.exe scripts/wait_idle.py [--quiet 10] [--max 8] < /dev/null"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ak820health as H  # noqa: E402
from menu_s0_session import read_state  # noqa: E402


def sample():
    h = H.open_device()
    try:
        return H.read_stalls(h)["key_presses"], read_state(h)["session"]
    finally:
        h.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", type=float, default=10.0, help="minutes with no key press and no menu")
    ap.add_argument("--max", type=float, default=8.0, help="hours to wait at most")
    a = ap.parse_args()
    end = time.monotonic() + a.max * 3600
    keys, _ = sample()
    quiet_since = time.monotonic()
    while time.monotonic() < end:
        time.sleep(60)
        try:
            k, session = sample()
        except SystemExit as e:   # a flash or a replug: not idle
            print(f"{time.strftime('%H:%M')} no board ({e})", flush=True)
            quiet_since = time.monotonic()
            continue
        if k != keys or session != "none":
            keys, quiet_since = k, time.monotonic()
            print(f"{time.strftime('%H:%M')} in use (keys {k}, menu {session})", flush=True)
        elif time.monotonic() - quiet_since >= a.quiet * 60:
            print(f"{time.strftime('%H:%M')} idle for {a.quiet:.0f} min", flush=True)
            return 0
    print("still in use after the wait", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
