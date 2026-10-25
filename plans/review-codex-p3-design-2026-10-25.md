# Codex on P3's design (Connection: the Bluetooth slots and pairing), 10-25

Prompt: `plans/review-prompt-p3-design.txt`. Line references are to `a9f750ff`.

## Dispositions

1. **The bounce's 5B 32 fires the pair, which replaces the bounce (must fix):**
   taken. The driver gains `ch582_select_state()`: pending (`PA_BOUNCE` or
   `PA_SELECT`), acked (the module acted on the last select: a `5B 31`-`36`
   or the 5A promotion, outside a bounce, since `ch582_set_profile()` or
   `ch582_cancel_connect()`; `select_acked`), or lost. The menu's pair fires
   only when acked; `bt_pair_hold_task()` waits while pending. The "already
   advertising" shortcut needs a confirmed `5B 31`, which a bounce's own no
   longer sets (`pair_confirmed` is set outside a bounce only). Tested on the
   real driver (`scripts/ch582_sim/btui.c`, `pair_bounce`: the bounce slot's
   `5B 32` mid-bounce, then the target's select at 700 ms, then the pair);
   a mutant that fires while pending fails it.
2. **A menu select must supersede a pending pair (must fix):** taken; the code
   already did (`bt_ui_select_slot()` disarms, and the pair re-arms after its
   own select). The design now says so, and `pair_superseded` covers the
   menu's select, a slot key, `Fn`+`P` and the slider.
3. **An exhausted select leaves LINKING forever (must fix):** taken. A click on
   the current slot does nothing only while it's connected, or linking on a
   select that isn't lost (`ENV_PF_SEL_LOST`, a fourth fact); a lost one is
   selected again. A pair on the current slot with its select lost selects it
   first. A pair whose select is lost is disarmed, never sent: the Pairing
   page reads failed. `pair_lost_select` runs the eight tries out; a mutant
   without the re-select fails it.
4. **"Failed" and "advertising" overstate the evidence (must fix):** taken in
   part. A lost `5B 31` after the twelve tries leaves the optimistic `PAIRING`:
   a sixth phase, unsure (`The radio didn't` / `confirm pairing.` /
   `Click or hold: stop`), which a click or a hold stops, the stop's select
   cancelling it (`pair_lost_confirm`). Failed is now only a link that isn't
   advertising with nothing confirmed or pending. The end of advertising with
   no device isn't observable: the driver ignores `5B 23` (periodic, in every
   state), so a page left advertising keeps saying so until something changes;
   the band has the same gap, and the whole page is on the 3-minute backstop
   (point 7). Recorded as known, not fixed.
5. **The BT rows' signature (should fix):** taken; the code already put the
   word's state in `val` (bits 7-4) beside the bullet and lit bits. The design
   says so now.
6. **Sub 16's stand-in still reaches the radio (should fix):** taken. While it
   is set, `env_bt_select()`, `env_bt_pair()` and `env_bt_pair_stop()` do
   nothing (`menu_glue.c`). The cable doesn't mean the slider is on it.
7. **The terminal pages' dwell (should fix):** taken. The whole Pairing page has
   the backstop, so a page that turns connected after 24 s isn't closed the
   moment it does.
8. **The menu's structure (notes):** no change. Bit 0 stays the lit bit; the
   follow-the-slider return sets the list layout from a confirm page.
9. **Real-driver sequences (notes):** taken. `scripts/ch582_sim/btui.c` builds
   `bt_ui.c` and `ch582f_ajazz.c` verbatim on the harness's world, the module
   ACKing every frame and the case sending its `5B` frames: twelve cases (the
   tap, the current slot linked, another slot rejected, the 6 s cap, the old
   host, the bounce, the lost select, the supersessions, the lost
   confirmation, the 5A promotion, the stops, already advertising). Two
   mutants, each caught. RAM measured: the dev gap is 136 B (from 144), daily
   2,264.

## The review, verbatim

Reviewed against `a9f750ff`; references use that revision. The draft needs changes before implementation.

