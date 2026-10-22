# AK820 Pro → QMK ("Jackrabbit") — working notes

[`README.md`](README.md) is the front door: what this is, how to set up, build,
flash and install the host agents. This file is the stuff you need when you are
*changing* something.

Personal-first: built for JD's unit, published for other AK820 Pro owners,
deliberately NOT generalized for upstream. `ak820pro-builds/UPSTREAM-CONTRIBUTIONS.md`
sorts genuine bugs from personal preference.

## Layout

The repo tracks its own files (`README.md`, `docs/`, `hostagent/`, `scripts/`,
`assets-src/`, `plans/`, `history/`, `setup.sh`, `build.sh`, `flash.sh`,
`env.sh`, `deps.lock`). The four dependency clones are gitignored, created by
`setup.sh`, and pinned by [`deps.lock`](deps.lock) — **change a pin there, not
in a clone.** `qmk_firmware-ak820pro/` is the exception you may commit into: it
carries the board work on `ak820pro-jdlien`, and its `lib/chibios-contrib`
submodule sits on our `ak820pro-patches` branch.

## The topic docs — read the one for the area you're touching

| Doc | Covers |
|---|---|
| [docs/wireless.md](docs/wireless.md) | CH582F module, BT/2.4G, pairing UX, the `A6`/`5B` quirks, slot memory |
| [docs/display.md](docs/display.md) | LCD panel variant, band layout, glyph queue/DMA pump, backlight, overlays, host text slot |
| [docs/fonts-assets.md](docs/fonts-assets.md) | Font atlases, Cozette, clock crop, the flash memory map, provisioning and its traps |
| [docs/clock.md](docs/clock.md) | The two RTCs, divider trim, persisted period, host clock sync (the daemon; the Python timekeeper before it) |
| [docs/leds.md](docs/leds.md) | **Interrupt priorities**, RGB field rate, indicator LEDs, the rainbow, effects |
| [docs/hardware.md](docs/hardware.md) | Slider power quirk, bootloader, build/flash, watchdog+health, hang history, diagnostics |
| [docs/sn32f299.md](docs/sn32f299.md) | The MCU's manual distilled, with page numbers: memory map, clocks, Sleep and Deep-sleep and what wakes them, interrupts, GPIO, timers, watchdog, the peripherals, the flash controller, electrical figures, this board's pin map, errata and what the manual does not say. Look a register up here before opening the PDF |
| [docs/battery.md](docs/battery.md) | What the board can know about the pack, the regulator hiding it, the level estimate, idle ladder, the unexplained power-off |
| [docs/power.md](docs/power.md) | The reader's summary, linked from the README: runtime awake and asleep, each feature's draw, the model as arithmetic, charging, what we don't know. Each number is marked measured or modelled; update it when R5 or a new map lands |
| [docs/test-bench.md](docs/test-bench.md) | The bench, run from the Mac: the USB relay (relay 2 cuts the keyboard's 5 V; relay 1 presses a key, the wake rig, with its measured reliability and latency), `uhubctl` (USB data), the trial and its guard, the power logger (INA228 + MAX17048) and measuring loads from the Mac, the "Christmas Tree" outlet, hub depth limits |

**Resuming work? Start at
[`plans/current-status.md`](plans/current-status.md)** — where things stand and
what to pick up next, written to be read cold. Live work:
[`plans/`](plans/) (`BACKLOG.md`, `AK820-AGENT-CROSSPLATFORM-PLAN.md`,
`CLOCK-FORMAT-PLAN.md`).

**`ak820-agent/`** — a Rust rewrite of the host agents as one daemon, now on
Windows and macOS. **Windows: every phase met as of 2026-09-06.** Since 14:40
that day the daemon owns now-playing **and** the clock on the Windows PC
(gremlin) and the Python timekeeper is removed; over its first 50 syncs it
beat the Python it replaced on every tail statistic (95th percentile residual 21.0 ms against 51.1, worst 23.8
against 994.5, learned bias inside 61 ppm against 709). Phases 0–2, 3a and 4a
were each audited by codex and every finding dispositioned. **v0.1.1 is
published** and proven to install on a clean Windows with no Python, no MSYS2
and no VC++ redistributable. ⚠️ **Five things are still open and none of them
blocks anything — read "What is left, for whoever picks this up next" at the
top of [`plans/AK820-AGENT-PLAN.md`](plans/AK820-AGENT-PLAN.md) before
starting work here.** The one that could still mean harm is the firmware's
unexplained ≥25 ms stall count, which moved from 12 to 18 across a day of
testing; a quiet night settles it, and **do not poll the board to
investigate** — a health read is itself board traffic, and the daemon already
samples it into its status file every 5 minutes.
**macOS: built and running on JD's Mac since 2026-09-16, not released.** The
LaunchAgent `com.jdlien.ak820pro.agent` owns now-playing (MediaRemote, through
the vendored helper in `ak820-agent/helper/`, hosted by `/usr/bin/perl`) and
the clock; the bash now-playing agent and the Python timekeeper are disabled
there. No macOS build is published and nothing is notarized: Phase 6 stops
before Apple. Status, owed checks and audits:
[`plans/AK820-AGENT-CROSSPLATFORM-PLAN.md`](plans/AK820-AGENT-CROSSPLATFORM-PLAN.md).
305 unit tests, the 2,309-case folding fixture, a 4-test replay of the
timekeeper's log and a 2-test health capture. Read
[`plans/AK820-AGENT-PLAN.md`](plans/AK820-AGENT-PLAN.md)
first; it carries the phase gates and the findings that are load-bearing.
Its two companions are part of the plan, not background:
[`AK820-AGENT-CLOCK-PARITY.md`](plans/AK820-AGENT-CLOCK-PARITY.md) (the Python
scheduler and bias learner) and
[`AK820-AGENT-CLOCK-TRANSACTION.md`](plans/AK820-AGENT-CLOCK-TRANSACTION.md)
(`ak820ctl`'s transaction, where the precision actually lives —
**the clock oracle is Python PLUS the pinned C utility**).
[`review-codex-ak820d-2026-09-05.md`](plans/review-codex-ak820d-2026-09-05.md)
is the review that reshaped all three.

Four things from that work that bite outside it:

- ⚠️ **Windows delivers HID input reports to EVERY open handle** (measured
  2026-09-05). A process that wrote nothing received another process's text
  echo, and a clock GET after a text write returned the text echo. Ordering
  cannot correlate a reply to a request — **validate every read against the
  command it answers**. `ak820ctl`'s `xfer()` does not, and fails safe only by
  accident via the protocol-version field.
- ⚠️ **Correlation is not enough for the clock, and this is the one that
  surprises.** A foreign `RTC_GET_TIME` reply is a *well-formed*
  `RTC_GET_TIME` reply — right channel, right command, protocol version 2,
  plausible fields — so no header check can tell it from your own. Taking it
  pairs someone else's board sample with your timestamps: a wrong offset with a
  plausible RTT, silently. **Exactly one process may run clock transactions at
  a time**; that, not the framing, is what makes the clock correct.
- ⚠️ **Never enumerate HID.** `hid_enumerate` opens every HID device on the
  machine; that wedged a UPS on this machine
  (`../jdrgb/docs/ups-wedge-incident.md`). `ak820text.py` is fixed; the
  timekeeper and `ak820ctl` are not — see `plans/BACKLOG.md`.
- ⚠️ **On Windows** the raw-HID interface is **shareable**, not exclusive — the
  old "VIA holding it" advice describes contention over *replies*, not over the
  open. ⚠️ **On macOS it is exclusive to hidapi**: `ak820ctl` and the Python
  tools seize it, and the daemon's opens and writes fail until they close (see
  "macOS raw HID is EXCLUSIVE" in
  [`plans/AK820-AGENT-CROSSPLATFORM-PLAN.md`](plans/AK820-AGENT-CROSSPLATFORM-PLAN.md)).
  And that contention **breaks VIA, not you**: measured 2026-09-05, VIA
  received another process's reply, rejected it, and then stayed
  **persistently off by one** for the rest of the session. The now-playing
  agent does this every ~3 s. **Pause the host agents before using VIA**
  (`ak820 status` shows the daemon and the older Python/bash agents), and read
  lighting values back over `[0x08, 3, 1..4]` rather than trusting VIA's UI
  after an error — the board executes the writes, VIA only loses the replies.

