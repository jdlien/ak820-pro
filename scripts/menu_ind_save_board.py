"""P2a's write attribution on the board: a Lock lights save through the menu
(op 27), then its kb_eeconfig write counted by itself on the flash counters'
page 3 (ak820health's read_flashw), and the level put back the same way.

    venv-win/Scripts/python.exe scripts/menu_ind_save_board.py < /dev/null"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ak820health as H  # noqa: E402
import menu_p1b_gates as g  # noqa: E402
from menu_s0_session import open_device, xfer  # noqa: E402

R_IND, SC_LOCKS = 4, 16 + 37


def fields(h):
    return H.read_flashw(h)["kb_field_sessions"]


def save_locks(h, delta):
    g.open_menu(h)
    g.turn(h, R_IND)
    g.click(h)                     # Indicators
    s = g.click(h)                 # Lock lights
    if s["screen"] != SC_LOCKS:
        sys.exit(f"not the Lock lights editor: screen {s['screen']}")
    g.turn(h, delta)
    g.click(h)                     # save
    g.close_menu(h)


def main():
    h = open_device()
    fails = []
    try:
        lv0 = xfer(h, 14)[12]
        f0 = fields(h)
        step = 1 if lv0 < 100 else -1
        save_locks(h, step)
        time.sleep(6.5)            # kb_eeconfig's 5 s settle, then its write
        f1 = fields(h)
        lv1 = xfer(h, 14)[12]
        print(f"saved {lv0} -> {lv1}: page 3 {f0['ind_locks']} -> {f1['ind_locks']}, charging {f1['ind_charging']}")
        if lv1 != lv0 + step:
            fails.append(f"the level {lv1}, not {lv0 + step}")
        if f1["ind_locks"] != f0["ind_locks"] + 1 or f1["ind_charging"] != f0["ind_charging"]:
            fails.append(f"page 3: {f0} -> {f1}")
        if any(f1[k] != f0[k] for k in f0 if k not in ("ind_locks", "ind_charging", "rtc_period", "batt_level")):
            fails.append(f"another field counted: {f0} -> {f1}")
        save_locks(h, -step)       # back as it was
        time.sleep(6.5)
        f2 = fields(h)
        lv2 = xfer(h, 14)[12]
        print(f"put back {lv1} -> {lv2}: page 3 {f2['ind_locks']}")
        if lv2 != lv0 or f2["ind_locks"] != f1["ind_locks"] + 1:
            fails.append(f"the put-back: level {lv2}, page 3 {f2['ind_locks']}")
    finally:
        h.close()
    print("PASS" if not fails else "FAIL: " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
