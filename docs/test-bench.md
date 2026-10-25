# Test bench: cutting the keyboard's USB power from the host

What this is for: charge and unplug trials that do not need JD to pull a
cable. The host cuts the keyboard's USB power, restores it, and timestamps
both from the USB side. Set up and measured 2026-10-08 on JD's Mac.

## The short version

- **The new Mac, from 10-23.** The bench moved to the Acasis, on bus 3:
  - the keyboard's relay cable: hub `3-1.3.4` port 2;
  - ⚠️ the UPS (`CP1000AVRLCDa`): the same hub's port 4, so name the port.
    A wrong `-p` drops the UPS off the Mac, and with it the Mac's shutdown
    signal;
  - the relay and the 2.4G dongle: the hub on port 3 (`3-1.3.4.3`, ports 1
    and 2);
  - the QT Py: `3-1.3.3` port 2.

  `0-1.4`, the dock's hub on the old Mac, does not exist here. The scripts
  pass `-e`, so a stale location fails instead of cutting something else.
  The wake rig is gone: a lead tore off its switch on 10-23, so relay 1
  presses nothing.
- **The bench's tools at a glance (10-16):** relay 2 switches the
  keyboard's charging; relay 1 presses a key (the wake rig, below; broken
  10-23);
  `uhubctl` cuts its USB data; the power logger measures the pack; the
  lighting and the screen's backlight are set from the Mac; and a listener
  times every rig keystroke's arrival. Everything but the wiring runs
  without JD's hands.