Measured results and audit findings from completed work: [`history/`](history/).
ChibiOS patch inventory: `keyboards/a_jazz/ak820pro/PATCHES.md`.

## Current state (2026-10-22)

**Resume from [`plans/current-status.md`](plans/current-status.md)** ("2026-10-22
— RESUME HERE"). **Feature-complete for JD's board.** What's left:
- an untethered drain at real use, running to the RGB cut;
- one firmware cleanup: a slow pass every second, the clock's seconds tick
  landing at 10 ms;
- stripping the bench, the soak, and the release for other owners.

**On the board since 14:22 10-21: `36afff30e8`** (dev, token
`0xef38330e`): Gremlin's frame trim for the wireless clock merged with
the 81-LED model; the Mac's daemon `21e8fe8` sends type 4. The 30 min
cut held the clock within ~20 ms
([`history/lockchan-clock-mac-cut-trim-20261021/`](history/lockchan-clock-mac-cut-trim-20261021/README.md)).
**From 10:50: `36330d5ec8`** (dev, token
`0x57c22634`): `9e52400ec9` plus the RGB model over 81 LEDs, not 82
(battery.c only). **From 01:50: `9e52400ec9`** (dev, token
`0x3c899a32`), the mainline with everything in one build: `ak820pro-jdlien`
and `deps.lock` point at it. It is `7ae8575c1a` plus Gremlin's wireless
clock (type 4), which the Mac does not send yet: its latency needs an
unlocked screen to measure.
- **`7ae8575c1a`'s overnight soak** (21:58-01:41,
  [`history/mainline-soak-20261020/`](history/mainline-soak-20261020/README.md)):
  139/150 sleep cycles, every failure a known kind (6 wake paints, 5 UART
  overruns); 15 min awake off USB within the ±2 s bound, with the legacy
  trim seen running; an hour asleep at 3.01 mA; every reconnect synced and
  every PCF write settled.
- ⚠️ **Lock-light frames into a sleeping board cost ~1.6 mA on average**
  while the Mac plays music (`plans/BACKLOG.md`).

**Before it, from ~21:50 10-20: `7ae8575c1a`** (dev, token `0x350912aa`):
`dd8391c28d` plus Gremlin's PCF writer fixes and the repaint at a guess.

