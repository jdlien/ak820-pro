# Codex review 3: verifying the configuration menu's build plan, revision 3 (2026-10-23)

The plan verified is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md),
revision 3 (`f1c9659`), against the second review
([`review-codex-config-menu-build-plan-verify-2026-10-23.md`](review-codex-config-menu-build-plan-verify-2026-10-23.md))
and its dispositions. The model was gpt-6-astra at xhigh, read-only, run from
gremlin with the firmware at `b9555ff3e6` and the prompt in
[`review-prompt-config-menu-build-plan-verify2.txt`](review-prompt-config-menu-build-plan-verify2.txt).
Codex's answer follows verbatim, then the dispositions. Revision 4 carries
the fixes.

---

**Revision 3 is not ready to implement S0 as written.** The remaining S0 blockers concern ownership transitions, restore completion, damage representation, and the test activation/protocol contract. C6 also has an omitted RGB writer that must be covered before P1.

I read only inside the repository and made no changes. This is static verification against the checked-out code, including inspection of the archived dev ELF; I did not run builds or hardware tests.

Below, **Plan** means [CONFIG-MENU-BUILD-PLAN.md](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md). Board-relative paths begin at `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`. For fixed findings, the severity shown is the original severity, not an outstanding blocker.

For round 2’s 17 findings:

1. **Partly fixed — must-fix before S0: ownership transitions and migration.**

   **Locations:** Plan:148–189; `graphics/display.c:1394,1444,2910,2950`; `graphics/lcd_bus.c:1083`.

   Separating owner, session and restoration is correct. The table is nevertheless incomplete, and its predicates cannot mechanically replace the old checks.

   Missing cases include `DBG_PAGE`/op 1 from `MENU`, op 1 while `PENDING`, startup redraw under another owner, self-heal/DMA loss, slider changes, and animation stop with a previously requested restore. There is also no general rule for unspecified events.

   **Failure:** the startup callback requests restoration while Animation owns the panel; stopping Animation then resumes an old restore cursor instead of starting a fresh clear. Alternatively, replacing the entire `ANIM_TOG` condition with `anim_admissible()` makes an active animation impossible to stop.

   **Fix:** complete the event policy, distinguish start admission from stop permission, and expand the migration checklist. The specific omissions and predicate corrections are below.

2. **Partly fixed — must-fix before S0: `display_restored(gen)` still lacks a reliable completion contract.**

   **Locations:** Plan:190–197; `graphics/display.c:1394–1434,1873–1878,2990–3023,3377,3421`; `graphics/lcd_bus.c:950–1023`.

   Adding `!lcd_blit_busy()`, battery damage and stale logos fixes several omissions. Two remain:

   - **Idle is not successful completion.** On exhausted recovery, `lcd_blit_wait()` sets `blit_done = true`, sets `blit_lost`, and returns false. The proposed conditions can therefore report restoration after missing pixels.
   - **Residual work has no specified executor.** If `restore_pending` stays true until battery and logos finish, `dash_paints()` blocks their ordinary painters. If it clears when the numbered stages finish, animation can enter before restoration is actually complete.

   The existing code also has no restore-generation completion record or logo-stale state. Those are buildable additions, but the contract must define them.

   **Fix:** give restoration explicit clear/stage/drain/residual/complete phases. Service battery and stale logos as restore work, independently of `dash_paints()`. Track success or damage from failed DMA, and invalidate a superseded generation. Define whether completion refers to the current visible dashboard or historical completion; I recommend the former.

3. **Fixed — original severity must-fix: matching-release ownership.**

   **Locations:** Plan:217–222; `quantum/encoder.c:38–45`; `ak820pro.c:425–431`.

   The three physical-control capture bits are sufficient to determine whether each corresponding release is swallowed. The bits survive close and handoff, and a release belonging to a forwarded press is forwarded.

   **Prevented failure:** a captured knob press mapped to `DBG_PAGE` no longer leaks its release into the debug toggle after closing.

   **Keep:** release routing must run before current-session or feature-enable checks. Gesture state must be separate: preserving a capture bit must not preserve an actionable hold timer after closing.

