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
| [docs/test-bench.md](docs/test-bench.md) | The bench, run from the Mac: the USB relay (relay 2 cuts the keyboard's 5 V; relay 1 presses a key, the wake rig, with its measured reliability and latency), `uhubctl` (USB data), the trial and its guard, the power logger (INA228 + MAX17048) and measuring loads from the Mac, the "Christmas Tree" outlet (retired from the bench by 11-03), hub depth limits, the camera (the Pixel 8 at 240 fps over adb, `scripts/phonecam.py`) |

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

## Current state (2026-11-02)

**Resume from [`plans/current-status.md`](plans/current-status.md)** ("2026-10-22
— RESUME HERE"). **Feature-complete for JD's board.** What's left:
- an untethered drain at real use, running to the RGB cut. It restarted
  from FULL at 04:44 10-24 (`charge_mah` -1116.956 at the start): the move
  to Buzz, the new Mac, on 10-23 spoiled the first;
- stripping the bench, the soak, and the release for other owners.

**v0.3.1, released 11-01 22:25 from `cfe6c2d3a5`** (`ak820pro-jdlien`
and `deps.lock` there since 18:36): v0.3.0 plus F-033's fix (the row ISR's
`NO_LED` read, ~1.3 mA on a dark frame), the daily and fpb builds, the
Windows agent 0.3.1 (a version bump). Tagged once codex's wake gate was
complete: cases 1, 2 and 4 on black, 3 on white
(`plans/current-status.md`).
**v0.3.0, released 11-01 from `4c7395a4c6`**: the 10-31 firmware audit's
fixes (41 of its 44 confirmed findings; `plans/AUDIT-2026-10-31.md`,
`plans/BACKLOG.md`'s audit section) and the battery readout's Icon only,
`ak820pro-jdlien` fast-forwarded to it and pinned in `deps.lock`; the daily
and fpb builds and the Windows agent 0.3.0. ⚠️ Shipped before two checks:
the clean-Windows install (gremlin's Windows Sandbox is off) and the wake
fixes' USB cases 2-4 (`plans/current-status.md`). A protocol change for host
tools: a profiles restore applies the live record before its commit, and
the commit names the live settings' side (`hostagent/ak820profiles.py`).
**On white since 17:20 11-04: the dev build of `row-isr` `245fcfe8e3`**
(token `0x154c76fb`; devprobe `0x82df55bc`, daily `0xa462d003`): stage 5h
plus the held-key fix (the slot scans the row whose rail it just
deselected: a held key's stored-charge flash under the finger; a
remainder on the row below at 1 tick, for the camera) and the dev
Diagnostics page **Floor probe**
(Color, Ticks, Color R, Ticks R, Split; a click captures the knob; in
the Write test's place, that page retired) and sub 3's every-LED (254)
and split (253) patterns. On devprobe a byte is its pulse width in
ticks (the dev build is the normal scale). **A flash moratorium on white
until the RGB cut** (the drain's last 15%, ~2 days from 11-04 evening).
**Stage 6's floor evening is done** (11-04
12:05-15:10, `history/rowisr-stage1-20261101/README.md`, "Stage 6's
floor by eye"): every colour visible at one tick; the eye's unit step
lost at 6-7 ticks red, 11-12 green and blue; the split match red 12 =
green 9-10 = blue 23 (the white's composition; equal ticks keep the
hue); **a held key brightens its column neighbours at the dim end** (the
scan's microsecond on the just-deselected rail: a stage 6 fix). Owed after the cut: the daily soak (JD's `Fn`+`Esc` for the return),
the camera's linearity pass at 1-8 ticks and its look at the held-key
remainder, D9. ⚠️ The power mode was set to Always on for the session and a restore
persisted it: Power saver goes back with the standing state.
**Before it, from 08:33 11-04: stage 5h of the row ISR rewrite,
`row-isr` `bde904e491`** (dev, token `0xfeeeb2db`, heap gap 368 B; the
daily `0xcaa61e41`, 2656 B; the floor probe `devprobe` `0xefa1c31f`):
the per-slot judgment back, the detector behind `ROWISR_USB_DETECT`
(the dev build's default, out of daily and fpb, `build.sh`'s check),
the silence report's fixes kept, `ROWISR_K_Q6` overridable for stage
6's floor measurement; codex READY twice. Measured on the flash: the
handler 52.8 us and 42.2% at full white (5g 52.1/41.7, 5e 52.3/41.8),
the lit draw 91.6 mA, 0 spurious; the silence set 10 of 10; the five
wakes 5 of 5 kept the key (0 spurious, 0 frame rejects); Hutch's M4
with-run on it ARRIVED (the rig's key on the Mac after 32 min asleep
with the keep-alive). Owed: a daily build's soak (JD at the board: the
return to dev is `Fn`+`Esc`), then stage 6's floor evening with
`devprobe`. **White is Hutch's since 10:01 11-04, in the standing
state**, JD's lighting Purple/Blue (val 125). The 5g soak
ended 00:35 11-04 clean (4 h, 0 losses past the boot's, 0 frame
rejects of 14.8 M). The dim end's plateaus are QMK's CIE table before
the byte: stage 6's D9, with the per-colour floor by eye (the README's
"Stage 5h built overnight" and "Stage 5h on white").
**Before it, from 20:19 11-03: stage 5g of the row ISR rewrite,
`4f19e6c31f`** (dev, token `0x34d7c5fb`, heap gap 336 B, `row-isr`): 5e
plus the frame counter's judgment every eighth service with the evidence
kept at every one (three codex rounds, READY at 20:18). It measured
52.1 us and 41.7% at full white against 5e's 52.3 and 41.8%, so **the
decimation is reverted on 11-04** (the detector goes behind a flag the
daily build leaves out; the silence report's pairing and PENDING verdict
stay). The awake soak on it from 20:34 with JD typing, white to Hutch
asleep at ~00:35. JD's eye at 444 Hz: the fringe all but gone, the
screen's drawing about twice as fast (`plans/current-status.md`,
`history/rowisr-stage1-20261101/README.md`, "Stage 5g on white").
**Before it, from 15:06 11-03 (and 13:34-14:31): stage 5e of the row ISR
rewrite, the 125 us cadence, `739fe1b635`** (dev, token `0xf222e31c`,
heap gap 376 B, `row-isr`; the keep-alive and the battery icon's colours
in it; 5d `6a9fc0fcfe` from 13:02, the SRAM trial 5f from 14:31 to 15:06,
no gain): the
444 Hz field, the light exact at full white, the handler 49.5 us and
39.6% CPU, 87 omissions in 300 s (the scan slots past the 90.5 us arm
deadline; 5c's 2,047 window omitted 2,311), the presser exact to 10 ms;
owed: the camera gate, the presser gates with Buzz locked, the soak
(`plans/ROW-ISR-PLAN.md`'s log, `history/rowisr-stage1-20261101/README.md`,
"Stage 5 on white").
**Before it, from 05:08 11-03: stage 4b of the row ISR rewrite,
`6b90f3b821`** (dev, token `0x4215c3e2`, heap gap 400 B, `row-isr`):
stage 3's scan without mode writes (BSET/BCLR only, two port reads, the
settle on the scheduler's counter, the consume's XOR under its lock, the
rig's keys counted at the scan, op 28 subs 12-14), the frame counter read
twice twelve cycles apart (it tears at a byte carry), the sections
opt-in (`ROWISR_SECTIONS`), and the clock chip's ordinary transactions
with the row ISR running through them, the 5 ms ones still held off (a
7-byte read stretches to ~5.5 ms unmasked). Flashed and gated hands-free
on JD's advance go for the night with the presser (every short-tap,
chord, settle, silence and wake gate exact; page 4 71.6 us a slot); the
night's awake soak ran clean to 09:35; **the camera gate met at 11:28
11-03 from the Mac** (two forced clock-chip writes filmed at 240 fps, no
trace; `history/rowisr-stage1-20261101/README.md`, "The gate met from
the Mac"), so `pcf-unseen`'s deferral retirement is JD's call
(`plans/current-status.md`, the 11-03 night block;
`history/rowisr-stage1-20261101/README.md`).
**Before it, from 02:27 11-03: the exit-only build, `f0ec5c68df`** (dev,
token `0x9e2d894a`, heap gap 408 B, `row-isr`): the diagnostic below with
the exit snapshot time only and the elapsed sample's verdict by the two
spans and the bus-event generation; flashed on JD's advance go for the
night, the board woken by the presser's own press. Its stamps read
73.6 us a slot against 80.2 (page 4 still 80.2: the dev build's section
instrumentation costs the same outside the stamps, compiled out next);
the silence set 15 of 16, the FAIL a torn FRMNO read at a byte carry
(two false losses; fixed next by reading until two reads agree)
(`history/rowisr-stage1-20261101/README.md`, "The exit-only build's
flash"). The presser (A1 = (0,13) Delete = F19, A0 = (3,14) PgDn = F20,
pressed from the logger's REPL by `scripts/presser_repl.py`) runs the
short-tap and wake gates hands-free.
**Before it, from 00:06 11-03: the cost diagnostic, `95ef5cbc5d`** (dev,
token `0xda2a24d5`, heap gap 408 B, `row-isr`): the trim below plus the
handler's sections stamped (op 28 sub 11) and a register read timed
(sub 10). It answered the 19 us: a register read is free, and the
detector's four sections (both snapshots, both judgments) are 31 us of
bookkeeping with no hot spot, at 3-5 cycles an instruction from flash;
the remedy is the judgment every eighth slot and no exit judgment, next
(`history/rowisr-stage1-20261101/README.md`, "The cost diagnostic").
**Before it, from 23:19 11-02: the trim, `a47c134079`** (dev, token
`0x1a291156`, heap gap 464 B, `row-isr`): the detector build below with
no software divide on the slot. Its warm windows: 80.0 us a slot against
the detector's 78.8 and stage 2's 59.8, so the divides were not the cost
(stage 2's vector had five divide calls and was fast); the suspects are
the six USB register reads a slot and the 20 kHz tick's. The cost
diagnostic `95ef5cbc5d` (token `0xda2a24d5`, dev only: the handler's
sections stamped, op 28 sub 11, and a register read timed, sub 10) is
built for the next key and go (`history/rowisr-stage1-20261101/`,
"The trim's flash"). Also that night: the first key after a sleep over
30 min takes ~2.4 s on the Mac, the module's own link drop
([docs/wireless.md](docs/wireless.md), "The module ends the link"), not
the firmware's; accepted, a keep-alive wake pinned in `BACKLOG.md`.
**Before it, from 16:42 11-02: stage 2 plus D3's USB frame-counter
detector and the all-interrupt silence injection, `5c0e6249d0`** (dev,
token `0x60d4a06b`, `row-isr`, heap gap 464 B; nine codex rounds, the
closing invariant "wherever time is discarded the loss generation moves";
`plans/ROW-ISR-PLAN.md`, D3 case 5): the silence set passed 16 of 16 as
predicted (`history/rowisr-stage1-20261101/`, `silence_check.sh`: 5-7.9 ms
exact, 8.1-200 ms the guard, 350/700/1,049 ms the frame counter past the
tick's 349.5 ms alias, 1,000/2,048/7,000 ms the guard; with the data cut
350 ms undetected, the declared limit). Dev op 28 subs 6-9
(`scripts/rowisr_diag.py usb|silence|report`). The wake read after JD's
key (19:06): one sleep of 2.3 h, no stray, spurious 1 across the wake and
0 across the silences, the window 3,743.5/s with nothing missed. Owed on
it: the witness's edges for the lengths, and its cost: the warm windows
(20:43) put the detector at +19 µs a slot by page 4 (59.8 to 78.8, CPU
22.4% to 29.5%), two divides per slot in the judgment beside stage 2's
three; a trim commit with no divide on the hot path is next, then stage
2's list below.
**Before it, from 19:44 11-01: the row ISR's stage 2, the hot path on
direct registers, `b120a2069c`** (dev, token `0x4849bde6`, the branch
`row-isr`, `plans/ROW-ISR-PLAN.md`, the record in
`history/rowisr-stage1-20261101/`; 21 h on white: 6 sleeps, 3 spurious
invocations, no stall): CT16B4 schedules the 267 µs slot,
CT16B0/1/2 fire one clean pulse per slot, the handler's mean 60 µs against
the old callback's 196 (page 4), the CPU share 22% against 73, no stall,
the row gaps as before. ⚠️ **Its first flash (19:20) settled the mux pin
order: R, B, G per key row, as `config.h` says**; the old driver's B, G,
R-of-next was a one-slot lead over the pins (its widths reached the LEDs a
cycle late), which stage 2's one-shot restart does not have, so the first
build rendered every frame rotated. Light at full scale within 1% of the
base by total; the old driver was not additive across colours (its white
64 was 54% of the sum of its single colours), so no one scale matches it
state by state. Owed on it: deep sleep's wakes with the waking key kept, the
witness's pulse gates (JD's eye, scan-only and the wake with the RGB
dark passed, 11-01 and 11-02 morning).
**Before it, from 18:09 11-01: stage 1 plus the NO_LED fix,
`b3270996d3`** (dev, token `0x991e7b11`): stage 1's A/B against the v0.3.0 candidate
passed every hands-free gate within 1.3% once the fix was in both builds
(`history/rowisr-stage1-20261101/`); the first stage 1 build drew 1.3 mA
more at dark through the audit's F-033 read, now fixed on the branch and
measured. Owed on it: Bootmagic, deep sleep's five wakes, the
phantom-or-missing count (the presser, 11-02). **Before it, from 14:40
11-01: `4c7395a4c6`** (dev, token `0x6f758b40`, the release candidate, its
checks in `history/v030-rc-white-20261101/`).
**v0.2.0, released 10-29 from `8ec0c8b9b4`**: the mainline below plus
Help's More info, fast-forwarded onto `ak820pro-jdlien` and pinned in
`deps.lock` for the release (the daily and fpb builds, the Windows agent
0.2.0; the README rewritten as the project's pitch). Warren's `ds-phase`
diagnostics stay out of it.
**The mainline from 10-28 evening to that release: `c4bc085271`** (`ak820pro-jdlien`
fast-forwarded from `ce3f842de2` by Warren): the
Font setting (8px, 10px, 10px bold; the preview, the face in profiles),
the 12 px greyscale icons, the dashboard's spacing, System info in
Diagnostics, the camera page removed, the screen's default level 80; and
Warren's `gremlin/pcf-unseen` (the clock chip's write when nobody is
looking) and the dev Write test. The daily build is clean (heap gap
2336 B). **The two boards are called white (JD's, on Buzz's bench: the
drain, the power logger) and black (gremlin's), after their cases.**
**Black runs Warren's `fcb7ae00b4` since 12:43 10-30** (ds-phase, as on
white; token `0xf2a645a7`), flashed on Buzz's relay cable
(`history/ds-phase-black-20261030/`). Before it: `8ec0c8b9b4` dev (token
`0xb5f2fdab`, flashed from Gizmo at 23:34 10-28), and gremlin's own
`c4bc0852` build (token `0x189635f2`) from 20:51 10-28.
**On white since 17:28 10-30: `5c8c5f5ea8`** (dev, token `0x5b880dd4`,
heap gap 224 B, the branch `icon-only`): the mainline `8ec0c8b9b4` plus the
battery readout's Icon only (`plans/BACKLOG.md`, "Icon only"; the text slot
clear, the icon and the warnings kept), flashed mid-drain with the settings
kept (`history/icon-only-20261030/`). Warren's ds-phase diagnostics are off
white now; they run on black.
**Before it, from 00:03 10-29: Warren's `fcb7ae00b4`** (dev, token
`0xf2a645a7`, heap gap 152 B, `gremlin/ds-phase`): `27d1105dc1` plus
codex's fixes and op 24 slot 10, the sleep a reset cut short, kept until
the next reset (`history/ds-phase-check-20261029-0002/`).
**Before it, from 23:51 10-28: Warren's `27d1105dc1`** (dev, token
`0xbc3b64c4`, heap gap 184 B, `gremlin/ds-phase`): the build below plus
deep sleep's phases in the watchdog record and the sleep kept through a
reset (op 24 slot 9), the diagnostic for gremlin's WDT reset in a deep sleep
(`plans/BACKLOG.md`). Its first finding: the WDT does not count in
Deep-sleep (840 counted s unfed, `history/wdt-asleep-20261028-2330/`).
**Before it, from 23:09 10-28: `8ec0c8b9b4`** (dev, token
`0xe612779e`, heap gap 224 B, the branch `more-info`): the mainline above
plus Help's More info (P1d): the credits beside the splash's bunny, and a
turn to a QR code to this repository
([`plans/MENU-TEXT.md`](plans/MENU-TEXT.md), "Help > More info";
`scripts/gen_menu_art.py`).
**Before it, from 20:39 10-28: `fbc6c4a1fd`** (dev, token
`0xd044efc5`, heap gap 224 B): the mainline above without the screen's
default level 80 (a default only, so no reflash is needed for it):
`8b0f47e245` below plus, in 10px (Terminus regular), the page titles and
the song's title kept bold.
**Before it, from 20:19 10-28: `8b0f47e245`** (dev, token
`0xb9f4c717`, heap gap 224 B, the local branch `menu-8x16`, not pushed):
`ccfe080920` below plus Terminus regular as a third face (8px, 10px, 10px
bold), the Font page's 0.3 s preview and note, the face in every profile,
About in Diagnostics as System info, and the Fn+D camera page removed.
**Before it, from 18:59 10-28: `ccfe080920`** (dev, token
`0x65019724`, heap gap 128 B, the local branch `menu-8x16`, not pushed):
`59b2c9d7b3` below plus the 10px face's icons from JD's 12 px set in four
greys (`graphics/res/icons12_2bpp.h`, made in `~/Documents/ak820pro-icons`)
and the Font icon he picked in both faces.
**Before it, from 18:44 10-28: `59b2c9d7b3`** (dev, token
`0x1765e95a`, heap gap 128 B, the local branch `menu-8x16`, not pushed):
`ecb10f0e9b` below plus the Font setting
([`plans/MENU-8X16-PLAN.md`](plans/MENU-8X16-PLAN.md)): a Font row after
Bootloader picks 8px (Cozette 6 x 14, the menu as it was) or 10px
(Terminus Bold 8 x 16, the default), and 10px also draws the song's
artist and title; the dashboard's song lines a row apart, the clock 2
rows down and the lock row 1 down ([docs/display.md](docs/display.md)).
Flashed mid-drain with the settings kept. **Before it, from 18:22:
`36fe62ea9c`** (token `0xf9274d6f`), the same without the spacing.
**Before it, from 11:05 10-28: `3b6e43ef73`** (dev, token
`0xcddf82ef`, the local branch `font-test`): `ecb10f0e9b` below plus a
temporary Font test page in Diagnostics, frames from the external flash at
0xE00000 for judging the 8 x 16 menu faces; not for merging.
**Before it, from 21:54 10-27: `ecb10f0e9b`, Warren's
`gremlin/pcf-unseen`, not yet merged** (dev, token `0xdc5524d4`, heap gap
128 B, at the floor): the mainline `ce3f842de2` (`deps.lock`) plus the
clock chip's write only while the lights are dark or after 10 min without
input, and the softer LED blink at a flash write with the dev Write test.
Flashed mid-drain with the settings kept; the profiles converted to the
Win/Mac switch's sides.
**Before it, from 20:29 10-26: `1f3c79e904`** (dev, token
`0x60a8fe4b`): the menu's idle close at 60 s.
**Before it, from 16:01 10-26: `553108e5f2`** (dev, token
`0x9286ca96`): the profile page's polish (the actions' icons, the
summary's rule, the 300 ms preview).
**Before it, from 13:29 10-26: `13c5e910cb`** (dev, token `0xffc7a951`):
settings profiles complete, eight slots with Save new, the preview and
Rename, flashed mid-drain with the settings kept for the first time.
**Before it, from 09:49 10-26: `57d5e90030`** (dev, token `0xde2973aa`):
settings profiles' P5a and P5b, the store, the Profiles pages and the
Next/Previous profile keys
([`plans/SETTINGS-PROFILES-PLAN.md`](plans/SETTINGS-PROFILES-PLAN.md)), and
Warren's effects' speeds, flashed mid-drain on battery from Warren's branch
for JD's look and merged after it.
That flash reset the EEPROM's settings one last time (firmware before P5a
has no `HC_PROFILES`); from here `flash.sh` keeps them. **Before it, from
19:08 10-25: the mainline until 10-26, `30f1e0cfde`** (dev, token
`0x195cbf4c`): Warren's configuration menu (S0 through P4, the Clock
options), the LED fix and the wake's dark-frame fix, flashed mid-drain on
battery; the drain runs on to the cut. ⚠️ **On Buzz the daemon's lock-light channel sent nothing from
10-23 to 19:28 10-25**, until Input Monitoring was granted
(`plans/current-status.md`): a new Mac needs that grant before it works.
**Before it, from 22:02 10-24: `52acdffe99`** (dev, token `0xab194817`,
`mac/wake-dark-frame`): `b9555ff3e6` plus the wake's dark-frame fix
(`plans/BACKLOG.md`). **Before it, from 23:48 10-23: the mainline until
10-25, `b9555ff3e6`** (dev, token `0x3c117332`), flashed from Buzz. It is `36afff30e8` plus `ce229f87c6` and a credit comment, and it
moves the glyph pump off the clock's seconds tick, the pass that hit 10 ms
every second. On gremlin's board since 17:03 10-22, `count_ge_10ms` fell
from 0.175 a second to 0.016. ⚠️ **The bench moved to Buzz on 10-23**: the
keyboard's data cut is `uhubctl -l 3-1.3.4 -p 2`, not `0-1.4`, and the wake
rig is broken ([docs/test-bench.md](docs/test-bench.md)).

