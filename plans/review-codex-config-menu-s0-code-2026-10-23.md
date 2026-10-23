# Codex review: the configuration menu's S0 code (2026-10-23)

S0 as committed on firmware `gremlin/config-menu` `dde661d1` and ak820-pro
`warren/config-menu` `25bc13d`, before any flash. The model was gpt-6-astra at
xhigh, read-only, run from gremlin, with the prompt in
[`review-prompt-config-menu-s0-code.txt`](review-prompt-config-menu-s0-code.txt).
Codex's answer follows verbatim, then the dispositions.

---

**S0 is not ready to flash on gremlin’s test board yet.** There are reproducible op-27 completion defects, incomplete wake integration, and gaps in the required host proof.

I verified that the 22 changed firmware files match `dde661d1`, compared them with `b9555ff3e6`, and verified the four host files against `25bc13d`. All file access stayed inside the repository. This is a static review: process creation was denied, so I could not rerun gcc tests or builds. Nothing was changed or flashed.

1. **Must-fix — coalescing can strand a synthetic mutation or report discarded input as done.**  
   [menu_input.c:157](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_input.c:157), [menu_input.c:218](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_input.c:218)

   Accept synthetic `+1`, then capture physical `−1` before `menu_task()`. The resulting `turns=0`, `latch=NONE` makes `mi_take()` return before retiring `owed`. `op27_poll()` does not handle this kind, so subsequent mutations remain busy until another event or the idle close rescues it.

   Conversely, accept a synthetic click or turns, then latch a physical close. `mi_take()` discards the turns and returns close, but marks the synthetic mutation **done**, although its action was discarded.

   **Fix:** track completion independently of whether the coalesced result is nonempty. Retire a zero-net action when the task processes that batch; report superseded/cancelled when precedence or close discards its action. Add both cases to the tests.

2. **Must-fix — physical navigation can erase pattern 2’s completion condition.**  
   [menu_slots.c:33](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:33), [menu_fixture.c:123](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:123), [menu_glue.c:104](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:104)

   Start partial B, then turn the physical knob before the stop. `fx_input()` calls `ms_retarget()`, whose `new_target()` clears `stop_n` and `stopped`. The outstanding `MI_KIND_PATTERN_STOP` now waits for a stop that cannot occur while MENU remains open. Physical navigation after an already completed stop also releases it, contrary to “holds until the next sub 0.”

   **Fix:** give the partial-stop request an explicit lifetime. Retargeting that disposes of pending work must retire its sequence; a completed stop must remain held until the specified release operation. Test physical turns, clicks, layout changes and ownership changes around the stop.

3. **Must-fix — the non-DASH wake predicate still waits on abandoned dashboard queues.**  
   [display.c:3446](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3446), [display.c:2950](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2950), [display.c:3614](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3614)

   `display_wake_repainted()` uses `display_bus_idle()` under another owner. That predicate includes `gq` and `lq`, but ownership entry neither discards those queues nor drains them under MENU/DEBUG/ANIM.

   For example, switch to DEBUG during a DASH wake after clock glyphs were queued. Even after the DMA finishes, the new wake predicate remains false. Those queues also block `rtc.c`’s wake admission. C1’s promised non-DASH wake fix therefore still falls back to recovery timeouts.

   **Fix:** discard obsolete dashboard queues at the ownership boundary after quiescing, and make the non-DASH wake check depend on actual bus activity rather than dormant dashboard work. Test the handoff with nonempty queues.

4. **Must-fix — the host tests omit the integration where these failures live.**  
   [menu_s0_test.c:8](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:8), [menu_s0_test.c:318](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:318), [menu_s0_test.c:419](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:419)

   The tests genuinely compile four production modules. However, they do **not** compile `menu_glue.c`, `display.c`, or the HID dispatcher. “Other owners’ handlers” checks returned action bits, not the handlers. “Op27 flight” checks input helpers, not op 27.

   Consequently they do not prove wire validation/framing, arm/disarm, injected-loss disposal at a handoff, the actual wake path, or the required frozen-Camera pumping test. The hold test also delays taking Back until release; production `menu_task()` takes it at 600 ms and performs the boundary then.

   **Fix:** add tests executing the production glue and relevant display integration with backend stubs—or extract those implementations into production modules that both builds use. Include the contract’s missing integration cases and findings 1–3.