1. **Must-fix — pairing can cancel the bounce and pair the wrong slot.** During `PA_BOUNCE`, `requested_profile` already names the target, but the radio temporarily uses another slot. Its `5B 32` changes the state to CONNECTED while deliberately preserving the bounce. P3’s next tick then calls `ch582_enter_pairing()`, which **replaces the bounce with PA_PAIR**, losing the target select. A6 51 pairs whichever slot the radio actually occupies. This is worse than the key’s nominal 2-second hold, which outlasts the 700 ms bounce. Gate pairing—and the “already advertising” shortcut—on completion of the target-selection transaction, not merely leaving LINKING. ([ch582f_ajazz.c:1561](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1561), [1596](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1596), [1998](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1998), [bt_ui.c:171](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:171))

2. **Must-fix — menu selection must supersede a pending menu pair.** The draft disarms on physical slot keys, Fn+P and slider events, but omits menu selection. Sequence: start pairing A while LINKING; close; reopen and select B before the pending start fires. The slotless A6 51 then pairs B. Disarm in the shared selection path, then explicitly re-arm for a new pairing request. ([design:1202](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1202), [1223](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1223), [ch582f_ajazz.c:1579](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1579))

3. **Must-fix — optimistic LINKING can make selection permanently inert.** Select-retry exhaustion clears `pa.kind` without changing LINKING. Consequently, “current + LINKING → nothing” removes the menu’s retry even when no attempt was acknowledged. Distinguish an acknowledged attempt, which must remain uninterrupted, from exhausted selection. Likewise, six seconds does not establish that a pending select reached its target. ([ch582f_ajazz.c:1540](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1540), [1766](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1766), [2033](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2033))

4. **Must-fix — “failed” and “advertising” overstate the available evidence.** Losing `5B 31` can leave the radio advertising after all twelve tries; exhaustion only clears PA_PAIR. P3 then reports failure and makes click/hold merely return, despite its stop helper being able to cancel optimistic PAIRING. Conversely, an advertising window ending with `5B 23` leaves PAIRING and the proposed confirmation flag intact. Use an unconfirmed outcome with an actionable stop, and define how advertising completion is observed. The flag correctly prevents an unconfirmed old-bond `5B 32` or 5A promotion from becoming “connected”; it does not solve missing events or bounce attribution. ([ch582f_ajazz.c:1780](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1780), [1977](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1977), [2060](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2060), [wireless.md:98](C:/Users/jdlien/code/ak820-pro/docs/wireless.md:98))

5. **Should-fix — specify the BT-row signature payload.** The latch and retarget are appropriate, but explicitly encode the displayed status in `val`, alongside the existing bullet/lit bits. Retargeting alone does not repaint a committed row, and revision 13 resumes partial rows with unchanged signatures. Without this, a status change can leave stale or mixed text. ([menu.c:549](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:549), [menu_slots.c:180](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:180), [259](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:259))

6. **Should-fix — make sub 16’s isolation explicit.** Its fake reads still invoke real actions. A connected cable does not imply USB slider mode; raw HID works in every position. Suppress radio mutations while overridden, or enforce actual USB mode throughout the override’s lifetime. ([design:1258](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1258), [wireless.md:18](C:/Users/jdlien/code/ak820-pro/docs/wireless.md:18))

7. **Should-fix — decide terminal-page dwell.** After pairing takes over 24 seconds, switching to the ordinary timeout closes the success/ended page immediately: idle time still dates from the last knob input. Keeping the backstop for the entire Pairing page avoids another timer. ([menu_ops.c:154](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:154))

8. **Notes — menu structure is otherwise compatible.** Frame replacement fits `stack[3]`; new row IDs fit six bits and distinguish slot identities. Pairing signatures fit 16 bits and are distinct within the confirm layout. Cross-layout overlaps such as `0x8000` are harmless because layout changes invalidate slots. Preserve bit 0 as the highlight bit. Slider redirection must clear when leaving confirm geometry. ([menu.c:134](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:134), [552](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:552), [940](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:940), [menu_slots.c:134](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:134))

9. **Notes — validation needs real-driver sequences.** The listed stub tests would not catch findings 1, 3 or 4. Add bounce-window events, select exhaustion, lost/late confirmation, 5A promotion, close/reopen supersession, and partial-row status changes. The existing radio harness already provides recorded UART writes and injected RX. Keep 2.4G excluded, verify close leaves pairing running, and measure the linked RAM gap: eight estimated bytes leave only eight above the floor. ([harness.c:3](C:/Users/jdlien/code/ak820-pro/scripts/ch582_sim/harness.c:3), [44](C:/Users/jdlien/code/ak820-pro/scripts/ch582_sim/harness.c:44), [design:1268](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:1268))

Static review; no builds or hardware tests run.