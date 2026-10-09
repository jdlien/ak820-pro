#!/usr/bin/env python3
"""Switch the bench's USB relay: the keyboard's charging, without its data
(docs/test-bench.md, "The USB relay").

A DCT Tech HID relay (VID 16c0, PID 05df). A USB cable's 5 V wire runs through
RELAY2's COM and NO, and its data wires bypass the relay. Relay off: no VBUS,
so the keyboard stays enumerated over data alone, on battery, NOT charging.
Relay on: VBUS, so it charges.

  usb_relay.py status
  usb_relay.py on N | off N      N = 1 or 2 (the board has two), or "all"

Opens only that VID/PID (hid.enumerate filters on both), so it touches no
other HID device. Every switch is read back from the board's state byte, and
the exit status is 0 only if the read-back matches.

Protocol, from jdlien/hdd-toggle src/relay.c: a 9-byte feature report
[0, cmd, n, 0, 0, 0, 0, 0, 0]. cmd 0xFF turns relay n on, 0xFD off; 0xFE and
0xFC switch all of them. The state is the last byte of a 9-byte feature read,
one bit per relay. ⚠️ The `hid` package counts the report-ID byte in its
size: ask for 8 and you lose the state byte.

The board names itself "USBRelay4" but has two relays, so bits 3 and 4 switch
nothing. ⚠️ The slider must be on BT or 2.4G: on cable, cutting VBUS is a
cold power-off, and the battery log in RAM is lost.
"""
import sys

import hid

VID, PID = 0x16C0, 0x05DF
NRELAYS = 2


def read_state(dev):
    raw = dev.get_feature_report(0, 9)
    if len(raw) != 9:
        sys.exit(f"short feature report ({len(raw)} bytes): {raw.hex(' ')}")
    return raw[8]


def describe(state):
    return ", ".join(f"relay {i + 1} {'ON' if state >> i & 1 else 'off'}"
                     for i in range(NRELAYS))


def main(argv):
    devs = hid.enumerate(VID, PID)
    if len(devs) != 1:
        sys.exit(f"expected one USB relay ({VID:04x}:{PID:04x}), found {len(devs)}")
    with hid.Device(path=devs[0]["path"]) as dev:
        if argv == ["status"]:
            print(describe(read_state(dev)))
            return
        if len(argv) != 2 or argv[0] not in ("on", "off"):
            sys.exit(__doc__)
        on = argv[0] == "on"
        if argv[1] == "all":
            cmd, n = (0xFE if on else 0xFC), 0
        else:
            n = int(argv[1])
            if not 1 <= n <= NRELAYS:
                sys.exit(f"relay must be 1..{NRELAYS} or all")
            cmd = 0xFF if on else 0xFD
        dev.send_feature_report(bytes([0, cmd, n, 0, 0, 0, 0, 0, 0]))
        state = read_state(dev)
        print(describe(state))
        mask = (1 << NRELAYS) - 1 if n == 0 else 1 << (n - 1)
        got = state & mask
        if got != (mask if on else 0):
            sys.exit("read-back does not match the command")


if __name__ == "__main__":
    main(sys.argv[1:])
