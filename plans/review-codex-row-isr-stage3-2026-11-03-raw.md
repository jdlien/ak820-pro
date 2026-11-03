**P1 — blocks the flash: `scan_settle()` can publish a sample before the requested settling time has elapsed.**

At [rowisr.c:720](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:720), an MR9 reset makes the unsigned subtraction enormous. For example, with the 12,816-tick period, `t0 = 12810` and the next reading `4` represent approximately **10 elapsed ticks**, but satisfy the exit condition for a 96-tick wait. Late entry or preemption can place the scan there. [scan_key_row:785](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:785) then reads and publishes the sample; the [crossed-slot check:1129](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1129) prevents an LED arm, not that publication.

**Fix:** calculate elapsed time modulo the active `slot_ticks`, or restart the settling interval when a reset is detected. Keep the requested delay below the active period. This preserves the minimum settling time even on late scans.

I found no other P1. There is a definite daily-build compile failure and a missing host diagnostic field, both P2 below. Review was read-only; no builds, tests, or board operations ran.

1. **GPIO invariant — holds on the inspected paths.**

   The running handler writes GPIO only through BSET/BCLR. [The pin helpers](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:800) use atomic port operations; `columns_release/active` change timer PWM ownership registers, and `pulse_park/arm_all` change timer registers. The [PAL implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/GPIO/hal_pal_lld.h:330) confirms these operations use BSET/BCLR. The health hooks add no GPIO writes.

   [Initialization](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1322) establishes all six key rows as push-pull outputs high and all columns as pull-up inputs before starting the scheduler. During a scan, only the selected key row goes low; it returns high before instrumentation or publication. GPIO modes remain inputs underneath PWM ownership, which is released before each ordinary scan.

   **Deep sleep is correctly ordered.** The system lock starts at [sleep.c:471](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:471); the scheduler is stopped/disabled before rows are lowered at lines 496–500. On every normal exit—including an admission-time wake without WFI—all rows return high at [sleep.c:620](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:620), before scheduler restart at line 635 and unlock at line 641. The first resumed scan cannot encounter the sleep configuration.

   Light sleep changes no matrix pin modes. Scan-only releases columns for its duration and restores ownership before ordinary operation; its cadence-change invocation returns without scanning. See [rowisr.c:1036](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1036).

   [Quiesce](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1397) cancels diagnostic holds, disables/stops/clears the scheduler, then changes LED pins to floating inputs. `blank()` aliases it. Its caller is the terminal [bootloader route](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/watchdog.c:129), covering Bootmagic and the other jumps. The flash guard either skips scanning or runs the ordinary scan; it never lowers another key row or changes GPIO modes.

   Thus I found **no reachable leftover-low row** during another row’s scan.

2. **Column assembly — correct; the check is diagnostic rather than protective.**

   [columns_read()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:696) matches [keyboard.json:143](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/keyboard.json:143):

   | Matrix bits | Source pins |
   |---|---|
   | 0–1 | A4, A5 |
   | 2–5 | C0–C3 |
   | 6–7 | A6, A7 |
   | 8–11 | C4–C7 |
   | 12 | C14 |
   | 13–14 | C8, C9 |

   Inversion makes a low pin a pressed bit; masking excludes unrelated port bits and bit 15. The pressed-state and COL2ROW guards agree.

   The initialization comparison checks every configured column against `col_order`, but does not verify the assembly expression independently or stop a mismatched configuration. That is acceptable for **this inspected, matching, immutable configuration**. For future changes, prefer build-time validation or refusing initialization on mismatch over knowingly publishing wrong keys.

   **P2:** firmware reports the fault at [rowisr_diag.c:386](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:386), but [the host’s `status_dict()`](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:160) ignores byte 31. Neither normal status output nor JSON exposes it. Add `col_map_fault: bool(r[31])` and a visible warning.

3. **Settling — no reachable stopped-counter hang found; minimum-delay defect is the P1.**

   Scheduler stop paths disable its IRQ under the system lock and clear pending state. A thread cannot execute those paths while this handler is active. Deep sleep restarts the counter before enabling its IRQ; initialization failure returns before scheduler IRQ enable. Light sleep and row-IRQ holds leave the scheduler counting. See [sleep hooks](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1218), [scheduler initialization](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1303), and [initialization failure](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1355).

   With the counter running and no reset, 96 ticks means **2 µs from the initial counter read**, plus instruction/loop overhead and any preemption. The nominal waiting alone averages about 0.67 µs per ordinary slot, because only every third slot scans.

   Two microseconds is a reasonable **starting experiment**, not an established electrical margin. Normally the parked PWM outputs already left unpressed columns high; selected pressed columns discharge through the switch/diode into a driven-low row. The weak pull-ups matter especially for recovery from previous low states and in scan-only operation. The manual gives the GPIO and pull-up behavior at [sn32f299.md:580](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:580).

   Q1 must demonstrate clean ISR transitions and no unwanted rises with held cross-row chords, each colour, both boards, and margin above the shortest clean setting. Include late-service/hold-off recovery after fixing the reset arithmetic; otherwise the configured sweep value is not a guaranteed minimum.