- **For the keyboard's charging, use the USB relay**
  ([below](#the-usb-relay-the-keyboards-charging-from-the-host), since 18:30
  10-08). It cuts only the keyboard's 5 V, the keyboard stays on USB, and the
  host switches it. The outlet is for cutting the whole hub.
- The keyboard goes on JD's **Acasis 16-port hub**. The hub's power brick is
  plugged into a **smart outlet named "Christmas Tree"**. Without its brick
  the hub has no USB at all, so cutting the outlet cuts every port.
- **Home Assistant switches the outlet** (`switch.christmas_tree`, since
  2026-10-13; before that it was in Apple Home, and two Shortcuts switched it,
  one of which once hung for 60 s). From a terminal:

  ```sh
  scripts/bench_power.py off   # the hub and everything on it lose power
  scripts/bench_power.py on    # both confirm on the bus (below)
  ```

  HA accepts the call in about 0.2 s. Measured (with the Shortcuts, 10-08):
  the hub was gone from USB within 1 s of "off". After "on", its first chip
  was back in 3 s and all six main chips in 5 s.
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
  is plugged into it before cutting it.

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
- **RELAY1 presses a key** (from 10-16): the wake rig,
  ["The wake rig"](#the-wake-rig-relay-1-presses-a-key-10-16) below.
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

**By hand, from any folder: `relay`** (`scripts/relay`, linked into `~/bin` on
JD's Mac; `ln -s "$PWD/scripts/relay" ~/bin/relay` elsewhere). The relays go
by name: `key` is relay 1 (the wake rig's F19), `power` relay 2.

```sh
relay status            # relay 1 off (key), relay 2 ON (power)
relay tap [ms]          # press F19 once (default 100 ms)
relay off power         # on battery; `relay on power` charges again
relay toggle key        # hold F19 down / let it go
```

Every switch is read back, and `tap` refuses while the key is already held.
⚠️ Not during a bench run: the trial, the maps and the sleep runs own the
relay while they run.

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
relay cable plugs into. On the new Mac (from 10-23) that is the Acasis's
hub `3-1.3.4`, port 2; port 3 is the hub holding the relay and the 2.4G
dongle, and port 4 the UPS, so name the port. On the old Mac it was the
dock's hub `0-1.4`, port 2. With both off, the keyboard is unplugged except
for the ~0.2 mA its D+ pull-up drives into the hub's pull-down.

```sh
uhubctl -l 3-1.3.4 -p 2 -a off -e   # data off; -e: this hub only, no USB3 twin
uhubctl -l 3-1.3.4 -p 2 -a on  -e
```

`uhubctl` comes from Homebrew (`brew install uhubctl`); `setup.sh` does not
install it.

- **Measured 13:10-13:11 10-09**, with relay 2 off and the board on battery:
  - `off` at 13:10:28.34: the keyboard left USB 0.9 s later;
  - `on` at 13:11:29.28: back 0.7 s later, with no hang;
  - the board stayed on battery and linked throughout.
- **Check the port map first** (`uhubctl -l 3-1.3.4`, status only) after any
  re-cabling, and run it under a timeout: an `-a on` once hung on macOS.
  macOS has no `timeout`; `perl -e 'alarm 10; exec @ARGV' uhubctl …` works.
  ⚠️ On 10-15 that status call printed nothing within 10 s, with the keyboard
  still on port 2 (`ioreg`: `AK820 PRO@00142000`). Recheck before a trial
  relies on the data cut.
- **In software, the keyboard can now be:** unplugged (both off), data-only
  (relay off, port on), or charging and readable (both on).
  - ⚠️ **Data-only never deep-sleeps:** a host's frames on the bus block it
    (`DSB_USB` in sleep.c). On the night of 10-21/22 it sat awake and dark
    at ~28 mA for 8 h instead of ~3 mA. A battery run meant to match real
    use cuts both.
- ⚠️ **A killed run leaves the keyboard unplugged.** The sleep scripts
  (`deep_cycles.py`, `deep_sleep.py`, `idle_latency.py`,
  `sleep_baseline.py`) restore the bench in a `finally`, and their deadline
  guard is a thread in the same process. Neither survives the process being
  killed. On 10-18 an interrupted `deep_cycles.py` left relay 2 and the data
  off from 20:57 until 22:43: the board ran on the pack, awake (27.5 mA),
  out of the daemon's reach, and every later script would have refused to
  start ("relay 2 is off"). After killing one, check `usb_relay.py status`
  and `uhubctl -l 3-1.3.4 -p 2`, then put back what the `finally` would have,
  power first: relay 2 on (a board stopped asleep wakes when charging
  starts; with a full pack, press a key: the rig is gone), data on, the arm cancelled (op 14
  sub 4, arg 2), the bench sleep time cleared (op 14 sub 5, 0 ms), the mode
  put back (op 14 sub 1; the run prints the one it found), the stage
  released.

## Confirm every cut from the USB side

Home Assistant accepts the call before the outlet has switched. Treat it as
a request, and confirm it by watching the keyboard leave and rejoin the bus:

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
it asks Home Assistant, confirms on the bus, retries once, and logs both
times. The rest is
notes. A trial driver could:

1. Start once JD has set the slider to BT and confirmed the outlet carries
   only the hub.
2. **Cut:** switch the outlet off, poll `ioreg` until `AK820 PRO@` is
   gone, and log that time. If it has not gone within ~5 s, retry once, then
   abort and say so.
3. **Restore** at the planned time: switch it on, poll until the
   keyboard re-enumerates, and log that time.
4. Leave board traffic to whatever the trial already does. The cut and the
   check above touch no HID.

What it buys: B3-style partial-charge trials and relaxation runs whose
unplug and replug times come from the host, not from JD's notes or the video.

### On the relay: `bench_trial.py` and `trial_guard.py`

The driver that replaced the notes above. `scripts/bench_trial.py` runs a
trial on the USB relay end to end: wait for the RGB cut, charge N minutes,
relax, charge to FULL. It confirms every switch with the board's `supply`
line and turns the relay off on any failure. Its docstring lists the phases.

⚠️ It dies with the session that launched it, and a drain runs ~2 days. With
the relay off, a dead driver leaves the board running down through the cut
and its reserve, and the RAM log goes with it. `scripts/trial_guard.py --pid
<the trial's pid> --csv <its --out>` detaches itself (PPID 1) and watches the
trial's CSV:
- if the trial dies before the cut, it restarts it as `<name>-resumed-N.csv`;
- if it dies after the cut, before FULL-ON, it dumps the log unless the trial
  did, then turns relay 2 on;
- **progress, not just survival (10-15, codex):** before the cut, 45 min
  (`--stall-min`) without a successful board read stops the trial and turns
  relay 2 ON, so a stuck run charges the pack instead of draining it through
  the reserve unwatched; a FAIL before FULL-ON also ends with the relay ON
  (the trial's own `fail()` turns it off); 16 h (`--charge-h`) after FULL-ON
  without `done` stops the trial, relay left on;
- **an activity row after every successful drain poll** (10-15):
  `guard-activity.csv`, one light read (`read_stalls`, one transaction):
  key presses (16-bit, reset by a reboot), stalls ≥ 25 ms. JD's idle pattern
  for the power ladder, and a running stall watch. A failed read is a blank
  row, never zero presses.

The guard also takes gate 8's per-event reads that the trial does not: the
stall counters and the display probe at "Battery low" (`cfg` says `warned 1`)
and at the cut, the latter in the 60 s between the trial's dump and its
relay-on, so the plug-in is not in it. Each read goes right after one of the
trial's own: raw HID is exclusive on macOS, and two readers at once fail.
First used on the 10-12 drain (`history/battery-2026-10-12-drain-2e/`).

**Launch both detached** so they outlive the session (the 10-15 drain,
`history/battery-2026-10-15-drain-2f/README.md`): the trial through a
double fork (its pid in `trial.pid`), then the guard, then `caffeinate -i -s
-w <guard pid>`. **Start a drain from a verified FULL:** `bench_trial.py
--full` first, then relay 2 off at a logged moment, recording the power
logger's charge register there. **Other tools between the trial's reads:**
each waits for 20 s after the trial's latest row and must finish 30 s
before the next (`--trial-csv`).

## The power logger: an INA228 and a MAX17048 on the pack (10-13; on the pack since 10-15)

The bench measures the pack directly, beside the board's own `5C`. A QT Py
RP2040 running CircuitPython 10.3.1 reads two breakouts over STEMMA QT:
- an **INA228** (Adafruit 5832, 0x40) in series on the pack's + lead;
- a **MAX17048** (Adafruit 5580, 0x36) across the pack.

`scripts/qtpy/code.py` and `boot.py` live on the QT Py's `CIRCUITPY` drive.
`boot.py` turns off CircuitPython's USB keyboard and mouse, so the board is
serial only, never HID. The QT Py streams one line of raw integers a second.
`scripts/power_log.py --out <csv> --detach` timestamps them on the Mac and
converts them, finding the QT Py by its USB ids (Adafruit `239a`).

⚠️ **During a drain, run it as a LaunchAgent:** `scripts/power_log_agent.sh
install [csv]` (`status`, `uninstall`; label `com.jdlien.ak820pro.powerlog`).
A recorder started from a cmux shell dies when cmux restarts, even detached:
at 14:11:47 10-24 the drain lost 4.9 h of rows that way. The agent restarts
it within 10 s if it exits and again at login. Moving to it lost no row.
Only one recorder may run: `power_log.py` locks the CSV and opens the port
exclusive, so a second one refuses; two would each get some of the QT
Py's lines and interleave them in one file.

**In service since 10-15**, with the keyboard back in JD's daily use: the
pack's lead comes out of the reassembled case to the harness, and the board
runs as it always does. That makes three USB ports for a keyboard built to
need none. On the new Mac (from 10-23): the keyboard on its relay cable
(hub `3-1.3.4` port 2), the relay (`3-1.3.4.3` port 1) and the QT Py
(`3-1.3.3` port 2). On the old Mac they were on the dock's hub: `0-1.4`
ports 2 and 3, and `0-1.4.1` port 4.

**What to read for what:** current and mAh from the INA228 (`current_ma`,
`charge_mah`); the pack's voltage from the MAX17048 (`vcell_mv`), not the
INA228's `vbus_mv` (below).

**Measuring a load from the Mac (10-15):**
- `scripts/current_map.py --log <power.csv>`: on battery (it switches relay
  2), steps the lighting (VIA's channel, `_noeeprom`, RAM only) and the
  screen's backlight (`HC_DEVHOOK` ops 4-6, flash 2f, RAM only), forward
  then backward, and takes each state's current from the charge register;
  restores both and the relay after.
  `--set rgb-curve` (Phase 2): white at 14 values and the three colours,
  each with the board's LED drive read back; `--set stages`: the ladder's
  stages forced (`HC_DEVHOOK` op 14) at three lightings, each beside the
  board's own modelled draw (`HC_POWER`), and JD's lighting typing in Power
  saver (`jd saver`, at its 128 ceiling: ~161 mW with the USB data, ~154
  untethered). On Phase 2 firmware every map holds a mode (Always on but for
  `jd saver`) and a forced stage, so the ladder cannot move a load
  mid-hold. ⚠️ It refuses at a level of 15% or below, before and during the
  run: a held stage keeps the low cap's stages out but not its ceiling, Power
  saver's 128 while typing in every mode. The stage map also needs a known
  level and a dev build, and it reads op 14 back at each hold's start and
  end: a mode, stage or ceiling other than the one meant stops the run, since
  the logger would be measuring the wrong load.
- `scripts/ladder_check.py [--rig]` (Phase 2, and the modes' revision): on
  USB, the LED drive read back, op 14 read back after a tick:
  - every enabled effect through every forced stage in Always on: off must
    read 0.0%;
  - Power saver's ceiling per effect, ACTIVE held in Always on and in Power
    saver at value 255 and 100: at 255 Power saver at most 0.35 of Always on
    for the effects that convert at the user's value (DRIFT 0.70), at 100 the
    two alike; solid white at 255 in Power saver within 5% of white at 128;
  - a reference that reads 0 fails, so a dead renderer or a stuck reading
    cannot pass;
  - every effect at speed 255, and each hold's mean taken over samples 1.2 s
    apart (the board's figure is a second's), with a tolerance for the
    animated effects;
  - Typing Heatmap lights only pressed keys, so `--rig` taps the relay's key
    through its holds; without it the Heatmap is reported, not judged, and
    the run ends INCOMPLETE (exit 2);
  - about 18 minutes. The lighting, the mode and any stage held at the start
    are put back step by step; a failed step exits 1.
- `scripts/devhook.py lcd [LEVEL | on | off]`: the screen's backlight by
  hand.
- **Results** (`plans/POWER-CAMPAIGN-PLAN.md`, R1 and R2), at 4.17 V: JD's
  settings 73.5 mA, RGB off 28.3, every light out 27.3; the RGB is 45 mA of
  JD's 73.5, 10 mA at brightness 128; the backlight ~9.4 mA at full, linear
  in its duty, ~1 mA at JD's level 5. **USB data attached costs ~1.7 mA**
  (73.9 against 72.15 untethered, `uhubctl`). **The board is a
  constant-power load, ~307 mW** at JD's settings: its current rises as the
  pack falls (73.6 mA at 4.16 V, 75.2 at 4.09; R3, 10-16).

- **INA228 settings:** the ±40.96 mV range; 15 mΩ shunt (`R015` on the part,
  and Adafruit's driver default); `CURRENT_LSB` 5 µA; continuous bus, shunt
  and die temperature, 1052 µs each, 64× averaging (a result every ~200 ms;
  bus + shunt only, ~135 ms, until 10-15). Its **charge register integrates
  without gaps between rows**: use it, not the 1 s samples, for mAh. It
  clears only when the QT Py loses power; the script never resets it, and a
  soft reload of `code.py` does not clear it. Rechecked with the
  temperature on (10-15, nothing on the harness, 15.8 min): the register
  averaged 0.0258 mA against the 1 s samples' 0.0261 mA (ratio 0.990, about
  ±2% at this current; 0.998 in the old mode just before). So it still
  covers the whole cycle; a gap would read well below 1.
- **`temp_c` is the INA228's die (since 10-15): the logger board, not the
  cell.** It reads the room near the board (23.2 °C at 15:55 10-15, nothing
  flowing). It is there for context, since capacity and the voltage curve
  move with temperature; nothing uses it yet.
- **The QT Py's LED says whether the run is being recorded (10-15):** dim
  green while the Mac has its serial port open and the INA228 answers; amber
  while no one reads it (the recorder stopped, or the Mac asleep), so rows go
  nowhere; red while the INA228 does not answer. Amber is expected between
  runs, when nothing records.
- **The header repeats every minute, and the recorder checks each one** (the
  `current` LSB and the `temp` scale it converts with; a mismatch stops it).
  Until 10-15 the QT Py sent one header, at start, and the check never ran:
  CircuitPython's status bar puts its title-bar escape codes
  (`ESC ] 0; … ESC \`) in front of that line, so it never parsed as `H`. The
  recorder strips them now. It also reports a row of the wrong length
  (once a minute) instead of dropping it silently, and refuses to append to a
  CSV with other columns, so a column change means a new file.
- **Its zero with the harness on and nothing flowing:** −0.064 mA (−0.97 µV),
  sd 0.016 mA per row, and the charge register agrees (10-14). That is
  nothing over a charge (~0.6 mAh in 9 h) and matters only for standby floors.
- **Sign:** + while the board runs on the pack (out of the pack), − while
  charging. The 10-15 harness first had the pack on Vin− (−74 mA raw on
  battery, 20:53), so JD swapped the two + wires at the terminal block
  (~20:59); checked at 21:01, +74 mA on battery and −136 mA charging.
  `power_log.py`'s `SHUNT_SIGN` (+1) is there if it is ever wired the other
  way again; the QT Py's lines stay raw. The INA228 measures both ways, so
  the wrong way round stresses nothing.
- ⚠️ **The INA228's VBUS reads ~215 mV low (10-15), cause not found.**
  Against the MAX17048's VCELL it was 214-215 mV low at −74, 0 and +145 mA
  alike, so it is not a drop in the harness, and still ~213 mV low with VBUS
  on the pack side after the + swap. The board agrees with the
  MAX17048: its `5C` sat at the clamp (≥ 4036 mV) while VBUS said 3947.
  Adafruit's schematic (`Adafruit-INA228-PCB`, the `.sch`) puts nothing else
  on VBUS: the chip's pin, header pin 5, the jumper `SJ1` to VIN+, and the
  **middle position of the screw terminal** (VIN−, VBUS, VIN+ in order). The
  INA228's VBUS input is ~1 MΩ (0.8-1.2, TI's datasheet), so reading 5.1% low
  takes ~54 kΩ in series, which a solid solder bridge cannot be; a joint
  that never wetted one pad could. **Not `SJ1`:** JD wired the VIN+ screw
  to the middle (VBUS) screw (~21:31-21:32 10-15), bypassing it, and VBUS
  stayed 214.5 mV below VCELL. So the INA228 itself reads VBUS ~5.1% (or
  ~214 mV) low; the current channel looks right (74 mA on battery, as the
  board's ~50 h runtime implies). **Take the pack's voltage from
  `vcell_mv`**; the next drain, checked against `5C` below the clamp, says
  whether VBUS is off by a ratio or a fixed amount.
- **The shunt is a 1% part** per the schematic (`HoLLR2512-2W-15mR-1%`),
  though Adafruit's README says 0.1%. So the mA scale is good to ~1% unless
  checked against a known load.
- **The MAX17048 runs from the cell it measures,** so it is absent until a
  pack is on it. The script rewrites `HIBRT` = 0 every read, so it never
  hibernates and `VCELL` stays fresh.
- ⚠️ **High-side needs VBUS tied to V+.** The board ships low-side, with the
  jumper open; JD's unit has V+ and VBus bridged.
- **The harness is 1.0 mm SH (10-15).** The first one was built on a 1.25 mm
  extension and did not fit the pack (10-14). JD rebuilt its ends from an SH
  kit: an in-line socket (a board header with the wires soldered to its legs)
  for the pack's plug, and a wired SH plug into the board
  (`docs/battery.md`, "The pack connector").
- ⚠️ **Identify the harness's wires by position, never by colour.** Cheap
  pre-crimped leads come in whatever colours were on the spool. JD re-pinned
  the new SH ends to the standard colours (red +, black −, yellow for the
  pack's white NTC), but the first build's leads did not match, and the
  stubs between may still not. Check against the pack (red +, black −, white
  NTC) and the header's `NTC` label. Only + goes through the INA228 (Vin+
  battery side, Vin− keyboard side; it was first wired the other way round,
  under "Sign" above). − and NTC run straight
  through, and both − ends share the INA228's GND hole, which is the ground
  tap. Without it, both chips would measure against the Mac's ground through
  the USB cables, which charging shifts by tens of mV (an estimate).

## The wake rig: relay 1 presses a key (10-16)

⚠️ **Broken 10-23: a lead tore off the switch, and the rig is retired.**
Relay 1 still clicks, but it presses nothing. Reading a sleeping board now
takes a key pressed by hand, and the scripts below that tap the rig
(`--rig`, `relay tap`, the wake and keydrop tests) have no key to press.
(0,13) is play/pause again on both base layers (set in VIA, read back
23:44 10-23); the knob's press is still play/pause too. The section stays
as the record of how it worked.

**What it is.** A key the Mac can press. A stripped switch
housing with two leads soldered on sits in the socket at matrix (0,13), the
key right of F12, and the leads go to **RELAY1**'s COM and NO. Relay contacts
are dry, so the matrix and the relay board share no ground. The switch can
still be pressed by hand only by bridging its contacts. ⚠️ Its contacts are
fragile (JD broke and re-bent them on 10-16); give the cable strain relief.
`plans/POWER-CAMPAIGN-PLAN.md`, R7.

**The keymap** (written over VIA's dynamic-keymap commands between the
trial's reads, not with VIA): (0,13) is **F19** on both base layers (0, 2).
F19 rides the keyboard report like any letter, which the media keys do
not, and macOS gives it no action. ⚠️ **Except in a terminal**: one with no
F19 mapping prints the tail of F19's escape sequence (`ESC [ 3 3 ~`) as a
**`~`** (seen 20:20 10-18, a terminal in focus while the deep-sleep cycles
ran). Keep a terminal out of focus during rig runs, or move the rig to a key
no app turns into text, if that becomes a nuisance. The knob's press, (0,14), became
**play/pause** on both base layers; mute is `Fn` + knob press (layer 3). The
keymap before: `~/Documents/ak820pro-keymap-before-f19-20261016.json`. To
watch a test type, remap (0,13) to a visible key the same way, and back.

**Pressing it.** `usb_relay.py on 1` / `off 1` by hand, or in-process
(9-byte feature report, `0xFF`/`0xFD`, relay 1 only; relay 2 is never
touched). It is loud.

**The Mac's end: AK820 F19 Listener** (`hostagent/f19listener/main.swift`,
`scripts/build-f19-listener.sh`): a background app in `~/Applications`,
signed with the Developer ID identity and a fixed identifier
(`com.jdlien.ak820pro.f19listener`), since TCC keys Input Monitoring on the
signature; JD granted it on 10-16. Start it with `open -a "$HOME/Applications/AK820 F19 Listener.app"`
(`open`, so the grant is the app's, not the shell's), stop it with
`pkill -x ak820-f19-listener`. It logs F19 down and up only, with the
event's own timestamp on the wall clock, to `~/Library/Logs/ak820pro/f19.log`.
⚠️ An event tap sees every key: the callback matches F19 and returns every
other event untouched, never stored. Keep it that way.
⚠️ **When the monitors sleep, this Mac locks, and from then on the listener
registers no keypresses** until it is unlocked: keys at the lock screen go to
the login window under secure input, which no listener sees.
`keydrop_test.py` therefore refuses to start while the Mac is locked (it
reads the console session's `CGSSessionScreenIsLocked`), holds the displays
awake for the run (`caffeinate -d`), and flags its result if the Mac locked
anyway. On 10-17 at
12:50:22 a rig press woke the sleeping displays and the lock screen, and an
Apple Watch unlocked it, yet `f19.log` got nothing. A missing line therefore
is not a missing keystroke while the Mac might be locked. For wake tests,
keep it unlocked (no password on display sleep while testing), or count at
the board (`raw_edges`, `key_presses`).
**The Mac's power log sees it anyway.** `pmset -g log` recorded both lock-screen
presses (12:50:22 and 12:52:31 10-17) as `WindowServer TurnedOn UserIsActive
"com.apple.iohideventsystem.queue.tickle ... product:AK820 ..."`, the
keyboard named as the source, then "Display is turned on" ~2 s later. It
fires on the first activity after idle, to the second: the Mac-side record
a wake test needs (did the first key after a long idle arrive, and when),
locked or not. The unified log may carry the same with finer timestamps
(unchecked). Counting every key of a burst, to the ms, still needs the
listener and an unlocked session: run those with JD at the desk, or with
the session left unlocked for a window (JD's call).

**The tests:**
- `scripts/relay_press_test.py`: dwell and rate sweeps against the board's
  `raw_edges` (before debounce) and `key_presses` (after). It first checks
  the rig with one slow press, so a broken switch cannot read as a slow
  relay (the first sweep on 10-16 did exactly that).
- `scripts/keydrop_test.py --n N --dwell MS --gap MS`: sent against
  registered against received, and latency from the relay command to the
  Mac's key-down (paired in order, only when every press arrived).
- `scripts/deep_sleep.py`: one deep sleep, watched on the logger: woken by
  the rig (default), by its cap (`--no-press`), unfed (`--no-feed`), or the
  32-bit widths with the count preset near 65,535 (`--preset 65500
  --no-press`).
- `scripts/deep_cycles.py --n 100`: the soak, by default **through the
  ladder's own path**: Lights out and a 30 s bench sleep time (op 14 sub
  5; a bench time, not Lights out's own 1 min), no stage forced; the mode
  found is put back. Each cycle passes only on exactly one press, a fresh sleep sequence number, no reset, no new pass
  of 25 ms or more, no new transport error, the PCF's slept seconds within
  2 s of the logger's fall and rise edges, and the Mac's key-down within 1 s,
  all judged once the wake's recovery has closed. It keeps the recovery's
  timed-out steps and the daemon's first clock offset after each wake. `--arm` uses the
  experiment's op 14 sub 4 instead; `--awake` is the awake control;
  `--tap-ms 25` the input gate's short taps.
- `scripts/ladder_sleep.py --mode N [--asleep-s S] [--charge-wake]`: one
  sleep through the ladder at the mode's real time (Balanced 1200 s, Power
  saver 180, Lights out 60): a rig tap starts the idle, data off, the sleep
  timed from the tap, the wake (the rig, or relay 2 on), then the daemon's
  first clock sync before any read of its own (macOS opens raw HID
  exclusively), and the board's figures. The mode is put back.
- `scripts/fnb_caps_test.py [--control]`: the Mac's Caps Lock toggled through
  IOKit while JD presses Fn+B on the pack (or nobody, `--control`), against
  the stall counters. ⚠️ Every keyboard on the Mac types in capitals while it
  runs. It found the CAPS paint's 25 ms (`history/fnb-caps-20261019-jd/`).
- ⚠️ `key_presses` counts every key: **hands off the keyboard** while any of
  these runs. With `--trial-csv` they wait for the gap after a running trial's
  read. A test during a drain shifts its load slightly and shows in
  `guard-activity.csv`: note when and how many in the drain's README.

**Measured (10-16; `history/wake-rig-2026-10-16/`):**
- **The relay closes its contact down to a 5 ms command**; it is not the
  limit.
- **The debounce is** (`sym_defer_pk`, 5 ms stable per key): presses held
  under ~10 ms, and releases that short, are rejected, as designed. 15 ms
  and up: 10/10.
- **One key, reliably, to ~24 presses/s** (25 ms held, 10 ms open); at that
  edge the debounce rejected none of 10 in the sweep, then 10 of 100 in the
  drop test: marginal.
- **End to end at typing speed: 200 of 200** reached the Mac, down and up
  (9/s, 40 ms held). **Latency, relay command to the Mac's key-down: median
  33.5 ms, p95 45, max 108** (relay, debounce, firmware, CH582F, BT link,
  macOS).
- At ~24/s, every press the board registered reached the Mac (90 of 90).
- **The board's BT queue never filled** under ~120 play/pause presses in 14 s
  (`queue_full` 0, `replaced` 0); the music toggling on for about a minute
  after was downstream (the CH582F's own buffer or, likelier, macOS working
  through the commands). Media keys go in a different report from typing:
  test drops with F19.
- Unexplained: `raw_edges` ran one short in every batch (19/20, 399/400,
  198/200) with every press counted.
- For scale: 300 wpm is ~25 keystrokes/s, but spread over many keys, so the
  per-key debounce never sees one key at that rate; one key hammered at
  24/s is harsher. Overlapping presses (rollover) need a second key: the
  QT Py's spare GPIO with optocouplers, if one key finds something.

**Next** (after the drain, R7): bursts at 20-30/s during plug-ins, redraws
with a track playing and the overlay; 10,000-press runs; a nearly flat
pack; a weak link; and the first key after a long idle, the baseline for
every standby design. The relay's contact life (millions at signal current)
is not a concern at that scale.