4. **Fixed in substance — original severity must-fix; should-fix documentation completion.**

   **Locations:** Plan:88–101,205–240; `quantum/action.c:78–138`; `quantum/quantum.c:172–177,258–282`.

   The selected hook, physical identification, Fn definition and `pre_process_record_user()` fall-through are correct. Revision 3 removes the false weak-modifier guarantee.

   Its description still omits module preprocessing and one-shot timeout handling, despite the disposition saying the real semantics are written down.

   **Remaining failure risk:** tests assume a captured knob event interrupts an unrelated pending tap-hold or combo. It does not reach those processors.

   **Fix:** add the complete ordering described below and restore explicit one-shot/pending-tap-hold tests to the test list.

5. **Partly fixed — must-fix before P1: C6 misses QMK’s shared underglow keycodes.**

   **Locations:** Plan:337–352; `quantum/quantum.c:355,414–417`; [process_underglow.c:17](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_underglow.c:17).

   The VIA hook, release-edge `RM_*` interception, whole-config conflict domain, enabled-last restoration and explicit Lights save are correct.

   However, this checkout also routes **`UG_*` / `QK_UNDERGLOW_*` keys into RGB-matrix setters on press**. `RGB_MATRIX_DISABLE_SHARED_KEYCODES` is not defined in the board configuration I inspected.

   **Failure:** while previewing hue, a VIA-mapped `UG_TOGG` or `UG_HUEU` changes the live RGB config without cancellation. Later Cancel restores the snapshot and loses that external change.

   **Fix:** intercept the enabled shared-under­glow range on its press edge, alongside release-edge `RM_*`, board wrappers and repeat steps. No quantum change is required. Also include dev op 4 in Screen-edit cancellation if C6’s “external write” promise includes dev controls (`hid_protocol.c:1032`).

6. **Fixed for the permitted P3 deferral — original severity must-fix before P3.**

   **Locations:** Plan:427–438,557–562; `bluetooth/ch582f_ajazz.c:1530,1587,1755–1786`.

   The plan now requires driver-owned operation IDs, phases, failure/supersession results and a separately reviewed P3 plan. That is sufficient to defer the detailed Bluetooth design.

   It is **not yet a complete pairing implementation contract**. “Cancelling is defined for every phase” is a requirement on that future plan, not a definition supplied here.

   **Prevented failure:** P3 must not recreate the existing select-then-pair overwrite of `PA_BOUNCE`.

   **Required P3 decisions:** selection-completion evidence, cancellation destination per phase, stale-result rejection, retirement of queued commands/retries, and every terminal failure path.

7. **Fixed for the permitted P3 deferral — original severity must-fix before P3.**

   **Locations:** Plan:439–448; `bluetooth/ch582f_ajazz.c:595–617,1501–1513`.

   The sequence now covers all-up admission, A1/A3 suspension, successful release delivery, operation execution and all-up resumption. It explicitly tests input arriving during transition.

   **Prevented failure:** a press during the bounce no longer reaches an intermediate host.

   **Required P3 detail:** define delivery tokens/results, bounded failure exits, treatment of already-queued reports, and cleanup when an operation is cancelled or superseded. Those belong in the promised P3 plan; they need not block S0.

8. **Fixed in C7 — original severity must-fix: visibility and sleep follow the session.**

   **Locations:** Plan:354–370; `graphics/display.c:135,214–223,238–312`; `sleep.c:152–154,240–267`.

   A separate volatile visibility flag, unchanged requested settings, wake hold applied last, and `DSB_MENU = 0x4000` resolve the central problems. Diagnostics remains covered through session lifetime.

   **Prevented failure:** entering from requested Screen Off or level zero can illuminate the menu without overwriting the setting.

   **Keep:** resolve C1’s conflicting PENDING actions in favor of C7: PENDING blocks sleep but does not enable menu visibility. C7’s concurrency and decoder details check out below.

