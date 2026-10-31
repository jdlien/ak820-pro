**AK820 Pro RGB driver rewrite: design and validation plan**

I recommend a **board-local driver with direct register access, a fixed 125 µs slot schedule, and hardware-terminated PWM pulses**. The target is **444 Hz per RGB field, 444 key samples/s/row, and under 20% measured row-ISR occupancy**, while preserving existing brightness. These are design targets, not measured results.

The rewrite can remove the clock transaction’s deliberate LED blackout and make ordinary LCD activity stop changing average LED brightness. It cannot make internal-flash erases transparent to normal interrupt-driven multiplexing.

No files were changed and no builds were run. Paths below are repository-relative; `qmk/` abbreviates `qmk_firmware-ak820pro/`, and `kb/` abbreviates its `keyboards/a_jazz/ak820pro/` directory.

**1. Where time and light go today.** The useful baseline is the board measurement, not the nominal PWM frequency.

| Quantity | Value | Evidence |
|---|---:|---|
| Row callbacks | 3,876/s | Measured |
| Callback duration | 187.9 µs mean; 160.0 µs minimum; 261.3 µs maximum | Measured |
| Callback occupancy | 72.8% | Measured elapsed callback time / elapsed wall time |
| RGB field / samples per key row | 215.3 Hz | Measured |
| Actual mean slot interval | 258.0 µs | Derived: `1 / 3876` |
| Configured PWM clock | 4.8 MHz, `PRE=9` | Code |
| Configured period | 256 ticks; period match 255 | Code |
| Nominal PWM interval | 53.33 µs | Derived |
| Time outside the measured callback | 70.1 µs/slot | Derived; includes that PWM interval and other overhead |

Sources: [hardware measurement](/Users/jdlien/code/ak820-pro/docs/hardware.md:778), [period and clock](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:117), and [prescaler/period programming](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_pwm_lld.c:292).

The dominant work is avoidable dispatch and register manipulation:

- Every callback disables 15 PWM outputs, clears 18 mux pins, looks up 15 LEDs, and enables 15 PWM outputs individually.
- The LED-only baseline costs approximately `160 µs × 3876 = 62.0%` of elapsed time.
- Scanning contributes approximately `(187.9−160) × 3876 = 10.8%`. Because it occurs once every three callbacks, its average incremental cost is approximately **83.7 µs/scan**. The 101.3 µs difference between measured extrema is not a clean scan measurement.
- The generic matrix reader selects and unselects through pin-mode changes and reads columns individually. The PWM LLD also dispatches through driver pointers and reads/modifies control registers for each channel.

See `qmk/drivers/led/sn32f2xx.c:472–560`, `qmk/quantum/matrix.c:136–194`, and `qmk/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_pwm_lld.c:381–417`.

**The reported 72.8% is callback occupancy, not exclusive instruction execution.** The health hooks measure elapsed CT16B5 ticks, include preemption by higher-priority handlers, and exclude the callback’s final re-arm plus surrounding IRQ machinery. Their resolution is 5.33 µs. Optimization must preserve that measurement and separately measure the complete handler. [Health implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:65)

There is an important unresolved hardware discrepancy. The latest LED notes say the timers stop at period end, leaving the board dark during an ISR hold. However, the checked-in PWM LLD ordinarily selects **reset-on-match**, and `mcuconf.h` explicitly describes auto-reset. I found no enabling definition of `SN32_PWM_USE_ONESHOT` in the inspected configuration. Writing `TC=0xFFFF` alone does not establish stop-at-match behavior. The camera establishes the observed dimming; it does not establish the timer state.

Therefore these light-output estimates are **conditional on one bounded pulse per serviced slot**, and need waveform confirmation:

\[
T_\text{field}=18/3876=4.644\text{ ms}
\]

\[
D_\text{die}(c)\approx\frac{c/4.8\text{ MHz}}{4.644\text{ ms}}
\]

Thus channel code 255 gives approximately **1.144% continuous-equivalent duty**, versus the ideal multiplex ceiling of approximately 5.56%. Only approximately **20.7% of each mean slot** is available as the nominal PWM interval. At QMK values 64 and 128, the existing CIE conversion produces channel drives 12 and 48 for white: approximately **0.054% and 0.215% duty per die**.