**Before it, from 14:22 10-21: `36afff30e8`** (dev, token
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
([docs/hardware.md](docs/hardware.md)). (Through v0.3.1; the row ISR rewrite
on white since 11-03 runs 8,000/s at ~50 µs and ~40%: [docs/leds.md](docs/leds.md),
"The row ISR rewrite".) The old row ISR measures 3,876/s with a
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
- backs up the VIA keymap (with the macros since P5a), **the RGB
  lighting** and, where the firmware has `HC_PROFILES`, **the settings
  profiles and the live settings**, and refuses if any backup fails
  (`--no-lighting`, `--no-profiles`, `--no-backup` to override), or if
  the board holds eight profiles (a firmware since 10-27 keeps seven);
- **refuses on battery once the RGB cut has fired** (the reserve; a pack that
  dies mid-write leaves the board half-erased; `--on-reserve` overrides);
- **dumps the battery log** to `~/Documents/ak820pro-battlogs/`, fatal unless
  `--no-battlog` (a flash erases the RAM log; one was lost to a retry loop on
  10-11);
- asks the firmware to jump (`hostagent/ak820bootloader.py`); a build without
  the jump (daily, fpb) answers "unhandled", and it falls back to asking for
  `Fn`+`Esc`;
- flashes, restores the keymap, then the profiles and the live settings
  (the screen, the indicators, the clock format, the readout, the power
  mode and the lighting), and syncs the clock. The live record is the one
  RGB restore; the lighting's own restore runs only when there is none (a
  firmware from before P5a, or a failure).