9. **Partly fixed — must-fix before S0: pending entry conflicts with its transition actions.**

   **Locations:** Plan:150–152,228–230,356–367; `graphics/display.c:3315–3338`.

   Remembering the opener and allowing a second opener to cancel is good. But row 150 gives the same actions to immediate entry and deferred entry: supersede restoration, reset damage, enable visibility and start clearing.

   **Failure:** those actions run while wake painting is still responsible for the battery/clock, defeating the reason for deferring entry.

   **Fix:** split the row. PENDING retains dashboard/wake work and records only the request, capture ownership, overlay suppression and sleep blocker. The menu handoff and clear happen after `display_wake_release()`. Specify the release notification/query and behavior of other controls while pending.

10. **Partly fixed — should-fix: the measurement policy improved, but S0 still claims too much.**

    **Locations:** Plan:271–275,527,532–537,591–594; `quantum/encoder.c:30–45`; `config.h:392,401`.

    Renderer time and whole-pass time are now distinguished, and a big-value step is correctly one glyph operation.

    **Remaining contradiction:** S0 requires no pass of 25 ms or more, while bounding encoder draining is deferred to S1. A sufficiently large encoder backlog spends over 25 ms in the existing waits before menu painting starts.

    **Fix:** make S0’s result a measurement over a named workload, not a universal bound. Establish the required burst/backlog workload and any encoder-drain change in S1. Op 27 turn injection cannot measure the physical encoder drain.

11. **Partly fixed — must-fix before S0: C3 specifies erasure without storing enough information to perform it.**

    **Locations:** Plan:252–278; `config-menu-mockup.html:541–545`.

    Invalid/partial/committed states fix the conceptual A → partial B → A problem. Four bytes can store the stated signature, state and generation. They cannot additionally identify arbitrary old rectangles.

    **Failure:** after a marker moves or a screen replaces a region, regenerating only the current target loses the old footprint. Superseding an incomplete erase can leave pixels from more than one prior target.

    **Fix:** choose a concrete representation: fixed-footprint slots plus a bounded full-screen clear on layout changes, or retained geometry/paint-state sufficient to reconstruct every outstanding erase. Define how an interrupted erase continues and how overlap invalidation is ordered. More detail below.

12. **Partly fixed — should-fix: scratch sharing is sound; the stream and RAM contracts need tightening.**

    **Locations:** Plan:281–329; `graphics/lcd_bus.c:131–188,214–220,689–712`.

    The non-reentrant, main-thread ownership and panel-order emission rules are compatible with the current call graph. Sharing really does remove one 512-byte buffer.

    **Remaining failure risks:** a stream stays open across main-loop passes and another painter changes the LCD window; or an implementation uses ordinary `size` totals to calculate the heap gap.

    **Fix:** specify begin/quiesce/window/end ordering for **every** stream user and prohibit retaining an open stream across passes. Use `.heap` section size or linker symbols for the build gate. Re-budget after resolving C3, counting all static RAM rather than only BSS.

13. **Fixed for P2 planning — original severity must-fix before P2; one should-fix addition.**

    **Locations:** Plan:410–425; `flash_stats.c:31–32,38,58,128–142`; `hostagent/ak820health.py:309–315`.

    Bytes 7–9, mask widening, frozen page 1, page 3, old-firmware handling, simulator update and explicit non-migration of the keyboard block adequately address the finding for P2. Leaving Rust HC_FLASHW out of scope is accurate.

    **Additional build trap:** widening `kb_byte_field[]` to `uint16_t` breaks its current `sizeof(array) == EECONFIG_KB_DATA_SIZE` assertion.

    **Fix in P2’s plan:** compare the **element count**, and specify page 3’s remaining bytes as zero/reserved. Freeze the battery encoding explicitly: 0 unset, 1 Percent, 2 Hours; invalid values use the default.

14. **Partly fixed — should-fix before P1: promoting the power setter also requires changing the build guard.**

    **Locations:** Plan:396–408; `power.h:68–76`; `power.c:329–335`; [build.sh:146](C:/Users/jdlien/code/ak820-pro/build.sh:146).

    Clock mapping, nine effects, shared names, second-color semantics and indicator initialization are addressed.

    **Failure:** after promoting and using `power_set_mode()` in production, daily/fpb builds fail structural validation because `build.sh:147–149` explicitly forbids that symbol.

    **Fix:** remove only `power_set_mode` from that forbidden-symbol list when promoting it. Retain the prohibition on the actual dev-only force-stage/sleep controls.

