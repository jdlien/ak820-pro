# Codex's review of P1a's code, 2026-10-24

Prompt: [`review-prompt-p1a-code.txt`](review-prompt-p1a-code.txt). Reviewed:
qmk_firmware-ak820pro `gremlin/s1` `ffa80947..fd69a860`, with build.sh, the
generators, the battery simulator and the host tests. Model `gpt-6-astra`,
reasoning xhigh, read-only. Held the flash for two fixes and two tests.

## Dispositions (Warren)

- **1, a choice opened on the previous pass's saved value:** fixed in
  `5527c898` (`menu_input` syncs the model first); a regression (Fn+B and a
  click in one pass) fails on `fd69a860` and passes now.
- **2, a layout change's first op untimed:** fixed in `5527c898`
  (`ms_set_layout` abandons the discarded op unless its DMA flies); a
  regression (a click onto Reset counters mid-op, the first op timed) fails
  on `fd69a860`, passes now.
- **3, the production opener untested:** a `-DMENU_ENABLE` host build,
  `test_menu_enable()`: unarmed -> menu, armed -> fixture, disarm then
  unarmed, PENDING cancelled, close and reopen with no task between, the
  DEBUG/NONE opener (C1's do_open: the menu's top), Camera's return, and
  sub 5 after a menu session. The documented command names `menu.c`.
- **4, the About replacement test didn't keep old rows:** rewritten: Back
  for 0-5 passes, new facts, in again; removing `ms_invalidate_rows` makes
  it fail.
- **Can wait, done anyway:** About's uptime from `rtc_seconds_since_boot()`;
  sub 5's cursor after a menu session (a reporting kind kept past the
  close); `mi_init` resets `syn_back_taken`; the hint's intermediate
  target (the idle restarts in `menu_input`); the scheduler's order
  described as built in the design; coverage: the Back-row cancel, an
  external change inside an open choice, Camera's return, all four topics
  paged to their ends.
- **RAM:** dev 192 B gap (40 B used by P1a), devfault 240, daily 2,312;
  linked budget 416 of the amended 420.

## The review, verbatim

**I would hold the flash for two code fixes and the focused host-test additions below.** I found no out-of-bounds navigation path, signature collision in the current tree, or sequence that produces two lit rows.

1. **Fix before flash: choice opening can use the previous saved value.**  
   [`menu_ops.c:123`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:123) dispatches input before refreshing the model at line 140. [`menu.c:474`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:474) consequently calls `saved_row()` against the previous pass’s model.

   Failing sequence: settle Configuration on Power with Balanced saved; Fn+B changes it to Power saver and a queued knob click reaches the same menu task. Power opens with **Balanced selected**, then `menu_tick()` moves the bullet to **Power saver**. Clicking immediately commits Balanced again. Clock has the same race.

   Refresh the model before navigation uses it. Preserve the intended independence of cursor and saved value once a choice is already open. Add a regression that changes the fake getter and queues the opening click without an intervening pass.

2. **Fix before flash: layout changes suppress timing of the first new operation.**  
   [`menu_slots.c:129`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:129) discards the cursor without abandoning `op_started`. `new_target()` marks that old operation untimed; [`paint_piece():195`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:195) subsequently treats the first operation in the new layout as its continuation.

   Failing sequence: move onto Reset counters, let one piece of the old row’s cleanup paint, then click before that operation finishes. The confirm layout clears and starts its title, but its first complete half-title is counted **without updating `last_op_ticks` or `op_max_ticks`**. Close/reopen during a partial operation has the same problem.

   This predates P1a, but P1a introduces an ordinary navigation route through it. Settle ended DMA bookkeeping first, then abandon the discarded operation’s timing state while preserving any genuinely outstanding DMA completion. A new layout’s first operation needs a fresh timing origin.

   Regression: interrupt a synchronous multi-piece operation, reset measurement maxima, change layout, and run through its first complete operation. Its count should be one and its operation maximum nonzero.

3. **Add before flash: test the production opener configuration.**  
   The host suite still explicitly expects disarming to disable the opener at [`menu_s0_test.c:1462`](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1462). Those assertions cannot pass with `MENU_ENABLE`; the passing suite therefore does not cover the newly enabled production branch.

   Keep the S0 configuration, but add a `MENU_ENABLE` run covering unarmed→MENU, armed→FIXTURE, disarm followed by an unarmed opener, PENDING cancellation, and close/reopen without an intervening task. Include DEBUG/NONE entry and both Diagnostics returns. The documented compile command at line 10 also needs `menu.c` added.

4. **Add before flash: make the About replacement test preserve old About rows.**  
   [`menu_s0_test.c:1722`](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:1722) calls `m_click()`, which settles the parent completely before changing the snapshot. That removes the committed About rows whose equal signatures are the reason for `ms_invalidate_rows()`. The later rapid reentries use the same replacement facts.

   Instead: settle About A; Back for only one pass; change the facts; reopen before later rows repaint; settle and assert About B. Repeat across piece boundaries, including an active About row. The existing test does not establish the specific lifetime guarantee required by draft 3.1.

**These can wait until after the controlled test-board flash, but should be resolved before P1a acceptance:**