5. **Must-fix — the session script can report success without satisfying S0’s proof.**  
   [menu_s0_session.py:74](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:74), [menu_s0_session.py:179](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:179), [menu_s0_session.py:189](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:189)

   The 50-step array has the correct **28/10/4/4/2/2** mix. But:

   - Poll observations inside `wait()` are discarded, so transitions seen while polling are not recorded.
   - A timeout or refused/superseded result is not itself a failure if the final coordinates match.
   - The final close’s status/outcome and final DASH/NONE state are not enforced.
   - The required five-minute dashboard interval with a track playing is absent.
   - A positive ge25 delta is printed but does not fail the run.

   **Fix:** retain polling observations, define allowed outcomes per step—including legitimate hold cancellation—validate setup and final restoration, implement the five-minute interval, and enforce the timing criterion without resetting counters inside the span.

6. **Should-fix — the wake-while-OPEN transition is never connected to a real wake.**  
   [display.c:3408](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3408), [panel_owner.c:183](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:183)

   `PO_EV_WAKE_WHILE_OPEN` has an implementation and a unit test, but no production caller. An unexpected wake while OPEN therefore sets neither the sticky failure bit nor `close_on_release`; releasing the hold leaves the session open.

   **Fix:** post that event from the main-thread wake path when the session is OPEN. Test through `display_sleep_wake()` and release, rather than calling the owner event directly.

7. **Should-fix — navigation restarts an in-progress layout clear.**  
   [menu_slots.c:40](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:40), [menu_s0_test.c:528](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:528)

   `ms_set_layout()` unconditionally sets `clear_band=1`. Switch F1→F2, clear two bands, then navigate back: the sweep restarts instead of finishing its remaining bands. Repeated navigation can indefinitely delay completion. The test verifies eventual pixels, so it misses this contract violation.

   **Fix:** preserve the clear cursor when changing targets during the same MENU-owned sweep. Still force a fresh sweep on opening or returning from another owner. Assert the actual band sequence in the test.

8. **Should-fix — byte 29 counts armed glyphs as completed operations.**  
   [menu_slots.c:61](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:61)

   `ops++` happens immediately after `mb_glyph()` arms DMA. While that transfer remains busy, sub 5 reports it as a completed operation. Pattern 2’s stopped flag correctly waits for the bus, but the separately exposed count does not follow C9’s definition.

   **Fix:** count asynchronous operations when their transfer completes or fails; count synchronous fills on return. Test reads between arm and completion.

9. **Should-fix — A and B do not visibly differ in every slot.**  
   [menu_fixture.c:60](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:60), [menu_fixture.c:73](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:73)

   Separator and scrollbar signatures change with the pattern, but their pixels use the same colours in A and B. A skipped repaint of either slot is therefore invisible in the partial-B proof. The expected framebuffer reproduces this discrepancy.

   **Fix:** make these slots visibly pattern-dependent in the shared tables. Also reconcile the scrollbar’s x125–127/y15–127 footprint with C8’s x125/y15–126 geometry.

10. **Should-fix — C4’s scratch assertions are missing.**  
    [lcd_bus.c:143](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:143), [lcd_bus.c:241](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:241)

    Acquisition merely increments a counter on overlap and continues; release checks nothing. A nested stream can overwrite the active window and byte accounting, while an unmatched release or short stream ends silently.

    **Fix:** add the specified debug acquire/release assertions and stream completion checks. Current S0 callers appear balanced; this is a missing guard on the new API, not evidence of a current overlap.

11. **Should-fix — refused animation starts still access flash and may wait on DMA.**  
    [ak820pro.c:380](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:380), [lcd_bus.c:1156](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1156)

    `ANIM_TOG` now always calls `anim_toggle()`, which reads the header before checking admission. Fn+Delete under DEBUG, MENU, PENDING or a restore can therefore quiesce/wait/recover an in-flight transfer before being refused. The previous DEBUG guard avoided that work.

    **Fix:** reject an inadmissible inactive start before flash access. Continue validating the header before actually changing ownership, and always allow an active animation to stop.

