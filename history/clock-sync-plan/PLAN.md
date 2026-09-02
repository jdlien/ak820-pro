# AK820 Pro — accurate clock sync plan

Status: **APPROVED FOR IMPLEMENTATION, 2026-09-01 — Codex rounds 1–5
complete** (`review-codex-2026-09-01.md`, `-round2.md`, `-round3.md`,
`-round4.md`, `-round5.md`; 52 findings + 1 cross-reference fix, all
folded in). Round-5 verdict: **"no Critical or High findings remain."**
One residual limitation is acknowledged in §7.5 rather than fixed.

**Implementation status (2026-09-01):** Phase 0 done (`6b05be68e3`,
`phase-0-facts.md`); Phases 1+2 done (`cc786793ec`,
`phase-1-2-results.md`); Phase 3 done (`f7d3d97e11`,
`phase-3-results.md`). The daily build with all of it is on the board; the
timekeeper agent is installed (5-min cadence). Outstanding: the 24 h
30-s soak (`~/Library/Logs/ak820pro-clock-soak.log`, started 15:34), the
8 h unplugged test, T0.3's Mac-asleep/cable-out cases, and Phase 4
options. Baseline was `9d3316bd6d`.
Companion docs: `history/hardening-plan/` (conventions, health counters, soak
harness), `docs/clock.md` (the RTC topic doc, superseded where they conflict),
`keyboards/a_jazz/ak820pro/rtc/rtc.c`, `hid_protocol.c`,
`time-util-ak820pro/ak820ctl.c`, `hostagent/`.

Notation: **`P`** is a *register value* (what goes in `SECCNTV`); one RTC
period is **`P+1` ILRC cycles** (the counter runs 0..P inclusive, `SECIF`
at the match, the counter restarts at 0 on the next cycle; a write to
`SECCNTV` restarts it at 0 immediately). "cycles" = ILRC cycles; "RTC
ticks" = seconds. `T+ms` is true time.

## 0. Goal, non-goals, constraints

**Goal.** The LCD clock reads within **±50 ms of true time whenever the USB
cable is in**, any slider position, indefinitely, with no visible jumps
after the first sync; each boot starts within ~±20 ms of the battery-backed
reference so unplugged operation is bounded by the PCF8563 crystal (~58 ppm
measured, ~5 s/day), not by a random sub-second phase.

The comparison JD makes is against an Apple Watch (±50 ms claimed). The Mac
measured **+40 ms vs `time.apple.com`** on 2026-09-01, so "as good as the
Mac" is the ceiling. The board-vs-Mac design target is **±U after a sync**,
where **U is the one-way HID uncertainty measured in Phase 0 (T0.7)** —
expected 1–3 ms — and **±(U + ILRC tracking error + SOF-bias residual ×
cadence) between syncs**, expected < 10 ms once §3.4's bias measurement is
in. No number in this document is a promise until the Phase 0 table exists.

**Non-goals.** Sub-ms accuracy; hardware timestamping; display redesign;
any change to matrix scan, RGB ISR, UART2 priority, watchdog policy, or the
eeconfig write *mechanism*.

### Hard constraints (typing protection)

Every keystroke-eating incident on this board came from one of three
things. The plan adds none, and states real worst-case bounds:

| # | Constraint | How the plan honours it — and the true bound |
|---|---|---|
| C1 | **No new interrupt sources; near-zero added ISR work.** | The only ISR code added lives in the existing 1 Hz RTC second callback (priority 3, the same level as the RGB row ISR): one `FRMNO` read, one `SECCNT` read, a `volatile` byte read, a few adds/compares, and at most one reload write via `rtc_lld_set_period()` (X-class, ~1 µs). No SOF interrupt. Bound: ≤ ~2 µs per second. |
| C2 | **No new main-loop blocking; nothing new ever waits on the LCD DMA.** | From **Phase 1 onward** all PCF I2C traffic — including the write a host sync causes — goes through `rtc_fast_task()`, which runs **before** `display_blit_pump()`, performs **at most one I2C transaction per pass, only when `lcd_blit_busy()` is already false**, and never calls the blit-draining `rtc_bus_guard()`. A busy pass is skipped. True worst case per transaction: the I2C driver timeout, **20 ms, reachable only on a hung/absent bus**; after 3 consecutive timeouts the task backs off to one attempt/min and sets a health flag. No spin-waits anywhere; sub-second timing is done by the RTC prescaler or by deferred compares. The HID handler does *less* blocking than today. The legacy `0x01` path and the unchanged legacy PCF trim keep today's synchronous, bus-guarded transactions — pre-existing, once per 60 s / per sync, not new. |
| C3 | **No new internal-flash writes.** | Only the existing coalesced period persist (`kb_eeconfig`, ≥ 10 min uptime), with its change threshold raised 32 → **64** ticks so it fires *less* often. Nothing else is persisted. |

Every phase is gated on existing instruments (§6): `loop_gap_max_ms`
unchanged, instrumented `[stall]` count not increased, `scan_rate` in
band, `blit_timeouts == 0`, BT `tx_timeouts/tx_sent` unchanged,
`scripts/soak.py` green, real typing.

## 1. What is wrong today (measured 2026-09-01)

1. **Rate.** Board vs host, edge-sampled: 12:02–12:04 falling behind
   **6.2 ms/s**; 12:11–12:13 3.8 ms/s; peer cross-check −4100 ppm — the
   trim re-converging after the 11:58 reflash erased the persisted period.
   It needs ≥ 300 s windows, resolves ±3000 ppm per estimate (1 s reference
   quantisation), half-steps, so re-convergence takes hours with a visible
   2 s step-snap at each deadband crossing; restarts on any ILRC
   temperature excursion (RC oscillator, ~0.1–0.3 %/°C).
2. **Phase.** `rtc_lld_set_time` writes only the software seconds; `SECCNT`
   keeps counting, so every set leaves a phase uniform on [0, 1) s. Every
   trim rewrites `SECCNTV`, which resets `SECCNT` (DS §12.5.6) and discards
   the elapsed fraction of the current second (mean 0.5 s).
3. **Reference.** The PCF is read at 1 s resolution with a ±2 s deadband —
   a ±2 s floor even when converged — plus 58 ppm between 3 h host syncs.
