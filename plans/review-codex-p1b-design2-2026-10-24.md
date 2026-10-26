# Codex on P1b's design, draft 2 (10-24 night)

Prompt: `plans/review-prompt-p1b-design2.txt`. Answered by draft 3.

## Dispositions

1. **The fast turn's 16-bit clock aliases inside the 180 s backstop:** taken: 32-bit ms, cleared when an editor opens, an unsigned difference under 90 ms since a turn in the same editor.
2. **A changed signature isn't a new target:** taken: every external hook, with or without an open edit, sets a pending-change bit that `menu_tick()` consumes with `ms_retarget()` before the pump; tests after settlement and mid-slot, with C10's accounting and a pending stop.
3. **The tests must run the production adapter:** taken: the sequencing moves to a pure `menu/menu_edit.c` the host builds, over narrow `menu_env.h` primitives whose fakes copy QMK's semantics; the board asserts order, not only counts (a get returns the restored value, an increment lands on it, a set and an indication still apply, a forced save persists the restored config across a reboot); `UG_*`, unbound `RGBM_*`, `RM_FLG*` and the magic reset named as inspection; dev ops 4/5 by script.
- **Wording:** Save exempt from "mode only when it changes"; "last persisted values" for the reset paths; the daily gap's provenance (`925f029b`); `menu_p1a_board.py` already at 17 ms; `menu_s1_gate.py`'s two 15 ms assertions move to 17 when the gate runs on the editors.

## The review, verbatim

**Yes—three targeted changes should be settled before coding.** Draft 2 resolves the main defects from round one, but the timer, target accounting, and test boundary need amendments. No files were changed.

1. **The fast-turn timestamp can alias during an open edit. Must fix before coding.**

   [Design line 470](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:470) specifies a 16-bit millisecond timestamp, while [line 486](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:486) permits 180 seconds between inputs.

   A turn **65,556 ms** after the previous turn produces a 16-bit difference of **20 ms**, falsely qualifying for acceleration. Signed comparison does not fix that; a simple signed `< 90` comparison also mishandles negative differences after 32,767 ms.

   Specify either a 32-bit timestamp or explicit expiry of the previous-turn state before wrap, including initialization on editor entry. Add long-idle and wrap tests. A 32-bit timestamp should still fit the proposed padded 16-byte transaction/timing allowance, subject to linking.

2. **Live signatures provide repaint correctness, but do not create C10 targets. Must fix before coding.**

   [Design line 590](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:590) correctly explains how changed values restart partially painted slots. However, consider a settled Lighting list, no edit open, followed by an external brightness change:

   - [`menu_slots.c:265`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265) detects changed signatures and repaints.
   - Only [`new_target():100`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:100) advances `tgen`, resets settlement, supersedes pending stops, and marks interrupted timing appropriately.
   - [`note_settled():189`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:189) ignores subsequent settlement if `target_settled` remains true.
   - Existing [`menu_tick():673`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:673) detects only power, clock, and title changes.

   Specify how external RGB/LCD changes notify the target machinery **after the write and before painting**, including when no transaction exists. A pending-change notification consumed before the pump can preserve live reads without another configuration snapshot. Test changes both after settlement and during partial work, including C10 accounting and pending stops.

3. **The tests still need an executable adapter boundary and observable ordering checks. Must clarify before coding.**

   The RGB adapter is placed in `menu_glue.c` at [design line 521](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:521), but [line 685](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:685) excludes that file from the host target. Consequently, the fake-core cases at [line 697](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:697) do not yet specify how they exercise the **production adapter**. The existing boundary explicitly replaces environment functions with fakes ([`menu_env.h:4`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_env.h:4)).

   Specify a host-buildable production adapter against fake RGB primitives, or move its sequencing into a shared module. Otherwise these tests could verify a second implementation.

   Board-only proof of hook placement is reasonable, but the cancellation counter at [design line 708](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:708) proves invocation, not ordering. Require observable assertions: Get returns the restored value; increments operate on restored values; Set/indication survive cancellation; forced VIA Save persists the restored configuration across reboot. Explicitly assign `UG_*`, `RGBM_*`, held repeats, and dev ops 4/5 to board coverage or a named inspection exception.

The six earlier findings otherwise resolve as follows:

- **Writer inventory: correct.** `via_command_kb()` precedes dispatch ([`via.c:296`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:296)); including RGB reads protects the flashing backup. Device indication is covered. `command_extra()` precedes `command_common()` in both relevant command states ([`command.c:67`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/command.c:67)). Flags are now included, and repeat cancellation precedes increment calculation.

  **The reset exemption is sound for preventing preview persistence.** Shutdown performs no RGB configuration flush ([`quantum.c:208`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/quantum.c:208)). The raw-HID path drains radio traffic, displays the splash, waits, then resets ([`hid_protocol.c:1332`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1332)); the drain pumps only `ch582_task()` ([`ch582f_ajazz.c:1402`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1402)). Neither flushes RGB configuration. Qualify “saved values” as **last persisted values**: pending saves can be lost, and `QK_CLEAR_EEPROM` deliberately invalidates configuration so reboot restores defaults ([`process_quantum.c:57`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_quantum.c:57)). No additional rollback hook is needed for these terminal paths.

- **Value signatures and choice checks: correct.** I enumerated all **7,168** combinations of the revised formula: no duplicates, no existing row-class collisions, and bit zero always equals `lit`. Reading the entry snapshot for Effect/Lights checkmarks avoids moving the saved check with the preview.

- **Owner rollback placement and re-entrancy: correct.** `do_close()` and `enter_debug()` cover accepted departures from MENU; the other owner-changing paths cannot depart an active menu ([`panel_owner.c:121`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:121)). Calling rollback before those mutations restores values before overlay reprime and visibility publication. Its specified RAM-only work does not require LCD quiescence first.

  Calling `menu.c` does **not** inherently break the host boundary: the host target already links it ([`menu_s0_test.c:10`](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:10)), and hardware access remains behind environment functions. The proposed external hooks are outside `menu_input()`’s call tree; owner events resulting from input run after `menu_input()` returns ([`menu_ops.c:134`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:134)). The argument is sound; the fake hook counter alone is not its proof.

- **Hue bands: correct.** Relative centres **−2…9 plus no overlap**, with complete background regeneration, cover the five-pixel triangle. Absolute second-color hue is the correct marker input.

- **RAM and live reads: acceptable with finding 2 addressed.** Hash-verified archived ELFs confirm gaps of **160 / 200 / 1,312 / 2,312 B** for dev/devfault/instrumented/fpb. The named instrumentation totals **14 B**. Live reads preserve partial-slot correctness and the one-lit-row rule because configuration writers do not interleave signature evaluation and painting within a pass; choice checks remain snapshot-based.

  One nonblocking provenance correction: the archived daily ELF showing **2,312 B** is `925f029b`, not `541a8cbd`. P1b’s own linked-build checks remain necessary.

- **Tests and 17 ms: substantially improved, subject to finding 3.** The 17 ms policy matches JD’s amendment. The draft’s claim that `menu_p1a_board.py` still fails at 15 ms is already stale: [`line 204`](C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:204) uses 17,000 µs. The shared S1 gate still enforces 15,000 µs and zero `over15` ([`menu_s1_gate.py:435`](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:435)); update both assertions when applying the amended editor gate, retaining the count for reporting.

One final wording correction: [design line 534](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:534) should explicitly exempt **Save** from “mode is set only when it changes.” Effect Save must call the saving setter even when preview already installed that mode. The preceding sentence already requires this, so it is a clarification rather than another design blocker.