# Deep sleep, the build: the ladder's last stage

Status: **revision 5, cleared for the build by codex's fourth verify
(10-19): no blockers left.** The plan review and four verifies, every finding
dispositioned, are at the end.

The experiment (`SLEEP-PLAN.md`, "Deep sleep: the experiment") proved the
mechanism over 10-18/19. This plan makes it the board's standby: on by
default on battery, in every build. It carries the decisions in
`SLEEP-PLAN.md` ("Decided", "Asleep, the RTC's second runs ~13% slow", "Time
left with deep sleep"). Every flash gets a codex review first.

## What the measurements say (10-18, 10-19)

- **Asleep: 13.35 mW at the pack**, against ~114 mW awake and dark
  (27.5 mA). The asleep figure is 3.24 mA at 4.12 V, from the logger's 1 Hz
  samples over 05:46-06:43 10-19, inside the hour asleep. At that rate the
  pack's 15,579 mWh would last ~1,170 h (~7 weeks), by arithmetic.
- **It wakes on a key, and the key registers at the board.**
  - 247 of 247 soak cycles, board-only, all on one P2 column (the rig's F19),
    with sleeps of 7-30 s.
  - The 1 h sleep and the 10-18 runs.
  - No stray wakes and no radio give-ups. The PLL relocked in ~127 loops.
  - Delivery at the host was checked only on 10-18: a P0 key pressed by
    hand reached the Mac.
- **The first key after a sleep reaches the Mac ~28 ms later** than an awake
  key (10-18). It is unexplained: the radio retries as often awake as after
  a sleep (the awake control, 10-19), so that rules out its retries.
- **The watchdog does not count asleep** (10-18).
- **Asleep, the RTC's second runs ~13% slow.** The hour counted 3139 s for
  3600 (0.872), and the 10-18 cycles fit 0.842. The PCF8563's crystal keeps
  time through it.
- **USB:** the transceiver is off after a deep sleep, and setting its bit
  back was enough on every bench wake. But each time the host's data was
  cut through the sleep and restored after the wake, so the host always
  enumerated a board that was already awake. **A host that appears while
  the board sleeps is untested.**
- **The radio:** the link stayed up through every bench sleep, with the Mac
  close by.
  - What the module sends while the board sleeps is lost, and there is no
    way to ask it its state (`docs/wireless.md`).
  - The battery reports (`5C`) answer only the board's own poll (`A6 53`,
    every 5 s), so none are sent while it sleeps.

## The design (revision 5)

### 1. When it sleeps (power.c, sleep.c)

The ladder gets a sleep time per mode, `SLEEP-PLAN.md`'s first draft, to tune
in use:

| mode | dim | lights off (screen dim) | screen off | deep sleep |
|---|---|---|---|---|
| Full | never | never | never | **never** |
| Normal | 1 min | 5 min | **7 min** (was 15) | **7 min** |
| Saver | 30 s | 2 min | **3 min** (was 5) | **3 min** |
| Minimal | at once | at once | at once | **30 s** |

> Revised 2026-10-20 (Normal dim 10 min, dark and asleep 20; Saver dim 1 min,
> asleep 3; Minimal asleep after 1 min):
> [`POWER-MODES-REVISION-PLAN.md`](POWER-MODES-REVISION-PLAN.md). The table
> is what this build shipped.

- **Low battery** shortens Normal's sleep to Saver's 3 minutes. Minimal's is
  already shorter.
- **Full never sleeps, even at low battery.** In Full the low cap stays a
  lighting cap: `power_task()` gives Full Saver's stages when low, and those
  stages keep their effect on the lights, but sleep is not one of them.
- **On battery only.** With the cable in, every mode is Full and nothing
  sleeps.

**Who decides.** `power.c` says when a sleep is wanted
(`power_sleep_wanted()`: on battery, not Full, the idle time past the sleep
time). `sleep.c` sleeps at the first main-loop pass where every
precondition holds, and it keeps checking while the sleep is wanted. This
production path shares nothing with the experiment's arm: no 60 s give-up,
and no terminal `DS_DONE` state.

**Preconditions.** The experiment's (`sleep.c:226-246`) and new ones:

- **Kept from the experiment:**
  - no key down;
  - no USB host (the frame number still for 100 ms);
  - the radio's side quiet (its queue, the serial output queue, UART2's
    transmitter empty), rechecked under the lock;
  - the display bus and both SPIs idle;
  - no flash program or erase, and no deferred eeconfig write;
  - every column on P0 or P2;
  - the watchdog running.
- **The RTC fully idle:**
  - no slew or reload;
  - no PCF write pending (`pcf_pending`) and its write machine idle
    (`ps_state == PS_IDLE`), which also covers its verification and STOP
    recovery;
  - no acquisition running.
- **The backlight off** (`display_backlight_effective() == 0`). This is a
  hard rule: the lit screen needs the 20 kHz tick, which a sleep stops. So a
  message's 4 s in Minimal, or `Fn`+`D`'s pages there, keep the board awake
  by rule.
- **The RGB dark** (`power_rgb_dark()`).
- **Not pairing** (`ch582_is_pairing()`).
- **The last wake's recovery finished** (section 4), including any USB
  re-attach.
- **The knob at rest.** The encoder's two-bit state must equal the
  decoder's stored state. After the wake edges are armed and cleared, a
  second read must match and no edge be latched (section 2).

**Not blockers:**

- **The link's state** (LINKING or failed): the module keeps trying on its
  own.
- **An overlay or alert in its hold:** it resumes after the wake.
- **A lock LED lit:** it goes dark asleep and comes back at the wake.

### 2. The sleep itself (sleep.c)

The experiment's locked sequence stays as codex cleared it
(`sleep.c:258-421`):

- PRIMASK held through the clock restore;
- I-class calls and register writes only;
- each wake source cleared in the peripheral and in the NVIC, with the
  temporary vectors disabled before the old enables are restored;
- the clock contract: the IHRC, then the PLL off, then the flash's slow
  mode, and back in reverse with a bounded relock.

What changes:

- **The system time is frozen for real.**
  - ChibiOS's counter, CT16B5 (`SN32_ST_TIM`, 16-bit at 187.5 kHz), runs on
    HCLK. So today it keeps counting through the core's microseconds awake
    each second, at a quarter rate on the IHRC, and through the entry and the
    exit.
  - Over a week that is more than one wrap (350 ms) unobserved, which breaks
    QMK's wrap extension (`platforms/chibios/timer.c`).
  - The fix: CT16B5 is stopped (`TMRCTRL.CEN` off) under the lock before the
    clock switch, and started again after the restore. It is restarted on
    **every** exit, the no-sleep unwinds included, before the unlock.
    `CEN` holds both the counter and the prescale counter (manual p. 125;
    `CRST` is the separate reset), so nothing is rewritten. The SysTick alarm
    is handled as now: off, then pended at the end. Its handler computes the
    elapsed ticks and re-arms the next deadline, and QMK's half-wrap timer
    stays valid (codex's verify).
- **In every build: the production path.**
  - Automatic admission and its repeated checks.
  - The locked sequence, its bounded clock restore and the watchdog feed.
  - The LED driver's `sn32f2xx_sleep_enterI()`/`_exitI()`, under a new
    `SN32F2XX_DEEP_SLEEP`. Its definitions and declarations are split
    consistently, keeping the I-class calls, the PWM pending clear and the
    synchronized counter re-arm (`sn32f2xx.c:797-830`). The 20 kHz tick's
    hooks are already outside the dev guard.
  - The UART drain **and the parser's resync**: the 3-byte window reset is
    under `AK820_DEV_HOOKS` today (`ch582f_ajazz.c:1047`), and its request
    and its consumer both move into every build.
  - The wake's recovery (section 4), and `HC_POWER` page 1 (section 8).
- **Dev-only:** light sleep's bits (scan-only, the yield, WFI, PMU Sleep),
  the idle hooks in `chconf.h`, and the arm and cancel. Also:
  - a short sleep time for the bench, not persisted, and never under 30 s,
    so physical holds and short release deadlines still finish first;
  - the backstop's preset (section 2);
  - `ds_no_feed`, the forced stages, and every op 14 mutation.
- **Wake sources:**
  - **A key:** the 15 columns, falling edges, as now.
  - **The knob:** both encoder pins, both edges (encoder bits only). A is
    `B2` (P1.2, IRQ30) and B is `A10` (P0.10, IRQ31) (`docs/sn32f299.md`).
    This reverses 10-18's "the knob need not wake it": after 7 minutes of
    listening the board would otherwise ignore the knob until a key.
  - **The charger:** CHRG (`B16`, P1.16, sharing IRQ30, an input with a
    pull-up, `ak820pro.c:68`), falling, meaning charging began. A cable
    plugged in wakes the board within microseconds, well inside USB's 100 ms
    attach debounce, so the host finds an awake device.
    - A full pack may not start charging, so CHRG may not fall. That
      insertion waits for a key, the knob or the backstop: the USB
      re-attach (section 5) cannot wake a sleeping board.
- **What sleeps with the board:**
  - **The NVIC:** P0, P1, P2 and the RTC. P1 joins both the peripheral's
    cleanup and the NVIC's disable and pending clear before the old enables
    are restored.
  - **The knob check:** pins read and compared with the decoder's stored
    state (`encoder_state[i] & 3`, through a new read-only accessor in
    `drivers/encoder/encoder_quadrature.c`, another local core change that
    leaves the decoder's history alone); edges armed (both edges); cleared
    after the pins settle; read again and the latched edges checked. A
    changed state, or an edge, is a wake with no sleep. The columns are
    checked as now, and CHRG already low is a wake too.
- **The RTC's second** still wakes the core each second, to be counted and
  to feed the watchdog. Feeding it is harmless: the watchdog does not count
  asleep.
  - **A 24 h backstop:** counted seconds, so ~27.5 h real at the hour's
    rate. It is a wake with no input. The recovery runs, and then the board
    sleeps again.
  - It bounds a missed wake (a full pack plugged in) to about a day, and
    finds a supply change. It is no failsafe against an RTC that stops:
    that loses the timed wake, and the watchdog does not count asleep,
    though a key, the knob and the charger still wake it.
  - **Every second count is 32-bit:** the cap, the loop's local count, the
    record, and the status reply. Today they are 16-bit
    (`sleep.c:140,157,184,310`): 86,400 assigned to the cap would become
    20,864.
- **The dev record** (op 14 sub 4) becomes version 2 at the new widths:
  - the sleep's sequence number;
  - the wake source (key, knob, charge, backstop, strays);
  - the PCF's slept seconds, the counted seconds, and the recovery's
    results.

### 3. Time across a sleep: the timer stands still

**QMK's timer and ChibiOS's system time stand still across a sleep**, now
exactly (section 2): a sleep is an instant to everything driven by the timer.
Two reasons not to advance it instead:

- The true slept time comes from the PCF after the wake, so the timer could
  not be advanced before anything runs.
- A jump of hours would land under a key that is down and debouncing, and
  the stall accounting would see a pass of hours.

**Codex's audit** of every timer consumer (its review, section 1) finds
freezing correct for nearly all of them, at production thresholds:

- debounce, tap and hold, Space Cadet, the radio's ACKs and retries, holds,
  overlays, the LED drive accounting, RGB animation, deferred execution,
  persistence, the health and loop statistics;
- uptime and the loop statistics now mean awake time; `ak820health.py` says
  so.

The exceptions, each handled in the wake's recovery:

| What | Why it cannot just stand still | Handled by |
|---|---|---|
| the gauge's energy | the pack drains while asleep | the sleep term (section 6) |
| the battery log's cadence and dating | the host dates entries by elapsed time | the log's own time base (section 6) |
| the 30 min relaxation after an unplug (`battery.c:858-878`) | the pack relaxes physically while asleep | aged by the slept time, then a fresh `5C` |
| `5C`'s freshness, and the radio's cached report age (`ch582f_ajazz.c:987,1348`) | reports from before the sleep would pass for fresh | the ring forgotten, the age marked stale |
| the ladder's idle | a lost first detent decodes nothing, so QMK sees no activity | the key or knob wake triggers it itself |
| host text (3 min) and the playback heartbeat (20 s) (`display.c:419,441`) | a text could reappear hours later | both expired at the wake |
| the lock-LED receiver (dev) | a frame in progress cannot finish | reset; its diagnostics kept |

### 4. The wake's recovery: one owner, in steps

`sleep.c` owns the wake and holds the board awake until every step has
ended. **One step per main-loop pass at most**, each bounded, so no pass
carries two of them. Each step's state and result are kept under the
sleep's sequence number (section 8).

**Before the lock** (at admission, in thread context):
- the energy since the last 1 Hz tick is integrated up to the sleep, so no
  awake energy is left pending across it;
- the PCF's "before" read (step 2's rules: the raw path, the bus idle).

0. **In the locked exit, as now:**
   - the counted seconds go to both software clocks (`rtc_account_sleepI`);
   - the SOF reference is broken completely: its epoch bumped, the streaks
     and qualification reset, outside the `seconds == 0` early return, since
     a sub-second sleep breaks continuity too;
   - the trim window is invalidated, and **the 60 s PCF discipline is
     suspended** until step 4 ends;
   - the host-sync generation is noted;
   - **the log's open period is frozen.** Its accumulators (the `5C`
     sum, count, minimum and maximum; the VDD and LED sums; the flags; the
     period's energy), as they stood at the sleep, are copied into a frozen
     record. The live ones are reset, so everything after the wake lands in
     them. That includes the radio's `5C` reports, which `ch582_task()` feeds
     straight in (`ch582f_ajazz.c:1343`), and the 10 Hz samples.
     `HC_BATTLOG` answers "pending" until step 3 commits (the host retries),
     since its age would otherwise date the old entries hours too recently;
   - `5C`'s ring is forgotten, and the radio's cached battery age is marked
     stale.
1. **The waking input first.** No recovery I/O, and no battery poll (the
   radio's periodic one is held too, `ch582f_ajazz.c:1159`), until the
   input that woke the board has been processed:
   - **a key:** until its press is counted, or 50 ms. Debounce is deferred
     per key (`sym_defer_pk`, 5 ms from the first changed sample), so a
     short tap needs more than one pass;
   - **the knob:** until an encoder event is decoded, or 50 ms;
   - **a charge or backstop wake:** nothing to wait for.
   - A key or knob wake triggers QMK's activity itself
     (`last_matrix_activity_trigger()` / `last_encoder_activity_trigger()`).
2. **The coarse clock:** one `pcf_read()`.
   - Slept seconds = after − before, signed and checked against the counted
     seconds.
   - `rtc_seconds_count` takes the difference atomically. The calendar is
     set to the PCF's whole seconds, which supersedes the coarse count rather
     than adding to it.
   - **A host sync since the wake wins:** if the generation moved, the
     calendar is left alone. In practice none can arrive, because USB must
     re-enumerate first, but the rule makes it certain. The old sync's
     `host_synced` is cleared once, here, and a new one is never cleared.
   - If a read fails, the counted seconds stand, flagged.
3. **The gauge and the log** (section 6), right after step 2, since it
   needs only the slept seconds and the acquisition can take 1.5 s:
   - the sleep energy, then time left recomputed;
   - the relaxation aged;
   - the log's entries for the sleep written from the frozen record, and
     `HC_BATTLOG`'s "pending" cleared.
4. **The phase:** the boot acquisition is re-armed.
   - Every field is reset: the failure count, the previous edge, the timeout
     origin, the uncertainty, the result.
   - Its edge pass is split. The bracket read, the full read and the
     confirming read become one transaction per pass; today they are three in
     one call (`rtc.c:1471-1490`).
   - **Splitting must not lose the second.** The full calendar's seconds
     must equal the new second the bracket saw, and the full read must come
     within 900 ms of the edge; otherwise the bracket is dropped and
     reacquired. Today the confirmation compares only the full read with the
     last read, so a full read a second late would pass, and the 999 ms
     clamp would set the clock nearly a second wrong.
   - Its 1.5 s timeout and its cancellation by a host sync are checked every
     pass, even while the bus arbiter defers its transaction. A reacquisition
     keeps the original 1.5 s, and the final confirming read's equality check
     stays.
   - Done or aborted, it ends the step; an aborted one never holds the board
     awake. With `rtc_valid` false (no PCF ever read), it is skipped.
   - It aborts on a new host sync, as now. The 60 s discipline resumes
     afterward, with a fresh trim window.
   - The whole-second set does not fix the phase; this step does, to
     ~±20 ms at boot. Under wake load that is measured, not assumed.
5. **The radio:** the battery poll (`A6 53`). It goes once step 1 has let
   go and the waking input's report has left (the TX queue empty, or
   100 ms). The periodic poll resumes with it. The step waits for the reply,
   or 2 s.
6. **Host content:** host text and the playback heartbeat expired.
7. **The supply:** 1.5 s of fresh samples, counted after the wake
   (`supply_tick` needs 0.5-1 s; nothing pauses its producer now), so a
   charge wake is classified. On EXTERNAL the board stays awake, since the
   ladder is off on USB. The step ends 3 s after the wake whatever the
   samples (too few, or intermittent), flagged if short.
8. **USB:** the re-attach (section 5), when no SOF has arrived since the
   wake, through to D+ restored.
9. **The display:**
   - **The backlight is held dark** from the wake until two repaints have
     finished: the clock's, after step 2's correction, and the battery row's,
     after step 3's debit (painted incrementally, `display.c:1809`). The
     queue is pumped as usual, and nothing drains it synchronously.
   - **Each repaint is tracked by a generation.** The correction or debit
     bumps it, and the painter records the generation it drew from, so only
     a paint made after the change counts. Finished means its glyphs drawn
     and the bus idle (`display_bus_idle()`: the final DMA done, not just the
     queue empty).
   - **Both repaints are scheduled, not left to the cadence.** Today a
     clean battery row waits for the next second, and dirty components
     advance at 10 Hz (`display.c:3001`), so a 7-glyph row plus its bar could
     take longer than the bound. The correction and the debit mark the clock
     and the row dirty, and while the hold is on, one component is painted
     every pass (each pass's paint still one component, within the budget).
   - **Step 4's later phase correction is not waited for.** The acquisition
     takes up to 1.5 s, too long to keep the screen dark after a key, which
     is why the gauge (step 3) now runs before it. The phase correction
     moves the seconds by at most one, like an ordinary tick.
   - **The terminal cases:** with the clock off (`DISPLAY_CLOCK_OFF`), or
     with the panel owned by `Fn`+`D`'s pages or the splash, there is no
     clock to wait for. In the date format it waits only if the date
     changed.
   - **The bound:** a repaint not finished 500 ms after step 3 releases the
     hold anyway, flagged. 500 ms covers a full row and its bar painted one
     component per pass, with margin. On that failure only, the screen can light
     showing stale pixels; the promise is "never stale unless a repaint
     fails".
   - Then the wake's message (section 7).

**The budget: one shared pass, scheduled from its start.**
- **One arbiter for every PCF transaction during a recovery.** That covers
  the recovery's own, the write machine's (its two-transaction STOP recovery
  included, `rtc.c:1429`), and the discipline's. It admits at most one per
  pass, from `rtc_fast_task()`'s slot, before the display pump. The
  pre-sleep read goes through it too.
- **A transaction is admitted only when:**
  - no blit is in flight and the glyph queue is empty;
  - **the pass so far has taken under 10 ms**, measured from the pass's
    start: a stamp taken before keyboard processing (`quantum/main.c:48`), at
    the board's first code each pass. `loop_acct`'s interval closes at
    housekeeping, after the input work (`health.c:138`), so it is not that. Earlier input work can itself take ~8 ms:
    the modified-consumer ordering, `consumer_mod.c:51`.
- **Recovery transactions use a 5 ms I2C timeout**, not 20. The software
  I2C applies the timeout as a deadline from the transaction's start (the
  fallback driver's `i2c_check_timeout`). With rtc.c's 15-NOP bit delay, a
  whole read is well under a millisecond; the 17 ms passes marked `i2c`
  before (`BATTERY-GAUGE-REFINE-PLAN.md`) included the bus guard's wait on a
  blit. The build measures it (`i2c_max_cycles`).
- **They take the raw path,** never `pcf_read()`'s bus guard, which waits
  on the LCD synchronously (`rtc.c:224`).
- **A pass that carries a transaction defers the rest of its display
  work:** the band, the battery row's glyphs (~7.5 ms for three,
  `display.c:1804`), `Fn`+`D`'s clear (`display.c:788`), and animation.
  So the worst pass is under 10 ms + 5 ms + the housekeeping's small work.
- **The legacy synchronous SET** (`rtc_set_time`, `rtc.c:1105`) answers
  "retry" during a recovery.
- **Deferred flash writes wait until the recovery ends:** eeconfig's,
  `rtc_persist`'s, and the level's save.
- **The log's sleep entries**, up to 720 written in RAM (a few ms), go in a
  pass with no I2C.
- **Validated by count:** passes of 25 ms or more through every step, with
  each failure forced in turn: a failed PCF read before the sleep, a failed
  one after, an aborted acquisition, a stuck bus.

### 5. The radio and USB after a wake

- **The radio:**
  - the UART drain and the parser's resync (now in every build);
  - the battery poll, after the waking input (step 5).
  - The link's state cannot be asked, so a drop or a reconnect while asleep
    stays unknown until the module says otherwise. A missed `5B 32` is
    recovered by the 5A promotion. Accepted.
    ⚠️ **Corrected by the 10-31 audit (F-023):** the promotion fires only
    after a wake, on a 5A, and the host's LED report at connect went out
    while the board slept; the module forwards changes only, so the next 5A
    comes with a lock change, and before the fix none came from REJECTED at
    all. Since then a link attempt under 60 s old holds off the sleep
    (`DSB_LINKING`), the promotion fires from REJECTED too, and after a
    sleep the band stops naming the "Hold Fn+Q 2s" remedy until the module
    names a state again.
- **USB, when a host appeared while the board slept.** The charge wake
  covers most cases. Otherwise:
  - **One re-attach**, if no SOF has arrived within 3 s of the wake. Its
    states are pending, done, or not needed, under the sleep's sequence
    number.
  - **D+ off, then on.** The pull-up goes off: `usbDisconnectBus`, which
    clears `CFG.DPPU`, read-modify-written under the lock against the USB
    ISR's own `CFG` writes. At least 100 ms later, by a state deadline and
    never a wait, it goes on again (`usbConnectBus`).
  - **The latch:** whether any SOF arrived after this wake, from the frame
    number moving since the wake, not "seen recently".
  - **Why it is enough:** on this LLD both calls only flip `DPPU`, with no
    delay (`hal_usb_lld.h:376-390`). The host's bus reset then runs
    `_usb_reset()` (`hal_usb_lld.c:234`).
  - Never `restart_usb_driver()`, whose 50 ms wait loses a tap.
  - The recovery holds the board awake until D+ is restored.
- **A suspended host** (on the pack with data, the host asleep, no SOFs) is
  indistinguishable from an absent one. The re-attach then turns a
  resumable device into a detached one, and the remote-wakeup relationship
  is lost. Real use never has data without VBUS, since on USB nothing
  sleeps, so this is a bench-only cost. Accepted.

### 6. The gauge and the log

- **The sleep term** (step 3):
  - `P_SLEEP_UW` 13,350 × the slept ms, 64-bit from the first multiply,
    with the remainder kept;
  - stale `band_hold` cleared first, since `c5_forget()` alone does not;
  - into `e_used`, the level's count (the 1% floor, the cut's 0, an unknown
    level and a pending re-seat all as now) and the log; never into the
    minute's energy;
  - then time left recomputed at once. Today it changes only on a minute
    boundary.