Bootloader by hand is `Fn`+`Esc`. **A flash erases the emulated EEPROM**: VIA
keymap and RGB effect/colour, LCD brightness, clock format, the indicators,
the readout, the power mode and the settings profiles (all restored by
flash.sh since P5a, `hostagent/ak820profiles.py`; the first flash from an
older firmware has nothing to back up and resets them one last time), BT
slot, the saved battery level, persisted RTC period
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
- **The Next and Previous settings-profile keys** (`PROF_NXT`, `PROF_PRV`;
  "Prof+" and "Prof-" among VIA's custom keycodes) are unbound by default:
  bind them in VIA. A press loads the next or previous saved profile and
  names it in the dashboard's status band.
- ⚠️ **VIA's macro buffer is 18 B since the 10-31 audit** (19 B from P5d,
  10-26): the profiles' block (seven profiles and the Win/Mac switch's
  last record since 10-27) takes the EEPROM's top 218 B and the byte below
  it is the settings' owner (which side of the switch the live settings
  are), and QMK's 100 B minimum is sidestepped by sizing the buffer
  directly (`config.h`). Sixteen empty macros fill 16 of those bytes: in
  practice, no macros. A backup whose macros don't fit restores without
  them (`ak820keymap.py` exits 3, `flash.sh` warns).
