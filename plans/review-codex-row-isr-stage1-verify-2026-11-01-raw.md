# Codex verify of stage 1 (the row ISR rewrite), 2026-11-01, raw

gpt-6-astra, xhigh, read-only, launched 12:08 on the worktree after the first review's fixes; the prompt is below the review.

The four original **P1s are fixed for the current call paths**. No remaining P1 found. Some diagnostic edge cases remain.

- **Nested holds:** All depth changes are serialized by the system lock. Either release order preserves the first holder’s enable state until depth reaches zero; the priority-2 tick cannot release RTC’s ownership. The backstop’s locked recheck prevents a second release after tick completion. [rowisr.c:446](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:446), [rtc.c:294](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:294), [rowisr_diag.c:124](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:124).

- **Sleep cancellation:** `pwm_tick_stopI()` releases the hold or clears the skip before lowering the pins. Deep sleep does this before saving `ISER`; RTC transactions are synchronous on the same thread and cannot straddle this entry. Wake restores the enabled row line and restarts notifications before unlocking. No armed countdown, marker ownership or skip survives. [indicators.c:220](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/indicators.c:220), [sleep.c:484](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), [sleep.c:618](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:618).

- **Countdown:** The 32-bit word holds all 200,000 ticks. Unsigned deadline subtraction followed by the signed comparison handles the `2^32`-ms wrap for these bounded intervals. `> 0` merely delays the backstop until after the exact deadline millisecond. [rowisr_diag.c:83](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:83).

- **Quiesce:** The thread cannot run concurrently with an active callback; the lock prevents a new callback during teardown. I-class channel disables release PWM ownership, then `pwmStop()` clears CEN, disables vectors and gates clocks without restoring IOEN. GPIO input mode removes pull-ups. With `hw_up == false`, no PWM object is accessed. Repeated calls are harmless on this terminal bootloader path. [rowisr.c:567](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:567), [hal_pwm_lld.c:335](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_pwm_lld.c:335).

Remaining findings:

- **P2 — Caps marker fix is incomplete at transitions.** Clearing Caps or its preview changes desired state immediately, but D15 may remain high until the next tick. A hold accepted in that interval still lacks its rising edge. Check the actual pin under the start lock as well. [rowisr_diag.c:107](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:107), [indicators.c:128](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/indicators.c:128).

- **P2 — quiesce leaves diagnostic hold ownership armed.** A tick expiry after `pwmStop(&PWMD1)` can re-enable its NVIC line. Disabled notifications, stopped timers and released outputs prevent relighting, so this is not a flash blocker, but the promised final line-off state is not unconditional. Cancel diagnostics before disabling the line. [rowisr.c:585](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:585), [rowisr_diag.c:94](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:94).

- **P3 — measurement qualifications:** Scan skip does not affect the separate scan-only branch; measure attribution in normal mode. `status_fill()` is unlocked and can mix pre-expiry and post-expiry fields; a locked snapshot would remove that ambiguity. [rowisr.c:366](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:366), [rowisr_diag.c:151](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:151).

The RGB-disabled P2 is fixed. No additional ordinary pulse/scan behavior change found beyond the dev skip check and diagnostic overhead; `hw_up` retains once-only initialization, and `quiesced` affects terminal teardown only. Settings and drive accounting remain unchanged. The inherited `NO_LED` undefined read remains the accepted P3.

Host framing and status offsets match. The counters wrap at **256**, although transmitted as zero-extended 16-bit fields. Eight synthetic hold/skip cases passed, including 3,277, 5,000 and 10,000 ms. No hardware measurements or rebuild were performed.

**READY TO FLASH for stage 1’s measurements. Remaining P1s: none.**
---

## The prompt