- **Time left is hours of use, with no new arithmetic.** The average is
  built from awake minutes only (`battery.c:729-743`), so
  `battery_time_left_min()` already means minutes of awake use at the
  recent awake draw, to the cut.
  - The 12 h constant is now 12 awake hours, ~1.5 days at 8 h of use a day.
  - The maturity rule, the freeze on USB and the strings stay as Phase 2
    built them.
- **The relaxation:** `relax_from` is moved back by the slept time
  (saturating at done). The re-seat then waits for the first fresh estimate
  after the wake, since the ring was forgotten.
- **The log's own time base.**
  - Log time = QMK's timer + the slept ms accounted so far (u32, modular,
    like the timer). The period's start, the newest entry's end and
    `battery_log_read()`'s age (`battery.c:1394`) all read it, so the host's
    dating (`ak820battery.py:245`) stays right.
  - The calendar is never used for this, since a host sync would move the
    boundaries.
- **The log, v7.** `vdd_avg` gives way to **the period's slept seconds**
  (u16, 0-900). On battery `vdd_avg` reads the buck-boost's 3.90 V, and the
  supply is already in `flags` and `flags_any`.
- **No period closes between the wake and step 3.** `log_task()` keeps
  collecting into the live accumulators but never closes or resets a period
  until step 3 has reconciled the sleep (`battery.c:1357,1382`). Otherwise
  the open period could close by the timer, on its awake time alone, before
  the sleep is laid in, and entries would be reordered or observations lost.