The electrical measurements support calibrating against drive rather than UI value: full white adds approximately 189 mW, value 128 approximately 43 mW, and value 64 approximately 18 mW. These are existing board measurements, not predictions for the rewrite. [Power measurements](/Users/jdlien/code/ak820-pro/docs/power.md:199)

Two additional defects must not survive the rewrite:

- The hardware path reads `led_state[led_index]` without checking `NO_LED`; the check is compiled only for software PWM. There are **nine unpopulated positions in the 6×15 LED map**, including the knob. Those slots must explicitly produce zero duty. This is a source-level bounds defect, not an established explanation for the observed flicker. (`qmk/drivers/led/sn32f2xx.c:515–534`; `qmk/quantum/rgb_matrix/rgb_matrix_types.h:70`.)
- The documented rainbow calculation assumes colour separation of one-third of a field. The pin list groups R/B/G by physical row, while the driver has an unusual offset between mux row, key row and programmed colour. Do not carry the documented 18.6 arcminute estimate into the new design without measuring the actual colour pulse sequence. (`docs/leds.md:289`; `kb/config.h:6–12`; `qmk/drivers/led/sn32f2xx.c:491–559`.)

**2. Proposed architecture.** Put the implementation under the keyboard directory, using QMK’s custom RGB driver and custom matrix integration. Keep QMK’s effects, key processing and deferred per-key debounce. The board’s fixed pin map, three-timer wiring, power accounting and sleep contracts justify specialization; maintaining these as branches in a shared Sonix driver makes their ownership harder to audit.

Use `RGB_MATRIX_DRIVER=custom` and `CUSTOM_MATRIX=lite`, with board implementations of initialization and `matrix_scan_custom()`. Preserve the current health/power interfaces through an explicit adapter during migration. Ensure matrix sampling starts early enough for Bootmagic and continues when RGB is disabled. The existing custom-matrix wrapper already calls debounce after consuming raw samples. (`qmk/builddefs/common_features.mk:580,665`; `qmk/quantum/matrix_common.c:145–174`.)

**Separate slot scheduling from pulse generation.**

| Resource | Proposed use |
|---|---|
| CT16B4, currently free | Fixed 8 kHz slot interrupt; becomes the row ISR |
| CT16B0/B1/B2 | Column PWM, explicitly one-shot; no periodic interrupts |
| CT16B3 | Existing 20 kHz backlight/indicator tick |
| CT16B5 | Existing ChibiOS timebase |

This deliberately moves the row ISR away from CT16B1. Update every IRQ-hold, sleep and diagnostic assumption accordingly; do not leave the RTC code masking an obsolete vector.

Program CT16B4 from HCLK, `PRE=0`, nominal `MR9=5999`, reset and interrupt on MR9. For its small-timer register layout, that means keyed `MCTRL` with **MR9IE bit 21 and MR9RST bit 22**, no stop bit. Confirm the exact 6,000-clock cadence on hardware before acceptance.

For the PWM timers choose **48 MHz, `PRE=0`, a nominal 4,096-tick window: 85.33 µs**. CT16B0/B2 use MR9; CT16B1 uses MR12. Explicitly select stop-on-period-match, with reset-on-match **clear**:

- CT16B0/B2: keyed MR9 and `MCTRL.MR9STOP`, bit 23.
- CT16B1: MR12 and `MCTRL2.MR12STOP`, bit 8.
- All duty matches have interrupt/reset/stop disabled.
- Active-low columns use PWM mode 1: low before their match, high afterward.
- Limit nonzero widths to **4,094**, below the terminal match. Zero must remain continuously inactive.
- Re-arm with counters positioned immediately before wrap and `CEN` explicitly enabled last. Do not assume a stopped timer restarts merely because TC was written.

The stop-at-match/output behavior is a hardware acceptance gate. In particular, **reset-plus-stop must not freeze a counter at zero with an active-low output asserted**. Register layouts and write keys are documented in [the MCU reference](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:706).