15. **Partly fixed — must-fix before S0: op 27 and the proof harness remain underspecified.**

    **Locations:** Plan:241–243,488–506,513–527,573–602.

    Subcommand numbers, eight-event capacity, busy-on-full and asynchronous holds are improvements. They do not constitute the claimed exact wire contract:

    - reply byte offsets, field widths, enum/status values and timing units are absent;
    - there is no distinction between accepted and completed work;
    - the synthetic hold duration and press/release behavior are not fixed;
    - sub 0 lacks its data/pattern source and coordinate/style bounds;
    - there is no activation mechanism for physical capture with `MENU_ENABLE` off.

    **Failure:** host tests report success after enqueueing an event, while the action never completes—or exercise only model calls while the real preprocessing hook is disabled.

    **Fix:** freeze the 32-byte request/reply layout, completion polling, validation and test activation before S0. Add the omitted one-shot/pending-tap-hold cases. Final-DMA completion needs observable state or assertions; a final photograph cannot prove when `display_restored()` became true.

16. **Fixed — original severity should-fix: Fn+D unassignment.**

    **Locations:** Plan:457–467; `keyboard.json:200`; `scripts/keymap_to_c.py:7–31`.

    `KC_NO`, JD’s board as authority, explicit dump regeneration, readback, exact two-key diff and end-of-P1 timing resolve the issue.

    **Prevented failure:** `KC_TRNS` typing D, or a bench dump replacing unrelated default mappings.

    **Keep:** preserve encoders and `QK_BOOT`, and do not modify other owners’ stored maps.

17. **Partly fixed — should-fix before P1: geometry mostly matches, but QR placement does not.**

    **Locations:** Plan:378–390; `config-menu-mockup.html:472–545,581–589`.

    Range/hue value positions and preview-versus-commit choices now agree. The timeout implementation in the mockup also distinguishes committing choices.

    **Mismatch:** with 29 modules and the specified border, the mockup computes a 99×99 QR at **x=14, y=22**, not y=16:
    `16 + floor((112 − 99) / 2) = 22`.

    **Fix:** change C8 to y=22 or deliberately change the authoritative mockup. Also include the inverted row’s x=3 padding pixel in its footprint; the mockup draws it at line 503.

The contract checks expose the following implementation details and remaining decisions.

**C1’s transition table is not exhaustive.** A full Cartesian table is unnecessary, but it needs explicit defaults and policies for these cases:

| Event/state | Recommended decision |
|---|---|
| Op 1 or `DBG_PAGE` from `MENU, OPEN` | Cancel any edit, enter Health, retain the session, and establish the Diagnostics return location. |
| Op 1 during PENDING | Refuse without changing the pending request or wake work. |
| Ordinary knob input during PENDING | Capture and discard; a second Fn+press cancels. Do not buffer navigation for a screen that has not opened. |
| Startup redraw while another owner is active | Record dashboard invalidity; do not run dashboard painting beneath that owner. On return, begin a fresh restore. |
| Slider move | Preserve panel/session ownership, update underlying state and logo damage; P3 additionally supersedes its connection operation. |
| Wake while a session is OPEN | Normally prevented by `DSB_MENU`; assert that invariant. Define recovery behavior for forced/test paths. |
| Wake under standalone Debug or Animation | Preserve ownership and explicitly define owner-aware completion; do not wait for dashboard work whose painter is gated. |
| DMA recovery/loss | Attribute damage to the owner/generation that issued the transfer. Recover that owner’s content; do not silently declare success. |
| Animation start | Validate the header first; an empty slot is a no-op. Admit only from eligible DASH. |
| Animation stop, including a pending dashboard request | Always permit stopping an active animation; quiesce it and begin a new restore generation from stage 1. |
| Unsupported events in each state | Explicit no-op/refusal; never an implicit fall-through that changes ownership. |

These decisions address concrete paths at `display.c:1444,1480,2963,3297`, `bt_ui.c:55`, and `lcd_bus.c:1083`.