- **About reports awake time as uptime.** [`menu_glue.c:58`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:58) uses `timer_read32()/1000`. Sleep explicitly stops that counter. After an overnight sleep, About omits the night; it also wraps after approximately 49.7 awake days. Use [`rtc_seconds_since_boot()`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.h:87), which includes slept seconds.

- **Sub 5’s non-menu cursor sentinel depends on stale kind.** [`menu_ops.c:176`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:176): close a real menu and read sub 5 immediately—byte 15 is `0xFF`. Run the task, which clears `menu_kind`, and read again—the fixture branch returns `fx_cursor()`. Apply the non-MENU-owner sentinel independently of kind. This is a reporting defect; I found no corresponding stale-kind screen dispatch.

- **Scheduler order differs from draft 3.1.** [`menu_slots.c:258`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:258) resumes *any* unchanged partial slot before cleanup, whereas the design gives that priority only to an active cleanup. For example, an unfinished hint-title paint continues after a cursor move before dimming the old row. This delays cleanup but does not create a second highlight. Either amend the design to describe this deliberate behavior or implement its stated order; verify progress under continuous input.

- **Navigation during the hint creates an avoidable intermediate target.** [`retitle():556`](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:556) uses the previous `last_idle`. At 4.5 seconds idle, entering Diagnostics initially targets Diagnostics with the hint; the following tick sees fresh knob input and retargets again with “Diagnostics.” No paint occurs between them, so this is extra target accounting/work rather than mixed title pixels. Address it alongside the input/model ordering.

The remaining static checks came out as follows:

| Area | Assessment |
|---|---|
| Navigation | Stack depth is bounded by the actual three-level tree. Parent cursors survive Back; choice commit/cancel, topic clamp, About return, both Reset pages, Diagnostics rebuilding, and Exit follow the intended paths. Clock’s Date/Off enum mapping is correct. |
| Target creation | No navigation path directly calls both `ms_set_layout()` and `ms_retarget()`. About correctly invalidates rows and then retargets once. Separate input/title/model changes can create multiple targets in one task, as noted above. |
| Signatures | Item node, value, bullet and lit state cover the painter. Topic/line, title ID and confirm-page signatures are sufficient. About’s snapshot is safely omitted only because replacement invalidates rows. Build facts read during painting are immutable. |
| Text | Current labels and values fit. The 21-byte output, bounded About buffer, bullet in cell 0 and right-aligned values are safe. All four generated Help topics match the amended mockup; their lengths are 11/12/12/13 lines and every line fits 20 cells. |
| Highlight safety | `maybe_lit` is set conservatively before painting and survives abandonment, loss and invalidation. It clears only after a complete unlit commit or successful whole clear. The lit-target wait preserves the invariant. Fixture and confirm layouts correctly declare zero rows. |
| Session routing | A new opener overwrites kind while the session is NONE before synchronous callbacks. Thus close/reopen in one pass and disarming do not dispatch through the old kind. Pending kind survives until opening. Camera return reads the preserved debug-page identity correctly. |
| Hold fix | Delivered Back is distinguished from a lost latch, without injecting another Back at release. Cancel, new-hold and release paths reset the flag. The fixture-closing hold remains CANCELLED and a 300 ms hold remains a click. `mi_init()` omits resetting the new flag, but new-hold initialization prevents a current behavioral failure. |
| Firmware adapters/build | Power and Clock use the correct persistence paths. Link packing matches the CH582 enums and slot numbering; pack-zero and time-left sentinels are correct. Flavour precedence/fallbacks and the dedicated devfault trim are correct. Op 27 remains dev-only with `MENU_ENABLE`. |

The host framebuffer expectations are reasonably independent of `menu.c`: they spell out expected text and decode the face independently. They share the font and colour constants, so they cannot validate those assets against the intended appearance. More significantly, the fake environment bypasses `menu_glue.c`, explaining why uptime and adapter errors escape it; its health-reset stub also does not advance the fake reset generation.

Coverage remains narrower than the design promises: three Help topics, Camera return, Back-row cancellation, external changes inside choices, flash wraparound, and menu open/page/close-reopen interruption sweeps are missing. The new stress loop primarily covers top-level moves. Existing fixture tests do not substitute for those tree-specific cases.

Using your linked figures, **RAM passes now but has essentially no future slack**:

- Dev and daily grew **40 B**, rather than the nominal 30 B estimate.
- The projected total becomes `312 + 40 + 16 + 12 + 36 = 416 B`, under the amended 420 B ceiling.
- Spending the remaining reservations leaves dev at **exactly 128 B** and devfault at **176 B**. Account for `last_idle` and `syn_back_taken` explicitly; the growth is not merely padding.
- The devfault comparison starts at an older revision, so its net delta needs a matching-baseline map before attributing all growth to P1a.

The two getters are simple reads. New costs include tree/signature evaluation, title arithmetic, text composition, and About’s **64 formatting calls per full page**—eight pieces per row. Payloads remain bounded: text pieces are at most 488 bytes, and the scrollbar’s combined fills also fit. Actual pass timing and stack watermarks still need the board run; the fixture’s 14.8 ms result does not establish P1a’s margin.

All changed firmware files matched `fd69a860` against repository Git objects. This was read-only and confined to the requested repository. I could not rerun host tests or builds because process creation was denied; the findings above are from static tracing.