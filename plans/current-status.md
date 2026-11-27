# Current status

Updated 2026-11-26, at v0.5.0. Written to be read cold. The day-by-day log
this file used to carry, from the September crash hunt to the v0.5.0
release, is in
[`../history/current-status-to-20261126.md`](../history/current-status-to-20261126.md);
look there for the detail behind anything summarized here.

## Where things stand

**The firmware is feature-complete for JD's board, and released.**
[v0.5.0](https://github.com/jdlien/ak820-pro/releases/tag/v0.5.0) went out
on 11-26 from `ak820pro-jdlien` `0d8da8b797`, pinned in `deps.lock`. It is
v0.4.0 plus **the reserve's last stage**: after the RGB cut the board types
on as before; an hour of awake use later (or sooner by voltage) it goes
dark in every mode, sleeps 30 s after the last input, and shows "Charge
now" at every wake ([`../docs/battery.md`](../docs/battery.md), "The
reserve's last stage"). The agent 0.5.0 is a version bump only. The
release carries the daily and fpb firmware, the assets, `via.json` and the
Windows agent zip; its daily binary is the one on white.

What's left for the project as a whole: the checks owed below, then
stripping the bench, a soak, and a release meant for other owners (the
README already is their front door).

**Releases so far:** v0.5.0 (11-26, the reserve's last stage), v0.4.0
(11-13, the row ISR rewrite, D9's brightness curve, Rain, now playing and
the clock without the cable), v0.3.1 (11-01, F-033's fix), v0.3.0 (11-01,
the 10-31 audit's fixes, Icon only), v0.2.0 (10-29, the menu, profiles,
fonts, Help's More info). Release notes are on GitHub; the process is in
`CLAUDE.md`, "Build & flash".

## The boards and the bench, now

**White (JD's board, on Buzz's bench):**
- **Firmware:** the daily of `0d8da8b797` (token `0x8c6de7d9`) since
  19:37 11-24. JD pressed `Fn`+`Esc` with the data line off, so `flash.sh`
  found the bootloader at once and restored the 00:20 backups (keymap,
  lighting, profiles, live settings). A daily has no USB bootloader jump:
  every flash from it needs JD's `Fn`+`Esc`.
- **Its read at 20:42 11-26** (the daemon out, the data line on for
  seconds): 41,990 presses since the flash, no stall >= 25 ms (one pass
  >= 10 ms, the clock chip's I2C at 10), no watchdog event, no blit
  fault. BT `tx_timeouts` 18,372 of 119,167, no give-ups or drops: the
  module's slow-ACK mode
  ([`../docs/wireless.md`](../docs/wireless.md)). `cfg`: `lights_cut 0`,
  `reserve 0`, the pack full (`level 100.0 %`).
- ⚠️ **The power mode read Lights out** at 20:42 11-26, after the flash's
  restore set Power saver; the health counters show one power-mode write
  since. JD hasn't said whether they switched it. If not, it's the same
  unexplained switch as 10:12 11-14 (the archive's 11-13 block). It
  doesn't matter on USB power; set it back with `Fn`+`B` before a test on
  battery.
- **Keymap:** (0,13) is Play/Pause again (`0x00AE` on layers 0 and 2,
  since 19:37 11-24). JD took both of the presser's switches off white on
  11-23, so the presser can't press keys there.
- **Power:** relay 2 on (the board on the bench's 5 V); the data line off;
  the daemon running (now playing and the clock over Bluetooth, the
  lock-light channel).
- **The pack:** charged. The recharge from empty ran from 21:47:46 11-23
  to 10:17:18 11-24 (the last row under -5 mA): **4,103.7 mAh in over 12 h
  30 min**, 17 mAh more than the drain took out. FULL's reference for a
  new drain: `charge_mah` **-3864.725** at 10:17:18 11-24, so mAh since
  FULL = `charge_mah` + 3864.725 (the INA228 counts charge negative).

**The logger** (INA228 + MAX17048 on the pack lead, a QT Py on Buzz)
writes `history/power-bench-2026-10-15/power.csv` once a second. ⚠️ Its
QT Py dropped off USB for 3 s at 12:49:02 11-23 and its count restarted;
any count crossing that moment needs the offset (the archive's 11-13
block).

**Black (gremlin's board):** as last recorded, `row-isr` `6683c18134` dev
since 11-11 (`GREMLIN-RESULTS.md`, §22). Warren's.

**The bench supply:** a Riden RD6006P, `ridenctl` on Buzz since 11-18,
its server (ridenboard) on bun. Reads and OFF are free; anything that
powers the output needs a lease JD grants with a passkey, 2 h at most
([`../docs/test-bench.md`](../docs/test-bench.md), "The bench supply").
Raising the cap to 8 h (where it was before a review cut it) is JD's call:
an edit to riden-bridge and a sudo deploy on bun. To stand in for the
pack: the red and black posts, not the green battery terminal; one plug
from JD's SH lead kit into the harness's in-line socket, no soldering;
relay 2 off, so the charger never pushes into the supply.

## Owed, in order

1. **The reserve's last stage on the board.** The simulator covers the
   logic (264 cases) but not `sleep.c`, so the wake paths have never run:
   "Charge now" after a key, a knob and a keep-alive wake, and the 30 s
   sleep in each mode. JD released without it. If something is wrong
   there, it only shows in the last hours of a charge. Two ways to run it:
   - **With the pack (no hardware change, about an hour of awake use):**
     `Fn`+`B` to Power saver first. Then relay 2 off; raise the cut above
     the full pack's voltage, `ak820battery.py cfg 3680 4200` (RAM only;
     the cut fires after 30 s under it); JD types until the board has
     been awake an hour, longer by the clock, since sleep doesn't count.
     Then check: dark, asleep 30 s after the last key, "Charge now" lit
     4 s at each key or knob wake; after a keep-alive wake, at the first
     key. Afterwards `cfg 3680 3400` and relay 2 on (5 s of cable lifts
     the cut and the stage).
   - **With the Riden (faster, and tests one more thing):** the supply at
     ~3.2 V in place of the pack; the estimate stays under 3225 mV for
     30 s and the stage starts at once, which also tests the voltage rule
     on hardware (so far only in the simulator, on 11-23's readings).
     Best done inside test 2 below, with the same setup.
2. **The bench supply's tests** (`plans/BACKLOG.md`, "The bench supply as
   the pack"; tasks 22-26 in `.taskmaster/tasks/tasks.json`). Unblocked
   since the drain ended. Test 2 (Battery low and the RGB cut on demand)
   takes the reserve's voltage rule too. Test 3 (where the keyboard dies)
   starts at 2.40 V, because the board still ran at 2.32 V on 11-23. Test
   5 (the charge measured from the USB end) waits for a charge. Each needs
   JD's lease and the plug swap.
3. **The clean-Windows install of the release zip:**
   `scripts/sandbox-6b.ps1 -Tag v0.5.0 -Wait`. Owed since v0.3.0;
   gremlin's Windows Sandbox is off, and every release since has shipped
   without it.
4. **The power mode on white** (above): ask JD whether the Lights out was
   theirs.
5. **Measurements owed on v0.4.0's curve** (`plans/BACKLOG.md`,
   "Brightness after the new curve"): the knobs sweep, and the gauge
   model's gap at middling brightness (the board draws 3-5.5% more than
   its model from 5% to 75%).
6. **A stale backlog heading:** "On 2.4G with music playing, the board
   barely sleeps" still reads "neither built; blocks raw81 in a release",
   but v0.4.0 shipped raw81 with the agent's 180 s radio hold (its fix 1,
   in part). Re-measure the sleeping board on 2.4G with music, then
   update the item.
7. **Housekeeping:** `.taskmaster/tasks/tasks.json` (untracked) has many
   items still in progress that are done (the audit, the fonts, More
   info, deep sleep).

**Waiting on JD's yes (ideas and offers, not to build unasked):**
- a louder "Battery low": it shows once a discharge for 60 s and JD
  never saw it this time (`plans/BACKLOG.md`, the first item);
- the README's Lights out line (README.md, the power-mode table);
- an after-drain analyser for the logger's CSV;
- the supply's stepping script, tried first against ridenboard's
  simulator;
- JD's two checks of the agent on black (an Ø/ß title, a skip with no
  pause flash), which JD skipped for v0.4.0.

## What the last drain settled

The drain from FULL at 13:56:13 11-05 ran at JD's real use, untethered,
to the end (`docs/battery.md`, "The reserve below 0%"):
- **The RGB cut at 13:41:22 11-23**, after 17 d 23 h 45 min and 3,888 mAh.
  "Battery low" had fired (`warned 1`), unseen.
- **The end at 21:43:10 11-23**, 8 h 02 min and 199 mAh after the cut:
  the pack's protector opened cleanly at 2.32 V under ~67 mA, with the
  board still running. A brownout isn't what ends a discharge.
- Whole drain: 18 d 7 h 47 min, **4,087 mAh** net, 9.29 mA mean.
- ⚠️ **Near empty, `5C` flattens above 0 and reads high** (3 counts with
  the pack at 3.00 V), so the zero rule almost never fires. That is why
  the last stage starts by time and at 3225 mV.
- 1 h of use past the cut left 154 of the reserve's 199 mAh; 2 h left
  104. Hence the hour.

## Bench rules (details in [`../docs/test-bench.md`](../docs/test-bench.md))

- ⚠️ **Never enumerate HID**, and **pause the daemon before any raw-HID
  tool** (`launchctl bootout gui/$UID/com.jdlien.ak820pro.agent`; back
  with `launchctl bootstrap gui/$UID
  ~/Library/LaunchAgents/com.jdlien.ak820pro.agent.plist`).
- **White's data line:** `timeout 20 uhubctl -l 3-1.3.4 -p 2 -a on|off -e`,
  3 s between an off and an on. ⚠️ **Port 4 on that hub is the UPS:
  never touch it.**
- **Relay 2 is the keyboard's 5 V:** `venv/bin/python
  scripts/usb_relay.py on|off|status 2`.
- **Dump the battery log before any reset or flash** (`flash.sh` does it
  when the board is running QMK; from the bootloader it can't).
- **The slider stays on BT or 2.4G**: it is a power switch.
- **Flash only provenance-named artifacts, on JD's go each time.**
- **Don't poll the board:** a read is traffic; the daemon's status file
  (`~/Library/Application Support/ak820pro/ak820-agent.status`) shows
  what it sees, though on BT with the data line off the board reads
  absent there.
