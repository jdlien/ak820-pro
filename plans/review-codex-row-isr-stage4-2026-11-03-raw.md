**READY TO FLASH — the controlled dev flash on white.** I found no firmware P1 in `8a82367958`. This clears the experiment, not Stage 4’s completion gates. The timing estimate and bracket interpretation need corrections, and the overnight logger has a parsing defect.

I reviewed the source and diff read-only. No builds, tests, or board commands ran.

1. **GPIO invariant: passes.**

   I found no interrupt-context writer of GPIO `MODE`, `CFG`, `CFG1`, or whole-port `DATA` that can race with the transaction.

   | Path | Evidence |
   |---|---|
   | Row handler, including scan-only and scan/LED helpers | Key select/deselect use `palClearLine`/`palSetLine`; mux writes use `palClearPort`/`palSetPort`. Column ownership changes write **timer** `PWMCTRL`/`PWMIOENB`, not GPIO configuration. [rowisr.c:798](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:798) |
   | 20 kHz tick | `od_tick` and `rowisr_time_observe` update accounting/time state; `rowisr_diag_tick` can release the NVIC hold and change the marker level; backlight and indicators use `gpio_write_pin`. [indicators.c:174](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/indicators.c:174) |
   | USB | Handler and endpoint callbacks operate on USB registers, queues and state. Suspend/wakeup application work is queued for thread context. USB’s `CFG` writes are **not GPIO CFG writes**. [usb_main.c:178](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/tmk_core/protocol/chibios/usb_main.c:178) |
   | UART2 | FIFO/queue handling, UART registers and diagnostic hooks only. [hal_serial_lld.c:296](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/UART/hal_serial_lld.c:296) |
   | SPI0 DMA / SPI FIFO | DMA completion changes SPI registers and invokes `blit_done_cb`; that callback raises the two chip selects using atomic pin writes. SPI `DATA` writes are peripheral FIFO writes. [lcd_bus.c:1088](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1088) |
   | RTC and system timer | RTC callback updates clock state and `SECCNTV`; system-timer callbacks extend software clocks and service queues/timers. No GPIO configuration writes. [rtc.c:568](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:568) |
   | Encoder, lock LEDs, sleep | Encoder modes are initialized once; normal sampling reads pins. Lock LEDs use the PWM tick. Sleep’s row/column mode writes occur under the system lock, after the pre-sleep transaction has returned. [sleep.c:471](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:471) |

   The underlying PAL definitions confirm that set/clear operations write `BSET`/`BCLR`, including the “Port” forms; they do not read-modify-write `DATA`. [hal_pal_lld.h:330](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/GPIO/hal_pal_lld.h:330)

