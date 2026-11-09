#!/usr/bin/env python3
"""The title garble's switchable diagnostic: firmware branch lcd-diag only,
HC_LCDDIAG (0x14) on the health channel (graphics/lcd_bus.c, lcd_diag_op).

    venv/bin/python scripts/lcd_diag.py read | old | new | zero

old switches the polled send to 4790208267's, new back to fix A's (every boot's
default); zero clears the counters. Each prints the state after it. Needs the
board on USB with nothing else holding its raw HID (on macOS, the daemon out).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import current_map as cm  # noqa: E402

HC_LCDDIAG = 0x14
SUBS = {"read": (0, 0), "new": (1, 0), "old": (1, 1), "zero": (2, 0)}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SUBS:
        raise SystemExit(__doc__)
    sub, arg = SUBS[sys.argv[1]]
    h = cm.open_board(10.0)
    try:
        r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, HC_LCDDIAG, sub, arg] + [0] * 27)
    finally:
        h.close()
    if len(r) < 32 or r[0] == 0xFF or r[2] != HC_LCDDIAG:
        raise SystemExit("unhandled: not the lcd-diag build")
    b = bytes(r[4:32])
    u16 = lambda i: int.from_bytes(b[i:i + 2], "little")
    u32 = lambda i: int.from_bytes(b[i:i + 4], "little")
    gap = u16(11)
    print(f"mode                 {'old (4790208267)' if b[0] else 'fix A'}")
    print(f"giveups              {u16(1)}")
    print(f"strays               {u16(3)}")
    print(f"late                 {u16(5)}")
    print(f"window_notidle       {u16(9)}")
    print(f"dma_gap_min          {'none' if gap == 0xFFFF else f'{gap} ticks ({gap * 1e6 / 187500:.1f} us)'}")
    print(f"windows_after_dma    {u32(13)}")
    print(f"windows_total        {u32(17)}")


if __name__ == "__main__":
    main()