**On the board from 17:11 10-20: `845996c39c`** (`mac/lockchan-pm`, a
`dev` build, token `0x2e279a39`). It is the power modes revised
(`5df4e0e3b7`, which `ak820pro-jdlien` and `deps.lock` now point at) plus
the lock-LED handler and play times, which stay on their branch.
- **Validated:** deep sleep on BT and 2.4G, and `ladder_check --rig`
  ([`history/power-modes-20261020/`](history/power-modes-20261020/README.md)).
- **Since 18:30: `6fda6cd1c2`** (dev, token `0xa647bcb6`), the same plus a
  stray-wake diagnostic (op 24 slot 8). Lock-light frames into a sleeping
  board proved harmless (80 frames, no strays); the soak's one stray, about
  one in 50 sleeps, is unexplained (`plans/BACKLOG.md`).
- **Since 20:30: `dd8391c28d`** (dev, token `0x28e58a4c`), the same plus
  the fix for the clock flashing at lock-light title frames
  (`plans/BACKLOG.md`, "The clock flashes"; codex cleared it).

**Before it, from 15:16 10-20: `8b06e4dcc4`** (a `dev` build, token
`0x3e1c880c`). It is
`b2a07e0d37` with the deep sleep's wake from SRAM. On `b2a07e0d37` every
deep sleep ended after one second, because of where the linker put the WFI
([docs/sn32f299.md](docs/sn32f299.md), errata item 37;
[`plans/DEEP-SLEEP-REGRESSION-2026-10-20.md`](plans/DEEP-SLEEP-REGRESSION-2026-10-20.md)).
- **Its first checks:** 10/10 sleeps over 2.4G and 5/5 over BT.
- **Not yet run:** the long soak, and the two cross-check builds codex
  cleared (`221ffb103a`, `5a9f7b406d`). JD's call (10-20): the Rust
  lock-light agent first.
- **Open:** a 26-28 ms blit around some wakes, seen on the fix and on a
  pad build without it.

**Before it, from 01:04 10-20: `b2a07e0d37`** (a `dev` build, token
`0x398a2e17`). It is the UART-latency build ([`plans/UART-LATENCY-PLAN.md`](plans/UART-LATENCY-PLAN.md)):
- **the PCF's transfer runs unlocked,** with only the row ISR's IRQ held off;
- **UART2 sits above USB;**
- **the animation's stop and the boot redraw go through the staged restore;**
- **the pass budget is compared in ticks.**

Measured overnight with no hands
([`history/uart-latency-20261020/`](history/uart-latency-20261020/README.md)):
- **overruns:** under a PCF burst, 7.7% of radio requests lost became
  0.05-0.1%;
- **the release matrix passes, with no pass >= 25 ms anywhere:** the stuck
  bus, the staged restore, and 200 relay presses during a request stream.

**The Mac's daemon carries now-playing over the 2.4G dongle with the cable
out** (`--radio`, installed 01:06 10-20). Its cable-out test passes; the
track change waits for JD.
- ⚠️ **On a dev build, ops 20-26 change the board's diagnostics at run
  time:** the lock mode, UART2's priority, the gap monitor.
  `overrun_diag.py` puts the defaults back after its runs.
- ⚠️ **On macOS, flock and POSIX record locks never see each other:**
  every Mac tool on the radio lock uses flock.

**Earlier on 10-19:** **The night of 10-18/19, no hands:** 247 of 247 deep-sleep
cycles and an hour asleep at 3.17 mA, every waking key kept; ⚠️ **asleep, the
RTC's second runs ~13% slow** (3139 s counted for 3600), so the build takes
slept time from the PCF; the radio retries as often awake as after a wake; a
per-colour RGB model within 0.6%. **Deep sleep and the mode icons are on
the board** (`83d8768c64`, since 16:16 10-19; [docs/hardware.md](docs/hardware.md),
"Deep sleep"); its soak passed 97 of 100, the three failures UART overruns
at the link's long-standing rate (~1-2 an hour, not the sleep's; `BACKLOG.md`);
Balanced's real 7-min sleep passed; what is left is the plan's "Validation
results (10-19)". **Gremlin** (the Windows PC, its own AK820) has the
lock-light channel, the 2.4G dongle and Windows testing
([`plans/GREMLIN-HANDOFF-2026-10-19.md`](plans/GREMLIN-HANDOFF-2026-10-19.md),
[`plans/GREMLIN-RESULTS.md`](plans/GREMLIN-RESULTS.md)).
The mode names are settled (Always on / Balanced / Power saver / Lights
out, [`plans/POWER-MODE-ICONS-PLAN.md`](plans/POWER-MODE-ICONS-PLAN.md)),
built separately as the flash after.
Two workstreams, Phase 2 first:
- **Phase 2 is built and on the board (10-18, 16:54): an accurate gauge, a
  time-left estimate, the power ladder** ([`plans/PHASE2-BUILD-PLAN.md`](plans/PHASE2-BUILD-PLAN.md),
  three codex reviews; [docs/battery.md](docs/battery.md), "The gauge as
  built, Phase 2"). Next: tonight's maps, the wake/key test, then R5 (a drain
  in Normal at JD's use). R1-R4 are done (the per-load map, the USB offset, a
  logged drain and charge: 4011.6 mAh, 15,579 mWh to the RGB cut at JD's
  settings). A1: the gauge reads up to 13.7 points low on the plateau
  (70-80%, where 15 mV spans 85-70%), within 2.5 below 20%. No voltage table
  can fix that, so the plateau gets an energy count from FULL with the
  board's modelled draw. Next: A3, A4, A7, A8
  ([`plans/POWER-CAMPAIGN-PLAN.md`](plans/POWER-CAMPAIGN-PLAN.md)), the plan,
  codex, the flashes.