Retain the existing PFPA routing:

- B0 `0x3332`: channels 0–3.
- B1 `0x0F00`: channels 4–11.
- B2 `0x0000`: channels 1–3.

Use complete, precomputed control words instead of per-channel API calls. B1’s used enable/IO mask is `0xFF0`. B0/B2 use enable masks `0xF`/`0xE`, with IO bits at `20+n`. Every B0/B2 MR and PWMCTRL write includes `0x5A000000`; B1 does not need the key. (`kb/config.h:24–30`; PWM LLD `hal_pwm_lld.c:135–150,242–281`.)

**Each serviced slot does this:**

1. Acknowledge only the observed scheduler flag. Clear all LED mux rows through four `BCLR` writes. Stop/release the three column PWM outputs.
2. Once every three slots, scan the next key row. All six key rows remain configured as outputs; select with `BCLR`, deselect with `BSET`. Read GPIO0 and GPIO2 once each and assemble the 15 column bits.
3. Load 15 prepared duty values directly into the mapped MR registers. There is no colour conversion, division, effect evaluation or LED-index lookup in the ISR.
4. Select the physical mux row for an explicit `(key row, colour)` table, initially R/B/G for each row.
5. Check the remaining scheduler interval, then arm the three PWM timers together in a short critical section.

The GPIO masks are fixed:

| Purpose | GPIO0 | GPIO1 | GPIO2 | GPIO3 |
|---|---:|---:|---:|---:|
| LED mux rows | `0x00B00` | `0x00030` | `0x03C00` | `0x73F00` |
| Key rows | `0xC0000` | `0x8C000` | — | `0x80000` |
| Shared columns | `0x000F0` | — | `0x043FF` | — |

Configure column pull-ups and row modes at initialization or controlled sleep transitions. **The running ISR never writes GPIO MODE, CFG, CFG1, or a whole DATA register.** Atomic BSET/BCLR writes are sufficient. [PAL implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/GPIO/hal_pal_lld.c:202)

Start with conservative **2 µs settling allowances** around column release, selected-row sampling and restoration; overlap useful register preparation where safe. These are proposed allowances, not measured board requirements. The current select delay is only nominally 0.25 µs, and the driver’s unselect loop is not a calibrated 30 µs delay. (`qmk/platforms/chibios/_wait.h:52–66`; `qmk/drivers/led/sn32f2xx.c:158–161`.)

**Late service must fail dark, not corrupt the next slot.** Before arming, require enough time for the slot’s largest actual pulse plus a measured guard. If another scheduler match occurred during this handler, or insufficient time remains, omit that LED pulse and count it. Never replay missed periods in a catch-up loop. Continue key-row rotation on serviced scans, independently of whether the LED pulse was omitted. A delayed handler may reduce refresh temporarily; it must never leave one row repeating indefinitely.

The final arm/phase check should mask interrupts for **under 2 µs**, with a measured **5 µs maximum gate**. Leave UART2/system timer at priority 0, USB at 1, CT16B3 at 2, and the new row IRQ/SPI0 at 3. Priority changes are not part of this optimization. (`kb/mcuconf.h:77–96`.)

At 8,000 slots/s:

- RGB field: `8000/18 = 444.44 Hz`.
- Key-row interval: **2.25 ms**, with one sample per row per field.
- Mean complete ISR cost of 20 µs: **16% occupancy**; the release ceiling of 25 µs mean corresponds to 20%.
- Adjacent colour starts are nominally 125 µs apart; R-to-G separation is 250 µs. At 200°/s eye motion these correspond to **1.5 and 3 arcminutes**, respectively, before service jitter. This reduces separation; it does not eliminate colour breakup.

Keep the existing rolling matrix, six-row initialization mask and locked consume/copy/clear. Do not gate acquisition on main-loop consumption or RGB state. Do not add sticky edge bits. The shipped matrix fix—not the earlier staging-buffer proposal—is the contract to preserve. [Actual matrix-plan outcome](/Users/jdlien/code/ak820-pro/plans/MATRIX-PUBLISH-PLAN.md:233)

