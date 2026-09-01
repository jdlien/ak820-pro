# Phase 2 — Targeted audits

**Theme:** find latent bugs in the three classes that have actually bitten,
before restructuring anything. Read-only until findings exist; each audit
produces a short findings file in this directory
(`findings-<audit>.md`) with per-item severity and a proposed fix, reviewed
before any code changes. Fixes land one per flash, gated by the phase-1 soak.

Scope: `keyboards/a_jazz/ak820pro/**` (including `rgb_matrix_kb.inc`, the
custom RAINFALL/DRIFT effects) plus the QMK-core edits (`sn32f2xx.c` now
carries four: periodticks, ISR hook, `SN32F2XX_RGB_PWM_FREQ`,
`sn32f2xx_blank()`) and the six ChibiOS patches. Upstream code beyond that is out of scope except where
a board file calls into it with assumptions worth checking.

## 2.1 Concurrency audit

Cortex-M0: no atomic read-modify-write instructions; aligned 32-bit loads
and stores are single-copy atomic; anything wider or read-modify-write needs
masking. Contexts that can interleave:

| Context | Rate | Owns |
|---|---|---|
| main loop / housekeeping | ~390 Hz | display state, eeconfig, raw HID, encoder |
| row ISR (`CT16B0/1/2`, prio 3) | ~18,800/s | LED frame copy, `sn32_rgb_isr_hook` |
| GPT tick (`CT16B3`, prio 2) | 20,000/s | backlight + indicator PWM |
| UART2 ISR (prio 1) | bursty | ChibiOS serial rx/tx byte queues ONLY |
| SPI0 DMA completion | per blit | `blit_done` |

Important correction to a naive reading: the UART2 ISR does **not** touch
`conn_state` or the CH582F pending flags — it feeds ChibiOS's serial queue;
frame parsing and every state transition run in `ch582_task()` on the main
loop. So the CH582F state is main-loop-only and needs no `volatile`/masking
against the ISR (adding it would obscure the real ownership). **Trace call
context for every variable rather than inferring it from the peripheral**,
and write the ownership model down as the audit's first deliverable:
"UART ISR owns RX/TX byte buffering; main loop owns parser, state, and the
frame-level TX queue." That document alone materially de-risks phase 3.2.

Method: for every `static` variable in the board files, determine which
contexts touch it; flag any that (a) is RMW'd from two contexts, (b) is
multi-word state read non-atomically across a writer, or (c) lacks
`volatile` where a context reads what another writes. The recent
"lock the LED frame copy against the row ISR" commit is exactly class (b)
found ad-hoc — sweep for its siblings deliberately.

Known items to re-verify rather than trust: `ind_*` flags (single-byte,
write-main/read-tick — fine, confirm), `blit_done` (volatile? cleared in
main, set in DMA callback), `display_*` dirty flags vs. the GPT tick,
`bt_pair_timer`/`bt_pair_armed` (process_record vs. housekeeping — same
context, confirm), the `[health]` counters added in phase 1, and the new
glyph-queue + panel-shadow state from the blit pump (believed main-loop-only
— confirm, and confirm the pump cannot arm a new blit inside the
`backing_store_pre_write_hook()` → flash-write window; both run on the main
loop, so this should hold by construction). Also verify `sn32f2xx_blank()`
vs. the driver's own teardown (the `SN32F2XX_RGB_OUTPUT_ACTIVE_LEVEL`
polarity issue it works around).

The custom effects' state (`rgb_matrix_kb.inc`: RAINFALL's 162 B, DRIFT's
accumulators and derived palette) runs in `rgb_matrix_task` on the main loop
— confirm nothing else touches it, and re-verify the two invariants their
commits established: the simulation steps on `params->iter == 0` only
(LED_PROCESS_LIMIT chunks a frame into 5 passes — stepping per chunk
quintuples the rate), and DRIFT's accumulators wrap on a whole number of
noise-table periods (uint32; the uint16 version jumped visibly). Also
confirm per-frame CPU cost under DRIFT/RAINFALL via the scan-rate band —
they are the newest per-frame code on a CPU-saturated board.

Also audit the **interrupt-masked flash-program window** (`efl_ramtext`):
confirm nothing added since assumes interrupts stay live during a write.

## 2.2 Bounded-wait audit

Every failure of the "crawl" class came from an unbounded or over-long wait
on hardware that can fail to signal. `lcd_blit_wait()` is the template: a
bound, a teardown that leaves the bus in a defined state, a counter, a
console line. Sweep every spin/wait in the board files and patches:

- **Bit-banged RTC I2C (A14/A15)** — prime suspect. What happens if the
  PCF8563 (or a glitched line — it shares port A with flash SPI1) holds SDA
  low? Is there a clock-stretch bound? An I2C hang on the 10 Hz tick is a
  100 ms-cadence stall of the whole housekeeping path. Check the
  `i2c_fallback` patch's loops too.
- **SPI FIFO pump / flash DMA paths** (`spi_fifo_pump`, `spi_flash_dma`
  patches): every `while (!flag)` gets a bound and a defined-state exit.
