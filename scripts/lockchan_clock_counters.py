"""The board's lock-LED clock counters (type 4): HC_DEVHOOK op 17 sub 8,
over USB raw HID (a dev build; plans/LOCK-LED-CHANNEL-PLAN.md, "The wireless
clock"). Opens the board by its own path, never enumerating HID.

    python scripts/lockchan_clock_counters.py

Prints applied, refused (owner: usb_mode, or raw HID's clock within 10 min),
rejected, retried, dropped, the last applied's offset (target minus board, ms,
before the correction) and status (0 stepped, 1 slewing), and whether a retry
is pending.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hostagent"))
from ak820health import open_device  # noqa: E402

SET_VALUE, CH, HC, OP, SUB = 0x07, 0x13, 0x76, 17, 8
STATUS = {0: "stepped", 1: "slewing", 0xFE: "retry", 0xFF: "none yet"}


def main():
    h = open_device()
    try:
        h.write(bytes([0, SET_VALUE, CH, HC, OP, SUB]) + bytes(27))  # report id + 32 bytes: macOS drops a short one
        for _ in range(5):
            r = h.read(32, 1000)
            if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == OP and r[4] == SUB:
                break
        else:
            sys.exit("no reply (a build without op 17 sub 8?)")
    finally:
        h.close()
    c = r[5:]
    u16 = lambda i: c[i] | (c[i + 1] << 8)
    off = u16(10)
    off = off - 65536 if off >= 32768 else off
    print(f"applied {u16(0)}  refused {u16(2)}  rejected {u16(4)}  retried {u16(6)}  dropped {u16(8)}")
    print(f"last: offset {off:+d} ms (target - board), {STATUS.get(c[12], hex(c[12]))}; retry pending: {'yes' if c[13] else 'no'}")


if __name__ == "__main__":
    main()