- **The boundaries are counted from the sleep's start through step 3**, in
  log time with the sleep accounted, not just to the wake. A boundary can
  fall after the wake, during the recovery's few seconds.
- **No boundary through step 3:** the sleep merges back into one open
  period. The frozen record and the live accumulators are combined: sums
  and counts added, minimum and maximum taken, flags OR-ed, energies added
  with the sleep's. The slept seconds go in.
- **One boundary or more:** the sleep's entries are written at once in step
  3, from the record frozen in step 0.
  - **The first period to close always keeps its frozen contents,** plus its
    slept share: the sleep up to its boundary, or all of it if the sleep
    ended first, with that share's energy. Its flags and charging state are
    as at entry. Its level is the entry's, less the sleep's energy up to the
    period's end.
  - **Each later period the sleep covers whole** becomes one entry: 900 s
    slept, its energy at `P_SLEEP_UW`, no `5C` reports, a dark load
    (`led_pm` 0, `bkl` 0), the flags as at entry, and the level stepped down
    by the sleep's energy up to that boundary.
  - **A period whose boundary falls between the wake and step 3** holds only
    the part of the sleep's share inside it, with no observations.
  - **The period open at step 3** takes the live accumulators (all their
    `5C` intake, `battery.c:354`, and their live energy, `battery.c:666`),
    plus any of the sleep's share inside it. Live observations are
    aggregates and cannot be split, so at most a few seconds of them land
    one period late; declared and tested.
  - **Codex's example:** a period ending at 900 s, the sleep from 890 to
    899, step 3 at 901. The period ending at 900 closes with its frozen
    contents and 9 s slept, and the next takes the live 899-901.
  - **At most `LOG_LEN` entries are written**, since older ones would be
    overwritten anyway. `log_written` advances by the full count.
  - **Written synchronously**, so a dump never meets a catch-up that is
    still moving.
- **Consumers:**
  - **`ak820battery.py`:** decodes v7, with slept seconds in place of
    `vdd_avg`, and keeps v1-v6.
  - **The simulator's CSV reader:** stops indexing `vdd_avg`
    unconditionally (`sim.c:861`).
  - **The simulator's replay** of a v7 entry plays its awake part
    (900 − slept) at 10 Hz with its reports, then the slept part through
    the production sleep accounting. The order within a mixed entry, awake
    first, is an approximation the aggregate cannot avoid; it is declared
    and tested.
  - **`battery_fit.py`, `battery_charge.py`:** stay historical (v3-v5),
    noted in their docstrings.
- **Grading time left from dumps** (`SLEEP-PLAN.md`, "Grading it in days"),
  stated as an approximation:
  - each entry's awake draw is (energy − `P_SLEEP_UW` × slept) / awake,
    skipping wholly slept entries;
  - the 12 h average is rebuilt from those, to a stated tolerance, not
    exactly: the firmware's minute state and its starting point are not in
    the log.

### 7. The display

- **The battery row** shows the hours beside the level once time left is
  under 10 h and the average is mature (60 awake minutes or more): `18% 6h`,
  `99% <1h`.
  - That is at most 7 cells, the slot's 7, in the 8-byte buffer
    (`display.c:1667-1708`).
  - With `BATTERY_SHOW_TENTHS` (the calibration view) there are no hours.
  - The painting stays as it is: `BATT_TXT_CHUNK` 3, the clear separate,
    one component per call.
  - Hidden on USB, after the cut, with no pack, and with the level unknown.
- **A wake after 2 h or more asleep**, under the same conditions as the row,
  posts `6h use left` (`<1h use left` fills all 12 cells).
  - It goes through the owed-notice gate that "Saving power" uses: a free
    band and a lit screen. So it waits behind an alert rather than expiring
    unseen.
  - **In Minimal** the screen is dark until a message paints, so a lit
    screen cannot be the gate. There it needs only a free band, and is
    posted once the repaint hold (step 9) ends. Its paint then lights the
    screen for 4 s, like any message.
  - Rounded down.
- **The camera page** stays as it is (`58% 31h`), now reading as hours of
  use.
- **The clock after a wake:** the backlight is held until the corrected
  face is painted (step 9).

### 8. `HC_POWER` page 1

- **The request's `data[3]` selects the page.** It is read before the
  existing `memset` (`hid_protocol.c:765-787`). Page 0 stays byte for byte,
  so older hosts are unaffected.
- **Page 1 identifies itself.** Its reply's first byte is 0x81, and an older
  firmware's page-0 reply starts with 1, so it cannot be misread as sleep
  data.
- **What it carries:** 26 of the 29 bytes, snapshotted together, in every
  build:
  - **four u8:** 0x81; the last wake's source (key, knob, charge, backstop,
    strays); validity bits (the PCF figure, the acquisition, the USB
    observation, since otherwise 0 is ambiguous); the recovery's state;
  - **four u32:** sleeps since boot, which is also the last sleep's sequence
    number (one counter, defined so); slept seconds since boot (from the
    PCF); the last sleep's PCF seconds; its counted seconds;
  - **three u16:** the acquisition's step (ms, signed); PLL loops; strays.
- The payload's size is asserted. `ak820battery.py` prints the page, and the
  trial logs it.

### 9. Riding along

- **The per-colour RGB model**
  (`history/power-bench-2026-10-15/rgb-curve-20261019/`):
  - the driver's committed-frame accounting keeps three channel sums instead
    of one (`drivers/led/sn32f2xx.c`);
  - `model_nj()` weights them: B red 3,636, green 2,533, blue 2,294 nW per
    unit;
  - A is refitted against the model's own RGB-off draw. The fit's 7.71 mW is
    against the measured RGB-off, 0.9 mW above the model's, so expect ~8.6.
  - On the map, every step is within 0.6% and purple within 0.2%. The log's
    single `led_pm` cannot recover the colour split, but the log's energy
    field carries the model's total, which is what grading needs.
- **The sleep.c comment wording** (codex, sleep verify 3).
- **Optional:** `raw_edges` counted inside the lock (`BACKLOG.md`).

### 10. Not in this build

- **Light sleep:** optional.
- **A battery check while asleep:** the radio is the only voltmeter, and
  nothing could cut the 13 mW anyway.
  - A board asleep at the cut has about two days before the pack's own
    protection. That is an estimate: run 2's 5 h of reserve at the dark
    draw, over 13 mW.
- **The first key's ~28 ms:** measured again, not fixed here.
- **The wireless clock:** lock-LED item 5.
- **Sleep figures on `Fn`+`D`.**

## Validation (revision 5)

**On the host, before the flash** (`scripts/battery_sim`, building
`battery.c` and `power.c` on the Mac):

