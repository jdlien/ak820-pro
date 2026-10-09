# Test bench: cutting the keyboard's USB power from the host

What this is for: charge and unplug trials that do not need JD to pull a
cable. The host cuts the keyboard's USB power, restores it, and timestamps
both from the USB side. Set up and measured 2026-10-08 on JD's Mac.

## The short version

- **For the keyboard's charging, use the USB relay**
  ([below](#the-usb-relay-the-keyboards-charging-from-the-host), since 18:30
  10-08). It cuts only the keyboard's 5 V, the keyboard stays on USB, and the
  host switches it. The outlet is for cutting the whole hub.
- The keyboard goes on JD's **Acasis 16-port hub**. The hub's power brick is
  plugged into a **HomeKit smart outlet named "Christmas Tree"**. Without its
  brick the hub has no USB at all, so cutting the outlet cuts every port.
- Two Shortcuts in JD's Shortcuts app switch the outlet, and they run from a
  terminal:

  ```sh
  shortcuts run "Turn off Christmas Tree"   # the hub and everything on it lose power
  shortcuts run "Turn on Christmas Tree"
  ```

  Each returns in about 1 s. Measured: the hub was gone from USB within 1 s
  of "off". After "on", its first chip was back in 3 s and all six main chips
  in 5 s.
- ⚠️ **It cuts the whole hub.** Anything else plugged into it goes down too.
- ⚠️ **The slider must be on BT or 2.4G, never cable, during a cut.** On
  cable, a cut is a cold power-off ([hardware.md](hardware.md), the slider
  section), and the battery log in RAM is lost ([battery.md](battery.md)).
- ⚠️ **`uhubctl` cannot do this.** On this hub it switches a port's data off,
  never its 5 V, on every kind of port (tested below).
- **By hand:** hold a port's button for more than 1 s. That cuts that port's
  5 V. A bus-powered device then drops off USB, but **the keyboard stays on USB
  over data alone** and simply stops charging (next section).
- ⚠️ The outlet is named for what it powers in December. Check nothing else
  is plugged into it before running the shortcuts.

## The USB relay: the keyboard's charging, from the host

Set up 18:30 10-08. **This is how to control the keyboard's charging.** Unlike
the outlet, it cuts only the keyboard's 5 V, the keyboard never leaves USB,
and the rest of the hub stays up. Unlike the port buttons, the host switches
it.

**The hardware.** A DCT Tech USB HID relay (`16c0:05df`, the board JD's
`hdd-toggle` drives) sits on the Thunderbolt dock's built-in hub (`0-1.4`
port 3). It names itself "USBRelay4" but has two relays.
- A USB cable's red 5 V wire runs through **RELAY2** (silkscreened on the
  board), between COM and NO. The cable's data wires bypass the relay.
- The cable's host end is on the dock's built-in hub too (`0-1.4` port 2 on
  10-08).
- **Off is the safe state.** If the relay board loses power or is unplugged,
  its contacts open and the keyboard stops charging.

**Switching it.** No driver is needed: it is a plain HID device, and the script
opens only its VID/PID. Each switch is read back from the relay's state byte,
and the script exits 0 only if the read-back matches.

```sh
venv/bin/python scripts/usb_relay.py status
venv/bin/python scripts/usb_relay.py on 2     # VBUS: the keyboard charges
venv/bin/python scripts/usb_relay.py off 2    # no VBUS: on battery, still on USB
```

**Measured 18:28 10-08, with a bus-powered ESP32 on the cable:** it left USB
within 1 s of `off 2` and was back within 1 s of `on 2`, in both directions,
twice. Relay 1 has nothing wired to it: `on 1` did nothing.

**Verified with the keyboard, 18:32:35 10-08.** It moved onto the relay cable
at ~18:31, and had no VBUS on either side of the move: its Acasis port's
button was off. With relay 2 off, it enumerated on `0-1.4` port 2 and one
`ak820battery.py` read gave:
- `supply battery`, flags `on_batt`;
- CHRG high (not charging);
- VDD 3897 mV, the pack's regulator rather than USB;
- level 7.8 %, pack 3634 mV, mid-drain to the RGB cut.

⚠️ **While the keyboard is on the relay cable it is not on the Acasis, so the
outlet no longer reaches it.** `scripts/bench_power.py off` would cut the hub,
wait for the keyboard to leave the bus, and fail, because the keyboard stays
on the dock. Use the relay.

**With the keyboard on the cable:**
- ⚠️ **The slider must be on BT or 2.4G.** On cable the MCU runs from VBUS,
  so `off 2` is a cold power-off.