**Prepare immutable LED frames in the main loop.** Build an inactive `[18][15]` array of 16-bit widths, including explicit zeros for holes. Publish it through a short pointer/ownership handoff; the ISR adopts it at the field boundary. If a frame is still pending, retain the new render as dirty and retry without blocking the main loop. Never let the producer edit the active or pending array.

Distinguish **render completed**, **frame submitted**, and **frame actually displayed**. The existing committed-dark test and “two flushes” consumers must be audited against that distinction. In particular, sleep and early cleanup must not mistake a submitted black frame for one already displayed. (`qmk/drivers/led/sn32f2xx.h:87–110`.)

**3. Stalls and lifecycle behavior.**

| Mechanism | Proposed behavior and remaining limitation |
|---|---|
| Ordinary flash programming | Continue scanning between the existing 10–20 µs masked program windows. One-shot pulses finish without ISR intervention. Preserve the program-window protection and LCD-DMA drain. A late slot can still be omitted; ordinary writes were already visually invisible in the latest test. |
| Consolidation erase | Each page erase can prevent flash vector/instruction fetch for 1–2 ms. Pulses finish, then the board remains dark until service resumes. Two erases still create approximately 2–4 ms total interruption. The rewrite cannot remove this. |
| Whole consolidation | The approximately 58 ms synchronous operation also stops main-loop consumption, although scanning can run between flash-busy windows. Faster scanning alone cannot guarantee delivery of a press and release contained within that interval. |
| PCF I2C transaction | Once the ISR has no GPIO mode writes, remove its NVIC hold from the unlocked transaction hooks. Keep HAL’s unlock/relock contract and the LCD/SPI1 bus guard. This removes the deliberate 2–3.4 ms blackout and sampling pause. |
| LCD fills | Retain the current main-thread FIFO polling fix. A fixed scheduler no longer accumulates every small late start into a longer field. Within the pulse deadline, jitter changes pulse placement rather than delivered energy. Severe contention can still cause counted omissions. |
| Light sleep | At a dark-frame boundary, disable LED PWM and scan one key row every 625 µs: nominally 3.75 ms per matrix. Preserve the existing dev-only policy and bounded yielding. |
| Deep sleep | Under the existing lock: blank mux rows, disable PWM ownership, stop the scheduler and clear its peripheral/NVIC pending state. Leave columns as pull-up inputs for wake detection. Restore clocks and key-row levels before restarting; re-prime timing instruments and retain the dark frame until normal wake rendering permits light. |
| Bootloader | Add one idempotent terminal quiesce operation on the common jump path: stop scheduler, disable timer pin ownership, blank, then put LED pins high-impedance. Preserve watchdog stop, RAM magic and reset behavior. No pending ISR may undo blanking. |

The latest flash behavior is documented at [leds.md:211](/Users/jdlien/code/ak820-pro/docs/leds.md:211); the actual program mask is `qmk/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:332–339`. Preserve [the DMA drain](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:722).

Moving just the ISR into SRAM is **not an established erase solution**: the vector table has no documented SRAM mapping, and the only documented DMA moves SPI data, not timer/GPIO sequences. Making erases invisible would require a separate, proven RAM-only execution/vector strategy or different hardware. (`docs/sn32f299.md:129–135,882–886,1104–1125`.)

For I2C, keep both unlocked hooks, removing only the row-vector suppression after the GPIO audit. At 16–20% row occupancy, a simple load estimate predicts approximately **1.19–1.25×** transaction wall time, rather than today’s approximately 3.7× if the old ISR were allowed through. Actual bus timing, timeout behavior and phase-bracket accuracy must decide acceptance. Preserve the current write-deferral policy initially. [Current hooks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:270)

The LCD’s large fill regression is already substantially fixed: the mainline polls with SPI0’s sources disabled while the bus is quiescent. The rewrite must retain that fix and re-test DMA completion races because shortening the row ISR changes the transfer sizes exposed to interrupt timing. [Current polling path](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:132)

Sleep must retain the existing admission and wake sequence, not merely restart timers. (`kb/sleep.c:444–495,582–612`.) The current `bootloader_jump()` itself stops the watchdog and resets; the new common quiesce should cover every jump route. (`kb/watchdog.c:121–131`.)

