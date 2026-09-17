# Backlog — known, accepted, or deferred items

## ⚠️ Concurrent raw-HID use breaks VIA, and has been all along (2026-09-05)

**Symptom the owner sees:** VIA's console fills with `Receiving incorrect
response for command`, and lighting or keymap changes appear not to take.

**Cause.** Windows delivers HID input reports to every open handle, so any
other process talking to the board injects replies into VIA's stream. Measured
with VIA's own log: it asked `CUSTOM_MENU_SET_VALUE` and received
`07 11 01 00 85 60 17 CE` — an `FC_INFO` reply meant for another process — and
also `07 12 04 00`, the **now-playing agent's** `TEXT_PLAYBACK` echo. That agent
writes every ~3 s, so this is a near-certainty during any VIA session.

⚠️ **One injected report desyncs VIA persistently.** After the first bad pair,
every subsequent command received the *previous* command's echo; the stream
does not resynchronise on its own.

⚠️ **The writes still land.** The board executes and echoes each command — VIA
loses the confirmation, not the write. So a change made during a desync has
probably applied even though VIA reported an error, and VIA's displayed state
may then disagree with the board. Read values back (lighting is
`[0x08, 3, 1..4]`) rather than trusting the UI afterwards.

**Workaround now:** stop the host agents before a VIA session —
`hostagent/install-agents-windows.ps1 -Status` shows them.

**Fix, proposed for `ak820-agent` phase 4** and recorded in
[AK820-AGENT-PLAN.md](AK820-AGENT-PLAN.md#️-via-coexistence-the-broadcast-is-bidirectional-and-via-is-the-victim):
VIA's traffic is unmistakable in the daemon's drain log — leading id
`0x07`/`0x08`/`0x09` on QMK lighting channel `0x03`, which none of our four
channels can collide with — so the daemon can defer non-urgent work while VIA
is active. A clock sync has 300 s of slack and no reason to spend it stepping
on somebody's UI. That would make the daemon **better** for VIA than the Python
agents it replaces.

## ~~Red LED-row flash during/after RGB adjustment~~ — FIXED 2026-09-01 (6ca0102941)

**Resolution:** the driver's own `EFLD1.state != FLASH_PGM` guard skipped
the row ADVANCE during flash programming but left the current mux row
energized, so the masked program windows froze that row at its live colour
slot for the whole multi-ms write (~18x brightness: red one time, green
another). The FLASH_PGM branch now de-selects every mux pin (ISR-safe GPIO
writes; `sn32f2xx_blank()` is NOT ISR-safe under hardware PWM). Verified by
JD: long hue/brightness sweeps AND 15 host-forced EEPROM writes at 1 Hz --
no pops and no perceptible darkening. The
proposed-fix notes below are historical.

**Symptom (historical):** holding an RGB adjust key (e.g. Fn+Up), a row of red LEDs
flashes briefly. Longstanding, cosmetic.

**Root cause (understood, not guessed):** the settled eeconfig write fires
~0.9 s after the values stop moving (RGB_SETTLE_MS). The EFL program window
masks interrupts for its few-ms duration (efl_ramtext.diff -- deliberate,
see the audits), which freezes the LED row mux mid-cycle: whichever hardware
row was energized in its RED time-slot stays lit at full duty until the
write completes. It is the flash write announcing itself.

**Proposed fix:** blank the LED matrix around the program window --
`sn32f2xx_blank()` exists for exactly this (forces every row/col pin
high-Z; created for the stop-the-ISR case, currently zero callers). Call it
from `backing_store_pre_write_hook()` before the write.
**⚠️ The blocker to resolve first:** blank changes pin MODES to high-Z; if
the row ISR only writes levels/duties and never re-initialises pin modes,
the matrix stays dark after the write. Verify whether `rgb_callback` /
the driver's row advance reconfigures modes per cycle, or add an explicit
re-init after the write. Needs a hardware round-trip -- do not ship blind.

## Row-ISR body: the one lever that lifts scan rate, main loop and field rate together (measured 2026-09-03)

`rgb_callback` re-arms its PWM counter at its END, so its period is (body +
~70 µs) and the body sets everything downstream. Health page 4
(`ak820health.py --isr`): 3,876 ISR/s, body **188 µs mean** (160 µs LED-only,
261 µs with the row scan), **72.8% of the CPU**. Where it goes: 15
`pwmDisableChannel` + 15 `pwmEnableChannel` through the ChibiOS API at ~5 µs
each (osalSysLock/Unlock, driver dispatch, RMW on PWMIOENB/PWMCTRL), 18 row-pin
writes, and a ~85–100 µs row scan whose `select_row`/`unselect_row` go through
`palSetLineMode` (slow on SN32). Direct register writes and a pre-computed
IOENB mask per row would plausibly halve the body; the row scan could drive the
row pin without a mode change. Every 10 µs off the body is ~+4% ISR rate, i.e.
+4% field rate AND +4% per-row sampling AND a proportionally faster main loop.
Not for now: it is a rewrite of a shared core driver on the input path of a
daily driver, and the owner's constraint is "any flickering is a non-option".
Measure with `--isr` before and after; the observer effect of the hooks is nil.

## Clock: the sync interval and the firmware's frequency window must agree, and nothing checks it (2026-09-04)

`sync_interval` (host, `ak820-timekeeper.py`) must exceed `WIN_LOCKED` (firmware,
`rtc/rtc.c`) plus a slew's settling: a slew writes the period register ~3 times
and every write restarts the frequency window, so a window longer than the
clean stretch between syncs never completes and the loop freezes. That is
exactly what happened 05:30–11:00 on 2026-09-04: a 120-s "fast" interval
against the then 128-s window froze the loop at a wrong period while the ILRC
sped up ~0.8 % overnight, the residual stayed at +300 ms per sync, and the
large residual is what kept the interval fast — the symptom sustained its own
cause. Both constants were individually reasonable; only their product was
wrong, and it presented as "the clock is 300 ms off", not as two constants
disagreeing. Fixed by hand (interval 180 s, window 32 s), which restores the
convention but not a check.

**Proposed:** expose `WIN_LOCKED` and the slew rate on an `HC_RTC` page and have
the timekeeper read them at startup and refuse or warn if its interval is too
short. That turns an unenforceable cross-language, cross-repo comment into a
runtime check on the only channel that sees both sides; the health version byte
degrades it gracefully on older firmware.

## Scan-rate observation

Instrumented builds read ~230-310 Hz (console + probes overhead); the daily
build reads ~375 Hz. Judge scan-rate bands per flavor.

## rx_malformed baseline

The fault suite's byte soup legitimately raises rx_malformed (by ~5 per
run) for the remainder of that boot. Normal-use expectation is 0 growth.

## On-LCD health readout (BT-mode diagnostics)

Raw-HID replies don't come back in BT mode, and flipping the slider to read
them wired POWER-CYCLES the board (see CLAUDE.md), wiping the counters. The
only way to diagnose a BT session is to show the counters ON THE PANEL --
e.g. a magic-key or Fn-combo that paints tx_sent/timeouts/drops/gap into
the text band for a few seconds. Small, uses display_set_param_status-like
plumbing.

## Keystroke-miss hunt (transport-independent)

JD perceives occasional missed keystrokes on BOTH transports; tonight's BT
bursts measured clean (drops 0, coalescing never engaged). Prime suspect:
wear-leveling sector erases blocking the main loop 50-300 ms, rare and
irregular. Protocol: instrumented build + consolelog.sh + normal typing;
the [stall] line attributes any >=4 ms gap to flash/blit/i2c the moment it
happens. Run when it next "feels bad".

## Slider power asymmetry + host-switch key clearing (2026-09-01, Rachel + JD)

Measured: wired->BT does NOT reboot; BT->wired reboots EVERY time (power-
source switchover; direction-asymmetric ride-through). The boot reset cause
is now readable -- HC_CONN reply byte 7 carries raw RSTST. MEASURED
2026-09-01: the BT->cable flip reset is rstst=0x05 (LVD+SW, no POR) --
an LVD BROWNOUT during the power-source switchover. Question CLOSED.

Held-key-across-host-switch: QMK's handle_host_changed() verifiably never
clears report state (Rachel, from source), but the predicted stuck key did
NOT reproduce on macOS. clear_keyboard() now runs before the route flips
anyway (bt_ui_mode_slider). Upstream issue DEFERRED until the consequence
reproduces on some host (try Windows) -- the source-level observation alone
is thin receipts.

## RTC: reflash erases the persisted trim; SECCNTV write costs ~0.5 s phase (2026-09-01) — trim phase loss FIXED
**Status 2026-09-03:** the SECCNTV phase loss is already gone — every steady-state
period write happens in the tick ISR at the match since the sub-second work
(`docs/clock.md`, "Reload ownership"), so the "apply trims at a second boundary"
idea below is done. What remained was the 5-minute sawtooth, diagnosed and
mitigated host-side the same day (`docs/clock.md`, "The 5-minute sawtooth");
the outstanding firmware item is the loop's tracking bandwidth against ILRC wander.

Measured after the flash marathon: board ~4100-6200 ppm slow, halving per
trim -- RE-CONVERGENCE from the compile-time seed, not a regression. Two
facts to carry: (1) every reflash erases eeconfig incl. the persisted
divider period, so the ~hour-long climb (with 2 s snaps) restarts after
each flash until the first post-10-min trim persists again; (2) per SN32F299
datasheet 12.5.6 (found by the f4 session), writing SECCNTV resets SECCNT,
so each trim discards the elapsed fraction of the current second -- a mean
0.5 s phase loss per trim, later corrected by a snap. Possible improvement:
apply trims only at a second boundary (right after the 1 Hz callback) to
bound the loss to ~0. Also: the ILRC's temperature coefficient means a
fixed RTC_PERIOD_INITIAL can be thousands of ppm off on a different day --
the persisted value is the real seed; the constant is only for fresh EEPROM.

## Host tooling — found during the packaging work (2026-09-01)

### `nowplaying-macos.sh` still hides late Automation failures

`probe_automation()` now reports a TCC denial at startup, which closes the case
that made the agent look like "nothing is playing" forever. But the per-call
getters still send `osascript` stderr to `/dev/null`, so a permission **revoked
while the agent is running** is silent again until the next restart. Low
priority — revocation mid-run is rare — but the fix is cheap: have `state_of()`
distinguish an empty result from an error and log the first one it sees.

### ~~The Windows host path is untested~~ — ran 2026-09-05, superseded 2026-09-06

`hostagent/nowplaying-windows.py` ran as a Scheduled Task from 2026-09-05
23:00 and is the oracle the Rust daemon's media loop was ported from. On
Windows the daemon (`ak820 install`) now replaces it: `install` unregisters
the Python task, and if the PowerShell installer re-registers it the Python
agent exits at once because the daemon holds its mutex. The file stays as
the reference implementation and the rollback.

### `ak820ctl` and the timekeeper both open the raw-HID interface

Not a defect today — the timekeeper shells out per transaction, so it holds the
interface only for the length of one call, and `install-agents.sh` refuses to
install a second clock agent. Worth remembering before adding any third host
tool that polls: the interface is exclusive, and the failure mode looks like a
firmware fault rather than a host one.

## Status-band text uses synchronous per-glyph blits — measured, NOT a defect

`draw_locks()`, `draw_battery()` and `draw_conn_number()` paint through
`lcd_draw_flash_text()`, which is synchronous and issues **one LCD operation per
glyph** — a window command, a flash read and a DMA arm each, all of which dwarf
the ~460 bytes of a 10×23 cell. The clock and host-text bands do not do this;
they queue through `display_blit_pump()` at one glyph per main-loop pass.

**Measured 2026-09-03, page closed, over the cable, ~10 Caps Lock presses:**

```
count_ge_25ms        0        blit_gap_max_ms   22
count_ge_10ms       19        key_presses       54
```

**22 ms, and that is under the line that matters.** A stall shorter than the
shortest keypress (25 ms) cannot lose a press — the key is still down when the
loop catches up. So this costs latency, never a keystroke, and it does not need
fixing on those grounds. The prediction that it "has been costing a stall on
every Caps press" was wrong; the measurement is what corrected it.

It exceeded 25 ms in exactly one place: the **Fn+D debug-page exit**, which forced
a full repaint after clearing, so `draw_locks` painted CAPS *and* WIN *and* the
slot text in one pass. ~30 ms, on a deliberate keypress, on a feature added the
same day. **Fixed the same evening (`821431e3e4`)** without touching the queue:
the restore stays on its lock stage painting one component per pass, and
`draw_battery()` stopped clearing its whole 128x22 strip (~7.6 ms) on every
percent tick. Measured after the flash: `count_ge_25ms_nonflash` 0 across
several dismissals and 682 presses, `blit_gap_max_ms` 20 (Caps-on, unchanged).

### If it is ever worth doing

Route the status band's text through `queue_line()` like the clock band already
does. With the exit stall gone this would only trim the 10-20 ms Caps/battery
paints and the sub-10 ms hitches — the queue moves glyphs, not the padlock,
bar, bolt or clears — so the payoff is latency, not keystrokes.

**Weigh the risk honestly.** This is shared dashboard code that runs constantly,
and it was broken twice on 2026-09-03 while chasing this same class of problem —
once badly enough to hang the board and trip the watchdog (`8dc74f7015`,
reverted). With nothing on the board over 25 ms any more, the remaining exposure
is zero keystrokes and a few milliseconds of latency. That is a poor trade for
touching this subsystem without a plan.

Related, larger, same file: `display.c` is ~2,200 lines carrying ten owners
(clock, playback, text band, battery, locks, connection strip, backlight,
splash, glyph queue, shadow diffing, debug page). The queue and its shadow
machinery are a self-contained subsystem with real invariants and would be much
safer behind their own boundary.

### Two comments in this tree document code that does not exist

Both cost real time on 2026-09-03 by being believed:

- **`lcd_draw_flash_text_staged()`** — declared in `lcd_bus.h`, recommended by
  name in the host-text band's comments as the fix for exactly this problem, and
  **has no definition anywhere in the tree**. Using it is a link error.
- **`display_set_param_status()` "draws ~12 blocking DMA blits"** — stale. It
  copies a string and sets `text_dirty`; the band draws through the glyph queue.
  Both sites are now annotated with which part is historical.

A file that confidently documents something untrue is worse than one that
documents nothing.

## Timekeeper: a 13-minute sync gap, and why it still matters (2026-09-05, Windows)

**Symptom.** The Windows timekeeper Scheduled Task logged `timekeeper start` at
15:11:46 with no corresponding stop, and no periodic syncs between 14:58:04 and
that restart -- 13 minutes with a 300 s cadence, so two syncs are missing. The
board free-ran and was **+1042.5 ms** out by the time it resynced, corrected as
a *step* rather than a slew because it exceeded the slew threshold.

There were five starts that day; the other four were deliberate restarts
during development (install, the CREATE_NO_WINDOW fix, the share-mode
experiment).

**Cause: the host bugchecked.** Confirmed from the System event log after the
fact -- an earlier draft of this entry speculated about Claude Code session
teardown, which was wrong.

| | |
|---|---|
| 14:58:04 | last sync before the gap |
| **15:02:56** | unexpected shutdown; **BugCheck `0x0000001A` (MEMORY_MANAGEMENT)**, dump at `C:\WINDOWS\MEMORY.DMP` |
| 15:10:30 | boot |
| 15:11:46 | `timekeeper start` -- 76 s after boot, i.e. at logon |

So the agent did not die; the machine did. The task's at-logon trigger brought
it back correctly and it resynced on its own. Nothing here is an agent defect,
and the restart policy never needed to fire.

**Root cause, from the kernel dump** (analysed in a separate session; bucket
`0x1a_31_nt!MiApplyCompressedFixups`, crash time 15:03:01 by the dump, five
seconds later than the event log's write): a third-party utility launched a WPF
process, and the kernel faulted while re-basing the shared NGEN image
`PresentationFramework.ni.dll` for it -- `NtCreateSection` ->
`MiShareExistingControlArea` -> ... -> `MiApplyCompressedFixups`, decoding its
own compressed relocation stream from paged pool and running off the end of a
4 KB page.

**It is persistent RAM corruption, not a transient read.** Three single-bit
flips in ONE 64-byte cache line of kernel paged pool -- phys `0xe638f808c` bit
3, `0xe638f8094` bit 2, `0xe638f80ac` bit 7 -- inside the relocation stream for
page `0x13ed000`. Decoding the corrupted stream with the kernel's exact
semantics reproduces both the bugcheck and the scribbled target page with zero
bytes of mismatch, and flipping those three bits back matches the on-disk
`.reloc` block exactly. The other 1,106 page streams in the block are intact.
Recommendation to the owner was MemTest86 and the ASUS 2402 BIOS.

### ✅ CLEARED 2026-09-06 — the machine is stable, and flashing is allowed again

The owner applied the **ASUS 2402 BIOS** plus tuning tweaks, then ran a **clean
MemTest86 pass** and about **five hours of y-cruncher** without error. That is
the clearance this item was waiting for: a memory test is the only thing that
speaks to three bit flips in one cache line, and a five-hour stress run covers
the load-dependent case a short pass would not.

**The do-not-flash rule below is lifted.** It is kept, struck through, because
the *reasoning* in it is not about this machine — it is a permanent property of
the flashing pipeline, and the next person to ask "would a corrupted image be
caught?" deserves the answer.

⚠️ **Keep the hash habit anyway.** Not because the RAM is suspect now, but
because `sonixflasher` verifies against **what it sent**, so nothing downstream
of `build.sh` can catch a corrupted buffer — on any machine, ever. Reproducible
builds make the check free:

    sha256sum ak820pro-builds/out/via-daily-<hash>-*.bin   # must all agree

**Historical status:** during 2026-09-05 the rule stood, and the phase-0
`ak820-agent` work was done entirely without flashing.

**Nothing of ours is in the stack**: no `hidclass`, `HIDUSB`, `kbdhid` or
`mouhid`, no I/O manager at all, no Bluetooth. A concurrent-HID-open experiment
of ours had ended about five minutes earlier and was explicitly checked and
ruled out; it is recorded here only so the coincidence is not rediscovered as a
suspicion later.

### ~~⚠️ Consequence for this repo: do not flash from a machine with bad RAM~~ — lifted 2026-09-06

A bit flip in a firmware image between `build.sh` and the board would not be
caught by anything in the current pipeline. `sonixflasher` reports
`Flash Verification Checksum: OK` by comparing the board against **what it
sent**, so a buffer corrupted before transmission verifies perfectly. The
structural checks in `build.sh` (initial SP, reset vector, USB descriptor) only
sample three places and would miss a flip anywhere else in the 256 KB image.
There is no read-back path to compare against: the stock firmware cannot be
read off the board, and neither can ours.

~~Until the memory is cleared, either do not flash, or verify the artifact by
hash before flashing.~~ **Reproducible builds make that easy and are the reason
this is checkable at all**: two clean builds of the same commit are
byte-identical, measured 2026-09-05.

    sha256sum ak820pro-builds/out/via-daily-<hash>-*.bin   # must all agree

Checked after the fault was identified, with no errors: `git fsck --full
--strict` on this repo (every object SHA verifies, so no flip reached git),
a clean working tree, and all three clean builds of `8608c4f6` still hashing to
`e504bf9dddc91dd1...`.

**Two reasons it is worth keeping.**

- It is a real instance of the whole-second blind spot recorded in
  [AK820-AGENT-CLOCK-PARITY.md](AK820-AGENT-CLOCK-PARITY.md):
  `clock-phase.py` recovers sub-second phase only, so it would have reported
  this ~1.04 s error as roughly +42 ms.
- `-Status` reported **Running** throughout, which is exactly the
  "task running can coexist with hours of failed syncs" gap the Codex review
  raised. Evidence for the daemon's observability requirement: *last successful
  sync* has to be a first-class readout, not liveness.

**Kept anyway**, because the two observations above stand on their own: the
instrument cannot see a whole-second error, and `-Status` reports Running while
nothing is being synced. Both are requirements on the Rust daemon regardless of
what caused this particular outage.

**If a gap recurs with no bugcheck:** log on exit as well as entry, and check
the Task Scheduler operational log.

## Host tooling still enumerates HID; only ak820text was fixed (2026-09-05)

**Why it matters.** `hid_enumerate` on Windows opens **every** HID device on the
machine to read its attributes; the VID/PID filter is applied afterwards and
spares none of them. `../jdrgb/docs/ups-wedge-incident.md` records that pattern
twice wedging an APC Back-UPS here.

`hostagent/ak820text.py` was fixed (`61038c6`, `b31acd9`): cached path,
exponential backoff, and a `GetSystemPowerStatus` gate that holds off while AC
is offline and for 60 s after it returns -- the window jdups measured both
wedges in. **The rest was not.** Still enumerating:

| Source | Frequency |
|---|---|
| `ak820-timekeeper.py` `hid_present()` | every `LOOP` (15 s) |
| `ak820-timekeeper.py` `controller_id()` (Windows) | every loop while the cache has no bias |
| `ak820ctl` — **every invocation**, including `clock --bias` | 2-3 per sync |
| `clock-phase.py`, `ak820health.py` | per run |

Roughly 8 enumerations a minute, continuously, plus the per-sync ones.

**Accepted for now** on jdups' own evidence: it saw no trouble in the window we
were running hard, and enumeration on steady mains has never hurt it. But
⚠️ **fix the timekeeper's two before any long capture run for
[AK820-AGENT-CLOCK-PARITY.md](AK820-AGENT-CLOCK-PARITY.md) phase 3a**, which
deliberately runs the oracle harder and longer than normal operation.

The Rust agent removes the class entirely, and as of 2026-09-05 this is built
rather than intended: `ak820-agent`'s discovery reads the Configuration
Manager's own records and opens nothing. `ak820 list` prints the ratio it
avoids — **33 HID interfaces present, 5 of them this board's** — and at most
one of those five is ever opened.

**2026-09-06:** the Python now-playing agent is retired on this machine (the
daemon has its job), which removes `ak820text.py`'s share. The timekeeper's
two enumerations per loop went with it at 14:40 the same day (`ak820 install
--clock`, the plan's phase 4b): **nothing on this machine enumerates HID now**
except a hand-run `ak820ctl` or `clock-phase.py`.

## The daemon's verify residual runs +1.7 ms above the C's (2026-09-06)

Measured across the takeover's first ten syncs: `after` minus `before` — the
verify GET's offset against the burst's min-RTT sample — averages +1.7 ms
(max +2.9) in the daemon, +0.4 (max +1.2) in the last 60 Python-driven
`ak820ctl` syncs on the same board. Everything else in the line is inside the
C's spread (`plans/AK820-AGENT-PLAN.md`, "Phase 3b evidence").

**Why it is not urgent:** neither learner uses `after`. The lead learns from
the SET reply's receipt offset and the bias from `before`; `after` feeds the
printed line and the stepped-case `warning:` gate only.

**Why it is worth understanding:** a single sample's offset sitting +2 ms off
the min-RTT sample's means the two transports' write/read asymmetry differs,
and asymmetry is what the midpoint estimate cannot see — so `before` itself
could carry a small constant offset the C's did not. The check is cheap:
capture a burst's five (t0, t1, board) triples with `ak820 clock --raw` (with
the daemon stopped, never beside it) and compare per-sample offsets against
the same capture through `ak820ctl clock --read` on the pinned C.

## nowplaying-macos.sh: the measured cost of the poll loop

**The macOS port is PLANNED AND REVIEWED — see
[`AK820-AGENT-CROSSPLATFORM-PLAN.md`](AK820-AGENT-CROSSPLATFORM-PLAN.md)**
(drafted 2026-09-10, reviewed, dispositioned in 9f5f7d3, nothing built). That
plan already covers MediaRemote in much more depth than anything here, including
the nuance that it is *not* purely event-driven — it carries a heartbeat, and the
plan explicitly forbids claiming otherwise.

This entry exists only for the one thing the plan does not yet quantify: **what
the current bash agent actually costs.** Verified against the script
2026-09-16:

- `INTERVAL` is 3 s (`nowplaying-macos.sh:40`), and each field is its own
  `osascript`: `running` per app (twice), `player state`, then while playing
  `name`, `artist`, `player position`, `duration` — **6 to 8 `osascript` per
  3-second loop while playing**: 6 with Spotify playing, 7 with Music playing
  and Spotify closed, 8 with Spotify open but stopped and Music playing (it
  falls through, asking both apps for `player state`). Corrected 2026-09-16 by
  the Fable review's finding 9; this said "up to 7".
- Every push runs a **fresh venv Python** (`ak820text.py`), so the exclusive HID
  interface is opened and closed per update. This is also why the `mkdir` lock at
  `$TMPDIR/ak820pro-nowplaying.lock` exists; holding the interface open for the
  process lifetime retires it in favour of a single-instance check.
  ⚠️ **Rejected for the port, 2026-09-16.** On macOS a lifetime open locks
  `ak820health.py`, `ak820keymap.py` and `ak820lighting.py` out for good — they
  work only by retrying between the agents' brief opens. The daemon opens per
  interaction, as the Windows daemon already does; a single-instance guard
  still replaces the lock. See the plan's exclusivity section.

Reported by another session diagnosing this Mac, **not verified here, re-measure
before citing**: ~100–200k short-lived processes/day, each `osascript`
registering with WindowServer and its exit making FocusManager re-evaluate focus,
on a machine at swap 24.6/25.6 GB with `fseventsd` at 20 GB and 58 days uptime.
They did confirm the agent itself does not leak — 1.5 MB after 6.7 days.

Note this is a *cost* argument, and the plan's own "Why" section is explicit that
cost does not justify the port — unification, capability and two named defects
do. Useful as a supporting measurement; not a reason on its own.

**Measured 2026-09-16, macOS 27.0, Music.app playing** with
`scripts/agent_overhead_macos.py`: five 240 s windows, the agent frozen with
`SIGSTOP` in alternate ones.

| | per 240 s window | share of one core |
|---|---|---|
| the agent's own child processes (kernel rusage, exact) | 50.6 / 38.4 / 53.2 CPU-s | **19.7%** |
| `tccd`, `launchservicesd`, `trustd`, `runningboardd`, `launchd`, which move only while it runs | ~20–30 CPU-s | ~8–12% |
| **total** | | **~30%, continuously while playing** |
| for contrast: the sibling's event-driven MediaRemote helper | 0.76 CPU-s in 98 min | ~0.01% |

What this does **not** confirm:
- **The ~100–200k processes/day.** System-wide launches ran 1,068–1,604 a
  minute in every window, paused or not; post-upgrade Spotlight indexing buried
  the agent's share. The script's structure gives about 20 launches per 3 s
  while playing, so ~570k a day. That figure is derived, not measured.
- **The WindowServer/FocusManager churn.** WindowServer used 105–124 CPU-s per
  window whether the agent ran or not; any effect is below the resolution.
  Music.app's cost of answering Apple events was likewise invisible.

The owner's complaint that the Mac "seems to suffer a lot of overhead" from
this agent is therefore **confirmed on CPU**. Cost stays a supporting argument
in the plan's terms, but it is now the owner's stated priority for the port.

## Whole-second clock slips: four, on both boards, both OSes, both host implementations (found 2026-09-16)

**The signature, identical every time:** a periodic sync reads `before` about
**one second low** (e.g. `-1006.4 ms` where the true offset was a few ms), the
SET lands normally (`after` in single digits), **no bias line follows** (the
learner correctly refuses it), the scheduler comes back **~180 s later instead
of 300**, and that sync is back in single digits. The board was one second
behind for at most one sync interval, and nothing warned.

| when | board / firmware | host | before → after | next sync |
|---|---|---|---|---|
| 2026-09-06 04:41:24 | gremlin, `8608c4f6-dirty` | Windows, Python + `ak820ctl` | −987.2 → +13.2 ms | 180 s, +2.0 |
| 2026-09-06 09:04:42 | gremlin, `8608c4f6-dirty` | Windows, Python + `ak820ctl` | −994.5 → +6.3 ms | 180 s, −12.0 |
| 2026-09-08 19:58:51 | gremlin, `8608c4f6-dirty` | Windows, Rust daemon | −1006.4 → −7.0 ms | 180 s, −4.9 |
| 2026-09-10 15:01:46 | the Mac's, pre-`b89777` | macOS, Python + `ak820ctl` | −999.8 → −0.8 ms | 183 s, −7.1 |

The three gremlin rows were found by the Claude session on gremlin
(`scripts/clock_log_windows.py`, committed in `8cf2c8d`) from logs that live on
gremlin; the Mac row was read here from `~/Library/Logs/ak820pro-timekeeper.log`.
The takeover table's "worst 994.5 ms" (`AK820-AGENT-PLAN.md:274`) is the second
row, and the first was hidden behind it because the table reports only the
worst. A 2026-09-02 `-1131.5 → -131.8` on the Mac is **not** counted: older
firmware, and `after` did not land.

**What this rules out, and what it cannot.**

- **Not the transport, not the OS, not the Rust port.** It appears through
  hidapi and through `CreateFile`, on Windows and macOS.
- ⚠️ **Not ruled out: the shared clock contract.** The Rust daemon reproduces
  `ak820ctl`'s transaction by design, so a contract-level flaw (say, a GET
  sample whose seconds and fraction straddle a second boundary) would appear in
  both, and **oracle parity would carry it faithfully to macOS**. Firmware is
  the other candidate. A torn seconds/fraction read fits the signature — exactly
  one second, a clean verify right after — but that is a hypothesis, not a
  finding.
- ⚠️ **The rate changed, which says there is a condition, not just chance.**
  Four slips in roughly 1,900 periodic syncs up to the evening of 2026-09-10, then **none** in
  about 3,270 since: gremlin's 1,614-sync baseline (09-09 → 09-15) and the
  Mac's 1,657 syncs after 09-10 18:00. At the earlier rate about 6–7 were
  expected. Gremlin's firmware did not change in that time.
- **HID text traffic does not separate them — checked 2026-09-16.** Both
  now-playing agents send traffic even when nothing plays and log none of it:
  a playback request every 3 s and a text keepalive every 30 s
  (`agent.rs:271-300`, `media.rs:63-72`; `nowplaying-windows.py:241`,
  `:255-262`). That steady traffic was running at all three gremlin slips, with
  no media change within ±10 min of any of them. It **also ran through the
  zero-slip baseline**. Slip 3 is the sharpest case: the daemon runs media,
  clock and health **sequentially on one thread** (`agent.rs:267-320`), so its
  own text cannot interleave with its own clock transaction. That rules out
  self-contention, though not a foreign process: discarded foreign reports go
  only to the status file's overwritten `foreign_reports`. Slips 1 and 2 had a
  second process on the HID (`ak820ctl` beside a now-playing agent).
  **Reported by the gremlin session from its logs and the code.**
- *A coincidence, not a finding:* both zero-slip eras begin at a restart.
  gremlin's begins at the 09-09 03:27 Windows Update reboot (unknown whether
  the board lost USB power). The Mac's begins near `b89777`'s commit at 17:57
  on 09-10, and presumably its flash. Against it: gremlin's board had absent
  blips on 09-06 20:08, likely a reset, and slip 3 came after that.

**Why it matters now:** this is the "plausible wrong time" failure mode the
whole clock effort exists to prevent, and neither implementation warns.
Minimum ask, whatever the cause: **warn when `before` jumps by ~1 s against
the previous sync**, so the next one is visible without a log dig.

⚠️ **Do not poll either board to look into it** — a clock read spoils the live
agent's sync. Start from the logs, and from `rtc.c`'s GET reply construction.

## Stalls during the S2 transport soaks (2026-09-16, the Mac's board) — probably ours

After the S2 and Phase 1 soaks, `ak820 health --stalls` read
`count_ge_25ms_nonflash 12`, `count_ge_10ms 1180`, `blit_timeouts 216`, with
`loop_gap_max_mark blit`, at `key_presses 27804` (counters since the board's
last boot; ~15:35 MDT). `plans/current-status.md` had recorded **0** such stalls
across a 13-hour overnight on this board.

**Probable cause, not proven: the soaks.** They drove `TEXT_PLAYBACK` state 0 —
the daemon's idle readout — tens of thousands of times, much of it while the
bash now-playing agent was pushing state 1 for music that was playing. Each flip
hands the band between the clock and the playback readout, which is an LCD
redraw, and the slowest stall is marked `blit`. The owner was typing throughout.
The soaks were stopped the moment the counter was seen.

**Read again (2026-09-16):** `count_ge_25ms_nonflash` was **14** at 20:01:50,
when the daemon started, and **15** at 20:46:57. Between 15:35 and 20:01 the only
board traffic was the bash now-playing agent and the Python timekeeper, as
before today; nothing new. **So it rose**, which by the rule below means the
soaks did not cause all of it. The daemon now samples these counters into its
status file every 5 minutes, so the rate is visible without polling.

**How to tell:** re-read the counters after an hour or more of ordinary use with
no bulk traffic. If `count_ge_25ms_nonflash` is still 12, the soaks caused all of
it; if it rose, something else is stalling and `docs/hardware.md`'s
keystroke-loss section applies.

⚠️ **Rule for every future transport soak:** use a command that touches only RAM
on the board — health page 1 (`HC_GET`) — never one that can move the LCD, and
never while the owner is typing or a now-playing agent is live. The
`TEXT_PLAYBACK` choice was made to be "production traffic, faster"; faster is
exactly what production traffic is not.