4. **Locked consume — correct, with unchanged matrix semantics.**

   [rowisr.c:1580](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1580) performs six bounded iterations: six XORs, six scratch stores, and up to six row copies, then clears the dirty flag. The scratch array is 12 bytes for this matrix. No timer read, popcount, or explicit function call lies inside the lock.

   `changed` is true exactly when the old `memcmp` would differ. Copying only differing rows produces the same final matrix as the previous conditional whole-array copy. [health.c:123](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/health.c:123) counts the exact copied differences after unlocking.

   **Exact means transitions presented to debounce.** A press and release both overwritten between consumes remain invisible to `raw_edges`; the ISR rig counters address that separate limitation.

   The board declaration, weak definition, strong definition and caller all use the new signature in both dev and daily. The remaining old-signature definition/call are in `drivers/led/sn32f2xx.c`, excluded by this board’s [custom-driver/lite-matrix rules](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rules.mk:79).

   Host decoding needs no protocol change. However, [sleep_baseline.py:263](/Users/jdlien/code/ak820-pro/scripts/sleep_baseline.py:263) and [sleep_sizing.py:165](/Users/jdlien/code/ak820-pro/scripts/sleep_sizing.py:165) still accept 98% of expected edges. Those historical allowances must not serve as stage 3’s exact-edge gate.

5. **Rig counters — correct for the two distinct default positions.**

   [rig_note()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:732) computes rises as `now & ~prev` and falls as `prev & ~now`. It removes matched rig rises before counting “other”; falls elsewhere are intentionally ignored.

   With no transition it returns before position comparisons or counter updates. A transition costs two position checks, applicable increments, and at most 15 iterations over remaining rise bits. Exact execution time is not established by C inspection.

   [Read-and-zero](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:755) excludes the ISR with `chSysLock`, so increments cannot be lost between copying and clearing. Counters wrap at 65,536; use bounded windows for a long run.

   Bounds checking rejects rows ≥6 and columns ≥15 and preserves positions on the sentinel. **Note:** duplicate positions are permitted. If both identify one key, slot 0 consumes its rise, so slot 1 records releases but no presses. Reject duplicate positions or count each against the original rise mask. This does not affect tonight’s defaults. Configure positions while idle and begin a fresh counting window.

6. **FRMNO — the hypothesis fits; three reads are a mitigation with an unproven hardware assumption.**

   [frmno_read()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:282) does **not** always obtain two matching consecutive reads: on disagreement it returns the third unconditionally. Three suffice if the suspected transient has ended before that third read, and two equal reads cannot both observe the transient. The supplied MCU documentation establishes neither bound.

   The “11 cycles apart cannot both be torn” comment is too categorical. The recorded [11-cycle result](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/readcost-exit.txt:1) includes the diagnostic loop; it does not establish the optimized helper’s read spacing or hardware update duration. Describe this as a bounded retry mitigation pending qualification, or explicitly validate agreement with bounded retries and handle unresolved ambiguity.

   **The rejection trace supports your explanation.** With `fresh` true, [the rejection path](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1012) invalidates without staling frames and sets `adopt_pending`. If the service commits, [service_commit()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:880) copies **s1**, replacing only its generation. Its torn `frm` survives. Thus `0x0ff → 0x000 → 0x100` yields 1793 then 256 modulo 2048, both rejected over short elapsed intervals. A service that crosses a slot and does not commit need not produce that pair.

   A transient `0x1ff` produces the opposite ordering. A bad SOF-number observation or actual abnormal host-number excursion could produce the same arithmetic; the last rejected span plus a count of two does not prove which occurred. Normal wrapping cannot: the mask matches the LLD’s `0x7ff`. FRMNO is a read-only 32-bit register, and the [LLD reset path](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:233) does not software-write its bytes. Reset/suspend normally have bus-state/generation evidence.

   Every detector use is covered, including the [20 kHz tracker](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:374). A tick-only tear usually affects freshness temporarily and is corrected by the next observation; it can falsely refresh trust or clear recovery. `take_snapI()` also calls that tracker and copies its result, so tracking is not universally “freshness only.”

   All helper calls are already under locks. It adds a volatile read and comparison normally, another read rarely, with no division or HAL call. The supplied BL inventory is consistent with that; the local outlined tail is not a GPIO-mode operation. Its frequent tick cost still belongs in the measured CPU comparison.