**4. Brightness, colour and resource costs.** Preserve the meaning of stored HSV values during the timing migration.

At the proposed 444.44 Hz field, preserving the conditional old pulse energy requires:

\[
w_\text{new}(c)
 = \operatorname{round}\left(c
   \frac{48\,\text{MHz}}{4.8\,\text{MHz}}
   \frac{215.333}{444.444}\right)
 = \operatorname{round}(4.845c)
\]

Thus old channel 255 becomes approximately **1,235 ticks**, not 4,095. Exposing the full new window immediately would increase maximum average LED drive approximately **3.3×**. Calibrate the preservation factor from the actual old waveform and power map before shipping it.

The hardware offers nominal 12-bit timing, but at preserved maximum output only approximately **1,236 codes—10.3 bits—are used**. The 20.83 ns timer increment is not proof of optical resolution: transistor switching and minimum useful pulse width may dominate.

| Adjustment | Benefit | Cost and compatibility |
|---|---|---|
| Value step 1 | Finer UI adjustment | Negligible CPU/RAM/flash; existing byte settings remain valid. Alone, repeated CIE outputs still produce identical light. |
| Wide CIE/perceptual conversion | Retains dim-end values before rounding | Approximately 512 B flash per 256-entry 16-bit curve; conversion in main loop. No field-rate cost. Preserve byte HSV settings and the old curve’s overall appearance. |
| RGB white-balance gains | Corrects colour ratios without coarse integer multipliers | Three fixed-point gains, approximately 6 B state; up to 243 multiplies per changed frame. Use saturation and attenuation initially. No ISR conversion or field-rate cost. |
| Higher-precision effect output | Gives fades and mixed colours useful extra PWM codes | A 16-bit board-local colour path; extra render work and buffer RAM below. Existing effects need explicit adaptation to benefit. |
| Slot reordering | Makes a preferred two-colour combination adjacent | Small flash table; no extra slots or field-rate cost. Validate physical colour mapping first. |
| Per-key/channel calibration | Corrects spatial variation | At least 243 B for one-byte trims, plus main-loop multiplies. Defer until variation is measured. |
| Temporal dithering | Can represent fractions below one physical pulse step | Additional state and ISR work; a four-field pattern repeats at only 111 Hz. Do not enable initially at the dim end. |

**Widening the driver alone does not restore precision already lost upstream.** QMK applies its CIE lookup to an 8-bit value and performs colour mixing into 8-bit components. Multiplying those bytes afterward preserves their plateaus. (`qmk/quantum/color.c:22–61`.)

Introduce a board-local 16-bit colour submission interface, first for a precision Solid effect and then the board-local effects. Keep the old byte interface for unchanged QMK effects. A separate precision effect can receive a new append-only profile ID while existing profiles retain their current rendering. Do not apply a second gamma curve to already CIE-converted bytes. Preserve `power_val_cap()`, the lights-out scale, and DRIFT’s different value-scaling semantics. (`kb/power.c:137–168`; `docs/leds.md:337–366`.)

A concrete upper buffer budget is:

| Allocation | RAM |
|---|---:|
| Persistent 81×RGB16 render state | 486 B |
| Two prepared 18×15×uint16 frames | 1,080 B |
| Ownership, slot summaries and accounting allowance | ≤256 B |
| Total | ≤1,822 B |

The old RGB buffers use 486 B. Removing three mutable PWM configurations and three PWMDriver objects can recover approximately **552 B**, calculated from the current 32-bit layouts, subject to linker verification. The resulting planned increase is approximately **528–784 B**, before any precision effect’s private state. (`qmk/drivers/led/sn32f2xx.c:150–151,179–204`; `hal_pwm_lld.h:139–224`.)

That fits the documented daily-build margin more plausibly than the dev build: the latter had **224 B** free, with a **128 B enforced floor**. Reclaim roughly **0.7 KiB elsewhere in the dev configuration** for the upper budget before accepting it; do not shrink stacks or lower the floor. Tables should be const in flash. Exact code-size change remains unknown until a later build. [Recorded margins](/Users/jdlien/code/ak820-pro/CLAUDE.md:134) · [RAM gate](/Users/jdlien/code/ak820-pro/build.sh:197)