- **UART2 TX** (`ch582f_ajazz.c`): confirm the queue-full path drops with a
  counter rather than spinning (believed yes — `tx_stat_drop`).
- **`usb_wakeup_try`**, `pwm_tick_init`, anything in `early_hardware_init_post`.
- The animation player's waits (one was unbounded until 2026-08-30 — confirm
  no others remain in `lcd_bus.c`).

For each wait found: bound it, count it, and decide the recovery action
(teardown vs. skip vs. nothing-safe → let the phase-1 WDT catch it).

**2.2b Remaining blocking draw paths (stall budget).** The dropped-keystroke
cause is fixed for the text band (commits 6689927483/9dd6300e7b: per-glyph
blocking DMA waits → 53 ms scan holes; now a non-blocking glyph queue pumped
by `display_blit_pump()` at main-loop rate, plus cell diffing). But blocking
`lcd_draw_flash_text()` remains in the clock, battery %, conn digit, lock
labels, and playback paths. Per-change redraws are a few glyphs (cell-diffed
— fine); the suspects are **full repaints**: boot, overlay handback, lock
band appearing (~10 glyphs), `display_set_paused(false)`'s forced repaint.
Measure the worst case with the loop-gap counter; anything over ~10 ms
migrates to the glyph queue (the mechanism now exists and is cheap to feed).
Under-budget paths get a comment stating their measured cost so the next
band doesn't regress blindly.

## 2.3 Input-validation audit (`raw_hid_receive` and friends)

Host-controlled bytes parsed by firmware. Low likelihood, high consequence,
cheap to verify. Attack surface note: raw HID is reachable by any local
process with HID access — and in BT mode the CH582F relays from the paired
host — so "the host script is trusted" is not a full answer.

- **`flash_command` (0x11):** address/length validation on write and erase.
  Can a malformed packet program or erase below `FLASH_ASSET_BASE`
  (`ak820ctl` enforces `--unlock` host-side — does the firmware?)? Bounds on
  `fw_pg[256]` fill (`fw_fill` arithmetic); behaviour on out-of-order or
  duplicate packets; CRC command with pathological length (`crc_left`
  wraparound).
- **`text_command` (0x12):** length clamps vs. `DISPLAY_TEXT_MAX_L0/L1`
  (19/21); line index validation on `TEXT_SET_LINE`; icon id range;
  non-ASCII already maps to `?` — confirm for every entry path including
  `TEXT_PLAYBACK` (0x04) field parsing.
- **`rtc_apply_bytes` (0x10):** reject impossible dates/times rather than
  writing them to the PCF (month 0, day 32, BCD nonsense) — a garbage write
  here persists in a battery-backed part.
- **`via_custom_value_command_kb`:** id/range checks on every custom value.
- **CH582F RX parser:** frame length handling on truncated/oversized `5B`/
  `5A`/`5C` frames; resynchronisation after a garbage byte (the UART was
  historically mangled by the priority inversion — the parser should survive
  arbitrary byte soup indefinitely).

Bias fixes toward **reject-and-count** (a `[health]` counter for malformed
frames) rather than silent clamping, so bad producers surface.

## 2.4 CH582F TX-queue overflow policy and UART RX FIFO

Two concrete, cheap, potentially high-value items in `ch582f_ajazz.c`:

- **Overflow drops key releases.** `ch582_send_command()` drops the whole
  frame when the 24-entry ring (23 usable) is full — `tx_stat_drop++`,
  including a *release* whose press already went out, i.e. a stuck key over
  BT under burst load. Retrying state reports does not repair a discarded
  release. Evaluate: replace an older queued report of the same type with
  the newer one (keyboard/consumer reports are absolute state, so the newest
  supersedes); or reserve capacity for release/neutral reports; or force a
  neutral-state report after any overflow. Newest-supersedes is likely both
  simplest and strictly better — decide in the findings doc.
- **The UART RX FIFO is disabled** (`UART_FIFOControl = 0`), leaving ~87 µs
  of service slack per byte at 115200 against ~39k interrupts/s of competing
  load. The priority fix made this survivable; the FIFO would make it
  robust. Evaluate enabling it (check the LLD supports it and the CH582F
  framing tolerates the latency change); measure `[ch582]` counters before
  and after.

## 2.5 Cheap static passes (opportunistic, same sweep)

- Build with `-Wextra -Wshadow -Wundef` (scoped to the board files if the
  QMK tree is too noisy) and triage.
- `cppcheck` over `keyboards/a_jazz/ak820pro/` — cheap, occasionally finds
  real RMW/size bugs; expect noise, timebox it.

## Deliverables

- [ ] `findings-concurrency.md`, `findings-bounded-wait.md`,
      `findings-input-validation.md` — each item: location, class, severity,
      proposed fix, "fix now / fold into phase 3 / accept-and-document".
- [ ] Accepted-risk items get a ⚠️ entry in CLAUDE.md so they are not
      re-derived.
- [ ] Approved fixes landed one per flash, soak-gated.
