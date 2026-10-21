**I would hold the pair for one further daemon fix. Must-fix 1 and 3 are closed; must-fix 2 is only partially closed because the new USB escape hatch can clear a newer discontinuity.** Firmware `01abfe0e` remains cleared by the source review.

1. **Must-fix — the USB event has the wrong timestamp.** [agent.rs:485](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:485) passes `Instant::now()` **after `clock.tick()` returns**, rather than a timestamp belonging to the successful SET. After receiving its SET acknowledgement, the tick still performs verification, status reads and cache work ([transaction.rs:409](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/clock/transaction.rs:409), [agent.rs:963](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:963)).

   A concrete ordering is: SET acknowledged at 100; sender observes a host step at 101; tick returns and reports `usb_clock_set(102)`. [clock.rs:121](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:121) then clears the quarantine, although the board was set **before** the step.

   The sender can remain granted while the daemon is inside that tick. A brief USB reconnection need not qualify SOF—entry requires three accepted samples ([rtc.c:690](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:690))—so SOF-exit invalidation does not necessarily rescue this. Marked frames can be refused during USB ownership; a later plain frame can still learn the step.

   **Fix:** carry the successful SET’s clock-sampling instant, or conservatively capture an instant immediately **before `clock.tick()`** and use that on success. Keep the completion timestamp for `usb_clock_synced()`’s refusal delay. Add a regression for a step between SET acknowledgement and tick completion.

2. **Should-fix — production lifecycle coverage remains partially open.** [lockchan_media_test.c:24](/C:/Users/jdlien/code/ak820-pro/scripts/lockchan_media_test.c:24) still substitutes a fake setter; the lifecycle assertions at line 492 exercise the pure helpers. Your disposition accurately describes this limitation. The production calls remain correct on inspection, but those tests cannot detect their removal or reordering.

The original findings otherwise resolve as follows:

| Finding | Verdict |
|---|---|
| **1: step before anchor** | **Closed.** [sender.rs:1057](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1057) compares the anchor’s wall sample and payload offset against the scheduler reference. Line 1076 starts quarantine regardless of send outcome. The warm-up injection test targets the original hole. |
| **2: lost marked frame** | **Quarantine mechanism fixed; not fully closed.** `sent()` no longer clears suppression, and reacquisition preserves it. The USB ordering defect above provides a premature escape. |
| **3: startup continuity** | **Closed.** [clock.rs:120](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:120) marks unknown continuity; line 180 starts quarantine at the first observation. |

**Notes on the quarantine reasoning:**

- **3900 seconds is adequate for the measured awake board rate, not an unconditional bound.** [clock.rs:84](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:84) requires the board to accumulate more than 3600 seconds before expiry: approximately **0.9231 board seconds per host second**, allowing just under 7.7% slowness before boundary allowances. At 1% slow, it accumulates 3861 seconds. The documented roughly 0.6–0.9% variation fits comfortably. The allowed divider range alone does not prove this rate bound.
- **Board deep sleep does not undermine that argument.** Every actual sleep increments `ft_sleeps`, including zero-counted-second sleeps; [rtc_payload.h:114](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc_payload.h:114) rejects the retained window. Its 13–16% sleeping slowdown therefore need not fit the timeout margin.
- **An acknowledged USB SET after the discontinuity is a valid early exit in principle.** It replaces the board’s baseline; failures do not earn that exit. The defect is establishing its chronology using tick completion.
- **Host sleep differs by platform.** Windows `Instant` uses QPC, which includes suspend time; ordinary sleep alone therefore need not appear as a step. macOS uses `CLOCK_UPTIME_RAW`, which excludes sleep: a wall/monotonic mismatch exceeding 500 ms starts another quarantine. That extends suppression conservatively. ([Rust implementation](https://doc.rust-lang.org/src/std/sys/time/unix.rs.html), [Windows QPC documentation](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps))
- **STEPPED remains isolated from FORCE_STEP.** [ch582f_ajazz.c:492](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:492) maps it to omission of `RTC_SETF_FRAME`; ordinary phase correction still operates.
- **Startup can quarantine even after an earlier USB sync.** Observations run only while granted ([sender.rs:655](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:655)). Starting on USB and first acquiring BT later creates a newer first-observation quarantine. Safe, but budget those 65 minutes into the test.

**Flash recommendation:** fix the USB timestamp ordering, install that daemon, then proceed with JD’s attended BT test using `01abfe0e`. I found no additional firmware blocker. Keep the convergence interval uninterrupted and awake; perform USB/sleep invalidation trials separately.

I verified main’s exact commit/parent objects, matching reviewed source files, and the archived firmware BIN/ELF hashes. Native execution was denied, so I did **not** rerun Rust/C tests or the reported mutants. The ordering counterexample and arithmetic above were independently replayed in JavaScript; installed-daemon identity was not verified.
---

## Dispositions (gremlin session, 10-21)

- **Must-fix 1, the USB set's timestamp:** taken. agent.rs takes `before = Instant::now()` ahead of `clock.tick()` and passes it to `usb_clock_set` on a success; the SET comes after it, so a step seen in the tick's tail stays after the set and quarantined. `usb_clock_synced` keeps the completion time for the refusal floor. The regression is at the scheduler level: `a_step_or_an_offset_change_marks_frames_for_the_quarantine` shows that a set before the step does not end the quarantine. The agent loop's ordering itself is not unit-tested.
- **Note, starting on the cable:** taken, because it would have spent JD's test. The sender observes on every pass while the clock is on, granted or not, so a daemon started on the cable makes its first observation at its first pass, and a USB set after that ends the start's quarantine. Only a granted channel schedules frames. Test: `a_daemon_started_on_the_cable_is_trusted_after_a_usb_set`, which fails if observation is restricted to granted passes again.
- **Should-fix 2, rtc.c's lifecycle on the host:** unchanged from the last disposition. The attended test covers it on the hardware.
- **The other notes (the 3900 s margin, sleep, platforms):** agreed, no change.
