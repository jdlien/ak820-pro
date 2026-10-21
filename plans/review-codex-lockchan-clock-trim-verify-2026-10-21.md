**I would hold the firmware/daemon pair pending daemon fixes.** The firmware correctness findings are closed, and the propose/publish split is correct. Main HEAD `4fa1ac12` still has paths that let host phase changes become rate trim.

Firmware paths below are under `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`.

1. **Must-fix — a host step before the anchor can go unmarked.** [sender.rs:1013](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1013) captures `stepped` before warm-up, quiet and preamble. The payload samples the wall clock later, at line 1026; continuity checking starts from that new sample. A step between those points therefore produces a complete frame containing the new time **with flags 0**. Completion then rebases the scheduler, hiding the discontinuity permanently. With an eligible 600-second window, a +1-second step falsely changes **32500→32473**. Compare the anchor sample against the scheduler’s previous reference before choosing the flag. Add a warm-up/preamble injection test; the new test injects its step after the anchor.

2. **Must-fix — local send completion does not establish that the board received STEPPED.** [clock.rs:169](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:169) clears the marker after a credited send, but this channel has no clock-application acknowledgement. If the marked frame is lost or rejected, the board retains its old trim window. The next plain frame can learn the host step: +1 second over a retained 1200-second window gives **32500→32487**. Retain suppression through a conservative interval covering the firmware’s maximum eligible window, or introduce receiver-visible continuity tracking. Repeating the marker a fixed number of times only reduces this risk.

3. **Must-fix — process startup assumes continuity it cannot know.** [clock.rs:77](/C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:77) defaults `stepped` to false; the first observation has no previous reference. Restarting the daemon while the board retains an eligible window can therefore send an unmarked frame after an unseen host step. Preserving the marker across `acquired()` fixes reacquisition within the process, but not this case. Treat initial continuity as unknown unless a fresh board baseline is established.

4. **Should-fix — lifecycle test coverage is improved, but the previous finding is only partially closed.** [lockchan_media_test.c:492](/C:/Users/jdlien/code/ak820-pro/scripts/lockchan_media_test.c:492) exercises the real pure helpers. However, the setter remains fake at line 24, and `rtc.c` is not linked. Removing the actual SOF-exit drop, legacy-set drop or wake increment would leave these tests passing. So would moving publication before a rejection or reverting `P_set` usage. Add coverage of those production transitions and setter acceptance paths.

The previous findings resolve as follows:

| Previous finding | Status and evidence |
|---|---|
| Full-width offset before the 1% cap | **Closed.** [rtc.c:1347](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1347) passes `o`, not saturated `off`; the arithmetic guards precede multiplication. |
| SOF exit must invalidate | **Closed.** [rtc.c:708](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:708) drops the window. |
| Legacy setter must not establish a baseline | **Closed.** [rtc.c:1297](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1297) drops it. |
| Zero-counted-second deep sleep | **Closed.** [rtc.c:1889](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1889) increments in `rtc_wake_beginI`; `sleep.c:604` calls it whenever actual sleep occurred. |
| Lifecycle tests | **Partially closed**, as described above. |
| Publish only on acceptance | **Closed.** Ordering checked below. |
| Broader noise simulation | **Closed for the requested extension.** [lockchan_media_test.c:464](/C:/Users/jdlien/code/ak820-pro/scripts/lockchan_media_test.c:464) includes the +109 ms tail. My independent replay peaks at **184.4 ppm** from frame six onward. |

The **propose/publish split checks out**:

- [rtc.c:1356](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1356): both slew `D` and its per-second correction budget use `P_set`. Publication at line 1365 precedes `SLEW_START` at 1367, so the ISR uses the proposed nominal period.
- [rtc.c:1386](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1386): both parts of the step’s first-period calculation use `P_set`. Publication at 1401 follows the final rejection at 1396. The window opens after `clock_gen++`; the second `ft_accepted()` does not count another trim.
- **Note:** I found no new harmful ISR interleaving in this change. Sign, units and flag isolation remain correct. `STEPPED` suppresses learning without becoming `FORCE_STEP`.