The remaining implementation is substantially aligned with the contract:

- **C1:** the restore phases, RESIDUAL priority, immediate recording of a second loss during cooldown, DONE conditions and wake-generation handling are implemented. Camera dispatch is exclusive; the loss handlers invalidate the appropriate page. `QUIESCE_DROP` waits before dropping the loss and correctly supersedes an injected-loss sequence. Visibility is published after setup. The removed flags have no remaining live uses.
- **C2:** matrix/encoder identity and Fn detection match QMK. Release routing runs first; capture bits survive close/handoff; forwarded releases remain forwarded; synthetic input does not alter physical capture. I found no new captured-event leak or stuck-key path in that routing. `menu_task()` is correctly before the pump.
- **C3/C4/C7:** current-target signatures participate in settlement; partial slots restart correctly; menu and restore clear failures retain their band; commits wait for idle/no loss. Scratch remains held through synchronous SPI sends. The shared effective-backlight calculation, wake hold applied last, visibility override and `DSB_MENU` decoder index are correct.
- **Op 27:** byte layout, status values, sequence wrapping, handled reply byte 0, short-report rejection and argument ranges are otherwise consistent. A 650 ms hold becoming **cancelled** when its 600 ms Back closes/hands off is a legitimate terminal outcome.

For timing, I found no new routine full-screen synchronous clear. The relevant costs remain a synchronous clear band, an F1 half-row/F2 tile fill, up to three synchronous battery-text glyphs in RESIDUAL, and the bounded wait in `po_apply()`. A transition’s wait and the pump’s next operation can occur in the same pass, so the painter’s one-operation rule does not establish the whole-pass bound. The repaired workload must measure it. The startup callback only installs work; the DMA callback and backlight ISR do not acquire or paint through scratch.

[build.sh:197](C:/Users/jdlien/code/ak820-pro/build.sh:197) correctly computes the heap gap from the two linker symbols, rejects missing symbols and gaps below 128 B, and checks before publication. `devfault` includes all dev flags plus `WDT_TEST_HOOKS` and follows dev’s structural checks. I found no defect in those changes; the reported 360 B dev gap exceeds the floor by 232 B.
---

## Dispositions (Warren, gremlin, 10-23), fixed in firmware `321360c6` and ak820-pro's `warren/config-menu`

The verdict, not ready to flash, is agreed. Every finding is taken; the host
tests now cover the findings that live in pure code.

| # | Disposition |
|---|---|
| 1 | **Fixed.** `mi_take()` returns a batch whenever a synthetic action is owed, so a net-zero batch still ends it. A synthetic action whose latch is replaced by a higher one, or whose turns a close discards, ends superseded. Tests: a synthetic +1 against a physical -1 (done), a synthetic click against a physical close (superseded). |
| 2 | **Fixed.** The stop has a lifetime. A new target disposes of a pending stop, and op 27's poll ends its sequence superseded (`ms_stop_cancelled_take`). A reached stop holds through navigation until the next sub 0 (`ms_stop_release`). A layout change releases either. Tests: a physical turn before the stop (superseded), a turn after it (held), then sub 0 (released). |
| 3 | **Fixed.** Leaving the dashboard drops its queued glyphs after the quiesce: nothing drains them under another owner, and the restore at that owner's exit repaints from a clear and fresh shadows. `display_wake_repainted()` under another owner now waits only for `!lcd_blit_busy()`. Board-proved, not host-proved: `display.c` isn't built on the host (row 4). |
| 4 | **Partly taken.** `menu_task`'s logic, op 27 and the menu's side of an owner event moved into `menu/menu_ops.c`, pure. The host tests now run them with a fake environment (`env_po_event` is `po_event` plus the production `menu_ops_apply`). They cover op 27's validation, single flight, every completion and disposal path, arm and disarm, the pending opening and the wake notice, the idle timeout, and the hold through the production task (cancelled at 600 ms when Back closes; a 300 ms hold a click). **Not host-tested:** `display.c`'s side. The wake predicate (3), the Camera dispatch and `po_apply`'s display actions stay in `display.c`, which isn't built on the host. Extracting them is a larger change than S0 warrants. The Camera dispatch is a single exclusive `return`; it and the wake rule are proved on gremlin's board (a loss injected on the Camera page, photographed; the restore's phases read from sub 5). |
| 5 | **Fixed.** The script records every change seen while polling. It allows per step only the expected outcomes (a hold: done or cancelled), and fails on a timeout. It checks the setup and the final close, and waits for the dashboard restored. It runs the five-minute dashboard interval with no counter reset, records the daemon's now-playing line, and fails on any ge25 or invariant failure. |
| 6 | **Fixed.** `display_sleep_wake()` posts the wake-while-open event when the session is OPEN. |
| 7 | **Fixed.** `ms_set_layout(l, fresh)`: navigation keeps a running clear's band, while opening and coming back from another owner sweep afresh. Test: two bands, a layout change, then eight bands in all. |
| 8 | **Fixed.** An armed DMA's operation counts when its transfer ends; a fill counts at once. Test: read between the arm and the completion. |
| 9 | **Fixed.** The separator, the scrollbar's track and its thumb differ between A and B. The scrollbar is C8's x 125, y 15-126. The expected frames follow. |
| 10 | **Fixed.** Dev builds flag a second acquire, a release without one, a nested stream, an overlong write and a short end, as sticky `PO_FAIL_SCRATCH` and `PO_FAIL_STREAM`. |
| 11 | **Fixed.** `anim_toggle()` asks `display_anim_admissible()` before reading the header. |