4. **Display lag.** The clock repaint is triggered from the **10 Hz**
   housekeeping block when `rtc_get_seconds()` changes
   (`display.c:1629–1639`) — digits change 0–100 ms after the tick.
   Fixed in §3.9.

USB latency is *not* the problem, but it is *measured* (T0.7), not assumed.

## 2. Hardware facts the design rests on

**[HW-VERIFY]** items must pass in Phase 0 before anything depends on them.

| Fact | Source |
|---|---|
| SN32 RTC: 20-bit reload `SECCNTV` (R/W), 32-bit live count `SECCNT` (R only), `SECIF` at `SEC_CNT == SECCNTV`; period = `P+1` cycles. `SECIF` is a flag, not a counter: missed matches are not counted. | SN32F299 DS §12.3.3–12.3.4, §12.5.4–7; `SN32F290.h:2864–2912` |
| Writing `SECCNTV` resets `SECCNT` (0 → 0x8000 by hardware). `rtc_lld_set_period()` clamps > 0xFFFFF silently — a wrapped unsigned value becomes a ~31 s period. **[T0.1: same-value write resets? latency ≤ 1 cycle?]** | DS §12.5.6; `hal_rtc_lld.c:267–279` |
| `RTCEN` 0→1 also resets `SEC_CNT` (fallback re-phase). | DS §12.5.1 |
| ILRC on this unit ≈ 33.6 kHz → 1 cycle ≈ 30 µs. `rtc_init` clamps the period to 28000..40000. | CLAUDE.md, `rtc.c` |
| Patched LLD: absolute time is a software `time_t` bumped in the SECIF ISR (which clears `SECIF` first); `rtcSetTime` writes only that; `rtcSetTime`/`rtcGetTime` are unlocked wrappers around X-class LLD calls (safe under `chSysLock` or in an ISR). `rtc_lld_set_period()` writes `SECCNTV` **and** caches it in `RTCD1.period` under an X-class lock. | `hal_rtc_lld.c:110–124, 185–193, 267–301`; `hal_rtc.c:108–134` |
| `SN_USB->FRMNO`: 11-bit frame number of the last SOF (1.000 ms frames). Header proves the register, not its behaviour with SOF IRQ disabled or per slider/power state. **[T0.3]** | `SN32F290.h:4653–4659` |
| QMK's `usbcfg` has no `sof_cb`; the LLD disables the SOF interrupt; kept disabled. | `usb_main.c:320–324`; `hal_usb_lld.c:303–314, 480–484` |
| `usbGetDriverStateI()` is an I-class macro: valid from thread context under `chSysLock()`. | `hal_usb.h:389` |
| USB IRQ priority 1 (== UART2); no USB ISR work is added. | `hal_usb_lld.h:76–77`, `mcuconf.h:78–89` |
| PCF8563: no sub-second register. `STOP` = Control_status_1 bit 5; holds prescaler F2..F14 in reset; first increment **0.507813–0.507935 s** after release. Time-register writes do not reset the prescaler. Control_status_1 also carries TEST1 (7), TESTC (3): read-modify-write only. **[T0.5 on the CHMC D8563F clone]** | PCF8563 DS §8.3.1, §8.10, Table 26 |
| PCF CLKOUT/INT not wired (bit-banged I2C, A14/A15). | handoff, wiring, `rtc.c` |
| Bit-banged I2C shares port A with flash SPI1; `rtc_bus_guard()` **blocks** in `lcd_blit_wait()` (a full transfer, or up to the 250 ms recovery bound). I2C driver timeout 20 ms/transaction. Successful 1-byte read expected ~100–200 µs. **[T0.4]** | `rtc.c:24–27, 101–109`; `lcd_bus.c:628–695` |
| `housekeeping_task_kb()`: per-iteration section (`health_loop_tick`, `rgb_repeat_task`, `display_blit_pump`), then the 10 Hz block (`rtc_task`, `display_housekeeping_task`, eeconfig, health), then `watchdog_kick()`. Main loop ≈ 2.5 ms. | `ak820pro.c:434–475` |
| `display_housekeeping_task()` reaches the clock latch only after its user hook, pause/splash checks, and `gq_pending() == false`; the glyph queue is fixed-size and drops pushes when full. | `display.c:1395, 1605–1639` |
| Interrupts masked for each internal-flash *program* (ms), not erase. A masked SECIF is delayed, not lost — but hardware still resets `SECCNT` at the match, so software seconds and the hardware fraction disagree until the ISR runs (§3.1). | `PATCHES.md`, CLAUDE.md |
| QMK's ms timebase runs ~1.2 % slow under load; **never used for anything timing-critical here.** | CLAUDE.md |
| Flashing erases emulated EEPROM (persisted period lost); `flash.sh` does not resync. | `9d3316bd6d`, `flash.sh` |
| Raw-HID **replies** route through the active host driver: round-trips only in the wired position; write-only in any position with the cable in. `ak820ctl` reads 32 bytes, zero-pads requests; old firmware echoes the request, so unused reply bytes are **zero**. `hid_write()` returning means the host stack accepted the report, not that the device received it. | `host.c`, `ak820ctl.c:72–101`, `hid_protocol.c:283–290` |
| Existing `RTC_SET_TIME` validates all seven fields before writing. | `hid_protocol.c:22–50` |

## 3. Design

- **Host (Mac)** — truth (NTP). Supplies time with ms; measures offset;
  measures the SOF frequency bias and tells the board.
- **USB SOF (`FRMNO`)** — continuous **frequency** reference while the
  cable is in; never a time source (wraps every 2.048 s, no epoch).
- **PCF8563** — battery-backed **boot reference**; fallback frequency
  reference when unplugged; written with correct phase on host syncs.
- **SN32 RTC** — what the display reads. Frequency = `SECCNTV`; phase =
  reset of `SECCNT` with a computed first period; corrections = slew.

### 3.0 Ownership rules

- **R1.** Every reload write, any context, goes through
  `rtc_lld_set_period()` so `RTCD1.period` **always equals the live
  register** (the *active* period). `rtc.c` owns the *nominal* `P_nom`.
  `rtc_get_period()` returns `P_nom` (documented); `HC_RTC` reports both.
- **R2.** In steady state nothing writes the reload register. Writes happen
  only: at init; at a deliberate phase set (thread, §3.2); in the tick
  callback for restore, slew start/remainder/end, and trim application.
  **Any reload write invalidates the current estimator window** (§3.4).