- **`off 2`:** the keyboard stays enumerated over data alone (next section),
  runs on battery and does not charge. The host can still read it, and
  `venv/bin/python hostagent/ak820battery.py` prints `supply battery`.
- **`on 2`:** VBUS appears and the keyboard charges. The same read prints
  `supply external (USB)`.
- **Confirm a switch from the board, not from USB.** The keyboard stays on the
  bus either way, so the IORegistry check below cannot see this cut. One
  `ak820battery.py` read after the switch is the check. It is board traffic,
  so read once, not in a loop; the Mac's agent already samples health every
  5 minutes.
- **Every `on` is a plug-in to the battery gauge.** It re-arms the low-battery
  warning, and the next `off` is an unplug, which can re-seat the level
  ([battery.md](battery.md)). Plan trials around that, and log the times.

What it buys: charge for exactly N minutes, or hold the board on battery and
read it whenever needed, all from the host. That is B3's partial-charge trial
without anyone pulling a cable.

## A port switched off still carries data: reading the board on battery

**Measured 10-08, and it corrects "cuts power and data" below.** A port's button
cuts the 5 V (VBUS), but not the data lines. A bus-powered device like the
ESP32 dies with its VBUS, so it leaves USB whether or not the data was cut; the
tests here could never tell the two apart. The keyboard runs on its own
battery and does not check VBUS before connecting, so on a switched-off port it
**enumerates over data alone and does not charge**:
- 15:41-16:10 10-08 it sat on a switched-off PD 30W port. The Mac's agent
  synced its clock and read its health, and its battery log's entries for that
  window all say on battery, not charging, no external power.