- **The sleep term:**
  - a night into `e_used` and the level, and never into the average;
  - time left moves only by the level;
  - the floor, the cut's 0, an unknown level and a pending re-seat;
  - `band_hold` cleared;
  - the remainder carried across sleeps.
- **The relaxation:** aged by a sleep shorter than it and by one longer.
- **The log v7:**
  - sleeps within a period, across one boundary, across many, longer than
    the log;
  - entry and exit not aligned to a boundary, and repeated partial sleeps
    in one period;
  - each entry's slept seconds and energy add up to the sleep's, with the
    levels stepped right;
  - the dating through `battery_log_read()`'s age;
  - the PCF-failure fallback;
  - the round trip through `ak820battery.py`;
  - a dump between two sleeps, and one during a recovery (it answers
    "pending" until step 3, and the host retries);
  - `5C` reports arriving during the recovery land in the live period,
    never in the frozen one;
  - no period closes before step 3, even when the open period's awake time
    reaches its end during the recovery;
  - no boundary through step 3: one merged period; codex's case (the
    sleep ends just before a boundary that falls before step 3): the first
    period keeps its frozen contents and its slept share, and the live data
    goes to the next; a sleep across many boundaries with step 3 past
    another one.
- **The replay:** a v7 log with sleeps, through the sleep semantics; a CSV
  without `vdd_avg` is read; the mixed-entry approximation's error stated.
- **power.c:** each mode's sleep time, low battery's (Normal at 3 min, Full
  never), never on USB.
- **The strings:** the row up to 7 cells, the tenths view without hours, and
  the wake message's rule (2 h or more asleep, the row's conditions,
  rounded down).

**On the board, after the flash** (the dev build):

1. **The soak again** (`deep_cycles.py`, 100+ cycles), through the ladder's
   own path at the bench's short sleep time (30 s or more).
   - **Each cycle passes only if:**
     - **exactly one press** at the board (`key_gain == 1`), with a fresh
       sleep sequence number;
     - **no reset** (uptime continuity), no new pass of 25 ms or more,
       recovery included;
     - **no new transport errors:** the queue's full and replaced counts and
       UART errors unchanged;
     - **the slept time agrees:** the PCF's slept seconds against the
       logger's fall and rise edges, within ±2 s (1 s from each). Today
       `asleep_s` starts at the 3-sample confirmation; it moves to the
       edges.
   - **The clock:** the daemon's offset before its first SET after each
     wake, which comes after the acquisition (today −1.5 to +2.1 s; the
     target is ~50 ms).
2. **Real thresholds, the default mode:** Normal sleeps after 7 idle
   minutes, once, and the rig wakes it.
3. **An hour asleep:**
   - the slept seconds against the logger's edges;
   - the sleep's energy summed across whatever entries it spans, with the
     awake energy after the wake kept apart;
   - the clock's offset before the first SET.
4. **The clock without the daemon** (and the acquisition split, with a dev
   hook that defers its full read by 1 s once: it must reacquire, never set
   the clock a second wrong; the hook behind `HC_DEVHOOK`'s guard, dev builds
   only):
   - the daemon paused, and the board's clock read with `ak820 clock` after
     a sleep;
   - then host syncs injected at 0.2, 1 and 3 s after a wake (data on
     through `uhubctl`): the host's time wins;
   - the awake period (`P_nom`) and the persistence candidate unchanged by
     the sleep (`HC_RTC`).
5. **The wake sources:**
   - **the repaint hold's ends:** with the clock off, with `Fn`+`D`'s page
     open at the sleep, in the date format, and in a time format. The
     screen lights each time, and never with the slow time;
   - the rig's key (P2) with 25 ms taps (step 1's input gate), and presses timed around the
     admission;
   - a P0 key and a chord, by hand (JD, one action);
   - **the knob,** by hand: both resting states, both directions, a
     reversal, a wiggle with no detent, a fast turn. **Pass: no step in the
     wrong direction, at most one detent lost;**
   - optionally, the slider while asleep (it resets the MCU).
6. **Charge and USB:**
   - relay 2 on while asleep: the board wakes at once (the logger), with
     data on and off;
   - a full-pack insertion with no CHRG edge: it waits for the backstop or
     a key;
   - a host appearing while asleep (`uhubctl` on, relay 2 off), then a key:
     raw HID answers within ~5 s, which checks HID traffic, not SOFs alone;
   - host frames timed around the re-attach's 3 s and 100 ms deadlines.
7. **The backstop:**
   - the 32-bit widths, with the dev preset of the counted seconds near
     65,535;
   - the real length once, over a weekend: two autonomous cycles with no
     input.
8. **The builds:**
   - daily, fpb, instrumented and dev all build;
   - `build.sh`'s structural checks extended: the production sleep path
     present in every flavour, no dev mutation handler in daily or fpb;
   - one daily build on the board before a release, with JD's `Fn`+`Esc`
     back to dev: it sleeps by default and rejects `HC_DEVHOOK`.
9. **The stage test** (the Mac unlocked, the keyboard untouched ~10 min):
   - no lost keys at any transition, sleep included;
   - the first key's latency, and short bursts after a sleep (the battery
     poll waits for them).
10. **R5 with sleep:** a drain in Normal at JD's use, from the board's v7 log
    and the logger.
    - the gauge within ±3 points;
    - the sleep energy against the logger at the top of the pack, mid-drain
      and low (constant power is assumed);
    - time left graded per section 6.

## Questions for the fourth verify

1. The log's boundaries counted through step 3, and the first closing
   period always keeping its frozen contents: does that settle W2?
2. The gauge moved ahead of the acquisition, and both repaints scheduled
   one component per pass under a 500 ms bound: any new problem?

## Codex's plan review (10-19) and what changed

[Verbatim](review-codex-deep-sleep-plan-2026-10-19.md), prompt
[`review-prompt-deep-sleep-plan.txt`](review-prompt-deep-sleep-plan.txt).
"Revise before building": the approach sound, freezing QMK's timer right,
the locked sequence largely sound. Every finding was taken.

