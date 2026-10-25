"""Set the host's Caps Lock (Windows), so the board's Caps LED follows the
host's LED report: the indicator tick's timing runs (scripts/ind_timing.py).
Prints the state after. Touches no HID device: it injects one Caps Lock key
press and release into Windows' input, only when the state differs.

    venv-win/Scripts/python.exe scripts/caps_toggle.py on|off < /dev/null"""
import ctypes
import sys
import time

VK_CAPITAL, KEYEVENTF_KEYUP = 0x14, 0x0002
user32 = ctypes.windll.user32


def caps_on():
    return bool(user32.GetKeyState(VK_CAPITAL) & 1)


def main():
    want = sys.argv[1] == "on"
    if caps_on() != want:
        user32.keybd_event(VK_CAPITAL, 0x3A, 0, 0)
        user32.keybd_event(VK_CAPITAL, 0x3A, KEYEVENTF_KEYUP, 0)
        time.sleep(0.3)
    print("caps", "on" if caps_on() else "off")


if __name__ == "__main__":
    main()
