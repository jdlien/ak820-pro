**No P1 found. One remaining P2 path and one P3 timing issue prevent the blanket “never outlives the title” claim.**

1. **P2 — Raw HID can clear the title while leaving lock-channel playback running.** This is inherited behavior. [`TEXT_CLEAR`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:375) calls `display_clear_text()` without retiring playback.

   **Failure:** type 1 at t=0, type 3 at t=1s, raw HID clear immediately afterward; without a subsequent playback update, the title disappears while its lock-channel readout survives until approximately t=136s.

   **Fix:** track playback’s source and retire lock-channel playback when its title is cleared or becomes absent. Preserve raw HID playback’s independent lease.

2. **P3 — The cap is not an exact shared deadline, and repaint cadence permits a brief orphan readout.** [`lockchan_media_commit()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:453) samples the remaining lease before `display_set_playback_for()` takes a newer timestamp.

   **Failure:** sample at title age 179,999ms → `left=1`; stamp playback at 180,000ms. At 180,001ms the title expires, but playback’s strict `>` test still retains it. Independently, title expiry runs around 10Hz while playback expiry runs with the 1Hz clock, allowing the readout to remain until the next clock service.

   **Fix:** use one timestamp for calculating and assigning the capped deadline, and retire/repaint lock-channel playback when title expiry is serviced.

The other checks pass:

- **Arithmetic/boundary:** unsigned elapsed subtraction handles rollover; subtraction occurs only below 180,000ms, preventing underflow. The 135,000ms cap is sound. At exactly 180,000ms, admission rejects while `draw_text_slot()` still retains the title: a conservative one-millisecond boundary, not an unsafe admission.
- **Other paths:** type 1 renews text **and switches playback off**; type 2 and `display_sleep_wake()` clear both. When both expiries are serviced well overdue, `draw_clock()` expires playback before choosing its owner; there is no renewed 135-second tail.
- **Raw HID playback:** its setter still replaces the timeout with **20,000ms**, independently of the title cap.
- **Artifact:** both manifest hashes match; every file-backed ELF LOAD segment matches the BIN; `health_fill6` emits **`0x2e279a39`**. `ds_deep_wfi` remains at **`0x2000150c`**, with its PMU literal and 260-iteration wake delay in SRAM. `.data` **2,752 B**, `.bss` **26,832 B**, RAM gap **96 B**, MSP/PSP **1,024/2,048 B**—unchanged from the parent.

Read-only verification; no rebuild or hardware run. Gremlin’s sender P2 2 is outside this review.

**Verdict: clear `845996c39c` / `0x2e279a39` for the attended dev bench flash; the stale-admission fix passes, but P2 1 is not fully closed across all title-removal paths.**