"""The bootloader item on the board (plans/CONFIG-MENU-P1-DESIGN.md, "The
bootloader item"): drives the menu by op 27 to Bootloader, sends the click
that enters it, and waits for the bootloader's 0C45:7140 by Windows' PnP list
(never enumerating HID). Then `./flash.sh <artifact>` brings the board back
(it takes an already-entered bootloader: the last backups, no jump).

    venv-win/Scripts/python.exe scripts/menu_boot_board.py < /dev/null"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import menu_p1b_gates as g  # noqa: E402
from menu_s0_session import mutate, open_device  # noqa: E402

BOOT_PAGE, R_BOOT = 16 + 34, 7   # P2a: page one's last row


def in_bootloader():
    ps = ("Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_0C45&PID_7140' } | "
          "Measure-Object | Select-Object -ExpandProperty Count")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL).stdout.strip()
    return out.isdigit() and int(out) > 0


def main():
    h = open_device()
    try:
        g.open_menu(h)
        g.turn(h, R_BOOT)
        s = g.click(h)
        if s["screen"] != BOOT_PAGE:
            sys.exit(f"FAIL: not the Bootloader page (screen {s['screen']})")
        print("on the Bootloader page; clicking to enter it", flush=True)
        st, _ = mutate(h, 2)   # no wait: the board resets mid-reply
        if st != 0:
            sys.exit(f"FAIL: the click refused ({st})")
    finally:
        h.close()
    t0 = time.monotonic()
    while time.monotonic() - t0 < 15:
        if in_bootloader():
            print(f"PASS: 0C45:7140 after {time.monotonic() - t0:.1f} s")
            return
        time.sleep(0.5)
    sys.exit("FAIL: no bootloader (0C45:7140) within 15 s")


if __name__ == "__main__":
    main()