- **The lock-LED channel (host-to-board data over Bluetooth) is parked**
  with its transport proven: 24/24 frames on the board, and profile P3 moves
  no light ([`plans/LOCK-LED-CHANNEL-PLAN.md`](plans/LOCK-LED-CHANNEL-PLAN.md)
  has the resume list; what the module forwards is in
  [docs/wireless.md](docs/wireless.md)).
- **Before it, from 22:19 10-19: `e7f6890e06`** (a `dev` build, token
  `0xfa68ad25`): Gremlin's
  2.4G stage 1 with its pause fixed (the per-byte `timer_read` was a 64-bit
  software divide, ~250 us a call), plus the overrun/Caps build
  ([`plans/OVERRUN-CAPS-PLAN.md`](plans/OVERRUN-CAPS-PLAN.md)):
  - **the Caps label through its own queue;**
  - **the I2C driver restarted after a failure;**
  - **one PCF transaction a pass;**
  - **dev-only:** the overrun diagnostics (HC_DEVHOOK ops 20-24,
    `scripts/overrun_diag.py`).

  ⚠️ **UART2's receiver holds about one byte** (measured 10-19,
  `history/overrun-depth-20261019/`): any masked stretch over ~80 us while
  the module sends loses bytes, and the PCF's 2.6 ms transaction is the
  worst of them. The per-byte release is no fix and is dev-only, off. BLE
  has no vendor channel; its `FEE0` is the module's OTA, never to be
  written ([docs/wireless.md](docs/wireless.md)).
- **Before it: `7387d18947`** (token `0x19f958d5`, 18:32 10-19), stage 1's
  echo on the build below.
