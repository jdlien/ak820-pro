# Findings — bounded-wait audit (phase 2.2 / 2.2b / 2.4)

Audited 2026-09-01 against `ak820pro-jdlien` @ a4382c747c and the seven
patch commits on `lib/chibios-contrib` `ak820pro-patches`
(5bed8690..c07bfe95). Scope: every spin/wait in
`keyboards/a_jazz/ak820pro/**`, the patches, and the QMK-core edits, plus
the §2.2b draw-path stall budget and the §2.4 TX-queue/RX-FIFO items.
Glyph-stall arithmetic uses the measured datum 53 ms / ~40 glyphs ≈ 1.3 ms
per blocking glyph (6x14 face; the 15x22 clock face pushes ~4x the bytes,
call it ~2 ms).

## Findings, ranked

### 1. HIGH — `gq_flush()` can rebuild the ~50 ms stall the pump removed
`graphics/display.c:1334`. `while (gq_i < gq_n) { lcd_blit_wait(); pump; }`
drains the glyph queue *synchronously* so the other band owners (clock,
battery, locks — the comment says so) don't interleave windows with a
half-painted line. The loop is bounded (progress or bail on wait failure),
but GQ_MAX = L0+L1 = 40 glyphs, so a band transition that queues a full
two-line repaint immediately followed by a clock/battery/lock redraw in the
same housekeeping pass blocks ~40 × 1.3 ms ≈ **52 ms — the original
keystroke-eater number**, reachable through a different door. Cell-diffing
makes a full queue rare (band handbacks, font switches), which is exactly
when it will be observed as "typing hiccups when the song changes".
**Disposition: fold-into-phase-3** (band arbiter): either let the queue
drain across passes before other owners draw (defer their redraw a tick —
none of them is latency-critical), or cap `gq_flush()` at ~8 glyphs per
pass and re-enter. Do not remove the flush without replacing its
mutual-exclusion role (the interleaving hazard it guards is real).

### 2. MEDIUM — playback relayout draws up to 17 glyphs blocking
`graphics/display.c:~368-384` (`draw_playback`). Per-second updates are
cell-diffed (1-2 glyphs, fine), but `relayout` (start/stop of playback,
font switch at the 1-hour mark, `clock_force_repaint`) clears the band and
redraws every cell: `H:MM:SS/H:MM:SS` = 17 glyphs ≈ **22 ms** blocking.
**Disposition: fold-into-phase-3** — route through the glyph queue; the
queue/shadow machinery already handles exactly this shape for the text
band. Needs a third shadow slot (GQ_RUNS is 2) or `gq_push` reuse with the
band-clear invalidation rules already in `band_clear()`.

### 3. MEDIUM — clock full repaint ≈ 8 FONT_CLOCK glyphs blocking
`graphics/display.c:471` (`draw_time` inner loop). Diffed per second
(1-2 glyphs ≈ 2-4 ms — fine, that is the design and it never flickered).
Full repaint (`clock_force_repaint`: boot, paused-handback,
`display_set_paused(false)`) is 8 glyphs × ~2 ms ≈ **16 ms**. Same shape
as finding 2 and the same fix; boot's instance is masked by deliberate
boot blocking. **Disposition: fold-into-phase-3** (same queue migration);
until then it is a one-off 16 ms at media-pause, not a steady cost.

### 4. MEDIUM — lock-band and battery repaints, marginal
`graphics/display.c:806-814` lock labels: worst case CAPS+WIN+FN = 9
glyphs ≈ **12 ms**, only on a lock-state change — i.e. at the instant of a
deliberate keypress (Caps), where a 12 ms scan hole can swallow the *next*
fast keystroke. Battery % (`:730`) is ≤ 4 glyphs ≈ 5-8 ms on level/charge
change — under budget. Conn digit (`:617`) is 1 glyph — fine.
**Disposition: lock band folds into phase 3 with 2/3; battery and digit
accept-and-document** (add the "measured ~X ms" comment the plan asks for).