---

## Codex's verification of the fixes (round 2), verbatim

The fixes as firmware `321360c6` and ak820-pro `452f06c`, with the prompt in
[`review-prompt-config-menu-s0-code-verify.txt`](review-prompt-config-menu-s0-code-verify.txt).

**S0 is not ready to flash on gremlin’s test board yet.** Eight findings are fixed. Findings **2, 4 and 5 remain partly fixed**, with the remaining issues affecting the partial-paint contract or the validity of S0’s proof.

I verified that all 25 firmware files changed since `b9555ff3e6` match `321360c6`, and both reviewed host scripts match `452f06c`. All file reads stayed inside the workspace. Process creation was denied, so this is a static verification; I could not independently rerun the reported passing tests or build. Nothing was changed or flashed.

1. **Fixed — original must-fix closed: synthetic completion bookkeeping.**  
   [menu_input.c:61](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_input.c:61), [menu_input.c:171](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_input.c:171).

   Synthetic `+1` followed by physical `−1` now produces an owed, empty batch, which retires normally. Replacing a synthetic click with Back/close, or discarding synthetic turns with close, records `syn_lost` and ends superseded. Input clearing and `mi_finish()` reset the associated bookkeeping. The new production-task tests exercise the two reported failures.

   **Further fix:** none for the reported defect.

2. **Partly fixed — must-fix: a layout change still releases a reached stop.**  
   [menu_slots.c:59](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:59), [menu_slots.c:101](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:101), [menu_fixture.c:140](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:140).

   Pending-stop cancellation is correct: retargeting sets `stop_cancelled`, and polling retires the sequence as superseded. A reached stop also survives ordinary turns and pattern-toggle clicks.

   **Remaining scenario:** settle A at row 6, request partial B, wait for stopped/done, then physically click into F2. `ms_set_layout()` clears `stopped`, and painting resumes without another sub 0. This exception is stated in the disposition, but contradicts revision 6’s explicit “holds until the next sub 0.” The new test covers turns, not this layout-changing click.

   **Fix:** preserve a reached stop through ordinary, same-owner layout navigation. Prevent the pending clear from running while held—merely removing the assignment to `stopped` is insufficient because clearing precedes the stop check. Test layout clicks as well as turns, and distinguish navigation from fixture teardown/reopening.

3. **Fixed — original must-fix closed: abandoned dashboard queues.**  
   [display.c:3621](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3621), [display.c:3450](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3450).

   The reported DASH-wake→DEBUG handoff now quiesces DMA, consumes any loss, and discards both dashboard queues and their shadows. `po_event()` has already changed the owner, so the non-DASH condition is appropriate. Other non-DASH handoffs redundantly discard empty queues harmlessly.

   Non-DASH wake completion now depends only on actual DMA activity. This fits [sleep.c:813](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:813): release still waits for gauge accounting, then accepts this predicate instead of waiting on abandoned dashboard work.

   **Further fix:** none found in the implementation; the specific board regression test remains necessary under finding 4.