- **R3.** ISR-context reload writes are **latency-compensated**: the
  callback reads `L = SECCNT` at entry (cycles since the match restarted
  the counter) and writes `target − L`, so the match-to-match interval is
  exactly `target+1` cycles. **Range rule:** if `L ≥ target/2` (service
  grossly late) compensation is abandoned — write `target`, mark the window
  invalid and any in-flight slew/restore "late" (it is re-planned from the
  next `rtc_now()`); every value handed to the LLD is range-checked first
  (never the LLD's silent 20-bit clamp), against the range appropriate to
  the write: **steady-state and slew values** must lie in
  `[14000, 80000]`; a **deliberate first period** from a phase set (§3.2)
  must lie in `[500, 0xFFFFF]` (500 cycles ≈ 15 ms; the `MIN_FIRST_MS`
  branch guarantees ≥ ~670 at nominal `P_nom`, and the extended branch can
  legitimately exceed 40000). The model test exercises every
  `ms = 0..999` at `P_nom` = 28000 and 40000.
- **R4.** `rtc_fast_task()` never blocks on the LCD: it checks
  `lcd_blit_busy()` itself and skips the pass if true; it never calls
  `rtc_bus_guard()`. It is the **only** place new PCF I2C happens, one
  transaction per pass at most.
- **R5.** From Phase 1 onward the HID handlers do arithmetic and SN32
  register work only; every PCF transaction they cause is queued to
  `rtc_fast_task()`.

### 3.1 Coherent sub-second read

`bool rtc_now(rtc_stamp_t *s)` → `{ time_t sec; uint32_t cnt; uint32_t
period_active; }`:

```
for (tries = 0; tries < 8; tries++) {
    c1  = rtc_seconds_count;                 // bumped in the tick ISR
    cnt = SN_RTC->SECCNT;
    pa  = RTCD1.period;                      // active register value (R1)
    pending = SN_RTC->RIS & mskRTC_SECIF;    // match happened, ISR not yet run
    rtcGetTime(&RTCD1, &dt);
    c2  = rtc_seconds_count;
    if (c1 == c2 && !pending) return true;   // consistent snapshot
}
stale_count++;  return false;                // ISR starved: NO timestamp
frac_ms = cnt * 1000 / (pa + 1);            // 32-bit safe: cnt < 2^20
```

Lock-free. The `pending` test closes the hole where hardware has already
reset `SECCNT` at the match but the ISR (delayed by a flash program or
higher-priority load) has not yet advanced the software second. On
failure **no time is returned** — `SECIF` cannot say how many matches were
missed — and every caller postpones its action to a later pass (a host set
is rejected with status 0xFE "retry"; the PCF machine and acquisition
simply try again next pass). `stale_count` is in `HC_RTC`; it must stay 0
in normal use (T0.6).

### 3.2 Phase-correct set

`rtc_set_time_ms(const rtc_time_t *t, uint16_t ms, int16_t sof_bias_ppm,
uint8_t flags)` — main-loop context — means "at the instant this packet
was received, true time was `t + ms`". Validated first (§3.7); if
`rtc_now()` fails, reject with "retry".

Let `R = 1000 − ms` (ms to the next boundary), `first = (P_nom+1)·R/1000`
cycles (64-bit intermediate).

```
sec = t;
if (R < MIN_FIRST_MS /*20*/) { sec = t + 1; first += P_nom + 1; }  // label the following boundary
chSysLock();
rtcSetTime(&RTCD1, sec);                     // software seconds
restore_pending = true;                      // tick ISR puts P_nom back (R3)
rtc_lld_set_period(&RTCD1, first - 1);       // resets SECCNT: next SECIF in R ms
chSysUnlock();
window_invalidate();                         // R2
if (!flags.skip_pcf) pcf_queue(sec);         // R5: the fast task does the I2C
```

Critical section ~2 µs. On the next tick the callback applies `P_nom`
under R3. Residual after a set: host one-way error (§3.8, calibrated) +
reset latency (T0.1) + ISR write jitter (T0.2) — expected ≈ 1–2 ms,
host-dominated.

**Legacy `RTC_SET_TIME (0x01)` is unchanged** (whole seconds via
`rtcSetTime`, phase untouched, today's synchronous PCF write). Only `0x03`
carries phase semantics.

**Step vs slew.** `offset = (t+ms) − rtc_now()` in ms. `|offset| ≤
SLEW_MAX_MS (500)` and not the first set since boot and not
`flags.force_step` → slew (§3.3); otherwise step as above. DST/TZ changes
(±3600 s) step by construction. `sof_bias_ppm` (if not the "unknown"
sentinel) is stored for §3.4.

### 3.3 Slew

With `Δ` = offset in cycles (`offset_ms · (P_nom+1) / 1000`, 64-bit):

```
N = max(1, ceil(|Δ| / SLEW_STEP));   SLEW_STEP = (P_nom+1) * 20 / 1000   // 2 %, 20 ms/s
d = Δ / N  (integer, toward zero);   r = Δ − N·d  (|r| < N)
```

Reload writes, all ISR-context under R3, each invalidating the window (R2):

1. tick 0: `P_nom − d` (shorter period ⇒ clock advances; `d` may be
   negative) — held for the next `N−1` intervals;
2. tick `N−1`: `P_nom − d − r` for the final interval (only if `r ≠ 0`);
3. tick `N`: `P_nom`.

So **two writes when `r = 0`, three otherwise**, and the correction is
exact to one cycle. Register-value check: a period shortened by `d` cycles
is `P_nom+1−d` cycles, register `P_nom − d`. 500 ms completes in 25 s at
≤ 20 ms per boundary — invisible. Required unit tests (host-side model of
the tick sequence, no MCU): `N = 1` with `r = 0`; `Δ = ±1`; `Δ = ±SLEW_STEP`;
`Δ = ±(SLEW_STEP+1)` (forces `N = 2, r ≠ 0`); `Δ` negative with negative
`r`; a new offset arriving at tick `N−1`. A new host offset mid-slew
supersedes: remaining `Δ` is re-planned from the fresh measurement; the
reply flags say "slewing".

### 3.4 Frequency discipline

**Reference-source state machine.** Evaluated in the 10 Hz block from
values the ISR left; probes are performed by `rtc_fast_task()` (R4).

| State | Enter when | `P_nom` proposed by | Leave when |
|---|---|---|---|
| `SOF` | `usb_active` **and** 3 consecutive accepted `FRMNO` samples | FRMNO estimator | 3 consecutive rejected samples **or** `usb_active` false → `PCF_LEGACY` (always; if the PCF is dead, `PCF_LEGACY`'s own counter moves on to `NONE`). Exit action: discard the SOF window, invalidate `fn_valid`, cancel any pending `P_target`. |
| `PCF_LEGACY` | default at boot; from `SOF` on exit; from `NONE` after 1 successful probe | the legacy trim: `rtc_clock_discipline()` with its **estimator arithmetic and cadence unchanged**, but its result re-routed — it computes a `P_target` that the tick callback applies under R3, instead of calling `rtc_lld_set_period()` mid-second as today (that direct call resets `SECCNT` and is exactly the phase loss Phase 1 removes). Its ±2 s `rtcSetTime` snap stays as-is until Phase 4 replaces it with a slew. Its measurement span is invalidated by any external reload (R2), same as the SOF window. | `SOF` entry condition → `SOF` (PCF span reset); `pcf_avail_fail ≥ 3` → `NONE`. |
| `NONE` | `pcf_avail_fail ≥ 3` and no SOF | nobody; `P_nom` holds | `SOF` entry condition → `SOF`; one successful PCF probe (a 1-byte read/min from `rtc_fast_task`, bus-idle gated) → `PCF_LEGACY`. |

Exactly one estimator proposes `P_nom` at a time; a proposal is applied at
the next tick under R2/R3. Every transition cancels a pending proposal and
resets the incoming estimator's window/span. `ref_state` and the
transition count are in `HC_RTC`.

**Failure counters (definitions).** `pcf_avail_fail`: consecutive failed
PCF *reads* (I2C error or `VL` set) across the trim, probes, and
acquisition; reset to 0 by any successful PCF read; saturates at 255. The
host-sync PCF *write* machine (§3.5) has its own per-run retry handling
and feeds `pcf_avail_fail` only through its read steps. All counters live
in `rtc.c`, are updated in thread context only, and are visible in
`HC_RTC` page 2.

**FRMNO estimator.** In the tick callback (ISR):

```
L    = SN_RTC->SECCNT;                       // service latency, cycles
ua   = usb_active;                           // volatile uint8_t, read ONCE, before touching SN_USB
if (!ua) { if (fn_valid) sof_epoch++;  fn_valid = false; win_valid = false; }
else {
    fn = SN_USB->FRMNO & 0x7FF;
    d  = fn_valid ? ((fn - fn_last) & 0x7FF) : 0;  fn_last = fn;  fn_valid = true;
    if (d) sof_frames_total += d;                  // CONTINUOUS: counts whether or not ok
    ok = (900 <= d && d <= 1100) && (L < LATE_CYCLES /* ≈ 5 ms of cycles, from T0.2 */);
    if (ok) { win_ms += d; win_cycles += period_used + 1; win_n++; }
    else    { win_valid = false;
              if (d < 900 || d > 1100) sof_epoch++; }   // continuity itself is suspect
}
```

`sof_frames_total` (u32) accumulates **every** delta while USB continuity
holds — estimator-window rejection does not gate it, because the host
divides its change by wall-clock time and a silently missing second would
bias the result by ~1700 ppm. `sof_epoch` (u8, wraps) increments whenever
continuity breaks: `usb_active` dropping, or a delta outside [900, 1100]
(which means frames were missed or aliased, so the accumulated count can
no longer be trusted as "all elapsed frames"). The host uses an interval
only if `sof_epoch` is identical at both ends and the interval is < 24 h
(u32 at 1 kHz wraps in 49.7 days; 24 h gives huge margin), computing
`F = (uint32_t)(end − start)`.

`period_used` = `RTCD1.period` during the interval just ended (captured
before any write this tick). `usb_active` is a `volatile uint8_t` set in
the 10 Hz block from `usbGetDriverStateI(&USBD1) == USB_ACTIVE` under a
short `chSysLock`; the callback reads it once and never touches `SN_USB`
when it is false. Any reload write this tick also clears `win_valid` (R2).
`sof_frames_total` (u32, wraps) is the host's raw material for the bias
measurement below.

Every `WIN_S` valid samples (32 initially, 128 once |P_target − P_nom| <
16 for two windows), in housekeeping:

```
f_est    = win_cycles * 1000 / win_ms                    // uint64 → Hz, assumes 1.000 ms frames
f_true   = f_est * (1 + b)                               // b = SOF bias, below
P_target = round(f_true) − 1;  reject unless 28000 ≤ P_target ≤ 40000
P_nom   += (P_target − P_nom) / 2                         // damped; applied at next tick
```

Resolution: `FRMNO` quantises at 1 ms ⇒ ±31 ppm at 32 s, ±8 ppm at 128 s;
loop constant 1–2 windows; ILRC temperature wander is minutes-scale, so
tracking error is tens of ppm ⇒ a few ms between host syncs.

**SOF bias `b` — measured by the host, not inferred by the board.** USB 2.0
allows ±500 ppm on the frame period; a given controller is stable to ~ppm.
Define, over a wired interval of host wall-clock length `H` seconds during
which the board's `sof_frames_total` advanced by `F` frames:
`b = F / (1000·H) − 1` (positive ⇒ the controller emits frames faster than
1 kHz ⇒ `win_ms` over-counts true time ⇒ `f_est` is low ⇒ multiply up —
consistent with `f_true = f_est·(1+b)`). The host samples
`sof_frames_total` **and the full 8-bit `sof_epoch`** in each `GET`
(`[28..31]` and `[27]` — the complete byte, not a truncation: a mod-8
exposure would alias as "unchanged" after exactly eight continuity breaks
and admit a corrupted interval), keeps the first and latest sample with an
identical epoch byte, discards the pair and restarts on any epoch change
or controller-ID change, and
once `H ≥ 600 s` (uncertainty ±2 ms/600 s ≈ ±3 ppm) sends `b_ppm` in
every `0x03` (`[13..14]`, s16; `0x7FFF` = unknown). Cached in `~/.ak820ctl-cap` keyed by the USB host-controller
location ID (`IORegistry` `locationID` of the device's parent), so a dock
or hub change re-measures rather than reusing a stale value. The board
uses the last received `b`, 0 until told. T0.8 is this measurement done by
hand before Phase 2.

**Persistence.** Unchanged mechanism; threshold 32 → **64** ticks
everywhere. The persisted value is only a boot seed; in `SOF` the loop
overtakes it within ~1 minute.

### 3.5 PCF8563 phase-correct write — deferred state machine (Phase 3)

Owned by `rtc_fast_task()` (R4/R5). Armed by `pcf_queue()` from a `0x03`
set. **Six single-transaction states**, each attempted only when
`lcd_blit_busy()` is false, else retried next pass:

| State | One transaction | Next |
|---|---|---|
| `STOP_READ` | read Control_status_1 (1 B) → `ctl` | `STOP_WRITE` |
| `STOP_WRITE` | write `ctl | 0x20` (1 B) | compute `S` = next whole second per `rtc_now()` (if it fails: stay, retry), `T_rel = boundary(S) − D_first` (`D_first` from T0.5; datasheet 0.5078 s). If `T_rel` < 5 ms away use `S+1`. → `TIME_WRITE` |
| `TIME_WRITE` | write 7 time registers for `S` (8 B); calendar from `localtime_r(S)` (rollover-safe) | `RELEASE_READ` |
| `RELEASE_READ` | when `rtc_now() ≥ T_rel − 3 ms`: read Control_status_1 → `ctl` | `RELEASE_WRITE` |
| `RELEASE_WRITE` | **re-check `rtc_now()` immediately before the write**: if `> T_rel + 10 ms` (a busy pass delayed us) → back to `STOP_READ` with a recomputed later `S` (the registers still hold the old `S`; a deadline-only re-arm would leave the PCF one second slow). Else write `ctl & ~0x20` (1 B); stamp `rtc_now()` after. | `VERIFY` |
| `VERIFY` | read Control_status_1: STOP clear, TEST bits as read | done; `pcf_release_err_ms` = post-stamp − `T_rel` → `HC_RTC` |

A successful run is **six transactions**, ~100–500 µs each, spread over
≥ 0.5 s, never overlapping a blit; retries are unbounded in passes but
bounded to one transaction per pass. A new `pcf_queue()` while running
restarts from `STOP_READ`.

**STOP must never be left asserted.** `stop_asserted` is set true after a
successful `STOP_WRITE` and false after a successful release. If any
later transaction fails repeatedly (≥ 5 attempts) or the run is aborted
for any reason while `stop_asserted`, the machine enters **`RECOVER_STOP`**:
a single-transaction write of the preserved control byte with bit 5
cleared, retried at the back-off cadence **indefinitely** — the machine
cannot idle, and `NONE`/back-off cannot be entered, while `stop_asserted`
is true. Until recovery succeeds the health flag "PCF possibly stopped"
(HC_RTC page 2) is set; a frozen battery-backed reference is worse than a
missing one and must be loudly visible. Fault-injection tests: see the
three-scenario matrix in §6 (transient ⇒ retry only; five consecutive ⇒
`RECOVER_STOP`; abort while `stop_asserted` ⇒ recover first).

**Phase 1 interim:** `pcf_queue(sec)` performs today's 8-byte time write
as a single deferred transaction from the same task (no STOP) — R5 holds
from Phase 1; only the phase-correctness of the PCF arrives in Phase 3.

### 3.6 Boot phase acquisition (Phase 3) and edge bracketing (Phase 4)

**Boot.** `rtc_init` still seeds whole seconds immediately. Acquisition
starts after `display_splash_done()`, in `rtc_fast_task()`:

1. *Coarse:* one **1-byte** read of the PCF seconds register every 4th
   pass (~10 ms), skipping busy passes, until the byte changes; both the
   previous and the detecting read are stamped with `rtc_now()`. Edge
   estimate = **midpoint**, uncertainty = half the gap (≤ ~5 ms; larger if
   busy passes stretched it — then the fine step is mandatory). Load:
   ≤ 100 reads × ~150 µs over ≤ 1 s ≈ 1.5 %, in ≤ 200 µs slices. Abort at
   1.5 s without an edge (PCF absent/`VL`) — stays whole-second-seeded.
2. Immediately: a full 7-byte read, then a 1-byte seconds re-read; if the
   two seconds bytes differ (rollover raced) repeat. `rtc_set_time_ms(
   pcf_time, ms = rtc_now() − edge_midpoint, step)`.
3. *Fine (same task, next second):* around the predicted next edge, read
   every pass from −15 ms to +15 ms (≤ 12 reads); midpoint of the two
   bracketing reads → ±~1.5 ms; applied as a slew.

A host sync during acquisition cancels it (host outranks PCF).

**Bracketing while unplugged (Phase 4).** The fine step once per
`RTC_CHECK_INTERVAL_S` (60 s) in `PCF_LEGACY`: ≤ 12 reads/min replaces the
one 7-byte read, giving ±1.5 ms phase samples so the fallback trim
converges in one window and the ±2 s snap becomes a slew.

### 3.7 Protocol (raw HID, RTC channel 0x10)

VIA custom-value framing `[0x07, 0x10, cmd, ...]`, 32-byte reports, replies
echo the buffer. Existing commands byte-compatible.

| cmd | dir | payload / reply |
|---|---|---|
| `0x01 RTC_SET_TIME` | H→B | unchanged, behaviour unchanged. |
| `0x02 RTC_GET_TIME` | H→B | reply `[3]=ok [4..10] time` (unchanged) + **`[11] RTC_PROTO_VERSION = 2`** (old firmware echoes 0), `[12..15] cnt u32 LE`, `[16..17] period_active u16`, `[18..19] period_nominal u16`, `[20] flags`, `[21..22] last_host_offset_ms s16`, `[23..24] sof_bias_ppm_in_use s16`, `[25] ref_state (0 NONE, 1 PCF_LEGACY, 2 SOF)`, `[26] sync_age_min u8 (255 never)`, **`[27] sof_epoch u8`** (full byte; `pcf_release_err_ms` is reported via `HC_RTC` page 2 only), **`[28..31] sof_frames_total u32 LE`**. `flags`: b0 synced-since-boot, b1 slewing, b2 boot-acquisition done, b3 PCF I2C backed off, b4 stale_count > 0, b5..b7 reserved (zero). |
| `0x03 RTC_SET_TIME_MS` | H→B | `[3..9] yy mm dd wd hh mi ss`, `[10..11] ms u16 LE`, `[12] flags` (b0 force step, b1 skip PCF, b2..7 zero), `[13..14] sof_bias_ppm s16 (0x7FFF unknown)`. Reply `[3]` = 0 stepped / 1 slewing / 0xFE retry (`rtc_now` stale) / 0xFF rejected; `[4..5]` offset before correction, s16 ms clamped; **`[11] RTC_PROTO_VERSION`** (same offset as `GET`). |

Health: **`HC_RTC 0x03`** on channel 0x13 returns `[11..31]` identical to
`GET` plus `stale_count`, `i2c_timeouts`, `deferred_passes`,
`max_transaction_cycles`, `window_rejects`, `ref_transitions` in a second
report (`HC_RTC` with `[3] = page`). (BT position: no reply; counters
accumulate.)

Validation before any write: `ms ≤ 999`; reserved flag bits zero;
`sof_bias_ppm` in ±600 or the sentinel; month 1..12; day valid for
month/leap year; hour/min/sec ranges; weekday 0..6; **year 2026..2098**
(the PCF stores `year % 100`; 2098 leaves the `t+1` branch representable).
The `sec = t + 1` result of the `MIN_FIRST_MS` branch is validated after
the increment (a set at `2098-12-31 23:59:59.99x` is rejected, not
wrapped), and `mktime`/`localtime_r` failures reject the packet.

**Host-side version rule:** a reply is "new firmware" only if `[11] == 2`
exactly; 0 ⇒ legacy path; any other value ⇒ refuse to act and print it.
`[3]` is checked independently (clock validity), never used for version.

### 3.8 Host side

**Measuring offset (`ak820ctl clock`, wired).** For `i` in 1..5:
`t_send_i = clock_gettime` immediately before `hid_write(GET)`; `t_recv_i`
after `hid_read`; reply → board time `B_i` (sec + `cnt/(period_active+1)`).
With T3 = T2: `offset_i = B_i − (t_send_i + t_recv_i)/2`, `rtt_i = t_recv_i
− t_send_i`. Keep the min-RTT sample; uncertainty `U ≈ (rtt_max − rtt_min)/2
+ 0.5 ms`.

**Setting.** `hid_write()` returning proves host-side submission only, so
outbound delay is **calibrated, not assumed**. Signs first, explicitly:
the `GET` measurement is `o = B − H` (board minus host; negative = board
behind). The `0x03` payload carries target time `H_enc + lead_ms`
(`H_enc = clock_gettime` immediately before encoding; encoding is µs).
The firmware's reply field is `o′ = offset_before = target −
board_at_receipt`. Board time at receipt is `H_enc + delay + o` (host
time then, plus the board's offset), so

```
o′ = (H_enc + lead) − (H_enc + delay + o) = lead − delay − o
e  = o′ + o = lead − delay          → update:  lead_ms −= e/4,  clamp to [0, 10] ms
```

which converges on the true mean outbound `delay` (negative feedback; the
round-2/round-3 versions of this formula were wrong — this one is the
reviewed fix). Samples are excluded when the reply is `0xFE` (stale) or
the preceding `GET` was flagged slewing. Bootstrap `lead_ms = rtt/2`.
T0.7 measures the spread of `delay`; that spread is the floor on U. After
the set, one more `GET` → print `before / after / rtt / U / lead / flags /
ref_state / b_ppm`; an after-offset outside 3U prints a warning (a slew in
progress is reported as such).

**Fallback.** `GET[11] == 0` ⇒ legacy `0x01`, boundary-aligned as today.
`clock` writes `~/.ak820ctl-cap` (`{proto, lead_ms, controller_id, b_ppm,
b_H_s}`) after every wired run.

**`--no-wait` (any position, cable in).** Reads the cache: proto 2 ⇒ one
`0x03` with `t_enc + lead_ms` and the cached `b_ppm`; else one aligned
`0x01`. Never both. Logs the attempt only (no measurement is possible).

**`hostagent/ak820-timekeeper.py`** (persistent LaunchAgent, `KeepAlive`,
replacing the `clocksync` pair): loop every 15 s — `hid.enumerate` the raw
interface; sync on (re)appearance, on a loop wall-clock gap > 60 s (Mac
slept), and every 10 min (5 if T0.8 gives |b| > 200 ppm). Wired ⇒ full
measure/set; wireless ⇒ `--no-wait` (detected by a `GET` timing out
once). Appends `ts, mode, before, after, rtt, U, lead, b_ppm, ref_state,
flags` (wireless rows carry `mode=send-only` and no measurements) to
`~/Library/Logs/ak820pro-clocksync.log`. Opens the device per transaction,
retries on `exclusive access`, never holds it.

**`flash.sh`:** after the keymap restore, run `ak820ctl clock` and print
the result.

**`clock-phase.py` / `clock-error.sh`:** default to `cnt` (one round trip
per sample); `--edge` keeps the increment-hunting method as an independent
cross-check. Unwrap at ±500 ms before fitting slopes.

### 3.9 Display latency

Do **not** move the repaint. Add `display_second_edge_task()` to the
per-iteration section: `if (rtc_get_seconds() != edge_seen) { edge_seen =
…; display_housekeeping_task(); }` — i.e. on an RTC edge, run one *extra*
pass of the existing, fully gated 10 Hz display task (user hook,
pause/splash checks, `gq_pending()` gate, `last_shown_sec` latch all
intact). The 10 Hz pass that follows finds nothing to do. Digits then
change within one main-loop pass (~2.5 ms) of the tick plus one glyph
blit, instead of 0–100 ms. Verify: an edge during a full text/playback
repaint (queue busy) must defer, not drop — `gq_pending()` already gates
this; `blit_timeouts` stays 0; `scan_rate` unchanged.

## 4. Code map

| Area | File | Change |
|---|---|---|
| Firmware core | `rtc/rtc.c`, `rtc.h` | `rtc_now()`, `rtc_set_time_ms()`, tick-callback state (restore, slew schedule, FRMNO sample, `L`, `sof_frames_total`), reference-source state machine with counters, FRMNO estimator (64-bit), `rtc_fast_task()` (deferred PCF write → Phase 3 STOP machine, boot acquisition, `NONE` probe, Phase 4 bracketing), `rtc_status()` for HID/health, I2C timeout back-off and counters. `rtc_clock_discipline()`: **estimator equations and cadence retained; its direct mid-second `rtc_lld_set_period()` call is removed** — it emits a `P_target` that the tick callback applies (Phase 1). |
| Firmware glue | `ak820pro.c` | `rtc_fast_task()` and `display_second_edge_task()` **before** `display_blit_pump()`; `usb_active` mirror update in the 10 Hz block. |
| Display | `graphics/display.c/.h` | `display_second_edge_task()` (calls the existing task), `display_splash_done()`. |
| Protocol | `hid_protocol.c` | `RTC_SET_TIME_MS`, extended `GET`, `HC_RTC` (two pages), validation, version byte. |
| Persist | `rtc.c:433–436` | threshold 32 → 64. No layout change. |
| ChibiOS | **none** | registers via the header; reload writes via `rtc_lld_set_period()`; `RTCEN` fallback register-level. No `PATCHES.md` change. |
| Host | `ak820ctl.c`, `ak820-timekeeper.py` + plist (retiring `ak820-clocksync.sh` + its plist), `flash.sh`, `clock-phase.py`, `clock-error.sh`, `ak820health.py`; a host-side model test of the tick/slew sequence (`tests/rtc_model_test.py`) | §3.3 tests, §3.8, `HC_RTC` decode. |
| Docs | board `readme.md`, `docs/clock.md`, `history/hardening-plan/HARDWARE-CHECKLIST.md`, `BACKLOG.md` | supersede "±2 s is the design bound", "~1 s is the hard floor", "3 h resync"; add Phase 0 constants. |

Instrumented flavor extras: `[rtc]` lines for window results, slew events,
steps, PCF/ref-state transitions, acquisition, I2C timeouts; `HC_DRIVE`
ops to force a step, a slew of N ms, a fake host offset, an I2C fault;
`HC_RTCTEST` (Phase 0 only) for T0.1–T0.5 — these **deliberately mutate**
the RTC (reload writes, phase resets) and restore `P_nom` and phase
afterwards.

## 5. Phases (one flash each; each shippable alone)

### Phase 0 — instruments and hardware facts

Deliverables are new code (extended `GET`, `HC_RTC`, `HC_RTCTEST`,
`clock-phase.py --cnt`). `HC_RTCTEST` is **not** behaviour-neutral while
invoked: the §6 baseline gate runs **before and after** each test
invocation, never during. Steady-state behaviour of the Phase 0 build is
otherwise unchanged.

- **T0.1 `SECCNTV` reset.** Read `SECCNT` (large); write `SECCNTV` = same;
  read again (expect ≤ 2). Repeat with ±1. Decide same-value vs `RTCEN`.
- **T0.2 Tick ISR latency `L`.** Min/mean/max at callback entry over 60
  ticks under idle, RGB animation, BT burst, forced flash program. Sets
  `LATE_CYCLES`; confirms R3 jitter.
- **T0.3 `FRMNO`.** Per-tick deltas 60 s in each slider position, cable
  in; Mac asleep, board plugged; cable out (does the read fault when USB is
  unclocked? the design already gates on `usb_active`; if it faults even
  then, add a clock-gate check).
- **T0.4 PCF I2C cost.** `SECCNT` around a 1-byte read and an 8-byte
  write, bus idle (and once with a blit in flight, to size the hazard the
  design avoids).
- **T0.5 PCF STOP on the clone.** STOP, write, release at a stamped
  instant, bracket the next increment: release-to-first-increment ×5 →
  `D_first`. If STOP is inert: §3.5 degrades to a boundary-timed write;
  §3.6 still yields correct *board* phase each boot; note the loss.
- **T0.6 Coherent read.** `rtc_now()` vs `--edge` within 3 ms; `stale_count`
  stays 0 in normal use; correct across a forced flash program.
- **T0.7 HID timing.** 100 `GET`s idle and 100 under typing: RTT
  min/median/p99; then 20 `SET`s with `lead = rtt/2` and the reply's
  `offset_before` vs the preceding `GET` → outbound-lead mean and spread.
  **This table defines U** and every accuracy claim in §0.
- **T0.8 This Mac's SOF bias.** `sof_frames_total` vs host wall clock over
  10 min ⇒ `b_ppm` and its uncertainty. Expected tens of ppm.
- **T0.9 Console in the BT position.** Does the instrumented `[health]`
  line reach `qmk console` with the slider in BT, cable in? If not, the
  backlogged on-LCD health snapshot becomes a Phase 2 prerequisite.

Exit: `history/clock-sync-plan/phase-0-facts.md` with every number. Gate: §6
baseline unchanged outside test invocations.

### Phase 1 — phase-correct set, no phase loss, deferred PCF write, display edge

`rtc_now()`, `rtc_set_time_ms()` + `0x03`, R1–R5 (`pcf_queue()` with the
interim single deferred write), §3.9 edge task, `ak820ctl clock`
measure/set path with lead calibration and capability cache, `flash.sh`
post-flash sync. The frequency loop is still the PCF trim — with its
**estimator arithmetic unchanged but its result re-routed** through the
tick-applied `P_target` path (that re-route IS the "no phase loss on
trim"; the function is deliberately not byte-for-byte after this phase).
Model test for §3.3/R3 lands here even though slew ships in Phase 2 (the
tick sequencing is shared with restore).

Exit: after `ak820ctl clock`, |offset| ≤ 3U across 10 syncs; an `[rtc]
trim` moves phase < 1 ms (`--edge` before/after); digits change within
5 ms of the tick (240 fps phone video of panel + a `GET`-synchronised
host stopwatch, or the instrumented `[rtc] edge→blit` stamp — state
which); `HC_RTC` `deferred_passes` > 0 and `i2c_timeouts == 0` after 20
syncs (proves the deferral path runs and never hangs).

### Phase 2 — SOF frequency discipline, slew, bias, agent

§3.4 (state machine, FRMNO estimator, host-measured bias), §3.3 slew,
step/slew decision, persistence threshold 64, `ak820-timekeeper.py`.
Fallback = the Phase 1 re-routed trim (arithmetic unchanged since today).

Exit: cold boot + one sync ⇒ over 24 h wired, a **30 s-cadence**
`clock-phase.py --cnt` sampler (not the 10-min agent log — 10-min samples
cannot establish an "at all times" bound) shows |offset| ≤ 20 ms at every
sample, and the logged window data implies a between-sample excursion
bound consistent with that; BT position with cable in for 8 h: **evidence is (a) the
send-only log, (b) the instrumented console `[rtc]`/`[health]` lines if
T0.9 passed — else the on-LCD snapshot — sampled during the run, and (c)
one wired read at the end (final phase only; the flip reboots)**; no
`[rtc] corrected drift` steps after the first sync; a forced 400 ms slew
(`HC_DRIVE`) invisible on the panel; §6 in full.

### Phase 3 — PCF phase: STOP state machine + boot acquisition

§3.5 six-state machine, §3.6 coarse+fine boot path,
`display_splash_done()`.

Exit (separately): (a) BT→cable flip reboot with NO host sync since boot
⇒ first `GET` |offset| ≤ 20 ms, flags b0 clear / b2 set, ×10; (b)
`pcf_release_err_ms` within ±10 ms ×10 syncs; (c) 8 h unplugged (BT,
cable out) ⇒ |offset| ≤ 58 ppm × 8 h + 0.3 s = 1.97 s on reconnect, slews
to < 20 ms within 2 min; (d) §6 with a keystroke burst in the first second
after a flip (acquisition active).

### Phase 4 — decided from data

- Unplugged bracketing + slew in `PCF_LEGACY` (replaces the ±2 s snap).
- Sync-status indicator on the panel (BT diagnostics backlog).
- Retire `RTC_PERIOD_INITIAL` (keep the clamp).
- Cadence downward if the logged between-sync error says so.

## 6. Verification

| Check | Tool | Pass |
|---|---|---|
| Main-loop worst gap | `ak820health.py` `loop_gap_max_ms` | unchanged vs same-flavor baseline (daily: 14 ms) |
| Stall **count** and attribution | instrumented `[stall]` (≥ 4 ms, attributed flash/blit/i2c) over 10 min typing | count not above baseline; zero attributed to the new I2C path |
| Scan rate | `scan_rate` | in flavor band (daily ~375, instrumented ~230–310) |
| LCD DMA | `blit_timeouts` | 0 |
| BT link | `tx_timeouts / tx_sent` over ≥ 300 frames | ≤ 0.05 (baseline 0.042); `tx_drops` 0 |
| Keystrokes | `scripts/soak.py` + 10 min real typing wired and BT | no drops, stuck keys, double-fires |
| Watchdog | `wdt_fired_last_boot` | false after every test |
| Hang class | VIA key assignment ×20 during a slew, during acquisition, during a PCF run | no hang |
| Provisioning | `ak820ctl flash crc` during a slew | unaffected |
| RTC internals | `HC_RTC` page 2: `stale_count`, `i2c_timeouts`, `deferred_passes`, `max_transaction_cycles`, `window_rejects`, `ref_transitions` | stale 0; timeouts 0; max transaction ≤ T0.4; rejects only at documented events |
| Model | `tests/rtc_model_test.py` (§3.3 cases; R3 range rule; `MIN_FIRST_MS` branch; every `ms` 0..999 at `P_nom` 28000 and 40000; lead-calibration convergence from lead errors of ±5 ms) | all pass, run in CI-less `make test` |
| PCF fault injection | instrumented `HC_DRIVE` I2C-fault op, three scenarios per post-STOP state: (a) one transient failure — expect a plain retry, `RECOVER_STOP` NOT entered; (b) **five consecutive failures** — expect `RECOVER_STOP` entered and STOP cleared; (c) an abort/new-`pcf_queue()` while `stop_asserted` — expect recovery before the restart | machine never idles or backs off with STOP set; "PCF possibly stopped" flag set exactly while unrecovered |
| Clock | `clock-phase.py`, timekeeper log | per-phase exit criteria |

Instruments that do not yet exist are Phase 0/1 deliverables validated
before use. Rollback: one commit per phase; `flash.sh` the previous
provenance-named binary.

## 7. Risks, open questions, acknowledged limitations

1. **T0.1 fails.** Fallback `RTCEN` 1→0→1; verify no pending `SECIF` is
   lost and the cost is ≤ 1 cycle.
2. **Clone ignores STOP** (T0.5). §3.5 degrades; board phase still correct
   via §3.6 whenever the PCF was written by a synced board. Conversely, if
   STOP works, a failure mid-sequence could freeze the PCF — handled by
   `RECOVER_STOP` (§3.5), which is why that state exists and is
   fault-injection tested.
3. **`FRMNO` faults when USB is unclocked** (T0.3). Design gates on
   `usb_active`; add a clock-gate check if that is insufficient.
4. **SOF bias changes** (dock/hub). Cache keyed by controller ID; the
   agent re-measures over the next 10 min; the sync cadence bounds the
   damage meanwhile.
5. **Acknowledged limitation — a tick callback delayed ≥ 2 s.** `SECCNT`
   restarts at every match, so `L` at entry measures only the delay since
   the *latest* match; a callback delayed by 2048 + d ms aliases through
   the 11-bit `FRMNO` and passes the [900, 1100] test. Such a delay
   requires interrupts masked for ≥ 2 s, which would also starve UART2 and
   USB — outside the operating envelope (flash programs are ms). The
   consequence, if it ever happened, is one wrong window (≤ ~2000 ppm for
   ≤ 128 s) and a phase error the next host sync steps out; `window_rejects`
   and the log would show it.
6. **Boot acquisition vs splash.** Starts only after
   `display_splash_done()`; still skips busy passes.
7. **Concurrent session** committing in `rtc.c`/`hid_protocol.c`/`health.c`.
   One owner of `rtc.c` per phase; shared-binary hazard on every flash.
8. **Estimator starvation** by frequent slews. Slews are ≤ 25 s per
   10 min; `window_rejects` makes starvation visible.
9. **Lead calibration converges on a biased host.** It only ever learns
   the mean outbound delay; asymmetric jitter stays in U, which T0.7
   quantifies.
10. **TZ/DST.** Board time = host local time, no TZ notion (unchanged);
    steps by design.
11. **Watchdog.** No new path holds the main loop > 20 ms even on a hung
    I2C bus, and that path backs off; `watchdog_kick()` unchanged.
12. **`time_t` width.** Check in Phase 0; a 32-bit `time_t` is a
    pre-existing 2038 issue, out of scope, noted.