The migration checklist is **not complete**. In addition to its existing entries, name:

- `display.c:1395,1433`: restore cursor read/advance/completion.
- `display.c:2910`: `display_bus_idle()`.
- `display.c:2990,2992,2997`: both dev and non-dev restore dispatch.
- `lcd_bus.c:21`: the old `display_set_paused` declaration.
- `lcd_bus.c:1042,1060,1085,1099,1102,1117`: all actual `anim_on` declaration/read/write sites.

Also verify callers of the migrated APIs: `ak820pro.c:431,610`, `lcd_bus.c:405,421`, `sleep.c:246,812`, and `rtc/rtc.c:1832`. They need preserved semantics even if their spelling does not change.

The four predicates need these qualifications:

| Predicate | Assessment |
|---|---|
| `dash_paints()` | Correct for ordinary dashboard work. Retain splash, bus and pass-deferral gates. It cannot gate restoration’s residual battery/logo work. |
| `restoring()` | Correct as a state query, **insufficient** as the replacement for `display_band_busy()`. That function must also remain busy under Menu, Debug and Animation. I recommend PENDING too, since parameter posts are suppressed then. |
| `panel_lit_for_owner()` | Correct for Minimal-mode’s exception: standalone Debug or OPEN session, excluding Animation and PENDING. |
| `anim_admissible()` | Correct for **starting**. `ANIM_TOG` still needs `anim_active() || anim_admissible()` or separate start/stop dispatch. |

For overlays, explicitly clear an existing `param_status_on` and `param_force_kc` at entry and re-prime the polling baseline at exit. Dropping new posts alone does not remove an existing overlay (`display.c:2555–2568`; `param_overlay.c:191–262`). This is a **should-fix** clarification to Plan:198–201.

**C2’s actual QMK ordering is compatible with the design.**

At this checkout:

1. `action_exec()` clears weak mods on press. Applicable one-shot timeout handling also runs before preprocessing.
2. `get_record_keycode(record, true)` performs source-layer lookup/cache work and dynamic VIA lookup.
3. `pre_process_record_modules()` precedes `pre_process_record_kb()`.
4. Combo processing follows the keyboard pre-hook.
5. A false return prevents that event from entering tapping and later processing, including `process_record_kb()`.
6. Tick events can still advance an already-pending tapping state.

`pre_process_record_user()` is exactly the correct uncaptured fall-through.

Encoder identity is also right. `ENCODER_CW_EVENT` and `ENCODER_CCW_EVENT` are **event types**. Encoder index is `record->event.key.col`; the special rows are `KEYLOC_ENCODER_CW/CCW` (`quantum/keyboard.h:35–97`). VIA resolves their mappings through `dynamic_keymap.c:93–95`. Each dequeued detent produces a press/release pair with the two waits.

Reading `layer_state` at the physical knob press implements the stated Fn policy. An unresolved Fn layer-tap does not count.

**Under C2’s routing rules, neither a captured press with a forwarded release nor the reverse should occur.** A previously forwarded knob press remains forwarded on release even if op 27 opens a session meanwhile. Capture ownership must not be inferred again from the new state.

There is, however, an additional **must-fix S0 queue-policy ambiguity** at Plan:217–238,321,502: the physical encoder can produce more than eight queued turns before `menu_task()` runs, and physical input cannot receive a HID “busy” reply.

**Recommended decision:** capture ownership is independent of enqueue success. Coalesce/saturate turns with an overflow counter, reserve or separately latch close/Back, and never forward a captured release because the queue filled. Define opening/closing presses as non-click gestures, and cancel their hold actions on session termination while retaining release capture.

**C3 is buildable after choosing retained geometry and scheduler semantics.**

A concrete slot such as `uint16_t signature; uint8_t state; uint8_t generation;` fits four bytes. Use a size assertion. That answers only the storage of those fields.

To implement the stated rules within one operation per pass:

- PARTIAL work for the **same target generation** must resume its cursor, not restart because it is not COMMITTED.
- Old-footprint erasure needs a persistent phase/cursor and retained footprint.
- Finish required erasure before repainting regions it overlaps.
- A navigation change must preserve unfinished cleanup obligations or replace them with a bounded clear that subsumes them.
- Commit only after the final successful transfer, and invalidate the target on loss.

For this small display, I recommend **fixed geometry for slots within a layout, a banded whole-screen clear on layout changes, and a fixed envelope for the hue strip/marker**. That avoids an arbitrary history of moved rectangles. If selective old-rectangle erasure remains a requirement, budget the extra geometry/history explicitly.

**C4’s sharing claim checks out against the current users.**

| Buffer path | Current users |
|---|---|
| `tx_pixels()` through `lcd_blit_ram()` | AM/PM tile (`display.c:601`), battery bolt/bulb/absence tile (`1763`), transport icons (`2510`). |
| `lcd_fill_rect()` | Battery outline/nub (`1927–1933`), battery fill (`2010`), padlock shapes (`2067–2071`). |

Those drawing paths run on the main thread, including when called by the display pump. The deferred startup callback requests work; it does not render through scratch. The DMA completion callback at `lcd_bus.c:699` updates GPIO/state and does not paint.

The **SPI FIFO ISR does read the scratch source** while `spiSend()` is active (`hal_spi_v2_lld.c:96–125`). Thus “never used from an ISR” must mean “never acquired, filled or recursively rendered from an ISR,” not “never read there.”

The stream API fits the bus if its contract says:

- `begin`: validate dimensions, quiesce, acquire, then set the inclusive LCD window.
- `bytes`: synchronous panel-order bytes; define count units and total expected bytes.
- `end`: complete sends, deassert CS and release.
- Every bounded chunk finishes its stream before returning to the main loop.
- Generated-buffer access stays inside defined `lcd_bus.c` primitives or a scoped scratch API.

Do not move `bus_quiesce()` into `lcd_window()`: the DMA arm path deliberately calls that function after marking its own transfer busy (`lcd_bus.c:686–688`).

**C5’s budget is plausible, but its measurement prescription needs precision.**

I confirmed the cited dev ELF has:

- `.mstack`: 1,024 B
- `.pstack`: 2,048 B
- `.data`: 2,784 B
- `.bss`: 26,864 B
- `.heap`: **32 B**
- retained `.ram7`: 16 B

Sharing scratch nominally gives 544 B. Adding 400 B leaves roughly 144 B, so the 128 B floor is plausible but has little tolerance at the ceiling. The approximately 220 B estimate is not validated until C3’s missing storage and all state layouts are settled.

A build gate is buildable for both dev and daily:

- Prefer `__heap_end__ - __heap_base__` from the already-collected `nm_out`; or
- explicitly use `arm-none-eabi-size -A` and parse `.heap`.

The linker reserves the entire remaining region as a NOLOAD `.heap` (`rules_memory.ld:309–316`). Consequently, default aggregate `size` output cannot be treated as occupied data/BSS and subtracted from 32 KB.

**Suggested fix, should-fix before S0:** specify that formula, fail on missing symbols/sections, and enforce it before artifact publication. Count new `.data` as well as `.bss`. Do not deduct the fixed stacks or retained region a second time.

**C6’s named interception points work; the omitted writer is the shared `UG_*` path.**

- `via_command_kb()` runs before dispatch and can observe RGB-matrix Set and Save. Returning false preserves normal VIA processing and its reply (`via.c:290–298`).
- `process_record_kb()` precedes `process_rgb_matrix()`, whose trigger here is release. Intercepting `RM_*` there is correct.
- `param_repeat_step()` directly calls setters and must cancel before each RGB or Screen adjustment.
- `consumer_mod.c` does not write RGB configuration.
- The power ladder uses output caps/driver scale and effect reinitialization, not RGB configuration writes (`power.c:119–154`).
- Battery protection invokes that cap (`battery.c:1270–1282`).
- Deep sleep uses driver sleep operations, not RGB configuration edits.
- The lock-light channel updates clock/media/display state, not RGB configuration (`ch582f_ajazz.c:512–560`).

Do not cancel RGB transactions for those output-only power changes, and do not restore their caps from an RGB snapshot.