```
You are verifying the fixes to stage 1 of the row ISR rewrite of the AK820 Pro keyboard firmware (QMK on ChibiOS, Sonix SN32F290, Cortex-M0) after a first review. Read only files inside /Users/jdlien/code/ak820-pro; do not search or list anything outside it, and there is no AGENTS.md.

The first review is plans/review-codex-row-isr-stage1-2026-11-01-raw.md (its prompt is at the end of that file and describes the implementation and the tree layout). The owner's dispositions are in plans/ROW-ISR-PLAN.md under "Stage 1's review: codex's findings, dispositions (11-01)". The fixed implementation is on the worktree qmk_firmware-ak820pro-rowisr/ (branch row-isr; `git -C qmk_firmware-ak820pro-rowisr diff` for the tracked changes; keyboards/a_jazz/ak820pro/rgb/ is new), the host side in scripts/rowisr_diag.py. The unmodified reference for the old driver is drivers/led/sn32f2xx.c and quantum/matrix.c in the same tree.

What changed since the first review, all in keyboards/a_jazz/ak820pro/:
- rgb/rowisr.c, rgb/rowisr.h: sn32f2xx_row_irq_hold()/release() nest with a depth and the first holder's saved state (rtc/rtc.c no longer keeps its own bit); sn32f2xx_quiesce() (idempotent: the notification and NVIC line off with the pending flag cleared, every column channel off I-class, mux rows low, the three timers stopped with pwmStop(), every LED pin high-impedance; sn32f2xx_blank() calls it), called first in watchdog.c's bootloader_jump(), which Bootmagic, Fn+Esc and the raw-HID jump (reset_keyboard) all reach; sn32f2xx_prime_timed_out(); the dev-only sn32f2xx_scan_skip flag checked in update_pwm_channels(); the I-class comment narrowed.
- rgb/rowisr_diag.c, rgb/rowisr_diag.h: one 32-bit countdown for a hold (sub 1) or a scan skip (sub 4); rowisr_diag_cancelI() called by indicators.c's pwm_tick_stopI() before the tick's pins go low (light sleep's bit 3 and deep sleep's entry both go through it); the housekeeping backstop re-checks under the lock; a hold refused while the Caps Lock LED is lit or previewed; the pattern (sub 3) under RGB_MATRIX_ENABLE; the status reply (sub 2) extended: counts (8-bit, wrapping), the row line's state, the driver's hold depth, an overlap flag for the last hold, the prime's timeout, the skip's state.
- scripts/rowisr_diag.py: the new status layout and the `skip` command.
- Build: dev, daily and fpb all build; the dev heap gap is at or just above the 128 B floor (build.sh's gate), daily 2288 B.

Judge, with P1/P2/P3 and file:line references:
1. Is each of the four P1s and two P2s of the first review actually fixed, with no new hole? In particular: (a) the nested hold under every interleaving of the clock-chip transaction (rtc/rtc.c's ak820_i2c_xfer_begin/end, which run with the system lock held at begin's entry and end's exit) and the dev hold's start (chSysLock), its tick end (chSysLockFromISR at priority 2), its cancel (pwm_tick_stopI, I-class, called from sleep.c under chSysLock and from pwm_tick_run) and its backstop (chSysLock in the main loop); (b) deep sleep's entry and wake with a hold or skip armed (sleep.c around lines 470-500 and 620-640): is the line back before the wake's first scan, is the marker low, is nothing left that outlives the sleep; (c) the quiesce: idempotent, safe when called before matrix_init_custom() ran (hw_up false), safe from thread context while the callback is running (the lock, pwmDisableChannelI from a locked context, pwmStop after the unlock), and does lib/chibios-contrib's SN32 pwm_lld_stop() (os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_pwm_lld.c) leave the column pins released and the timers stopped so the ROM bootloader finds every LED off; (d) the countdown's width and the deadline arithmetic (timer_read32 wraps at 2^32 ms).
2. Any new behavioural difference in the moved driver's pulse path or scan path introduced by these edits (the scan-skip test inside update_pwm_channels is dev-only; the quiesced flag; the file-scope hw_up).
3. Anything in the changes that makes stage 1's gates unmeasurable or the build unsafe to flash on JD's board mid-drain.
4. scripts/rowisr_diag.py against rowisr_diag.c's reply layouts (status_fill) and the hold/skip framing.

Be concrete and brief; no praise. End with a verdict: READY TO FLASH for stage 1's measurements, or NOT READY, and the P1s.
```