### 5. MEDIUM — factual error: the UART RX FIFO is NOT disabled
`bluetooth/ch582f_ajazz.c:345` comment ("RX FIFO DISABLED ... ~87us or it
is lost") and `serial_cfg.UART_FIFOControl = 0`. The LLD's `uart_init`
**always** sets `UART_FIFO_Enable` and only ORs the config into the
threshold bits (`hal_serial_lld.c:216-219`); `0` == `UART_RxFIFOThreshold_1`
(`sn32_uart.h:217`) — a 16550-style 16-byte FIFO, enabled, IRQ per byte.
So the real overrun tolerance is ~16 × 87 µs ≈ **1.4 ms**, not 87 µs, and
the plan's "evaluate enabling it" is moot — it is on. What *is* tunable is
the threshold: `UART_RxFIFOThreshold_4` would cut UART IRQ count ~4x for
≤ 260 µs added delivery latency (safe: the parser is chunk-agnostic,
3-byte frames, and `ch582_task` drains up to 64 bytes per pass).
**Disposition: fix-now for the comment** (it is actively misleading and
CLAUDE.md repeats it); threshold change is **optional** — measure
`[ch582]` counters before/after per the plan if attempted, and note the
UART already sits at the top interrupt priority, so the win is CPU, not
robustness.

### 6. MEDIUM — TX-queue overflow policy: adopt newest-supersedes, A1/A3 only
`bluetooth/ch582f_ajazz.c:394` (`ch582_send_command`) drops the whole frame
when the ring (24 slots, 23 usable) fills — `tx_stat_drop++`, including a
key *release* whose press already went out: a stuck key over BT under burst
+ link stall (drops need ~23 queued frames, i.e. ACK stall × typing burst).
Frame mix through the queue: `0xA1` keyboard state (8 B), `0xA3` consumer
usage (2 B), `0xA6` control (select/bounce/pair), occasional `0xA5`/status.
The code's own contract (`:323`) says frames carry **state, not events**
and are idempotent — so for A1/A3 the newest frame strictly supersedes any
older *queued, not-in-flight* one.
**Recommendation: newest-supersedes for same-type A1 (and A3) frames** —
on enqueue of an A1, if an un-sent A1 is already queued, overwrite its
payload in place instead of appending; likewise A3. Under burst the host
then always converges to the true final state; a release can no longer be
lost behind a full queue, and queue depth stops growing with typing rate
at all. Rejected alternatives: *reserve-capacity-for-releases* (bookkeeping,
still drops intermediate presses, and "release" is not distinguishable
from "different press" in an absolute-state frame anyway);
*neutral-report-after-overflow* (asserts a state the host never had — a
drop on a press would type a phantom release).
**⚠️ Never coalesce `0xA6`**: the cancel-pairing bounce depends on
*ordered distinct* selects (bounce slot then target); collapsing them
re-derives the documented "same-slot select is a no-op" trap.
**Disposition: fix-now candidate** (small, self-contained, soak-testable
over BT); if deferred, fold into phase 3.2 step 1.

### 7. LOW — I2C fallback clock-stretch timeout leaves no bus-clear
`lib/chibios-contrib os/hal/lib/fallback/I2C/hal_i2c_lld.c:121`
(`i2c_wait_clock`): the in-loop timeout `return MSG_TIMEOUT` does not issue
a STOP or 9-clock bus recovery (the entry-point check at `:106` does call
`i2c_write_stop`). After a timeout mid-stretch, a slave still driving SDA
makes the *next* transaction fail arbitration (`:97-104`) — an error, not
a hang, so the 10 Hz tick degrades to failed 20 ms-bounded reads until the
slave releases. The clock shows stale time; nothing stalls.
**Disposition: accept-and-document** (the PCF8563 does not clock-stretch
in practice; the glitch source — port-A SPI1 coupling — is already removed
by `rtc_bus_guard()`). Optional phase-3 nicety: 9 SCL pulses on timeout.

### 8. LOW — ChibiOS-driver waits are unbounded by design; WDT is the backstop
`graphics/lcd_bus.c:250-255` (`spiSend`/`spiExchange` on SPID1) and
`bluetooth/ch582f_ajazz.c` `sdWrite` block the calling thread until the
respective ISR completes/drains; there is no timeout variant in use. A
lost SPI1/UART ISR would park the main loop — unkickable — and the ~12 s
watchdog resets. Local bounds would mean bypassing the HAL (already done
where it is known-necessary: `spi1_raw_byte`, `:281`, bound 500k).
**Disposition: accept-and-document — "let the WDT catch it" is the right
answer here**; these have never been observed to wedge, and the one
context where the vector is genuinely disabled already uses the bare-metal
bounded variant.

### 9. LOW — EFL busy-wait is unbounded, with interrupts masked
`efl_ramtext` patch (`sn32_flash_wait_busy`): `while (STATUS & BUSY)` on
the internal-flash array, executed from `.ramtext` with IRQs masked for
the program window. If BUSY never clears (dying flash array), this spins
forever; the WDT still fires (ILRC-clocked, independent of masked IRQs)
and the reset lands mid-flash-transaction — the exact case the phase-1
checklist's mode-2 stall test exercises for the wear-leveling recovery.
**Disposition: accept-and-document**; a local bound would have to decide
what to do with a half-programmed row anyway, which is the same recovery
the post-WDT eeconfig validation already owns. Sector erase is not masked
(deliberate, documented) and the same argument covers its wait.

### 10. INFO — waits verified sound (no action)
- `lcd_blit_wait()` `graphics/lcd_bus.c:660` — the template: two-phase
  bound (start-detect ~10 ms, then BLIT_WAIT_SPINS ≈ 250 ms), full bus
  teardown via `spiSN32FlashDmaAbort`, counter + `[lcd]` line,
  single-retry only for provably-never-started transfers.
- `spi1_raw_byte` `:281` — 500k bound, break-and-continue.
- `spi1_drain` BUSY-only idiom — bounded; the "correct" RX_EMPTY variant
  was measured worse (kept comment).
- Flash program/erase path `:340-400` — non-blocking by contract; callers
  poll `flash_busy()`; every SPI-level spin bounded.
- Animation player waits — now via `lcd_blit_wait()` (the 2026-08-30 fix);
  no unbounded waits remain in `lcd_bus.c`.
- CH582F RX parse loop `:669` — hard 64-byte cap, `TIME_IMMEDIATE` reads.
- CH582F TX pump — ACK timeout 10 ms, 8 retries, then drop+count.
- RTC I2C — every transaction `i2cMasterTransmitTimeout(..., 20 ms)`;
  clock-stretch loop bounded by the same window; SDA-low reads back as
  arbitration-lost (error, not hang); `rtc_bus_guard()` drains blits first
  and counts would-be overlaps.
- `usb_wakeup_try` — rate-limited 500 ms; `usbWakeupHost` sleeps a fixed
  2 ms.
- `process_modified_consumer` `wait_ms(8)` — deliberate, documented
  endpoint-ordering gap.
- `watchdog.c` / `health.c` — no waits (PRST pulse is two register
  writes); `HC_STALL for(;;)` is deliberate and instrumented-only.
- Bootloader splash (~70 glyphs, ~90 ms blocking) — runs immediately
  before the reset; nothing to preserve. Accept.
- `hardware_pwm` / `rtc_lld` patches — channel-bounded `for` loops only.

## §2.2b stall budget summary

| Path | Worst case | ms est. | Over 10 ms? | Action |
|---|---|---|---|---|
| gq_flush (band transition + other owner) | 40 glyphs | ~52 | YES | finding 1 |
| playback relayout | 17 glyphs | ~22 | YES | finding 2 |
| clock force repaint | 8 glyphs (15x22) | ~16 | YES | finding 3 |
| lock band appears | 9 glyphs + rects | ~12 | YES | finding 4 |
| battery change | ≤4 glyphs + rects | ~6 | no | comment cost |
| conn digit | 1 glyph | ~2 | no | comment cost |
| clock/playback per-second diff | 1-2 glyphs | ~3 | no | none |
| bootloader splash | ~70 glyphs | ~90 | pre-reset | accept |

Migration to the staged queue is mechanically straightforward per site
(the queue, shadows, and `band_clear` invalidation already exist), but
**shadow slots are the constraint**: GQ_RUNS = 2 (text lines). Clock,
playback, locks, battery each need a slot (or a shared "band run" table)
— that is band-arbiter design work, which is why 1-4 all say phase 3.

## §2.4 disposition summary

- RX FIFO: already enabled; **fix the false comment now** (ch582f + the
  CLAUDE.md echo); threshold_4 optional, measured, low priority.
- TX overflow: **newest-supersedes for A1/A3 only**, never A6; fix-now
  candidate, else phase 3.2 step 1.