4. **Partly fixed — must-fix for proof: the extraction is useful, but the named board substitutes are insufficient.**  
   [menu_s0_test.c:577](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:577), [menu_s0_test.c:597](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:597), [menu_s0_test.c:646](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:646).

   **The reasoning for leaving `display.c` outside the host build holds.** The tests now execute production `menu_ops_task()`, `menu_ops_op27()` and `menu_ops_apply()`. This closes the most consequential previous gap, including the hold being cancelled by the real task’s Back at 600 ms.

   However, the fake environment still implements quiescing/loss disposal itself. Its queue depths are always zero; battery and logo work are always absent. DEBUG and ANIM loss actions are not executed by its pump. “Framing” tests call the inner handler directly and do not test short-report rejection or the HID dispatcher.

   A Camera photograph after an injected loss and observations of restore phases do **not** establish the omitted wake and dispatch properties. Required substitutes should explicitly include:

   - Camera fully settled, values/time frozen, then continued pumping long enough to expose Health-grid fall-through; compare before/after pixels.
   - A DASH wake with demonstrably nonempty `gq`/`lq`, followed by handoff: verify queue disposal and wake release without the 500 ms fallback or display timeout bit.
   - The real wake-while-OPEN entry and release path.
   - An injected loss disposed of during a real ownership boundary, plus the contract’s real DMA retry/give-up tests.

   **Fix:** specify these as executable board acceptance cases and add focused host coverage for the remaining wire wrapper where practical. The dispositions’ “board-proved” wording describes future work: nothing has been flashed.

5. **Partly fixed — must-fix: the session script can still certify an incomplete workload.**  
   [menu_s0_session.py:248](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:248), [menu_s0_session.py:257](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:257), [menu_s0_session.py:281](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_session.py:281).

   The important repairs are present: polling observations are retained for mutations; unexpected terminal outcomes and timeouts fail; final close/restoration are checked; the default dashboard interval is five minutes; positive ge25 deltas fail.

   **Remaining scenario:** run with no track playing—or stop playback before the dashboard interval. Missing media only prints a note, and the script can return zero. Its two media observations bracket the entire run, so even two “play” observations do not establish playback through the dashboard interval.

   Also, a decreasing ge25 counter is accepted, although a reset makes that measurement invalid. Restore observations inside `wait_restored()` are still discarded.

   **Fix:** require and periodically verify playback during the dashboard interval, fail an invalid measurement span, and retain restore-poll transitions. Clearly identify shortened runs as smoke tests rather than full S0 proof.

6. **Fixed — original should-fix closed: wake while OPEN is connected.**  
   [display.c:3408](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3408).

   `sleep.c` reaches this function through `recovery_begin()`. It sets the wake hold before posting `PO_EV_WAKE_WHILE_OPEN`; the owner records the sticky failure and deferred close. The release notice reaches the production task and closes the session.

   **Further fix:** none found in the wiring. The host test still invokes the owner event directly; it does not execute this display entry point.

7. **Fixed — original should-fix closed: navigation restarts the clear.**  
   [menu_slots.c:59](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:59), [menu_fixture.c:93](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:93).

   `fresh=false` preserves an existing clear cursor; opening and returning from Diagnostics use `fresh=true`. Thus F1→F2→F1 after two bands finishes the remaining six. The new test asserts eight successful bands total, catching the former restart.

   **Further fix:** none for this defect; stop gating is the separate issue in finding 2.

8. **Fixed — original should-fix closed: completed-operation counting.**  
   [menu_slots.c:38](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:38), [menu_slots.c:87](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:87).

   An armed glyph records `ops_inflight`; settlement increments once when the bus becomes idle. Synchronous fills count on return. Retargeting resets accounting for the new target. The test actually reads the count before and after fake DMA completion.

   **Further fix:** none found for the reported early-count defect.