- At 16:18 a read over a switched-off port gave supply battery, CHRG high and
  VDD 3899 mV (the pack's regulator, not USB).

**So the board can be read and dumped while it discharges, without charging
it.** Before this, every read was a plug-in that charged it and disturbed the
run. Two caveats:
- It is not quite "unplugged": USB is active, and the Mac's agent talks to the
  board (clock syncs, health reads every 5 min, now-playing text). The LEDs
  dominate the load, so this is small, but it is not zero.
- The outlet cannot reach a keyboard on a switched-off port: a run needs the
  port **on** for the outlet to switch charging, and **off** to read without
  charging. Only the button moves between the two.

## Truly unplugged, from software: the relay plus `uhubctl` (proven 10-09)

The relay cuts the keyboard's 5 V. `uhubctl` cuts the data on the port the
relay cable plugs into. Here that is the dock's hub `0-1.4`, port 2; port 3
is the relay itself and port 4 JD's Stream Deck, so name the port. With both
off, the keyboard is unplugged except for the ~0.2 mA its D+ pull-up drives
into the hub's pull-down.

```sh
uhubctl -l 0-1.4 -p 2 -a off -e   # data off; -e: this hub only, no USB3 twin
uhubctl -l 0-1.4 -p 2 -a on  -e
```

- **Measured 13:10-13:11 10-09**, with relay 2 off and the board on battery:
  - `off` at 13:10:28.34: the keyboard left USB 0.9 s later;
  - `on` at 13:11:29.28: back 0.7 s later, with no hang;
  - the board stayed on battery and linked throughout.
- **Check the port map first** (`uhubctl -l 0-1.4`, status only) after any
  re-cabling, and run it under a timeout: an `-a on` once hung on macOS.
- **In software, the keyboard can now be:** unplugged (both off), data-only
  (relay off, port on), or charging and readable (both on).

## Confirm every cut from the USB side

`shortcuts run` returns 0 once HomeKit accepts the request, not once the
outlet has switched. Treat the shortcut as a request, and confirm it by
watching the keyboard leave and rejoin the bus:

```sh
ioreg -p IOUSB -w0 | grep -c 'AK820 PRO@'    # 1 = present, 0 = gone
```

This reads the IORegistry only and opens no device, so it is safe under the
never-enumerate-HID rule. Polling it every 0.25 s gave 1 s timestamps on
10-08. `date +%T` has no milliseconds and this Mac has no `gdate`, so use
`python3 -c 'import time; print(time.time())'` or `perl -MTime::HiRes` if
sub-second stamps matter.

## Where to plug the keyboard

The hub (JD, 10-08) has a USB-C upstream port and, downstream:
- 8 USB-C ports, two of them marked **PD 30W**;
- 6 blue **10Gb** USB-A ports;
- 2 **USB 2.0** USB-A ports, one of them on the end face.

There is a button with a blue LED for every port. The power brick is rated
150 W.

- **Use a blue 10Gb USB-A port or any USB-C port.** The keyboard only uses
  USB full speed, so any of these does. The PD 30W ports carry data too: the
  keyboard enumerated on one from 15:41 to 16:10 10-08.
- **Not the USB 2.0 ports.** They hang off an extra USB 2.0 hub chip one level
  deeper, whose ports macOS never sets up (next section). The keyboard would
  charge there but never appear to the host, so a cut could not be confirmed.
- **Known mapping:** the first USB-C port at the far end is the top chip's
  port 4 (USB2 `1-1.4` port 4 when the hub is on the Studio Display). An ESP32
  in a USB-A port came up on the USB 2.0 chip's port 2. Which USB-A port that
  was is not pinned down.

## Hub depth: why some ports carry no data

Inside, the hub is a tree of seven hub chips:
- one VIA VL822 (`2109:2822`/`0822`) at the top;
- two below it;
- three below the second of those;
- a USB 2.0-only VIA hub (`2109:2122`, "USB2.0 Hub C0", ganged power) on
  port 3 of the last bottom chip.

**On this Mac, macOS does not create a port, and so carries no data, where a
device's path from the root port would be six hops.** That is where its
`locationID` would need a sixth port nibble. Seen as `AppleUSB20HubPort` /
`AppleUSB30HubPort` objects missing in the IOService plane: the hub driver
attaches, but its ports never appear. The hubs inside a dock or display count
toward the six:

| Hub's upstream | Hubs inside it (USB2 / USB3) | Bottom chips' ports | USB 2.0 chip's ports |
|---|---|---|---|
| Thunderbolt dock | 2 / 2 | no data | no data |
| Studio Display | 1 / 2 | USB 2.0 data; USB3 devices run at USB 2.0 speed | no data |
| MacBook Pro directly | 0 / 0 | full (not tried) | should work (not tried) |

The Mac has no free port, so the hub lives on a Studio Display. The ports
that came up "half off" at power-up on the dock were this too: macOS never
set them up, so they sat in the hub's reset state.

## `uhubctl`: what it can and cannot do here (tested 10-08)

- Every VL822 reports per-port power switching (`ppps`). An `-a off` sticks,
  because macOS does not undo it, and the port's data goes away.
- **The 5 V does not go away.** An ESP32 dev board's LED stayed lit through
  both of these:
  - on a fast port (the top chip's port 4), with both halves off for 10 s;
  - on the USB 2.0 chip, whose ports read off for an hour while the LED stayed
    lit.

  The buttons drive the per-port power switches. The chips' power-enable pins
  evidently do not.
- ⚠️ **On the Studio Display, uhubctl pairs the USB2 and USB3 halves
  wrongly.** All the VL822s report the same container ID, and the display's
  USB3 side is one hub deeper than its USB2 side. uhubctl's path match fails,
  and it falls back to the first hub with that container ID and port count.
  `uhubctl -l 1-1.4` paired with the dock's `0-2.4`, whose port 1 carries the
  dock's Ethernet and card reader. On the display, use `-e` and name both
  halves: USB2 `1-1.4[.x[.y]]`, USB3 `1-2.4.4[.x[.y]]`. Check the pairing
  (a status-only `uhubctl -l X` prints both halves) after any re-cabling. On
  the dock the pairing was right.
- ⚠️ **Always pass `-l`.** Without it, `-p 4 -a off` hits port 4 of every
  hub, including whichever one the keyboard is on.
- On macOS, an `-a on` for a USB2 port with a device on it hung *after* it
  had worked. Run uhubctl under a timeout.

## An automated trial

`scripts/bench_power.py on|off|status [--log CSV]` does steps 2 and 3:
it runs the shortcut, confirms on the bus, retries once (a shortcut can hang:
one 'Turn on' sat 60 s and did nothing), and logs both times. The rest is
notes. A trial driver could:

1. Start once JD has set the slider to BT and confirmed the outlet carries
   only the hub.
2. **Cut:** run "Turn off Christmas Tree", poll `ioreg` until `AK820 PRO@` is
   gone, and log that time. If it has not gone within ~5 s, retry once, then
   abort and say so.
3. **Restore** at the planned time: "Turn on Christmas Tree", poll until the
   keyboard re-enumerates, and log that time.
4. Leave board traffic to whatever the trial already does. The cut and the
   check above touch no HID.

What it buys: B3-style partial-charge trials and relaxation runs whose
unplug and replug times come from the host, not from JD's notes or the video.