- **Before it: deep sleep and the power-mode icons**, `83d8768c64` (a
  `dev` build, token `0xcf9da0e0`, from 16:16 10-19: `26fcafaeca`, flashed
  13:18 and soaked, plus the bulbs' art reworked on the panel, display.c
  only): the ladder sleeps on battery (Balanced 7 min, Power saver 3, Lights
  out 30 s, Always on never; the enum keeps Full/Normal/Saver/Minimal), a
  bulb in the bolt's slot shows the mode on battery, and the bench's sleep
  controls are op 14 subs 4-6
  ([`plans/DEEP-SLEEP-BUILD-PLAN.md`](plans/DEEP-SLEEP-BUILD-PLAN.md),
  [`plans/POWER-MODE-ICONS-PLAN.md`](plans/POWER-MODE-ICONS-PLAN.md)). **Measured that evening:
  deep sleep draws 3.2 mA against ~27 awake and dark, wakes on a key, and
  the waking key is not lost; light sleep with WFI saves ~4.7 mA.** **Pushed 10-19** (`ak820pro-jdlien`
  and ChibiOS-Contrib's `ak820pro-patches`); `deps.lock` pins the board's
  firmware (`b2a07e0d37`, above), so a fresh `setup.sh` builds it. JD: push
  freely now; the repo is not widely circulated.
- **The power logger stays on the pack** (INA228 + MAX17048,
  [docs/test-bench.md](docs/test-bench.md), "The power logger"): current and
  charge from the INA228, voltage from `vcell_mv`. ⚠️ The INA228's VBUS reads
  ~5% low, and the MAX17048's own SOC is up to 22 points off: use neither.
- **Flashing needs no hands:** `./build.sh dev`, then `./flash.sh <artifact>`
  ("Build & flash", below). ⚠️ Keep the slider on BT or 2.4G. ⚠️ JD is often
  busy: one action per message. ⚠️ **Test display changes with a track
  playing** ([docs/display.md](docs/display.md)).

## Earlier state (2026-10-15)

The INA228 power logger went onto the pack (its shunt first wired
backwards, fixed at the terminal block); R1 mapped the loads (73.5 mA at
JD's settings, 28.3 with the RGB off, the screen ~1 mA at his level) and R2
the USB data offset (1.7 mA); R3, the logged cycle, started that night on
flash 2f.

## Earlier state (2026-10-14)

Phase 1b closed: "Battery low" and the RGB cut passed on the 10-12/14 drain
with no pass ≥ 25 ms; runtimes 51.13 h and 50.35-50.43 h; the gauge within
2.5 and then 4.6 points from 52% to the cut, up to 8.3 and 7.2 low on the
flat top (70-85%). The pack connector turned out to be 1.0 mm, not 1.25.

## Earlier state (2026-10-12)

Phase 1b done but for the drain's two per-event checks; firmware merged and
pushed (`3e18c70a74`).

## Earlier state (2026-10-11)

Flashes 2b-2e went on hands-free; gate 8's per-event checks found and fixed
the plug-in, page-exit and overlay stalls; E6 written.

## Earlier state (2026-10-08)

B3 trial 1 gave `K_CC` ≈ 133. Flash 2 was rebuilt on it and cleared by codex,
then flashed at 12:54 10-08.

## Earlier state (2026-10-04)

Phase 1b was about to start (revision 7, after six codex rounds). Run 2's
validation drain was done: 50.56 h to the RGB cut, then 5 h of reserve. The
fitted curve `759e265796` was on the board.

## Earlier state (2026-10-01)

**The battery gauge's drain test is done and the curve is fitted, committed,
not yet flashed.** Resume from [`plans/current-status.md`](plans/current-status.md);
the work is [`plans/BATTERY-GAUGE-PLAN.md`](plans/BATTERY-GAUGE-PLAN.md), the
evidence [`docs/battery.md`](docs/battery.md). The level comes from the
CH582F's `5C` (a linear voltmeter on the pack, within ~10 mV of a meter from
4.01 to 3.22 V, clamped at ~4.036/3.161 V), never from VDD (a buck-boost output
pinned at 3.90 V); 0% is the RGB cut at 3400 mV. ⚠️ Every internal-flash write
blinks the LEDs dark for a few ms (the row ISR's guard, not interrupt masking). ⚠️ Dump the RAM
battery log before any flash, with the slider on BT. Call JD by name in docs,
not "the owner".

## Earlier state (2026-09-24)

**Resume from [`plans/current-status.md`](plans/current-status.md).** The
2026-09-22/23 crash campaign fixed four things:

- **The SPI hang behind the 2026-09-22 reset.** A CPU transaction ran during
  an in-flight DMA; fixed by `bus_quiesce()`.
- **The fault recorder.** It lost its final write, so every crash record came
  back invalid.
- **The DMA "never-start".** It was really a lost completion: the SPI0
  half-transfer handler cleared a DMATCIF it had not read.
- **Two lock-nesting bugs, in the serial and USB drivers,** plus the CH582F
  TX pump order.

Analysis, a codex review and every disposition:
[`plans/FIRMWARE-FINDINGS-2026-09-23.md`](plans/FIRMWARE-FINDINGS-2026-09-23.md).
The instrumented build keeps the DMA and ACK diagnostics that found them;
the daily build carries none of it (verified by symbol diff).

## Earlier state (2026-09-03)

QMK VIA firmware flashed and verified (`0C45:8009`); assets provisioned. The
hardening project (phases 0-5) is complete and hardware-verified: board code
split into modules (`ak820pro.c` ~570 lines of init/dispatch; watchdog, health,
kb_eeconfig, bt_ui, consumer_mod, param_overlay, indicators, hid_protocol), a
~12 s hardware watchdog with reset-loop escape and LCD alert, health counters
on raw-HID channel 0x13, the CH582F pending-action machinery unified with fault
injection, nothing blocking the main loop on the glyph queue, and BT slot / LCD
brightness / RTC trim persisted. LED row-flash artifact and stray-glyph bug
fixed. BT at 0.042 ACK timeouts/frame (BT-mode typing burst). **2026-09-03:
the matrix publish fix** — the driver scans every row every ISR cycle, and the
worst per-key sampling gap fell from ~169 ms to ~5 ms
([docs/hardware.md](docs/hardware.md)). The row ISR measures 3,876/s with a
188 µs body (160 µs LED-only, 261 µs with the row scan) — **72.8% of the CPU** —
not the 18,750/s the timer implies, because it re-arms its counter at its end;
so the LED field rate is ~215 Hz and the main loop ~335 Hz. Health page 4
(`ak820health.py --isr`) measures it live. **`Fn`+`D` puts the health counters
on the LCD** for untethered use, with hold-to-reset
([docs/display.md](docs/display.md)). Everyday firmware measures **zero stalls
>= 25 ms**, the threshold below which a press cannot be lost — including
dismissing that debug page, which cost ~30 ms until `821431e3e4` staged its
restore (worst blit now 20 ms, the Caps-on paint).
Sub-second clock sync implemented the same day (phases 0-3):
host syncs land within ~3 ms, a USB-SOF loop disciplines the ILRC, offsets slew
instead of jumping — see [docs/clock.md](docs/clock.md). The repo was
restructured the same day into a clone-and-build package: `setup.sh` +
`deps.lock`, and a README that assumes no context.

## Build & flash

```sh
./setup.sh                  # idempotent; re-run after changing deps.lock
./build.sh dev              # JD's board: daily + the raw-HID bootloader jump + dev hooks
./build.sh daily            # what releases ship; or: instrumented, fpb
./flash.sh ak820pro-builds/out/<the printed artifact>
```

**`dev` is what JD's board runs while development lasts** (since 2026-10-11).
It adds `HC_BOOTLOADER` (`0x79` + `BOOT`), so `flash.sh` jumps to the
bootloader with no `Fn`+`Esc`, and `HC_DEVHOOK` (`0x76`: press `Fn`+`D`, read
the display probe, `scripts/devhook.py`). `build.sh` fails a daily or fpb
build that carries either, and releases ship daily and fpb only. ⚠️ On a dev
build any process that can open raw HID can drop the board into the
bootloader, which looks dead.

**Releasing:** `git tag -a vX.Y.Z` and push it; CI builds the agent zip into
a GitHub Release, then `scripts/release-firmware.sh vX.Y.Z` (from a checkout
at the tag) uploads this machine's firmware artifacts to it -- a clean build
of deps.lock's pinned commit only, never a `-dirty` one. Then
`scripts/sandbox-6b.ps1 -Tag vX.Y.Z -Wait` proves the published zip installs
on a clean Windows (no Python, no MSYS2, no VC++ redistributable) in Windows
Sandbox, and prints the sandbox's transcript back on the host. ⚠️ **The zip's
`INSTALL.txt` is what a stranger reads first, and it only changes with a
tag** -- v0.1.0 shipped one telling a clean machine to leave the clock to a
Python agent it does not have, which cost a v0.1.1.

Works on macOS and on Windows from the **MSYS2 MinGW 64-bit shell** (only that
shell — `qmk_cli` refuses the others). Windows has four traps that all present
as something else, and every one of them costs an hour if you meet it cold:
CRLF checkouts make `build.sh` see a permanently dirty submodule; the venv must
be named `venv-mingw64` (use `$AK820_VENV`, never a literal `venv`); the xpack
arm toolchain must come **last** on `PATH` or its bundled DLLs make the native
gcc fail silently; and `USE_LIBUSB=1` is macOS-only — on Windows the bootloader
is plain HID, so no Zadig. All four are written up in
[docs/hardware.md](docs/hardware.md#building-and-flashing-on-windows-msys2).

Windows host agents are Scheduled Tasks under `\ak820pro\`. **As of
2026-09-06 now-playing is the Rust daemon** (`ak820 install` / `status` /
`uninstall`, task `AK820Pro-agent`, log and status file in
`%LOCALAPPDATA%\ak820pro\`), and **since 14:40 on 2026-09-06 the clock too** (`ak820 install --clock`;
the Python timekeeper's task is removed). The Python agents' installer is
**PowerShell**: `hostagent/install-agents-windows.ps1 [-Status] [-Uninstall]`.
It **refuses** while the daemon owns the clock — the way back is a plain
`ak820 install` FIRST, then that installer — and its now-playing task exits at
once because the daemon holds its mutex, which is the intended outcome. The Python agents
need `venv-win` (native python) — `venv-mingw64` can never hold `winsdk`, so
`venv_bootstrap.py` picks the venv that *provides* the module, not the first
that exists. Two traps that fail silently: **ak820ctl must be linked static**
on Windows (a Scheduled Task has no MSYS2 on `PATH`), and it keys its
calibration cache off `getenv("HOME")`, which Windows does not set — the
timekeeper exports one agreed `HOME` so both see the same file.

macOS host agents are LaunchAgents. **Since 2026-09-16 the Rust daemon owns
now-playing and the clock** (`ak820 install --clock`, label
`com.jdlien.ak820pro.agent`; binaries in
`~/Library/Application Support/ak820pro/bin`, the status file one level up,
log `~/Library/Logs/ak820pro/ak820-agent.log`). Install stops and disables
the bash now-playing agent (`com.jdlien.ak820pro.nowplaying`) and the Python
timekeeper (`com.jdlien.ak820pro.timekeeper`); `ak820 uninstall` re-enables
them unless `--keep-bash-off` / `--keep-timekeeper-off`, and
`hostagent/install-agents.sh` refuses to start either beside a daemon that owns
its job. The MediaRemote helper is built by `scripts/build-helper-macos.sh`
and the binaries signed by `scripts/sign-agent-macos.sh` (TCC keys Automation
consent on the signature); `scripts/package-macos.sh` makes the release `.dmg`
and stops before notarization. The user-facing description is
`ak820-agent/INSTALL-macos.txt`.

`build.sh` enforces the submodule pin, structural binary checks and via.json /
enum sync; it refuses a dirty or off-pin tree. `flash.sh`, in order:
- backs up the VIA keymap **and the RGB lighting**, and refuses if either
  backup fails (`--no-lighting`, `--no-backup` to override);
- **refuses on battery once the RGB cut has fired** (the reserve; a pack that
  dies mid-write leaves the board half-erased; `--on-reserve` overrides);
- **dumps the battery log** to `~/Documents/ak820pro-battlogs/`, fatal unless
  `--no-battlog` (a flash erases the RAM log; one was lost to a retry loop on
  10-11);
- asks the firmware to jump (`hostagent/ak820bootloader.py`); a build without
  the jump (daily, fpb) answers "unhandled", and it falls back to asking for
  `Fn`+`Esc`;
- flashes, restores the keymap and lighting, and syncs the clock.

Bootloader by hand is `Fn`+`Esc`. **A flash erases the emulated EEPROM**: VIA
keymap and RGB effect/colour (both restored by flash.sh), BT slot, LCD
brightness, clock format, the saved battery level, persisted RTC period
(re-converges in ~4 min with the host attached — designed, not a fault). On
USB power the battery level is then unknown ("Charge") until FULL or an
unplug plus 30 min; on battery it comes straight back. The default keymap is
JD's VIA layout, regenerated with `scripts/keymap_to_c.py`, never hand-edited.

⚠️ **The RGB restore is new as of 2026-09-06** —
`hostagent/ak820lighting.py` (`show` / `dump` / `restore`), backup at
`~/Documents/ak820pro-lighting.json`, over VIA's own lighting channel
`[0x08, 3, 1..4]`. Before it, every flash silently reverted the LEDs to
`keyboard.json`'s `rgb_matrix.default` — unnoticed through all nine flashes of
2026-09-03. Keeping that default near JD's setup is still worth doing as
a backstop, because `--no-backup` and a missing backup file both fall back to
it. On Windows `ak820 lighting` reads the same values without enumerating HID.

## Working with VIA

Load `keyboards/a_jazz/ak820pro/via.json` at usevia.app → Settings → Show
Design tab → Load Draft Definition. The USB cable must be connected; **the
slider position does not matter** — raw-HID replies return over USB in any mode
(board commit 4b86d95014). Older notes demanding "wired mode" describe pre-fix
firmware.

- Layers: `WINBASE=0, WINFN=1, MACBASE=2, MACFN=3` — the mac/win dip switch
  picks the base, so per-key remaps usually need doing on both 0 and 2.
- **VIA's stored keymap overrides the firmware default** — a keycode newly bound
  in keymap.c will not appear if EEPROM already has that key assigned.
- **The `ak820pro_keycodes` enum is index-matched to via.json's
  `customKeycodes[]`. APPEND ONLY** — inserting shifts every later keycode and
  corrupts existing VIA keymaps (`scripts/check_via_sync.py` guards this).
- Keymap backup: `venv/bin/python hostagent/ak820keymap.py dump|restore|show`
  — raw dynamic-keymap buffer *and* encoders (a separate VIA command; skipping
  them silently drops the knob mapping).

## Stock Fn shortcuts (quick reference)

`Fn`+`Q/W/E` BT slots (tap = select, hold 2 s = pair) · `Fn`+`R` 2.4G ·
`Fn`+`←/→` hue · `Fn`+`↑/↓` brightness · `Fn`+`6/7` saturation · `Fn`+`X`
RGB on/off · `Fn`+`\` next effect · `Fn`+`-/=` speed (or 2nd colour on
Alphas/Mods) · `Fn`+`PgUp/PgDn` LCD brightness · `Fn`+`Home` LCD toggle ·
`Fn`+`Esc` bootloader · `Fn`+`Delete` ANIM_TOG · `Fn`+`C` clock format
(24h / 12h+AM-PM / off / date, persisted) · `Fn`+`D` debug page (tap
cycles debug page → camera page (big volts and %) → dashboard, HOLD
~800 ms resets the health counters) · `Fn`+`B` power mode (Always on /
Balanced / Power saver / Lights out; the enum keeps Full / Normal / Saver /
Minimal: the idle ladder on battery, Phase 2, shown on battery as a bulb in
the bolt's slot; Lights out keeps the lights and the backlight off, lighting
the screen briefly for a message). BT keys are inert in
wired mode. `Fn`+`P` (pair) is unbound by default.

## Critical warnings (details in the docs)

- ⚠️ **The mode slider is a power-source switch** — most flips brown-out the MCU
  and lose all RAM state; there is no "off" position. Cold power-off =
  `cable` + unplug ~10 s. → [hardware.md](docs/hardware.md)
- ⚠️ **The bootloader looks exactly like a dead board.** Check for USB id
  `0x7140` before assuming a hang. → [hardware.md](docs/hardware.md)
- ⚠️ **`ak820ctl flash write` erases first** — verify `ak820ctl info` answers
  before provisioning, and power-cycle after (a CRC match does NOT mean the
  board renders the new assets). → [fonts-assets.md](docs/fonts-assets.md)
- ⚠️ **Asset ids are assigned by sorted filename** — renaming/adding files
  forces a coordinated rebuild + re-provision. Two filenames are deliberate
  lies; do not "fix" them. → [fonts-assets.md](docs/fonts-assets.md)
- ⚠️ **If Bluetooth regresses, check the interrupt priority table first**, not
  the ISR rate. → [leds.md](docs/leds.md)
- ⚠️ **Keyboard feels slow / drops keystrokes?** Read `Fn`+`D` first: `rowgap`
  (single digits = healthy) and `stall>25` (must be 0) say whether the firmware
  is even involved. If both are clean, **check the HOST** — a leftover poller
  starves everything else. (On Windows, contention, not exclusivity: the
  interface is shareable; replies are what collide. Measured 2026-09-05. On
  macOS a hidapi poller seizes it outright.) `ak820 status` shows the daemon
  and the older agents; `hostagent/install-agents.sh --status` the older
  agents alone. → [hardware.md](docs/hardware.md)
- ⚠️ **Drawing to the LCD can eat keystrokes.** `lcd_draw_flash_text()` is
  synchronous, one LCD operation per glyph (~1.6 ms each); a full-screen
  `lcd_clear_rect()` blocks ~43 ms. Bulk drawing goes through the glyph queue,
  and big clears go in bands. Both rules were learned the hard way on
  2026-09-03. → [display.md](docs/display.md)
- ⚠️ **Never edit an installed LaunchAgent plist with PlistBuddy** — it silently
  strips the XML comments. Edit `hostagent/*.plist.in` and re-run the installer;
  the daemon's plist is generated whole by `ak820 install`, so re-run that.
- ⚠️ **Multiple sessions**: coordinate via SendMessage, claim files, flash only
  provenance-named artifacts. → [hardware.md](docs/hardware.md)
- ⚠️ **SPI0's `DMACNT` never counts down.** It holds the programmed length;
  progress is `CURCNT`, which keeps the previous transfer's count until the
  next one starts. And **never write SPI0's `IC` wider than the flags you
  just read**: `IC = 0x3F` after a `RIS` read was the lost-completion bug.
  Bitfield writes to `IC` are read-modify-writes too.
  → [display.md](docs/display.md)
- ⚠️ **SPI0 and the RGB row ISR share priority 3.** The row ISR's ~188 µs
  sets when DMA handlers run; changing either moves which transfer sizes are
  exposed to races. → [leds.md](docs/leds.md)
- ⚠️ **The last SRAM write before a loop that never writes again is lost at a
  watchdog reset.** Anything committed just before a spin, reset or lockup
  needs a sacrificial write after it (`commit_terminal()`).
  → [hardware.md](docs/hardware.md)
- ⚠️ **SN32 LLD files may have CRLF line endings.** Editing one with a tool
  that normalises newlines rewrites the whole file. Check `file <path>`
  first, and look at the diffstat before committing.

## Where things live

**Firmware** — `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/` (branch
`ak820pro-jdlien`; git history is the change inventory).
`graphics/lcd_bus.h` holds the authoritative flash memory map;
`graphics/res/flash_assets.h` is generated by `mkraw.py` and is the one
firmware↔asset coupling; `PATCHES.md` documents the seven ChibiOS patches.
Six core files outside `keyboards/` carry local commits —
`drivers/led/sn32f2xx.c` + `.h` (ISR hook, periodticks fix, flash-window mux
blanking, flush lock, Phase 2's committed-frame drive accounting, per colour
since the deep-sleep build, and the sleep pair),
`quantum/rgb_matrix/rgb_matrix.c` + `.h` (flush-allowed hook, Phase 2's
`rgb_matrix_reinit_effect`),
`platforms/chibios/.../wear_leveling_efl.c` (pre-write hook),
`drivers/encoder/encoder_quadrature.c` (`encoder_quadrature_state()`, the
deep sleep's knob-at-rest check) — all weak-hooked, no-op or additive for
other boards.

**Host daemon** — `ak820-agent/`, Rust, for Windows and macOS. One direct
dependency, Windows-only (`windows` pinned `=0.62.2`; the blocking async
spelling is `.join()`, not `.get()`); none on macOS, where the IOKit and JSON
code is hand-rolled. Two binaries because a PE has one subsystem:
`ak820-agent.exe` is windows-subsystem so it can never flash a console,
`ak820.exe` is a console CLI.
Built test-first; `cargo test` from that directory (305 tests + 9 integration).
`cargo build --release` gives static-CRT binaries (`.cargo/config.toml`); a
`v*` tag builds the Releases zip in CI (`.github/workflows/release.yml`).

The daemon side: `ak820 install [--in-place]` / `uninstall` / `status`, and
`ak820 --version` for which build and which protocols. The CLI is the evidence
for phases 0–2 — **every other command reads the board and never writes it**;
run these before touching the transport, they need no arguments and take under
a second each:

```sh
cd ak820-agent && cargo build            # then target/debug/ak820.exe
ak820 list            # 33 HID interfaces present, 5 of them this board's
ak820 list --caps     # the five collections; exactly one passes
ak820 info            # must equal `ak820ctl info` byte for byte
ak820 selftest        # budget guard, idle cancel, and recovery
ak820 watch [secs]    # narrate presence + what the drain discards
ak820 probe           # what SMTC sees; touches no keyboard at all
ak820 lighting        # RGB values read back off the board
ak820 health          # the firmware's counters, as ak820health.py prints them (--stalls --rows --isr --json --raw)
ak820 clock [--raw]   # the RTC, printed as `ak820ctl clock --read` prints it
```

`watch` is the one to reach for when something looks like contention: its drain
lines name whose traffic is landing on our handle. There is deliberately **no
CLI clock set**: one owner of the clock, or the lead learner is wrong. ⚠️ And
**`ak820 clock` refuses while the Python timekeeper task is running** — our
GET reply lands in its `ak820ctl`'s read and becomes one of *its* measurement
samples (the phase-2 audit's P1). `--anyway` accepts one possibly spoiled
sync; the other commands only print a note, because their replies fail the
C's version check rather than feed its learner.

⚠️ **The clock fixtures come from the C, not from reading the C.**
`scripts/clock_oracle.c` is the pinned `ak820ctl.c` clock code verbatim; its
tables feed `clock/cache.rs` and `clock/transaction.rs`, and its `decode` mode
renders a reply captured with `ak820 clock --raw` the way `ak820ctl clock
--read` would, which is the phase-2 gate. Build it with mingw64's gcc **first**
on `PATH` — otherwise gcc fails silently, the same xpack-DLL trap as `build.sh`.

⚠️ **Two generated files, one command regenerates both:**
`python scripts/gen_ascii_fold.py` writes `ak820-agent/src/text/fold_table.rs`
and `ak820-agent/tests/ascii_fold_parity.rs`. Never hand-edit either. The
generator checks the table against `ak820text.py`'s own `to_ascii` across all
1,112,064 scalar values and refuses to write if they disagree -- so a Python
carrying a different Unicode version fails loudly instead of drifting.

**Host tools** — `hostagent/` (`ak820text.py`, `ak820keymap.py`,
`ak820health.py`, `ak820lighting.py`, `ak820battery.py`; and the older agents
the daemon replaced, kept as the fallback: `nowplaying-macos.sh`,
`ak820-timekeeper.py`, the LaunchAgent templates and `install-agents.sh`);
`scripts/` (soak, bt_faults, consolelog, check_via_sync); `time-util-ak820pro/` (`ak820ctl`, `assets/mkraw.py`,
`mkanim.py`); `SonixFlasherC/` (flasher, libusb build).

**Reference** — `ak820pro-builds/` (build artifacts in `out/`, the chibios patch
bundle, `UPSTREAM-CONTRIBUTIONS.md`); `assets-src/` (font/splash sources and
shipped-atlas copies). Hardware datasheets, `CH582F_PROTOCOL.md`, pinouts and
the stock firmware images live in [fpb/ajazz-ak820-pro](https://github.com/fpb/ajazz-ak820-pro)
— a citation, not a component; `setup.sh` deliberately does not clone it.

If a dependency clone looks mass-modified, check
`git diff --ignore-cr-at-eol --stat` before believing it (CRLF from the
original Windows transfer).