Preserve stored HSV, effect IDs, defaults and profile records during the driver cutover. New calibration gains can initially be compiled defaults with RAM-only experimental controls. Persistent new controls require a separate versioned migration: the current **218 B profile block is fully occupied by its header and eight 27 B records**, and the macro buffer is already reduced to 19 B. There is no justified “spare byte” assumption. (`kb/menu/profiles.h:20–50`; `kb/config.h:275–284`.)

Update power accounting with the physical output. Precompute slot width sums and accumulate delivered pulse ticks, including omitted slots, using cheap ISR counters; normalize and perform wide arithmetic in the main loop. Keep committed-dark tied to the displayed frame. Refit base, lit overhead and colour coefficients with the logger before trusting the battery estimate.

Lower CPU occupancy does **not** imply proportional battery savings: the awake firmware currently spins rather than entering WFI. Measure dark-board power separately from LED power. (`kb/config.h:248`; `docs/power.md:204–208`.)

**5. Staging and acceptance.** Make each stage independently reversible. Use same-session A/B measurements; historical scan-rate differences below approximately 6% are not persuasive.

| Stage | Change | Measurable gate |
|---|---|---|
| **0 — establish truth** | Record current firmware token, settings, timer registers and controlled baseline. Resolve reset/stop behavior and physical colour sequence. | Three ≥20 s health windows: ISR occupancy, entries, per-row counts/gaps, scan rate, stalls and UART errors. Repeat with LCD load, PCF writes and cleanup. Capture fixed-exposure 240 fps video and power-map holds. |
| **1 — isolate ownership** | Introduce board-local driver/custom-matrix integration with equivalent timing, settings and lifecycle behavior. | No new phantom/missing keys; no new LCD timeout or watchdog reset; brightness/power within 3% in controlled holds. Bootmagic and every bootloader entry route work; bootloader stays dark and enumerates `0x7140`. |
| **2 — remove GPIO overhead** | Fixed pin modes, atomic row selection and two-port column reads. Keep current publication behavior and cadence. | Six row counts differ by at most one in uninterrupted rotation; ordinary-load row gap ≤7 ms; no column leak during held keys/chords. Relay delivery gate below. Do not yet remove the I2C hold while PWM overhead remains large. |
| **3 — replace PWM hot path** | Prepared frames, direct MR writes, explicit one-shot pulses and CT16B4 scheduler. Initially retain approximately 258 µs slots. Temporarily move the RTC hold to the new IRQ. | Complete handler mean ≤25 µs; existing callback metric falls substantially. No pulse repeats when the scheduler is held; zero output remains dark; max output remains bounded. Sweep LCD DMA lengths, including 660 bytes and neighboring sizes. No blit timeout/poll give-up. |
| **4 — let I2C coexist** | Remove row IRQ hold after confirming no interrupt-side GPIO mode writer remains. | PCF-correlated dark dips disappear in repeated camera comparisons. Successful transactions remain comfortably below the 10 ms timeout; stuck-bus/restart and complete-pass tests remain <25 ms. No worsening of bracket width, release error, UART OE/refused bytes or delivered requests. |
| **5 — raise field rate** | Set 125 µs slots and recalibrate widths to preserve light output. | Approximately 8,000 serviced slots/s and 444 samples/s/row; total row occupancy ≤20%; ordinary idle/typing row gap ≤4 ms; no nonflash pass ≥25 ms. No omissions in quiet runs; under defined mixed load, omitted slots <0.1%, with bursts examined separately. Current and camera brightness stay within the preservation tolerance. |
| **6 — add precision controls** | Wide conversion, precision effects and calibrated gains, one feature at a time. | Monotonic low-end optical steps; no zero/full-value glitch or colour discontinuity; render preparation ≤0.5 ms per changed frame as a proposed budget. Re-run every effect through power caps, darkness, profile restore and sleep/wake. |
| **7 — sustained release check** | Combined soak and power-model refit. | Same-session baseline/candidate comparison under typing, LCD, clock and flash activity; zero unexplained resets/timeouts, zero nonflash ≥25 ms passes, and no regression in transport or key delivery. Preserve all structural/RAM gates when implementation is eventually built. |

