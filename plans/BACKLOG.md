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

### The Windows host path is untested

`hostagent/nowplaying-windows.py` exists and has never been run. `setup.sh` and
the README are scoped to macOS and say so. Either test it on Windows or drop it;
an untested file that looks supported is worse than an honest gap.

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