| # | finding (short) | disposition |
|---|---|---|
| 1 | **must fix:** the SysTick alarm off does not freeze CT16B5, which counts through each second's wake and the entry/exit; a week passes QMK's wrap | **Fixed:** CT16B5 stopped under the lock, restarted after the restore (section 2). |
| 2 | **must fix:** the 30 min relaxation after an unplug must include sleep | **Fixed:** aged by the slept time, then a fresh `5C` (section 6). |
| 3 | the log needs its own time base and live/backlog separation | **Fixed** (13, 14 below). |
| 4 | a lost first detent decodes nothing, so QMK's activity is not reset; charge and backstop wakes need their own hold | **Fixed:** the wake triggers the activity itself; the recovery holds the board awake (section 4). |
| 5 | the radio's cached battery age stays fresh | **Fixed:** marked stale at the wake. |
| 6 | should fix: host text (3 min) can reappear hours later; the playback heartbeat too | **Fixed:** both expired at the wake. |
| 7 | the production path must not depend on the dev arm's give-up and `DS_DONE`; USB recovery's timers must run to the end | **Fixed** (sections 1, 4). |
| 8 | **must fix:** one owner and an order for the RTC's recovery: `ps_state` idle at admission; the trim window invalid before any discipline call; the 60 s discipline suspended through recovery; a signed atomic correction, the calendar set superseding the coarse add | **Fixed** (sections 1, 4: steps 0-3). |
| 9 | **must fix:** a host sync can come before the recovery's pass | **Fixed:** a generation rule; the newer host time wins; the old `host_synced` cleared once (step 2). |
| 10 | should fix: reset the SOF continuity fully, also for a sub-second sleep | **Fixed** (step 0). |
| 11 | the acquisition reused: reset all its state, aborted ends the hold, a defined case for no valid RTC | **Fixed** (step 3). |
| 12 | note: the whole-second set gives no phase; the boot's accuracy is not guaranteed under wake load | **Agreed;** measured (validation 1, 3, 4). |
| 13 | **must fix:** the catch-up cannot reuse the live accumulator (awake energy and the waking level in the sleep's entries; current observations erased) | **Fixed** in revision 3, after the verify found the pause incomplete: the open period frozen into a record in the locked exit, the live accumulators reset; the entries written from the record, each with its own level and a dark load (sections 4, 6). |
| 14 | **must fix:** the log needs its own elapsed time for dating | **Fixed:** log time = the timer + accounted sleep; never the calendar. |
| 15 | should fix: a dump during a catch-up that moves every 100 ms can exhaust the host's retries | **Fixed:** the entries are written synchronously. |
| 16 | **must fix:** the replay needs sleep semantics, and the CSV reader indexes `vdd_avg` unconditionally | **Fixed** (section 6, validation). |
| 17 | should fix: "rebuilt from any dump" is too strong | **Fixed:** an approximation with a stated tolerance; per entry, the awake draw. |
| 18 | **must fix:** the knob's A == B check misses 00 → 11 | **Fixed:** compared with the decoder's stored state, and latched edges checked after arming. |
| 19 | **must fix:** a recovery hold independent of decoded input (the RTC, the battery reply, the log, the supply, USB, the first input) | **Fixed** (section 4). |
| 20 | should fix: "no wrong-direction step" as the knob's pass | **Fixed** (validation 5). |
| 21 | **must fix (USB):** a state deadline, awake until D+ is back, `CFG` under the lock, a latch for SOFs since the wake, states per sleep | **Fixed** (section 5). |
| 22 | the re-attach cannot wake a sleeping board; a full pack with no CHRG edge waits | **Fixed** (wording, sections 2, 5). |
| 23 | note: the suspended host's cost | **Accepted,** bench-only (section 5). |
| 24 | **must fix:** the parser's resync is dev-only (`ch582f_ajazz.c:1047`) | **Fixed:** in every build (section 2). |
| 25 | the production and dev-only lists | **Taken** as codex gave them (section 2). |
| 26 | should fix: structural checks on every flavour; the production path present, `HC_DEVHOOK` rejected on daily/fpb | **Fixed** (validation 8). |
| 27 | the gauge: 64-bit from the first multiply, the remainder kept, `band_hold` cleared, time left at once | **Fixed** (section 6). |
| 28 | **must fix:** the backstop's counts are 16-bit (86,400 becomes 20,864) | **Fixed:** 32-bit throughout; the dev record versioned. |
| 29 | note: ~27.5 h; no failsafe against the RTC stopping; test two autonomous cycles | **Agreed** (section 2, validation 7). |
| 30 | the display: up to 7 cells, not 6; the tenths view; keep the chunking | **Fixed** (section 7). |
| 31 | should fix: the wake message under the row's conditions, queued rather than lost | **Fixed:** the owed-notice gate. |
| 32 | should fix: the calendar set before the backlight is not the panel painted | **Fixed:** the backlight held until the clock's repaint (step 9). |
| 33 | **must fix:** `HC_POWER` page 1: read `data[3]` before the `memset`, page 0 unchanged, a discriminator, validity bits, one snapshot | **Fixed** (section 8). |
| 34 | **must fix:** budget the whole wake pass, failure paths included | **Fixed:** one step per pass; validation counts long passes through every step and failure (section 4). |
| 35 | should fix: the battery poll can delay the waking input; measure bursts | **Fixed:** the poll after the first report (step 5); bursts in the stage test. |
| 36 | note: never batch encoder events into QMK's queue | **Agreed;** nothing is injected. |
| 37 | the validation's gaps: `asleep_s` from the edges; exactly one press and the transport counters gated; the ladder's own path; the daemon concealing a failed correction; the widths; more wake inputs; CHRG and USB cases; nonaligned log cases; Full at low battery | **Fixed:** the validation rewritten; Full never sleeps (section 1). |
| 38 | note: the evidence's scope (board-only, one P2 column, 7-30 s) | **Fixed** (the measurements' wording). |

## Codex's verify (10-19) and what changed

[Verbatim](review-codex-deep-sleep-plan-verify-2026-10-19.md), prompt
[`review-prompt-deep-sleep-plan-verify.txt`](review-prompt-deep-sleep-plan-verify.txt).
"Still needs changes before building."

- **Resolved by revision 2:** must-fixes 1, 2, 8, 9, 16, 18, 21, 24 and 28,
  and 14 once the log's sleep entries are committed.
- **The timer freeze confirmed:** `CEN` holds the counter and the prescale
  counter (manual p. 125), with no VT or QMK adjustment needed.
- **Partial:** 13, 19 and 33. **Not resolved:** 34.

Revision 3:

| # | finding (short) | disposition |
|---|---|---|
| V1 | **must fix:** "the first pass" cannot guarantee the waking report: debounce is deferred per key (5 ms), and a PCF read can eat a short tap; the periodic battery poll also goes out | **Fixed:** step 1 waits across passes for the press to be counted (or an encoder event), bounded at 50 ms; no recovery I/O, and the periodic poll held, until then (section 4). |
| V2 | **must fix (34):** one step per pass does not bound the pass. The acquisition's edge is three transactions in one call; `pcf_read()` waits on the LCD bus guard; display, 10 Hz and persistence work can share the pass | **Fixed:** at most one I2C transaction per recovery pass, from the fast task's slot with no blit in flight and the glyph queue empty, by the raw path (no bus guard), the pre-sleep read included; the acquisition's edge split into three passes; deferred flash writes wait until the recovery ends; long passes counted through every forced failure (section 4, "The budget"). |
| V3 | **must fix (13):** pausing `battery_task()` does not freeze the log: `ch582_task()` feeds `battery_5c_report()` directly; the awake energy since the last 1 Hz tick is pending; the first mixed entry's level must include its debit; an early `HC_BATTLOG` would date old entries hours too recently | **Fixed:** the open period frozen into a record in the locked exit and the live accumulators reset (everything after the wake, `5C` included, lands in the live ones); the energy integrated up to the sleep before the lock; the first entry's level less its sleep debit; `HC_BATTLOG` "pending" until step 4; nothing pauses `battery_task()` now (sections 4, 6). |
| V4 | **must fix (33):** page 1's fields come to 30 bytes, not 26 | **Fixed:** codex's 26-byte layout, four u8, four u32 and three u16, with sleeps since boot defined as the last sleep's sequence number (section 8). |
| V5 | **must fix (19):** the repaint hold has no end with the clock off, `Fn`+`D` owning the panel, or a failed repaint; the queue empty is not the DMA done | **Fixed:** no wait with the clock off or the panel owned elsewhere; the date format waits only for a changed date; "repainted" means the glyphs drawn and `display_bus_idle()`; a 250 ms bound after step 4 releases it anyway, flagged (step 9). |
| V6 | should fix: step 7 cannot count samples while their producer is paused | **Fixed:** nothing is paused now; samples counted after the wake, with a 3 s bound. |
| V7 | should fix: in Minimal the wake message needs a lit screen, but the message is what lights it | **Fixed:** in Minimal it needs only a free band, after the repaint hold (section 7). |
| — | note: compare the knob against `encoder_state[i] & 3` through a read-only accessor; "nothing else wakes" too broad; keep the `HC_DEVHOOK` guard | **Fixed** (section 2): the accessor, a local core change; the wording; the guard kept. |

## Codex's second verify (10-19) and what changed

[Verbatim](review-codex-deep-sleep-plan-verify2-2026-10-19.md), prompt
[`review-prompt-deep-sleep-plan-verify2.txt`](review-prompt-deep-sleep-plan-verify2.txt).
"Still needs changes": V1, V4, V5, V6 and V7 resolved; V2 and V3 partial; one
new must-fix. Revision 4:

| # | finding (short) | disposition |
|---|---|---|
| W1 | **must fix (V2):** a 20 ms timeout can share its pass with three battery glyphs (~7.5 ms), `Fn`+`D`'s clear, or ~8 ms of earlier input work; the legacy SET and the write machine's STOP recovery are outside the arbitration | **Fixed:** one arbiter for every PCF transaction during a recovery; admitted under 10 ms into the pass (from its start), with a 5 ms timeout; the pass's other display work deferred; the legacy SET answers "retry" (section 4, "The budget"). |
| W2 | **must fix (V3):** a resumed `log_task()` can close and reset a period before step 4; the zero-boundary merge and a boundary during the recovery are undefined | **Fixed:** no closure before step 4; the zero-boundary merge defined; a boundary during the recovery holds only the sleep's share, the live observations going to the period open at step 4 (an approximation, declared) (section 6). |
| W3 | **must fix (new):** split across passes, the acquisition's full read can come a second after the bracket and pass the confirmation, and the 999 ms clamp then sets the clock nearly a second wrong | **Fixed:** the full read's seconds must equal the bracketed second, within 900 ms of the edge, or it reacquires; the timeout and cancellation checked every pass even while deferred; a dev hook tests it (step 3, validation 4). |
| W4 | should fix: step 4 done is not the battery row repainted; step 3 can supersede step 2's clock; the 250 ms release cannot promise "never stale" | **Fixed:** two repaints tracked by generation (the clock after step 2, the row after step 4); step 3's later sub-second correction not waited for (a tick's worth); the promise is "never stale unless a repaint fails" (step 9). |
| W5 | note: keep the 3 s supply deadline unconditional | **Fixed** (step 7). |
| W6 | note: keep RX parsing, ACKs and reports running during the input gate | **Agreed:** only the battery poll and the recovery's I/O wait. |

## Codex's third verify (10-19) and what changed

[Verbatim](review-codex-deep-sleep-plan-verify3-2026-10-19.md), prompt
[`review-prompt-deep-sleep-plan-verify3.txt`](review-prompt-deep-sleep-plan-verify3.txt).
One must-fix left: W1, W3, W5 and W6 resolved; W4 resolved as a relaxed
policy, with a should-fix. Revision 5, with **steps 3 and 4 swapped** (the
gauge is now 3, the acquisition 4; the tables above keep the numbering of
their revision):

| # | finding (short) | disposition |
|---|---|---|
| X1 | **must fix (W2):** when the sleep crosses no boundary but the recovery does (sleep 890-899, step 3 at 901, boundary at 900), the merge rule and the recovery-boundary rule conflict, and the latter would drop the frozen contents | **Fixed:** boundaries counted from the sleep's start through step 3; none means one merged period; otherwise the first closing period always keeps its frozen contents plus its slept share, a period whose boundary falls during the recovery holds only the sleep's share inside it, and the live intake (`5C` and energy) goes to the period open at step 3 (section 6). |
| X2 | should fix (W4): generations say what was painted, not when; a clean row waits a second and dirty components go at 10 Hz, so 250 ms can be short; and the gauge's step came after the 1.5 s acquisition | **Fixed:** the correction and the debit mark the clock and the row dirty, and one component is painted every pass while the hold is on; the bound 500 ms; the gauge moved ahead of the acquisition (step 9). |
| X3 | note: `loop_acct`'s interval closes at housekeeping, after the input work; take the admission stamp before keyboard processing | **Fixed** (section 4, "The budget"). |
| X4 | note: keep the confirming read's equality check and the original timeout across a reacquisition | **Fixed** (step 4). |
| X5 | note: the new delay hook behind `HC_DEVHOOK`'s guard | **Fixed** (validation 4). |

## Codex's fourth verify (10-19)

[Verbatim](review-codex-deep-sleep-plan-verify4-2026-10-19.md), prompt
[`review-prompt-deep-sleep-plan-verify4.txt`](review-prompt-deep-sleep-plan-verify4.txt).
**No remaining build blockers.** X1-X5 resolved; the step swap audited
consistent; W2 settled (its example worked through); no new blocker from the
swap or the repaint scheduling.

- **Implementation note,** taken: the display hold's completion and deadline
  are serviced while the acquisition runs, and its accelerated painting
  yields on I2C passes under the shared budget.
- **Actual timing** is for the board validation.

## Codex's implementation review (10-19) and what changed

Of `bf7d7d0280` (firmware `442c9f49c9..bf7d7d0280`, outer repo `a4a810a`):
[verbatim](review-codex-deep-sleep-build-2026-10-19.md), prompt
[`review-prompt-deep-sleep-build.txt`](review-prompt-deep-sleep-build.txt).
**Three must-fix, six should-fix; every one taken.** All four flavours build
with no warnings after the fixes; the simulator 148 of 148, sanitizers
included.

| # | finding (short) | disposition |
|---|---|---|
| 1 | **must fix:** the PCF arbiter ends with the acquisition, not the recovery: the write machine then runs outside the 5 ms timeout, the admission and the display deferral; the legacy SET comes back; STOP recovery does two transactions in a step; the discipline's read bypasses the arbiter, and could snap the clock back to a PCF whose host-sync write is still pending | **Fixed** (`rtc.c`): the arbiter holds while `sleep_recovering()`, the write machine included; STOP recovery split into a write and a check, a pass each (`PS_RECOVER_VERIFY`); the legacy SET refused through the whole recovery; the discipline suspended through it, and in any state skipped while a PCF write is pending or running (the check stays due). |
| 2 | **must fix:** `display_pass_end()` clears the deferral flag before `sleep_task()`, so the gauge's "no I2C this pass" test always passes | **Fixed:** `rtc.c` counts PCF transactions (`i2c_note`), `sleep_task()` marks the pass's end (`rtc_pass_mark`), and the gauge runs only when the pass made none (`rtc_pass_used_bus`). The acquisition waits for the gauge (`rtc_wake_gauge_taken`), so the pass after the coarse read is always free and the gauge cannot starve. |
| 3 | **must fix:** the RGB's deferred flush checks DMA and settling, not the recovery | **Fixed:** `rgb_matrix_eeprom_flush_allowed()` also waits for `!sleep_recovering()` (`ak820pro.c`). |
| 4 | should fix: a short sleep's plausibility window admits -1 or -2 s, cast to u32; dev caps unbounded before the x1000 | **Fixed:** negative slept seconds rejected (the counted stand); the arm's span past its preset at most the backstop's 86,400 s, and the preset bounded so the cap cannot wrap. |
| 5 | should fix: a cancelled arm's cap, preset and unfed watchdog stay live for the next ladder sleep | **Fixed by isolation:** `deep_sleep()` takes its cap, preset and feed as arguments; the ladder passes the backstop, fed, from 0; only the arm passes its own (`ds_arm_*`, dev only). |
| 6 | should fix: the log's levels interpolate toward the final, possibly floor-clamped, level, spreading the clamp across the sleep; the sim checks only monotonicity | **Fixed:** each boundary's level is the level before the sleep less the sleep's energy to that boundary from the count's remainder, never below where the debit stopped (`sleep_level_at`). New `s_log_floor` (a night that reaches 1% at ~21 h) checks every entry; the old interpolation, planted, fails it. |
| 7 | should fix: the supply step counts time, not samples, with no 3 s short outcome; the 500 ms repaint timeout records nothing; neither shows under `BOUND` | **Fixed:** the supply step waits for 15 fresh samples (`battery_supply_samples`), or 3 s; a new byte (page 1's 29th, the record's spare) names every step that ended on its own timeout (input 50 ms, radio 2 s, supply 3 s, display 500 ms) or on the bound. |
| 8 | should fix: `deep_cycles.py`'s cleanup waits for USB before restoring power, so a run stopped asleep skips every control and leaves Minimal persisted; the log reader retries pending only 2 s | **Fixed:** both bench scripts restore relay 2 first (on USB power the ladder never sleeps; a charge start wakes the board), then data, then a rig tap if the board does not come back (a full pack gives no charge edge), then the controls. `ak820battery.py` retries pending for 12 s. |
| 9 | should fix: judge a cycle after the recovery closes, and cancel any old arm first; the sim lacks exact report conservation, the log energy's carry, the open period's share and a mixed v7 replay | **Fixed:** `deep_cycles.py` waits for page 1's open steps to clear (12 s) and gates on it, and cancels an arm at the start. The sim's log checks are exact (every report in exactly one entry, the energy to its carry, the open period's 600 s); new `s_replay_mixed` (600 s awake, 300 asleep, per entry). Planted, each is caught: a dropped carry, live reports in the frozen period, a mixed entry played wholly awake. |
| note | the locked sequence sound; page 1, record v2 and v7 decodes match; the RGB sums main-thread-owned; daily/fpb gain the sleep with no new dev exposure; `build.sh` proves linkage, not control flow | Noted. The instrumented build's PCF test ops (`WDT_TEST_HOOKS`) do synchronous I2C from raw HID and are not arbitrated: they mutate the clock on purpose and are never in a released or dev build. |

## Codex's verify of the fixes (10-19)

[Verbatim](review-codex-deep-sleep-build-verify-2026-10-19.md), prompt
[`review-prompt-deep-sleep-build-verify.txt`](review-prompt-deep-sleep-build-verify.txt).
**Nothing blocks the flash of `44605c1a9e`.** Findings 1-5, 7 and 9 verified
fixed (2 and 5 judged better than proposed); 6 and 8 partly open, as below.
No new keystroke-loss, stall, reset or daily-build regression found.

| # | finding (short) | disposition |
|---|---|---|
| V1 | should fix (6): the night's levels take their baseline at the accounting, after the recovery's live work; a cut before it would make the whole night 0 | **Fixed** (`752d4bcda7`): the level and the count's remainder are noted at the sleep's entry (`frz_level`, `frz_nj`); the debit runs down to the floor and not from it. New `s_log_late_cut` (a cut during the recovery, then the accounting); the late baseline, planted, fails it. 149 of 149. |
| V2 | should fix (8): the deadline guard turns the data on and exits, skipping the `finally` | **Fixed:** one `restore()` (`deep_sleep.py`), used by both scripts' `finally` and their deadline guards: relay 1, relay 2, data, the board back (a tap if not), then the controls. |
| V3 | should fix (8): the stage's release opens HID once; the daemon can hold it | **Fixed:** every stage call goes through the retrying open (`with_dev(cm.force_stage, ...)`). |
| notes | the host's SET_TIME_MS under the arbiter, `PS_RECOVER_VERIFY`, the discipline's skip on a failing PCF, the supply samples' independence, the 29-byte layouts byte for byte | Noted; nothing to do. |

## Codex's second verify (10-19), and the flash

[Verbatim](review-codex-deep-sleep-build-verify2-2026-10-19.md), prompt
[`review-prompt-deep-sleep-build-verify2.txt`](review-prompt-deep-sleep-build-verify2.txt).
**No must-fix; nothing blocks flashing `752d4bcda7`.** V1 and V3 verified
fixed; `frz_nj` the right remainder. **Flashed 12:57 10-19** (dev, token
`0x4aeddcd6`).

| # | finding (short) | disposition |
|---|---|---|
| W1 | should fix: a sleep on USB power (`p_uw` 0) can still debit history from a RELAX remainder left at the floor before a charge raised the level; the ladder never sleeps on USB, the bench arm can | **Fixed, codex's own one-liner** (`7df8a08e96`, `sleep_level_at` returns the entry level for `p_uw` 0); 149 pass. Not flashed: it rides with the next build (the power-mode icons), whose codex review covers it. |
| W2 | should fix: the guard's restore has no outer deadline, and a fired guard can overlap the run's own cleanup (a tap, the relay handle's close), possibly leaving relay 1 held | **Fixed** (`sleep_baseline.py`, `deep_sleep.py`): one re-entrant `cleanup_lock`, held by the guard across its restore and its exit; `restore()` runs once and later callers get its result; the guard opens relay 1 and turns relay 2 on last; an independent hard exit (300 s) after one more bounded try at both relays. Tested offline with the relays stubbed: the guard alone, the guard firing during the run's restore (one restore, then exit 3), and a stuck restore (exit 4 at the hard deadline). |

## Validation results (10-19)

On the Mac's board (`26fcafaeca`, then `83d8768c64`: the same code plus
bulb art) unless marked **Gremlin** (the second unit on Windows, `de5450e487`,
over 2.4G: [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md)). Smoke tests first, on
`752d4bcda7`: a rig-woken bench sleep and the 32-bit widths, both pass
(`history/deep-sleep-smoke-20261019-*`).

| # | item | result |
|---|---|---|
| 1 | the soak through the ladder | **97 of 100** (`history/deep-cycles-20261019-icons/`): every cycle one key, a fresh sequence, no reset, no pass ≥ 25 ms, the PCF **within 1 s** of the logger's edges, the recovery closed with nothing timed out; the Mac's key-down median 63.8 ms, worst 114.8. The 3 failures were UART overruns at the link's long-standing base rate (~1-2 an hour on builds with no sleep; `BACKLOG.md`), not the sleep's: the gate assumed a zero rate the link never had. **The per-wake clock check got no data:** the script holds raw HID and cuts the data each cycle, so the daemon's syncs failed; the one after the run read +288.4 ms after 85 min, the PCF's ~58 ppm. **Over 2.4G, 10 of 10** (the Mac's dongle, `history/deep-cycles-20261019-2g4/`): every check as above, the PCF within 1 s, the Mac's key-down median 48.0 ms and worst 56.4, 9 frames and 4 ACK timeouts every wake (BT: 8-9 and 3-7). The run's own verdict was 1 of 10, its logger edge at 15 mA: in 2.4G the module draws ~15 mA for ~5 s after the MCU stops, so the edge is now 22 mA (`deep_sleep.SLEEP_EDGE_MA`; the BT soak judges the same either way). |
| 2 | Balanced's real threshold | **Pass** (`history/ladder-sleep-20261019-balanced/`): asleep **421.0 s** after the tap (want 420), woke on the key, two keys, the PCF 65 s against the logger's 64. The clock +143.6 ms at the first sync after 8 min off USB (7 awake with no SOF, then the sleep), its frequency loop reset by a flash 15 min before. **Gremlin:** dark at ~7 min, Esc woke it and typed. |
| 3 | an hour asleep | **Pass** (`history/ladder-sleep-20261019-hour2/`, 19:47-20:48 over 2.4G, untouched): **the board's 3,603 s asleep against the logger's ~3,601.5** (two sleeps), the last sleep's PCF 45 s against the logger's 45, and the battery log's slept entries (11, 900, 900, 900, 892) summing to the same 3,603; 13.80 mW asleep over 2.4G. ⚠️ **One unexplained wake** 3,556 s in: ~3 s awake, then asleep again; not a key or the knob (either restarts the ladder's idle, and only the rig's taps were counted); the reason is lost because the page keeps the last sleep's only. Earlier (`history/ladder-sleep-20261019-hour/`, BT): 55 min 55 s until a key, **13.25 mW** asleep against the firmware's 13.35, within 0.8%. |
| 4 | the clock without the daemon; the acquisition's split (op 14 sub 6) | Not run. |
| 5 | wake sources | The rig's key (P2), hundreds of times. **Gremlin:** key bursts (all registered), the knob (the waking turn kept: it changed the volume). Not run: a P0 key or a chord by hand, the repaint hold's terminal cases, 25 ms taps. |
| 6 | charge and USB | **Gremlin: the cable's insertion woke it** (charge, 21 s by the PCF). Not run: the full-pack insertion with no CHRG edge, a host appearing while asleep, frames around the re-attach's deadlines. |
| 7 | the backstop | The 32-bit widths **pass** (60 counted s past 65,500; the PCF 71). The real 24 h length over a weekend: not run. |
| 8 | the builds | All four flavours build with no warnings; `build.sh`'s new checks pass on the right builds and fail on a dev ELF judged as daily and on a pre-sleep build. A daily build on the board: not run. |
| 9 | the stage test | **Fn+B on the pack: no pass ≥ 25 ms**, worst 21 ms (`history/fnb-caps-20261019-jd/`). The CAPS paint alone reached exactly 25 ms once in ~600 toggles (a blit): its own item, not the sleep's. The first-key latency: item 1's. |
| 10 | R5, a drain in Normal at JD's use | Not run. |