9. **Fixed — original should-fix closed: invisible A/B differences.**  
   [menu_fixture.c:23](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:23), [menu_fixture.c:75](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_fixture.c:75).

   Separator, scrollbar track and thumb now have different A/B colours. The scrollbar occupies x125, y15–126, matching C8. Expected-frame calculations follow that geometry.

   **Further fix:** none.

10. **Fixed — original should-fix closed: missing scratch/stream diagnostics.**  
    [lcd_bus.c:151](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:151), [lcd_bus.c:244](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:244).

    Double acquisition, unmatched release, nested streams, excess writes and short endings now produce sticky dev failures. These are diagnostic checks that continue execution, rather than aborting assertions; they make such misuse invalidate the board proof. I found no newly introduced imbalance in the current callers.

    **Further fix:** none required for S0’s diagnostic purpose. These paths are not exercised by the host suite.

11. **Fixed — original should-fix closed: refused animation reads/waits.**  
    [lcd_bus.c:1199](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1199).

    Inactive, inadmissible starts return before `anim_read_header()` and its flash transaction/quiesce. Header validation still precedes ownership acquisition; the active-stop branch remains unrestricted. `lcd_flash_init()` still precedes admission, but it does not perform the problematic header read or DMA wait.

    **Further fix:** none for the reported failure.

The extraction leaves **physical event classification and Fn-layer detection** in [menu_glue.c:51](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:51). Thus “everything with a decision” is literally overstated, but the remaining decisions are the QMK adapter; I found no menu-policy regression there. The op-27 request/reply implementation is guarded by `AK820_DEV_HOOKS || MENU_HOST_TEST`; the firmware wrapper and HID dispatch are dev-only. Common input/completion machinery remains shared.

The changed `po_apply()` order is sound: quiesce/drop/discard precede display setup, `menu_ops_apply()` retires dropped loss work before clearing input/opening the fixture, and visibility is published last.

**The host tests do run production code—five production modules—but establish a narrower result than “every completion and disposal path” or full integration proof.** They meaningfully test the new pure-code fixes. They do not establish real display, sleep, bus, HID-wrapper or Camera behaviour.

The remaining pre-flash work is to close finding 2, make finding 5’s success criterion enforce the workload, and make finding 4’s substituted board procedure explicit and sufficient. The reported passing build and 360 B heap gap do not resolve those issues.
---

## Dispositions (Warren, gremlin, 10-23), fixed in firmware `f583c15b`

| # | Disposition |
|---|---|
| 1, 3, 6-11 | Fixed, as codex found. |
| 2 | **Fixed.** A reached stop now holds through a layout change too. `ms_step()` checks the stop before the clear, so no clear runs while held. Only the next op 27 sub 0 (`ms_stop_release`) or a fresh screen (opening, or coming back from another owner) lets it go. The test now clicks into F2 while stopped (no band runs, the stop held), then sub 0 releases it and the clear finishes. Writing that test also exposed a firmware hazard: the idle timeout compared unsigned, so an input stamped a moment after `now` read as a wrapped 49 days. It now compares signed. |
| 4 | **Agreed.** The board's cases are now written down as executable acceptance cases, [`CONFIG-MENU-S0-BOARD-TESTS.md`](CONFIG-MENU-S0-BOARD-TESTS.md), A1-A12. They include each one codex named: Camera's dispatch photographed after 30 s of pumping, with its static cells checked (A2); the queues dropped at a real handoff (A3); a real dashboard wake handed to Fn+D, with the sleep page's display timeout bit (A4); an injected loss at a real ownership boundary (A6); and the devfault retry and give-up under each owner (A7). Two of them can't be run as codex described. **The Camera's values can't be frozen** on the board, since the clock moves, so A2 checks the static cells instead. **The wake-while-open path is unreachable by design** (DSB_MENU), so A5 checks the blocker, and its handling stays the host test's. The wording "board-proved" in round 1's dispositions meant these future cases; nothing has been flashed. |
| 5 | **Fixed.** A track must be playing through the dashboard interval, checked every 30 s from the daemon's now-playing line, unless `--smoke` (reported as not S0's proof; a shortened run also needs `--smoke`). A counter that went backwards, or a missing one, makes the span invalid and fails it. The restore's polls are recorded. |