**C7 is safe with the intended narrow implementation.**

The current PWM inputs—requested power, level, cap and wake hold—are already volatile byte/bool objects. A standalone `volatile bool menu_visibility`, written by main code and read by the ISR, follows that model. Byte accesses do not tear on this M0.

Make the shared effective-level function a pure calculation over local snapshots of those scalars. It must not read menu structs, transition state, timers or mutable compound snapshots, and must not change PWM phase. Separate volatile fields do not make a multi-field update atomic, but the proposed function does not require such a transaction if visibility is published after entry setup and wake hold is tested last.

`0x4000` is free, and the blocker carriers/replies are 16-bit. Appending `"menu"` at index 14 of `ak820battery.py:106` is correct.

**Neither `ak820health.py` nor the Rust daemon currently decodes this sleep-blocker word.** They do not need an invented decoder update. `ak820battery.py` is the relevant current decoder.

**C8 mostly matches.** Lists, separators, scrollbar, range bar, separate range/hue value positions and bunny placement agree. Correct the QR y-coordinate, retain the inverted-row x=3 pixel, and include the hue marker’s full horizontal extent: its triangle can reach x=126 near the high end, beyond the strip’s x=123 edge.

For S0, I recommend resolving these scope/proof decisions explicitly:

| Decision | Recommendation |
|---|---|
| Physical capture with `MENU_ENABLE` off | Add a dev-only, explicitly armed runtime test mode that enables the same real pre-hook. Default remains off. Pending captured releases must still drain after disarming. |
| Test display before P1 | Provide a minimal visible fixture using existing primitives, with owner transitions and deterministic A/B damage patterns. Do not require the P1 menu tree to exercise S0. |
| Session safety | Move the minimal visibility override and sleep blocker into S0 if op 27 can create real sessions. C1 already depends on them; leaving all of C7 until P1 is inconsistent. |
| Op 27 observability | Expose accepted/completed sequence, owner/session, restore generation/phase, outstanding damage, DMA busy/loss and queue overflow. |
| Damage proof | Host tests use a deterministic fake framebuffer and success/failure completion events; board tests verify the fixture’s pixels and recovery. |
| Input proof | Test physical presses/releases, Fn released first, timeout while held, remapped MT/LT/one-shot controls, pending tapping, and encoder backlog. Synthetic clicks alone are insufficient. |
| Timing proof | Record renderer and whole-pass measurements separately under a named workload. Keep the S1 encoder-drain decision explicit. |

With `MENU_ENABLE` off and op 27 **as currently specified**, S0 can prove ordinary debug/animation regression behavior, startup/dashboard restoration, scratch sharing and linked RAM usage. It cannot prove physical capture through the disabled hook, real encoder timing through injected turns, the full menu transition table without a fixture, or partial-render/final-DMA semantics without additional control and observability.

**Keep the stage order. Fix the S0 contract and proof gaps before handing it to the implementer.**
---

## Dispositions (Warren, gremlin, 10-23), fixed in revision 4

The verdict, not ready for S0, is agreed. Six claims were checked in the
source before relying on them:
- `process_underglow()` runs the `UG_*` keys into the RGB-matrix setters on
  press, and no board file defines `RGB_MATRIX_DISABLE_SHARED_KEYCODES`;
- `build.sh:146-149` forbids `power_set_mode` in daily and fpb builds;
- `flash_stats.c:32` asserts `sizeof(kb_byte_field) == EECONFIG_KB_DATA_SIZE`;
- the mockup computes the QR code's y as `16 + floor((112 - 99) / 2)`, 22;
- `display_redraw_dashboard()` sets the restore's cursor whenever the debug
  page isn't active, the animation's pause included (`display.c:1444-1448`);
- `display_wake_repainted()` waits on `batt_dirty` under every owner, and
  `sleep.c:812-816` releases the hold at `RC_HOLD_MAX_MS` when it never
  clears.

No change to the mockup was needed: it already draws the QR code at y 22,
the inverted row's pad pixel at x 3, and the marker's full width. The plan
now matches it.