**Note — the counters script is correct.** [lockchan_clock_counters.py:43](/C:/Users/jdlien/code/ak820-pro/scripts/lockchan_clock_counters.py:43) matches the firmware’s offsets 14 and 16. “Last period” means the last *frame-trim result*, not necessarily the current nominal period after USB/SOF resumes.

**Flash recommendation:** `01abfe0e` itself has no new must-fix from this review, but I would fix the daemon before giving the requested paired test a go. For that attended BT test, watch:

- **An uninterrupted battery interval:** keep the board awake and the slider on BT. Allow six eligible ten-minute windows, plus handover and any discontinuity quarantine. Reconnecting USB between samples invalidates the experiment.
- **Convergence:** the first accepted frame after SOF exit establishes the baseline without trimming. Later eligible frames should reduce drift; negative offsets should increase the divider. Watch for oscillation, rail-hitting or unexplained trim-count increases.
- **Invalidation:** brief USB reconnection, legacy sets and deep sleep—including zero counted seconds—must prevent learning across the interruption.
- **Host discontinuities:** test steps before the anchor and during transmission, a lost marked frame, and daemon restart. None should produce rate learning from the discontinuity.
- **Health:** capture counters and stack watermarks before and after; watch resets, dropped keys, ≥25 ms stalls, UART errors and persistent retries. Stop on a zero stack watermark. Avoid USB polling during the battery run.

I verified the exact commit objects, matching source files, and archived BIN/ELF hashes. Heap remains **32 B**, with **1024/2048 B** reserved stacks. Native execution was denied, so I did **not** rerun C/Rust tests or mutation tests; arithmetic results above are independent replays. The saved daemon status reports `d557e13`, so it does not establish deployment of reviewed HEAD.
---

## Dispositions (gremlin session, 10-21)

The firmware findings are closed, and 01abfe0e is unchanged. The three daemon must-fixes share one cause: the channel is one-way. The fix is a quarantine in `clock.rs`:

- **Must-fix 1, a step before the anchor:** taken. The build compares its anchor sample `w0`, and the payload's offset, against the scheduler's reference (`ClockSched::wall_ref`). A mismatch marks the frame STEPPED and starts the quarantine (`saw_step`) whatever the frame's outcome. Test: `a_wall_step_in_a_clock_frames_warm_up_marks_it_stepped`, with the step at the warm-up's second write.
- **Must-fix 2, a lost marked frame:** taken. Every frame for `QUARANTINE` (3900 s) after a discontinuity carries STEPPED. That is the board's `RTC_FT_MAX_S` (3600 of its seconds) with margin for its rate, so a plain frame's window spanning the step is too long to trim from. A frame sent whole no longer clears it. Only an acknowledged USB clock set after the discontinuity ends it early (`Handle::usb_clock_set`, called by agent.rs when `syncs` rises, not on failures), since that set is phase-correct and acknowledged.
- **Must-fix 3, process start:** taken. The first observation is a discontinuity, and nothing observed at all means STEPPED. A new daemon trims nothing for 65 min unless it completes a USB sync first. The first-frame test now expects STEPPED.
- **Should-fix 4, rtc.c's transitions untested on the host:** partly. The pure window is tested, and the production calls (`rtc_ft_drop` at SOF exit and in `rtc_set_time`, `ft_sleeps++` in `rtc_wake_beginI`, publication after the step's last reject, P_set in the slew and the step) were checked by both codex rounds. Linking rtc.c needs the ChibiOS HAL stubbed, which is out of scope for this test. The attended BT test reads `rate trims` and `last period` (op 17 sub 8), with USB replugs and sleeps planned as invalidations.

Mutants, each caught: the build's own step check removed, `saw_step` removed, the first-observation rule removed, the USB end removed, the expiry removed.
