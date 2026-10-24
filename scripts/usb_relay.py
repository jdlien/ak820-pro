#!/usr/bin/env python3
"""Switch the bench's USB relay: the keyboard's charging, without its data,
and the wake rig's key (docs/test-bench.md, "The USB relay").

A DCT Tech HID relay (VID 16c0, PID 05df), two relays:
- RELAY1, `key`: wired across one key's switch (F19, the wake rig). On holds
  the key down; `tap` presses it once.
- RELAY2, `power`: a USB cable's 5 V wire runs through its COM and NO, and its
  data wires bypass the relay. Off: no VBUS, so the keyboard stays enumerated
  over data alone, on battery, NOT charging. On: VBUS, so it charges.

  usb_relay.py status
  usb_relay.py on R | off R | toggle R    R = 1, 2, key, power, or "all" (on/off)
  usb_relay.py tap [ms]                   press the key once: relay 1 closed
                                          for ms (default 100), then open

`scripts/relay` runs this from anywhere (`relay tap`, `relay off power`).

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
cold power-off, and the battery log in RAM is lost. ⚠️ A bench run (the
trial, the maps, the sleep runs) owns the relay while it runs: switching it
underneath one spoils the run.
"""
import sys
import time

import hid

VID, PID = 0x16C0, 0x05DF
NRELAYS = 2
NAMES = {"key": 1, "power": 2}
ROLES = {1: "key", 2: "power"}
TAP_MS_DEFAULT, TAP_MS_MAX = 100, 2000
USAGE = """usage: relay status
       relay tap [ms]                  press the key (F19) once, default 100 ms
       relay on|off key|power|1|2|all  key: hold F19; power: the keyboard's 5 V
       relay toggle key|power|1|2
       (either order: `relay power on` works too)
(power off = on battery; keep the slider on BT or 2.4G. Details: scripts/usb_relay.py)"""


def read_state(dev):
    raw = dev.get_feature_report(0, 9)
    if len(raw) != 9:
        sys.exit(f"short feature report ({len(raw)} bytes): {raw.hex(' ')}")
    return raw[8]


def describe(state):
    # "relay 2 ON" is what current_map.py looks for: keep the form.
    return ", ".join(f"relay {i + 1} {'ON' if state >> i & 1 else 'off'} ({ROLES[i + 1]})"
                     for i in range(NRELAYS))


def relay_number(arg, allow_all):
    """1 or 2 from a number or a name; 0 for "all" where that is allowed."""
    if allow_all and arg.lower() == "all":
        return 0
    n = int(arg) if arg.isdigit() else NAMES.get(arg.lower())
    if n is None or not 1 <= n <= NRELAYS:
        sys.exit("relay must be 1, 2, key, power or all" if allow_all else "relay must be 1, 2, key or power")
    return n


def switch(dev, n, on):
    """Relay n on or off (n 0: all of them); exits unless the read-back agrees."""
    cmd = (0xFE if on else 0xFC) if n == 0 else (0xFF if on else 0xFD)
    dev.send_feature_report(bytes([0, cmd, n, 0, 0, 0, 0, 0, 0]))
    state = read_state(dev)
    mask = (1 << NRELAYS) - 1 if n == 0 else 1 << (n - 1)
    if state & mask != (mask if on else 0):
        print(describe(state))
        sys.exit("read-back does not match the command")
    return state


def main(argv):
    # Either order: `relay power on` reads as naturally as `relay on power`.
    if len(argv) == 2 and argv[1] in ("on", "off", "toggle") and argv[0] not in ("on", "off", "toggle"):
        argv = [argv[1], argv[0]]
    devs = hid.enumerate(VID, PID)
    if len(devs) != 1:
        sys.exit(f"expected one USB relay ({VID:04x}:{PID:04x}), found {len(devs)}")
    with hid.Device(path=devs[0]["path"]) as dev:
        if argv == ["status"]:
            print(describe(read_state(dev)))
            return
        if argv and argv[0] == "tap" and len(argv) <= 2:
            ms = int(argv[1]) if len(argv) == 2 else TAP_MS_DEFAULT
            if not 1 <= ms <= TAP_MS_MAX:
                sys.exit(f"tap: 1..{TAP_MS_MAX} ms")
            if read_state(dev) & 1:
                sys.exit("relay 1 is already on (the key is held): `off key` releases it")
            switch(dev, 1, True)
            time.sleep(ms / 1000)
            print(describe(switch(dev, 1, False)) + f"  (key pressed {ms} ms)")
            return
        if len(argv) == 2 and argv[0] == "toggle":
            n = relay_number(argv[1], allow_all=False)
            print(describe(switch(dev, n, not read_state(dev) >> (n - 1) & 1)))
            return
        if len(argv) == 2 and argv[0] in ("on", "off"):
            print(describe(switch(dev, relay_number(argv[1], allow_all=True), argv[0] == "on")))
            return
        sys.exit(USAGE)


if __name__ == "__main__":
    main(sys.argv[1:])