| # | Disposition |
|---|---|
| 1 | **Agreed.** C1's table names every state and event codex listed, with a rule that an unnamed event is a no-op or a refusal. `ANIM_TOG` stops an active animation and starts one only if `anim_admissible()`. `display_band_busy()` is its own predicate: not DASH, a session (PENDING included), or restoring. The migration checklist adds the restore cursor, `display_bus_idle()`, the dev and non-dev dispatch, `lcd_bus.c:21` and every `anim_on` site, and names the callers whose meaning must be kept. An overlay already showing is cleared at entry. |
| 2 | **Agreed.** The restore has phases: `SPLASH`, `WAITING`, `CLEAR`, `STAGES`, `RESIDUAL`, `DONE`. `RESIDUAL` paints the battery's dirty parts and the stale logos itself, not through `dash_paints()`. A loss marks the generation damaged, and a damaged one starts again instead of reaching `DONE`. `display_restored(gen)` means the dashboard now on the panel. Every start begins at band 1. |
| 3 | Fixed already. Release routing runs before any check of the session or `MENU_ENABLE`, and a close clears the gesture while keeping the bit. |
| 4 | **Agreed.** C2 lists what runs before the hook (the weak mods' clear, the one-shot timeout, the lookup, the modules) and what a false return skips. The one-shot, MT, LT and pending tap-hold cases are back in the tests, by remapping the knob for the test. |
| 5 | **Agreed.** The `UG_*` keys are observed on press, beside `RM_*` on release. Dev ops 4 and 5 cancel a Screen edit. The output-only changes (the ladder's caps, the RGB cut, sleep, the lock-light channel) cancel nothing and aren't restored from a snapshot. |
| 6 | Agreed: a requirement on P3's own plan, with codex's list of decisions to make there. |
| 7 | Agreed: as 6. |
| 8 | **Agreed.** PENDING blocks sleep but doesn't light the panel; C1's pending actions now say so. |
| 9 | **Agreed.** Pending entry is split from opening (actions P and O). P records the request, its capture, the overlays' suppression and `DSB_MENU`, and leaves the wake's work alone. `display_wake_held()` is the query and `display_wake_release()` posts the notice. Knob input while pending is discarded, and op 1 is refused. |
| 10 | **Agreed.** S0's timing proof is a measurement under a named workload. Real spins, the backlog and any bounded drain are S1's. |
| 11 | **Agreed, with codex's recommended representation.** Fixed slot geometry per layout, a banded clear on a layout change that is never superseded, and the hue strip and marker as one fixed envelope (x 1-126, y 20-40). No old rectangles are remembered. A partial slot resumes for the same target and restarts for a new one. |
| 12 | **Agreed.** The stream's begin, bytes and end are specified, and no stream stays open across passes. `bus_quiesce()` stays out of `lcd_window()`. The gap is `__heap_end__ - __heap_base__` from `nm_out`, and a missing symbol fails. The budget counts `.data` and `.bss`, and was redone (~212 B). |
| 13 | **Agreed.** The assertion compares the element count, page 3's other bytes are zero, and the battery view is 0 unset, 1 Percent, 2 Hours. |
| 14 | **Agreed.** `build.sh`'s list loses `power_set_mode` only, at P1. |
| 15 | **Agreed.** Op 27's request and reply are laid out byte by byte, with statuses, `accept_seq` and `done_seq`, the hold's bounds and the fixture's patterns. Sub 6 arms the physical test mode; subs 7 and 8 drive the restore and the loss rules; sub 5 exposes the restore's phase, the slots outstanding, the DMA and the overflow. |
| 16 | Fixed already. |
| 17 | **Agreed.** C8's QR code is at y 22, the row's slot includes x 3, and the envelope reaches x 126. |
| C2's queue | **Agreed.** Capture doesn't depend on room: turns are one saturating count with an overflow counter, and click, Back and close are latches. The opening and closing presses aren't clicks. |
| S0's scope | **Agreed with every row.** S0 builds the fixture, the armed test mode, C7's override and `DSB_MENU`, and the observability; the damage proof is host tests with a fake framebuffer plus the fixture's pixels on the board. |
