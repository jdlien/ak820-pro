"""The menu's board pass under a forced indicator load (codex, P2a's code
review, point 1): op 27 sub 15 sets the force bits and levels, sub 14 checks
them before and after, menu_p1a_board.py --no-ind runs (its indicator editors
would clear the force), and the indicators go back as they were.

    venv-win/Scripts/python.exe scripts/menu_forced_pass.py FORCE,LOCKS,CHG OUT.json < /dev/null"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from menu_s0_session import open_device, xfer  # noqa: E402


def state(h):
    r = xfer(h, 14)
    return {"open": r[6], "locks": r[12], "charging": r[13], "force": r[14]}


def put(h, force, locks, chg):
    r = xfer(h, 15, bytes([force, locks, chg]))
    if r[5] != 0:
        sys.exit(f"op 27 sub 15 refused ({r[5]})")


def main():
    force, locks, chg = (int(x) for x in sys.argv[1].split(","))
    out = sys.argv[2]
    want = {"open": 0, "locks": locks, "charging": chg, "force": force}
    h = open_device()
    try:
        before = state(h)
        if before["open"]:
            sys.exit("an edit is open in the menu: close it first")
        put(h, force, locks, chg)
        if state(h) != want:
            sys.exit(f"the load isn't set: {state(h)}")
    finally:
        h.close()
    here = os.path.dirname(os.path.abspath(__file__))
    rc = subprocess.run([sys.executable, os.path.join(here, "menu_p1a_board.py"), "--no-ind", "--out", out],
                        stdin=subprocess.DEVNULL).returncode
    h = open_device()
    try:
        after = state(h)
        put(h, before["force"], before["locks"], before["charging"])
    finally:
        h.close()
    held = after == want
    print(f"the load held through the pass: {held} ({after})")
    sys.exit(rc if held else 1)


if __name__ == "__main__":
    main()
