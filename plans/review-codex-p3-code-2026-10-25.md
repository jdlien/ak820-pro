# Codex on P3's code (Connection: the Bluetooth slots and pairing), 10-25

Prompt: `plans/review-prompt-p3-code.txt`. Line references are to `c66e6eaf`.
The fixes: firmware `47567935`; tests in this repo's next commit.

## Dispositions

1. **A key's hold still running can pair over a menu action (must fix):**
   taken. Every menu action (`bt_ui_select_slot()`, `bt_ui_pair_slot()`,
   `bt_ui_pair_stop()`, the new `bt_ui_pair_cancel()`) supersedes a slot
   key's or `Fn`+`P`'s hold: `bt_pair_armed` cleared and its hint taken
   down (`menu_supersedes()`). `btui.c`'s `hold_superseded`: a hold under a
   menu stop, a cancel, a select and a pair; only the menu's own pair goes,
   once. A mutant without it fails.
2. **"Already on BT n" leaves a pending pair armed (must fix):** taken. The
   branch calls `env_bt_pair_cancel()` (nothing sent). `test_p3` checks it
   with a pair waiting, connected and linking.
3. **The bounce's boundary takes the bounce slot's buffered 5B (must
   fix):** taken. `select_unsent`, set by `ch582_set_profile()` and cleared
   by the select frame's ACK or its give-up: a 5B or 5A before it neither
   counts for `select_acked` or `pair_confirmed` nor retires `PA_SELECT`;
   `ch582_select_state()` reads pending meanwhile. **Assumed, not measured:**
   the module ACKs a frame before it sends the 5B the frame causes. If it
   doesn't, the target's first answer is ignored and the next one counts,
   and the select may be resent once at 1.5 s; to check on the wire with
   the dev RX tap when the slider is on BT. `bounce_boundary` holds the
   ACKs, feeds a bounce-slot 5B 31 after the target's select is written:
   not confirmed, still pending, the pair still waiting; then the ACK and
   the target's own answer, and the pair. A mutant that counts it fails.
4. **The bounce slot's CONNECTED survives a lost target select (must fix):**
   taken. The bounce's real select leaves the link attempting, as
   `ch582_set_profile()` does (`conn_state` LINKING, `is_module_connected`
   false). `bounce_lost`: the bounce slot's 5B 32, then eight unanswered
   tries: lost, linking, no pair; `pair_bounce` checks linking after the
   700 ms select. A mutant without it fails both.
5. **The last select's try gets no window (must fix):** taken, for
   `PA_SELECT` and `PA_PAIR` alike: the give-up waits out the last try's
   interval. And `ch582_select_state()` is pending while the cold-boot retry
   still sends (`connect_requested && !module_alive`). `last_try_window` (an
   answer 1 s after the eighth try, then the pair) and `boot_retry_pending`;
   a mutant of each fails.
6. **A direct 5B 36 leaves the select pending (could wait):** taken: 36
   retires `PA_SELECT` as 33/34 do. `direct_36`; a mutant fails.
7. **The off-BT page's cursor inherits Reset's page (could wait):** taken:
   `menu_cursor()` returns 0 for it; `test_p3` checks it after Reset
   counters' second page.
8. **The stand-in's isolation has no regression test (could wait):** not
   taken now. `menu_glue.c` isn't compiled by the host tests; codex read the
   guards as correct. The board's pass runs on the cable, where `bt_ui`
   does nothing anyway.

RAM after the fixes: the dev gap is 136 B (unchanged), against the 128
floor.

## The review, verbatim

**Yes. I would fix these before the P3 flash.** I verified the reviewed files against the pinned commits. This is static review; process execution was unavailable, so I could not rerun the tests.

1. **An older key hold can pair the wrong slot despite a menu action.** [bt_ui.c:224](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:224), [243](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:243). Menu select, pair and stop leave `bt_pair_armed` and its hint intact. Hold Fn+P, then start a menu pairing shortly before the hold expires: the unconditional key path at line 213 can replace the new `PA_BOUNCE` with `PA_PAIR`, pairing its temporary slot. A menu stop can likewise be undone by the old hold. Explicit menu actions should cancel the earlier hold and clear its hint. `pair_superseded` tests the reverse direction and releases each key immediately.

2. **“Already on BT n” does not supersede a pending menu pair.** [menu.c:1167](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1167). Start pairing while linking, close/reopen, then click that current slot before six seconds. This branch skips `env_bt_select()`, so the pending pair remains armed and subsequently fires. Disarm it even when selection requires no radio command. The driver test calls `bt_ui_select_slot()` directly; the menu test exercises “Already” without a pending pair. Neither catches this.

3. **The bounce boundary accepts responses belonging to the temporary slot.** [ch582f_ajazz.c:1788](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1788), [2055](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2055). At 700 ms, the pump changes to `PA_SELECT` before draining RX and before transmitting the target select. A bounce-slot `5B 31` already buffered is consequently accepted as target confirmation: it clears the select retry, sets both facts, and makes the menu abandon its pair as “already advertising.” The page can name the wrong slot. Preserve the transaction boundary through RX processing and actual transmission. `pair_bounce` injects its event well before this boundary.

4. **A failed target select can retain the bounce slot’s CONNECTED state.** [ch582f_ajazz.c:1788](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1788), [menu.c:1168](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1168). A mid-bounce `5B 32` sets CONNECTED; issuing the real select does not reset it. If that select exhausts unanswered, the menu correctly drops its pending pair but labels the requested slot “Linked.” Clicking it does nothing because CONNECTED bypasses `SEL_LOST`. Reset target connection state when issuing the real select, and ensure a lost select remains retryable. Existing tests cover bounce and exhaustion separately.

5. **The eighth select gets no response window before being declared lost.** [ch582f_ajazz.c:1796](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1796), [bt_ui.c:197](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:197). The pass after enqueueing try eight clears `PA_SELECT` immediately. If a hold-task tick precedes its response, the menu permanently disarms; a subsequent valid `33`/`32` cannot restart pairing. Wait out the final confirmation interval. Also account for the independent cold-boot retry at driver line 1774: “lost” currently can coexist with continuing select sends. The harness always ACKs transport frames and never tests a successful final select response.

These can wait:

- **Direct `5B 36` unnecessarily leaves selection pending.** [ch582f_ajazz.c:2094](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2094) sets `select_acked` without retiring `PA_SELECT`. Pairing waits through redundant retries, potentially beyond six seconds. Retire only `PA_SELECT`, preserving bounce/pair actions. The rejection test supplies `33` first, masking this.
- **Connection-info cursor telemetry can inherit Reset counters’ page.** [menu.c:1381](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1381) returns stale `confirm_page` for `N_CONNINFO`; opening it does not reset that byte. Return zero explicitly. Rendering is unaffected.
- **Stand-in isolation lacks a regression test.** [menu_s0_test.c:1403](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1403) and adjacent fakes still mutate under an override. The board’s USB position also masks missing production guards. Test suppression with a live BT backing state.

Otherwise, the node coverage, latch/resyncs, frame replacement, slider return, whole-page backstop and signatures look correct. Bit 0 remains the row highlight; status occupies `val`; signatures fit 16 bits. The extracted key-press calls preserve their order and behavior. The six-second timer handles ordinary 16-bit wrap correctly.

Sub 14’s bytes and sub 16’s validation/suppression look correct. I found no additional cable-position flash hazard. The supplied **136 B gap clears the floor by only 8 B**; recheck it after fixes.