- Keymap backup: `venv/bin/python hostagent/ak820keymap.py dump|restore|show`
  — raw dynamic-keymap buffer *and* encoders (a separate VIA command; skipping
  them silently drops the knob mapping).

## Stock Fn shortcuts (quick reference)

`Fn`+`Q/W/E` BT slots (tap = select, hold 2 s = pair) · the slider picks BT /
2.4G / cable (`Fn`+`R` only re-selects the dongle with the slider on 2.4G) ·
`Fn`+`←/→` hue · `Fn`+`↑/↓` brightness · `Fn`+`6/7` saturation · `Fn`+`X`
RGB on/off · `Fn`+`\` next effect · `Fn`+`-/=` speed (or 2nd colour on
Alphas/Mods) · `Fn`+`PgUp/PgDn` LCD brightness · `Fn`+`Home` LCD toggle ·
`Fn`+`Esc` bootloader · `Fn`+`Delete` ANIM_TOG · `Fn`+`C` clock format
(24h:ss / 24h / 12h:ss / 12h / date / off, persisted; the menu's Clock page
sets the same) · `Fn` + a knob click opens and closes the configuration
menu (the knob drives it; typing still works;
[`plans/CONFIG-MENU-P1-DESIGN.md`](plans/CONFIG-MENU-P1-DESIGN.md); its
Profiles row, page one's last, holds up to seven settings profiles: Save
new, Load, Save, Rename and Delete, each with its icon, and a 0.3 s rest
on one previews its lighting and screen level; Rename alone takes the
keyboard's typing,
[`plans/SETTINGS-PROFILES-PLAN.md`](plans/SETTINGS-PROFILES-PLAN.md); each
side of the Win/Mac switch remembers its profile, and a flip brings the
other side back as it was left (10-27); Font, under Bootloader, picks
8px (Cozette), 10px (Terminus) or 10px bold (Terminus Bold, the default)
for the menu and the now-playing text, previewed after a 0.3 s rest and
saved in profiles too (10-28); Reset settings, under Font, puts the
defaults back and keeps the profiles; Help's More info shows the credits
and a QR code to this repository (10-28); System info, About's page, is in
Diagnostics since 10-28; the Power page shows each mode's bulb) ·
`Fn`+`D` debug page (a tap toggles dashboard ↔ debug page, or menu ↔
debug page inside the menu; HOLD ~800 ms resets the health counters; the
camera page was removed on 10-28, since the bench's power cut and INA228
logger replaced filming the screen, and the debug page still shows the
`5C`) · `Fn`+`B` power mode (Always on /
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
- ⚠️ **SPI0 and the RGB row ISR share priority 3.** The row ISR's ~188 µs (~50 on the rewrite)
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
Seventeen core files outside `keyboards/` carry local commits —
`drivers/led/sn32f2xx.c` + `.h` (ISR hook, periodticks fix, flash-window mux
blanking, flush lock, Phase 2's committed-frame drive accounting, per colour
since the deep-sleep build, the sleep pair, the wake's
`sn32f2xx_led_committed_dark()`, and since 10-27 the scan through a flash
program by default, `sn32f2xx_pgm_scan`, and the render count
`sn32f2xx_led_commits()`),
`quantum/wear_leveling/wear_leveling.c` + `.h` (`wear_leveling_consolidate()`
and `wear_leveling_log_used()`: `flash_tidy.c`'s early cleanup, where the
LEDs' blink can't be seen; since the 10-31 audit, an 8-byte line holds 4
value bytes and a Berger check, which no torn write passes, F-010, and
`wear_leveling_failures()`, the failed writes since the boot, which fail
every settings flush), `drivers/eeprom/eeprom_wear_leveling.c` (the write
hook that attributes the LED blink to its writer),
`quantum/nvm/eeprom/nvm_dynamic_keymap.c` (a VIA keycode is one write, not
two, F-017), `tmk_core/protocol/chibios/usb_main.c`
(`RAW_HID_TASK_MAX_REPORTS`: the raw HID reports a pass handles, F-001),
`quantum/rgb_matrix/rgb_matrix.c` + `.h` (flush-allowed hook, Phase 2's
`rgb_matrix_reinit_effect`, the effects' speed hooks
`rgb_matrix_runner_i_time()` and `rgb_matrix_jellybean_drop()`), and the two
animations that call them, `animations/runners/effect_runner_i.h` and
`animations/jellybean_raindrops_anim.h` (the board's curves are
`rgb_speed.c`),
`platforms/chibios/.../wear_leveling_efl.c` (pre-write hook),
`drivers/encoder/encoder_quadrature.c` (`encoder_quadrature_state()`, the
deep sleep's knob-at-rest check; `ENCODER_REST_PINS_EQUAL`, the count
restarted at each rest), `quantum/encoder.c` + `.h`
(`encoder_map_delay_wanted_kb()`: the menu skips the 1 ms detent waits for
turns it swallowed), `quantum/action_tapping.c` + `.h`
(`action_tapping_idle()`: the menu's Rename takes the keyboard only once
nothing is held or queued) — all weak-hooked, no-op or additive for other
boards.

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
ak820 health          # the firmware's counters, as ak820health.py prints them (--stalls --rows --isr --sched [--window N] --json --raw)
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