2. **I2C stretching is supported; the 5 ms margin needs measurement.**

   The active driver is `os/hal/lib/fallback/I2C`, selected by `USE_HAL_I2C_FALLBACK`, not the SN32 hardware I2C driver.

   It establishes **one absolute transaction deadline**. Byte-entry checks and SCL-low waits consult that same deadline; there is no separate per-bit or per-byte duration limit. Clock-stretch detection reads SCL’s level, so a delayed execution does not itself look like slave stretching. SDA is released while SCL is low; after sampling, SCL is lowered before SDA’s output mode is restored. Preemption extends these intervals without reversing edge order. [hal_i2c_lld.c:139](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/lib/fallback/I2C/hal_i2c_lld.c:139), [read-bit sequence:234](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/lib/fallback/I2C/hal_i2c_lld.c:234)

   **“No slave timeout” needs correcting.** NXP specifies no maximum SCL-high/low interval in the timing table, but the PCF8563 has an interface watchdog firing after 1–2 seconds and requires accesses shorter than one second. Millisecond transfers are comfortably inside that limit. This establishes the PCF8563 specification; the board’s CHMC clone still needs the bench confirmation. [PCF8563 datasheet, §§8.5, 9.6, 13](https://www.nxp.com/docs/en/data-sheet/PCF8563.pdf)

   Using your Stage 3 mean:

   \[
   73/267=27.3\%,\qquad 2.6/(1-0.273)=3.58\text{ ms}.
   \]

   Expect **about 3.6 ms nominal**, a roughly 38% increase. The 16–20% estimate is stale. Page 4 measures elapsed handler time, including preemption inside its hooks and excluding entry/exit overhead, so this remains an estimate—not a worst-case bound. A historical 3.4 ms transfer scaled similarly approaches **4.7 ms**.

   The ordinary **10 ms** path has substantial expected margin. Both **5 ms** paths are exposed: `rtc_sleep_prepare()` reads before stopping the row ISR; wake recovery reads after restarting it. [rtc.c:1989](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:1989), [sleep.c:635](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:635)

   Also, 5/10 ms are checked deadlines, not hard whole-call ceilings: the final byte, STOP, scheduling delay and restart can extend the observed call beyond them. Measure successful transfers and failure/restart calls separately. The comment claiming a full read is “well under 1 ms” is also obsolete. [rtc.c:36](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:36)

3. **Bracket telemetry: useful, but not a conservative uncertainty bound.**

   `ps_brk_prev_t` really is the previous successful read’s midpoint:

   ```text
   previous midpoint = (previous before + previous after) / 2
   reported width    = current after − previous midpoint
   ```

   That exactly exposes the interval used by the existing edge estimator. It includes intervening pass delays, failed-read attempts, and the current read. It is **asymmetric**, however: midpoint-to-end, not midpoint-to-midpoint or previous-start-to-current-end. [rtc.c:1757](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:1757), [previous stamp:1775](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:1775)

   Therefore I would not certify the new comment “the edge lies inside it” as a hard phase-error bound. A midpoint is an assumed sampling instant, and PCF reads themselves freeze the time counters temporarily. For conservative telemetry, retain the previous read’s **start**, report `current_after − previous_start`, and account for millisecond quantization. The feedback algorithm can remain unchanged. This is a measurement correction, not a newly introduced clock-control P1.

   Additional interpretation limits:

   - Width retains the **last successful bracket’s** value after a timeout or invalidated bracket.
   - `brk_fails` counts the `boundary + 400 ms` expiry, saturating at 255. It does not count `ps_brk_void` cancellations or failures before reaching BRACKET.
   - `runs_ok` increments at STOP verification, **before** bracket success. Consequently, `runs_ok` alone cannot prove every bracket settled.
   - Stage 3’s zero bytes are **not a width baseline**. A matched baseline requires the same telemetry with the transaction hold retained, or previously recorded read timestamps.

   Payload bytes `[25..27]` were free: page 4 was zero-filled and its last assignment was `[24]`. They occupy report bytes `[29..31]`. The Python addition decodes those offsets correctly. [rtc.c:879](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:879), [rtc_phase0.py:127](/Users/jdlien/code/ak820-pro/hostagent/rtc_phase0.py:127)

   I found no zero assertion in the named host tools. `ak820health.py` and Rust’s health Page 4 concern the **separate ISR-health page**; `ak820ctl`’s clock decoder consumes `RTC_GET_TIME`, not this status-page tail.

4. **Dev accounting and lock modes remain consistent.**

   In unlocked mode, `od_mask_end()` still closes the opening, partially measured locked stretch before unlock; `_end()` relocks before starting the closing measurement. Removing the NVIC operations removes previously excluded work. These remain **partial hook spans**, not measurements of every instruction under PRIMASK. [rtc.c:297](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:297)

   `OD_LOCK_TRANSACTION` returns before accounting or lock changes in both hooks. The LLD’s outer `SW_I2C_MASK_BEGIN/END` therefore still bracket the locked transfer. Byte mode likewise bypasses these hooks and unlocks only at its byte boundaries. Its predicate excludes unlocked mode. HAL still receives control locked and updates its state before its final unlock. [LLD wrappers:538](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/lib/fallback/I2C/hal_i2c_lld.c:538), [HAL:203](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios/os/hal/src/hal_i2c.c:203)

5. **No remaining functional dependency on transaction darkness or row silence found.**

   `pcf-unseen` still gates only the writer’s start. Its conditions are unchanged; an active writer finishes regardless of subsequent lighting/input. Keep that deferral until the camera gate passes. [rtc_pcf_sync.h:128](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc_pcf_sync.h:128)

   `display_defer_pass()` remains appropriate: it limits the work accumulated in a pass that used I2C. Bus admission and the DMA guard remain intact. Sleep performs its read first, then locks, stops scanning/PWM, and changes modes; wake restores scanning before later recovery transactions. [rtc.c:2333](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:2333)

   Op 28 sub 1 still has a balanced hold/release. The transaction now contributes neither operation, so a diagnostic hold may expire during I2C and legitimately re-enable scanning. The depth remains consistent; its comment about transaction nesting is stale. [rowisr_diag.c:119](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:119), [rowisr.c:1264](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1264)

   UART accounting still records valid observations, but **`ctx_pcf` means “observed during a PCF call,” not “caused by PCF masking.”** During unlocked transfers, the ring’s `mask_last` can describe only the opening partial span. Row-handler critical sections are not included in `max_span`. Use OE/refused-byte deltas, whole-call timing and the tick-gap monitor together. [overrun_diag.c:77](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/overrun_diag.c:77)

6. **Tonight can settle the machine gates; camera and matched width baseline remain outstanding.**

   Before leaving this build beyond the morning, I want this evidence:

   | Hands-free campaign | Required record |
   |---|---|
   | Op 23 read burst under lighting, repaint and UART load | Requested/completed/failed counts; per-kind op 22 `max_whole`; zero unexpected I2C failures; successful 5 ms reads with useful margin |
   | Presser during that burst | Both channels, scan press/release counts → consumed edges → debounced presses → host delivery where the listener works; no phantoms; row gaps within the existing gate |
   | Stuck-bus injection | Injection actually completed and failed as intended; whole call including restart; no pass ≥25 ms; subsequent ordinary reads succeed |
   | Daemon syncs over USB overnight | Actual PCF runs, not only host syncs; completed writer state, STOP/maybe-stopped clear, bracket misses unchanged, release/boundary/width samples and daemon residuals |
   | Sleep/wake cycles under load | Pre-sleep and recovery failures/timing, recovery completion, PCF-derived slept time, waking key retained, no new ≥25 ms pass or reset |
   | UART comparison | OE observations, drain OEs and refused bytes normalized to comparable traffic; intentional sleep receiver-off intervals separated |

   Three practical qualifications matter:

   - **Capture healthy `i2c_max_cycles` before injection.** It is a lifetime maximum and includes failed transfers; the deliberate 10 ms timeout will permanently contaminate the normal-transfer gate for that boot. It is on **RTC page 2**, while bracket fields are on RTC page 4. Op 22 measures whole calls including restart. [rtc.c:270](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:270)
   - **Ensure writes actually occur.** Repeated presser activity with lit LEDs can keep USB writes deferred. A burst permits a pending writer to start, but reads do not themselves request a write. Leave the daemon sole clock owner and arrange dark/idle periods for the soak.
   - **Fix the overnight logger before trusting it.** `rtc_phase0.py` prints dictionary keys such as `'brk_width_ms': 4`; [soak_watch_awake.sh:43](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/soak_watch_awake.sh:43) expects the colon immediately after the unquoted key, so its clock fields become `null`. Parse each dictionary structurally or accept the closing quote. Its 20-minute sampling also cannot retain every five-minute run’s last-value errors. The current [stuck-test runner:73](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/stage4_flash.sh:73) checks stall changes without subsequently checking the injection result; add that evidence and successful recovery reads.

   I would keep this as a dev experiment only if those machine gates are clean. Transfers crowding 5 ms, unexpected failures, lost keys or new stalls warrant returning to Stage 3. A result above approximately 3.5 ms needs an explicit disposition against the corrected occupancy estimate. **No-dark-frame remains JD’s camera gate, on USB and off; keep `pcf-unseen` until it passes.**