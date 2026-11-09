#!/usr/bin/env python3
"""The title garble's switchable diagnostic: firmware branch lcd-diag only,
HC_LCDDIAG (0x14) on the health channel (graphics/lcd_bus.c, lcd_diag_op).

    venv/bin/python scripts/lcd_diag.py read | zero | MODE | n N | div D

MODE picks the polled send (every boot starts in a):
    a | new     fix A's send
    old         4790208267's send, verbatim
    exit        old + A's exit (three idle STAT reads in a row)
    dly-after   old + N discarded STAT reads after its BUSY wait
    entry       old + A's entry (TX empty required, the RX drain)
    dly-before  old + N discarded STAT reads before its first byte
    acct        old + A's accounting (own entries only, bounded, all answered)
n N sets dly-after's and dly-before's N (0-255; the build's default 10; a
read costs ~7 cycles, 7N - 2 plus ~8 of setup). div D sets the painters' SCK
divider, 0-15: SCK = 48 MHz / (2 D + 2), 0 the 24 MHz every boot runs, 7 is
3 MHz; applied at the next painter's idle window, never to a DMA (the reply
shows the divider asked for and the one SPI0 holds). zero clears the
counters. Each prints the state after it. Needs the board on USB with nothing
else holding its raw HID (on macOS, the daemon out). The split's modes (2-6),
n, div and exit_extra need the split's lcd-diag (reply version 2); the older
lcd-diag builds answer modes 0 and 1 only, and the first one's bytes 7-8 are
its old_queued, printed as such. (c88bd9a7b1, the split's first cut, never
flashed, answers the split but leaves the version 0: not supported here.)
"div asked" is the request; "div in SPI0" is CLKDIV read back. "not yet
applied" means a change asked for has not reached a painter's idle window;
held 0 with nothing pending under a nonzero ask is a DMA's Prepare() having
reset SPI0 to 24 MHz since the last painter's window, which puts it back.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import current_map as cm  # noqa: E402

HC_LCDDIAG = 0x14
MODES = ["a", "old", "exit", "dly-after", "entry", "dly-before", "acct"]
NAMES = {"a": "fix A", "old": "old (4790208267)", "exit": "old + A's exit",
         "dly-after": "old + N reads after", "entry": "old + A's entry",
         "dly-before": "old + N reads before", "acct": "old + A's accounting"}


def parse(argv):
    if len(argv) == 1 and argv[0] == "read":
        return 0, 0
    if len(argv) == 1 and argv[0] == "zero":
        return 2, 0
    if len(argv) == 1 and argv[0] in ("new", *MODES):
        return 1, MODES.index("a" if argv[0] == "new" else argv[0])
    if len(argv) == 2 and argv[0] in ("n", "div") and argv[1].isdigit():
        v = int(argv[1])
        if argv[0] == "n" and v <= 255:
            return 3, v
        if argv[0] == "div" and v <= 15:
            return 4, v
    raise SystemExit(__doc__)


def main():
    sub, arg = parse(sys.argv[1:])
    h = cm.open_board(10.0)
    try:
        r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, HC_LCDDIAG, sub, arg] + [0] * 27)
    finally:
        h.close()
    if len(r) < 32 or r[0] == 0xFF or r[2] != HC_LCDDIAG:
        raise SystemExit("unhandled: not the lcd-diag build, or a mode/value it doesn't have")
    b = bytes(r[4:32])
    u16 = lambda i: int.from_bytes(b[i:i + 2], "little")
    u32 = lambda i: int.from_bytes(b[i:i + 4], "little")
    gap = u16(11)
    mode = b[0]
    version = b[23]   # 2 from the split on; earlier lcd-diag builds leave 0
    mhz = lambda d: f"{48 / (2 * d + 2):g} MHz"
    print(f"mode                 {mode} {NAMES[MODES[mode]] if mode < len(MODES) else '?'}")
    print(f"giveups              {u16(1)}")
    print(f"strays               {u16(3)}")
    print(f"late                 {u16(5)}")
    if version >= 2:
        print(f"exit_extra           {u16(7)}")
    else:
        print(f"bytes 7-8            {u16(7)} (unversioned: 5688b2a975 or earlier; old_queued on bc1b9f42cb, else 0)")
    print(f"window_notidle       {u16(9)}")
    print(f"dma_gap_min          {'none' if gap == 0xFFFF else f'{gap} ticks ({gap * 1e6 / 187500:.1f} us)'}")
    print(f"windows_after_dma    {u32(13)}")
    print(f"windows_total        {u32(17)}")
    if version >= 2:
        print(f"n (delay reads)      {b[21]}")
        print(f"div asked            {b[22]} ({mhz(b[22])}){'  (not yet applied)' if b[25] else ''}")
        print(f"div in SPI0          {b[24]} ({mhz(b[24])})")
    else:
        print("n, div               (unversioned build: none)")


if __name__ == "__main__":
    main()