7. **FRMNO scan — protocol correct; it deliberately perturbs main-loop timing.**

   [fscan_slice()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:296) checks elapsed time only after each 512-read batch. Therefore “3 ms” is a target with timer quantization, batch overshoot and interrupt latency, not a hard ceiling. Interrupts remain enabled.

   It runs immediately after the health boundary and before RTC/display work at [ak820pro.c:615](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/ak820pro.c:615). It consumes pass budget, can make the RTC’s 10 ms admission fail, and can push otherwise acceptable passes into health’s ≥10 ms bucket. The next health boundary includes that cost. Keep this probe separate from clean timing, short-tap and soak measurements.

   The watchdog is kicked after each completed pass; the scan is not a single 60-second blocking operation. Arming merely resets state and returns the reply; subsequent housekeeping performs slices. Later replies can wait for the current pass, not the whole requested scan.

   [Firmware serialization](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:320) and [Python decoding](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:323) agree:

   | Bytes | Meaning |
   |---|---|
   | 4–7 | Counted read-to-read steps |
   | 8–11 | +1 steps |
   | 12–15 | Other steps |
   | 16–17 | Remaining milliseconds |
   | 18 | Valid pair count |
   | 19–30 | Three little-endian `(prev,next)` pairs |

   Zero milliseconds reads without resetting; nonzero re-arms/reset counts, capped at 60,000. Duration counts accumulated slice time, so wall-clock completion can take longer. Old pair storage survives re-arm, but the reset pair count makes it invalid and Python ignores it.

   A tear can show `0ff→000→100` or `0ff→1ff→100`; ordinary short preemption generally yields a small forward skip. These are suggestive patterns, not definitive attribution without timestamps/bus-event context. Only three anomalous pairs survive, and slice boundaries deliberately omit inter-pass steps. The comment’s clock-chip/flash examples ordinarily run elsewhere in this same thread, rather than preempting this loop.

8. **Sections opt-in — preprocessing is consistent.**

   [rowisr.h:72](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.h:72) defines the default before the declaration guard. [rowisr_diag.c:14](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:14) includes it before `#if ROWISR_SECTIONS`; including `rowisr_diag.h` first is harmless.

   With dev+1, declaration, storage, stamps, commit and sub 11 all exist. With dev+0, stamps/commit become no-ops and sub 11 is unhandled. Without dev hooks, the diagnostic translation unit and instrumentation stay absent even if sections is 1.

   [The host command](/Users/jdlien/code/ak820-pro/scripts/rowisr_diag.py:284) explains the required build on refusal and exits before its ten-second window. Minor note: catching every `SystemExit` also mislabels “no reply” as “sections not compiled.”

9. **Tonight can establish substantial bench evidence, but not stage 3 acceptance.**

   The [stage 3 gates](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1252) and [delivery gate](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1478) require more than the existing batches.

   | Available tonight after the code fix | Still requires broader setup or observation |
   |---|---|
   | Repeat the parent-build 25/15/12/10/8 ms comparison with recorded release dwells; count rig rises/falls, other rises, consumed edges and debounced presses | Full ≥1,000-press batches per transport and prescribed stressor; broader short-tap characterization |
   | Hold A0 while pulsing A1, and reverse; repeat with software-selected colours | Other row/column combinations, especially same-column cross-row chords; both boards |
   | Six-row fairness and matched-load `row_gap_max`; classify PCF hold-off windows separately | Every physical key and knob in VIA; JD’s visual flicker/leak checks |
   | Board-side overnight stalls, resets, phantom counts and FRMNO rejection observations | Host delivery after the Mac locks; waveform/pulse/settling measurements requiring the witness |

   The checked-in [listener handles F19 and F20 separately](/Users/jdlien/code/ak820-pro/hostagent/f19listener/main.swift:71); host-delivery claims require that version running and an uninterrupted observable session. Board `key_presses` alone does not prove host delivery.

   Tonight’s two plugs occupy **different columns**, so they do not exhaust the same-column leak case. “Other presses” detects phantom inputs; it cannot certify absence of visible LED leakage.

   The [recorded parent baseline](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/README.md:667) supports A1’s short-dwell comparison and A0 at 25 ms—not A0 at every short dwell. The 76/100 result at 8 ms characterizes a boundary; repeat comparable batches rather than treating one proportion as an exact probability.

   **After fixing the P1, I would allow the controlled white-board dev flash to obtain these measurements.** Missing hands/witness gates prevent acceptance and progression, rather than preventing that experimental flash. The current P1 needs a code fix, not a gate unavailable tonight.

10. **P2 — daily does not compile cleanly under the stated flags.**

   [rowisr.c:788](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:788) declares `prev`, whose only use is `RIG_NOTE`. Without dev hooks, [that macro](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:768) discards its arguments. This leaves an unused local under [the build’s `-Wall -Werror`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/builddefs/common_rules.mk:73).

   **Fix:** guard the `prev` declaration with `AK820_DEV_HOOKS`, or restructure the instrumentation so the daily path creates no unused local.

   The other requested daily checks pass by inspection: `settle_ticks` becomes the constant macro; rig statics/functions disappear; `col_order` remains used by unconditional initialization; `col_map_fault` remains referenced; and `sn32f2xx_col_map_fault()` has external linkage and a declaration. None of those introduces an unused-static warning.