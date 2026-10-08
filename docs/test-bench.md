# Test bench: cutting the keyboard's USB power from the host

What this is for: charge and unplug trials that do not need JD to pull a
cable. The host cuts the keyboard's USB power, restores it, and timestamps
both from the USB side. Set up and measured 2026-10-08 on JD's Mac.

## The short version

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

- **Use a blue 10Gb USB-A port, or a USB-C port not marked PD 30W.** The
  keyboard only uses USB full speed, so any of these does.
- **Not the USB 2.0 ports, and probably not the PD 30W ports.** They hang off
  an extra USB 2.0 hub chip one level deeper, whose ports macOS never sets up
  (next section). The keyboard would charge there but never appear to the
  host, so a cut could not be confirmed.
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