The key-delivery gate should count **commanded contact closures → raw transitions → debounced presses → host down/up events**, with wireless retries, give-ups, replacements and queue drops beside them. Use at least 1,000 presses per transport at a reliable dwell, then short-tap and overlapping manual-key tests. Compare latency distributions, not just totals.

**The relay key rig is currently documented as broken.** Relay 1 clicking is not a press. Repair it and pass the existing slow-contact sanity test first; relay 2 remains useful for battery/charging transitions. Do not require perfect delivery at the historical 25 ms-held/10 ms-open marginal limit: characterize that separately. [Bench status and measured limits](/Users/jdlien/code/ak820-pro/docs/test-bench.md:527)

For power acceptance, use INA228 charge deltas and MAX17048 voltage, forward/backward holds at equal settings, and compare milliwatts. For the camera, fix exposure/white balance and compare timed event windows: **240 fps can reveal millisecond dimming but cannot validate 20 ns pulse resolution or uniquely measure a 444 Hz field**. (`docs/test-bench.md:396–418`.)

At every stage respect the historical failures:

- UART’s approximately 87 µs byte deadline; PRIMASK defeats priority.
- Matrix sampling must never depend on consumer phase.
- Shortening the ISR moves SPI DMA race exposure; preserve narrow flag clearing.
- Keep the flash/DMA drain and per-line programming masks.
- Do not report stalls by drawing to the LCD being measured.
- Keep power-source changes, host pollers and firmware changes separate in A/B tests.

These are the load-bearing warnings in [CLAUDE.md:653](/Users/jdlien/code/ak820-pro/CLAUDE.md:653) and the measured [UART-latency results](/Users/jdlien/code/ak820-pro/plans/UART-LATENCY-PLAN.md:314).

**6. Questions the sources cannot settle.**

| Question | Measurement that settles it |
|---|---|
| Do the current timers actually stop, reset, or expose another PWM behavior during an IRQ hold? | Read MCTRL/MCTRL2/TMRCTRL and capture one column plus its mux row during a controlled hold. This gates the old light-energy calculation. |
| Does stop-only PWM reliably finish inactive and restart cleanly on all three timer types? | Exercise widths 0, 1, terminal−1 and invalid terminal values; delay the ISR deliberately. Observe output during stop and restart. |
| How many optical bits are useful? | Sweep isolated low-width pulses with a photodiode/oscilloscope. Camera and power logger can establish coarse monotonicity, not nanosecond pulse fidelity. |
| What settling time is required with pressed keys and transistor charge storage? | Compare column waveforms and raw errors over a delay sweep, with cross-row chords and each colour active. Retain margin above the shortest clean setting. |
| What is the real old colour-slot sequence? | Single LED/pure-colour patterns and simultaneous mux/column traces. This determines mapping and the valid before/after fringe comparison. |
| Will I2C timing remain accurate with regular row preemption? | Existing per-kind whole-call measurements, stuck-SCL injection, phase-release/bracket statistics and daemon residuals under two-way radio/LCD load. |
| Can the target ISR and RAM budgets be met? | Later complete-handler timing and linker map, followed by health stack-watermark/soak checks. No source-only estimate proves either. |
| Does consolidation currently lose short presses despite continued row sampling? | Phase-sweep reliable 25–40 ms presses across cleanup, comparing raw samples, cooked events and host delivery. |
| Does faster service reduce energy use? | Matched dark/lit power-map runs, followed separately by the existing light-sleep probes. |

The consolidation input test is consequential: a rolling matrix can overwrite an entire press while the main loop is blocked for approximately 58 ms. If acceptance requires **zero loss through cleanup**, this rewrite needs an additional, separately reviewed input-event preservation or incremental-storage work package. Faster scanning and a clean `rowgap` counter cannot establish that guarantee. Likewise, erase-time UART loss remains a flash-execution problem, not something LED priority tuning can repair.