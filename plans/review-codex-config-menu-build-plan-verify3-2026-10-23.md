# Codex review 4: verifying the configuration menu's build plan, revision 4 (2026-10-23)

The plan verified is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md),
revision 4 (`d584faa`), against the third review
([`review-codex-config-menu-build-plan-verify2-2026-10-23.md`](review-codex-config-menu-build-plan-verify2-2026-10-23.md))
and its dispositions. The model was gpt-6-astra at xhigh, read-only, run from
gremlin with the firmware at `b9555ff3e6` and the prompt in
[`review-prompt-config-menu-build-plan-verify3.txt`](review-prompt-config-menu-build-plan-verify3.txt).
Codex's answer follows verbatim, then the dispositions. Revision 5 carries
the fixes.

---

**Revision 4 is not ready to implement S0 as written.** It resolves most earlier findings, but leaves must-fix gaps in restore completion, ownership invalidation, loss recovery, coalesced input, and the S0 test contract.

I read only inside the repository and made no changes. This is static verification; I did not run builds or hardware tests. “Fixed” means the plan now prescribes a workable fix, not that firmware implementing it exists.

Below, **Plan** means [CONFIG-MENU-BUILD-PLAN.md](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md). Board-relative paths start at `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`. References to dispositions mean the final section of [round 3](C:/Users/jdlien/code/ak820-pro/plans/review-codex-config-menu-build-plan-verify2-2026-10-23.md:373).

**The 17 carried findings**

For fixed findings, the severity is the carried severity; it does not indicate an outstanding blocker.

| # | Verdict and severity | Verification, failure scenario, and required treatment |
|---|---|---|
| 1 | **Partly fixed — must-fix before S0** | **Plan:167–268.** The migration checklist now covers the executable uses of the four old flags, and start/stop admission is correctly separated. The defaults make unnamed events explicit refusals/no-ops. However, completed-dashboard invalidation, PENDING → NONE with a waiting restore, and Animation loss recovery remain incomplete. These can leave `display_restored()` true under another owner or leave the dashboard permanently gated. Fixes below. |
| 2 | **Partly fixed — must-fix before S0** | **Plan:160–184; `graphics/display.c:1413,1429,2990,3000,3023`.** Explicit phases, damage tracking and restore-owned battery/logo work are improvements. RESIDUAL still lacks an explicit queue-draining schedule, and its written termination condition omits battery/logo completion. A mechanical migration retains the restore branch’s early return and never reaches the existing queue drain. Specify the scheduler and complete DONE invariant below. |
| 3 | **Fixed — original must-fix** | **Plan:303–315; `ak820pro.c:425–431`.** Release routing precedes state/enable checks; capture bits survive close; gestures do not. This prevents a captured knob release from reaching a remapped `DBG_PAGE`. Retain that separation, including in armed mode. Synthetic gestures need the additional isolation described below. |
| 4 | **Fixed — original must-fix/documentation follow-up** | **Plan:280–302,323–327,746–749.** The real preprocessing order, skipped processing, Fn definition and user-hook fall-through are now documented correctly. The one-shot, MT/LT and pending-tapping tests are restored. Tests must expect weak-mod clearing and must not expect captured events to interrupt pending tapping. |
| 5 | **Fixed — original must-fix before P1** | **Plan:490–518.** The omitted shared `UG_*` press path is now included, alongside release-edge `RM_*`, wrappers, repeat steps and VIA Set/Save. Dev Screen controls are covered. This prevents Cancel from overwriting an intervening external RGB change. The specified output-only exclusions are correct. |
| 6 | **Fixed for the permitted P3 deferral — must-fix in P3’s own plan** | **Plan:607–618; `bluetooth/ch582f_ajazz.c:1530,1587,1755`.** Driver-owned IDs/results and a separate reviewed plan are sufficient at this stage. The existing select/pair overwrite remains real. Selection-completion evidence, cancellation destinations and retirement of queued commands/retries still need definition in that future plan. “Cancelling is defined for every phase” currently states a requirement, not a supplied definition. |
| 7 | **Fixed for the permitted P3 deferral — must-fix in P3’s own plan** | **Plan:619–628; `bluetooth/ch582f_ajazz.c:1501–1513`.** The handoff now suspends forwarding and requires successful release delivery before switching. That addresses presses arriving during a bounce. Delivery tokens, bounded failure exits and cancellation cleanup remain P3 work; an empty TX queue must not become the success test. |
| 8 | **Fixed — original must-fix** | **Plan:520–543; `graphics/display.c:135,214–223,238,308`; `sleep.c:240–267`.** Visibility follows OPEN sessions, including Diagnostics; PENDING only blocks sleep. Requested settings remain separate. The scalar ISR interface and blocker allocation are sound. C7 is appropriately moved into S0. |
| 9 | **Partly fixed — must-fix before S0** | **Plan:191–217,227–234.** Splitting P from O fixes ordinary deferred entry. The wake query/notice and capture-and-discard policy are sufficient. But a restore request during PENDING changes its phase to WAITING; cancelling PENDING does not restart it. Define that transition explicitly. |
| 10 | **Fixed for S0’s measurement policy — should-fix clarification** | **Plan:752–769; `quantum/encoder.c:30–45`.** S0 now measures a stated class of workload rather than promising a universal pass bound. Physical encoder backlog is explicitly S1 work. Define the actual 500-command script and pacing; the later general test list at Plan:827–830 must not be read as an S0 gate involving screens that do not exist yet. |
| 11 | **Partly fixed — must-fix before S0** | **Plan:357–398; `graphics/display.c:834–838`; `graphics/lcd_bus.c:207–211`.** Fixed footprints and a non-superseded layout clear remove the missing-old-rectangle problem. Four-byte slots are feasible. But loss during a DMA-backed clear is not repaired by invalidating slots alone: pixels outside the new slots can survive. Specify successful-clear completion and loss restart/retry behavior. |
| 12 | **Fixed in substance — original should-fix** | **Plan:404–486; `graphics/lcd_bus.c:131–220,689–712`; `build.sh:113`.** Scratch lifetime, ISR reading, window ordering and within-pass streams are now correct. The heap-symbol formula is buildable. The estimate is plausible, not a measured allocation; include the remaining instrumentation, visibility, logo and stream state in linked accounting. |
| 13 | **Fixed for P2 planning — original must-fix before P2** | **Plan:586–605; `flash_stats.c:31–32,38,58,128–142`.** Element-count assertion, widened mask carriers, frozen page 1, separate page 3, reserved zeros, battery encoding and simulator update are specified. These prevent both the compile-time assertion failure and reply overflow. The non-migration policy is explicit. |
| 14 | **Fixed — original should-fix before P1** | **Plan:570–584; `power.h:68–76`; `power.c:329–335`; `build.sh:146–149`.** Promotion includes declaration/body and removing only `power_set_mode` from the forbidden-symbol list. Clock mapping, shared effect names, second-color semantics and indicator initialization are also addressed. |
| 15 | **Partly fixed — must-fix before S0** | **Plan:668–714,724–756.** Offsets, status values, bounded hold duration and physical arming are added. However, sequence completion is incompatible with unrestricted overlapping/coalesced commands; the fixture still lacks enough behavioral specification; and polling sub 5 cannot establish the claimed final-DMA timing invariant. Details below. |
| 16 | **Fixed — original should-fix** | **Plan:637–647; `keyboard.json:200`; `scripts/keymap_to_c.py`.** `KC_NO`, JD’s map as authority, readback, regeneration and exact two-key diff are retained. They prevent transparent fall-through or unrelated map replacement. This remains an end-of-P1 action. |
| 17 | **Fixed — original should-fix before P1** | **Plan:554–558; `config-menu-mockup.html:472–589`.** QR y=22, inverted-row x=3 padding and the marker’s full horizontal envelope now agree with the mockup. The row/envelope rectangles include harmless background padding. |

The dispositions overstate completion principally for **1, 2, 9, 11, 15, C2’s queue policy, and S0’s proof**. The P2/P3 dispositions are acceptable as deferrals.

**Outstanding S0 findings and recommended decisions**

1. **Must-fix: specify RESIDUAL’s executor and exact completion test.**

   **Locations:** [Plan:160](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:160), Plan:175–184,240; [display.c:2990](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2990), `display.c:1413,1429,1873–1878,3000–3023`.

   The existing numbered stages enqueue clock/text work. The current restore dispatch returns before the ordinary `lq`/`gq` drain. Merely extending that dispatch through RESIDUAL therefore strands the queues.

   Separately, Plan:164 says RESIDUAL ends when the queues are empty and DMA is idle. Immediately after the battery outline stage, the remaining battery parts are still dirty. Queue emptiness is insufficient.

   **Recommended decision:** RESIDUAL owns an explicit scheduler:

   - Service/recover an in-flight transfer and consume its loss result.
   - Drain queued labels/glyphs, or paint one battery component, or paint one stale logo, with a defined priority and at most one selected paint operation per pass.
   - Reach DONE only after **all** required battery/logo work, both queues and the final successful transfer are complete, and the generation is undamaged.
   - A damaged generation stays incomplete during the five-second retry cooldown.

   Battery rendering is buildable here: `draw_battery(false)` is already incremental and does not internally require `dash_paints()`. The two actual logo regions can likewise be painted from `mac_mode` and `connection_mode`; the five public logo functions are state-setting entry points, not five separate visual regions.

   Keep ordinary dashboard and wake painters gated during restoration. Explicitly choose whether the restore satisfies `wake_clock_due`/`wake_batt_due`, or whether `wake_paint_step()` retires them after DONE. Today, `draw_clock()` updates `clock_gen_painted`, but does not clear `wake_clock_due`; battery restoration does not clear `wake_batt_due`. Ignoring that distinction leaves wake release dependent on later work or the timeout.

2. **Must-fix: make restore validity consistent across every ownership/session transition.**

   **Locations:** [Plan:167](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:167), Plan:182–218; `graphics/display.c:1174–1220,1444–1448`.

   Two concrete failures remain:

   - Start from DASH/NONE/DONE, then enter standalone Debug or Animation. Those rows do not invalidate DONE. Action O only mentions superseding a **running** restore. Consequently, the specified `display_restored(gen)` can remain true while another screen occupies the panel.
   - While PENDING, issue the startup-style restore request—op 27 sub 7 permits exactly that exercise. The request sets WAITING. A second opener cancels PENDING but does not start the waiting restore. DASH/NONE/WAITING then has neither ordinary painting nor active restoration.

   **Recommended decision:**

   - Every handoff away from DASH invalidates current-dashboard completion, including a previously DONE restore.
   - PENDING preserves active dashboard restoration; it must not turn that work into WAITING merely because a session exists.
   - On PENDING cancellation, explicitly start any genuinely deferred restore, otherwise preserve the current dashboard work.
   - Make `display_restored(gen)` additionally require DASH and a valid current ownership epoch.

   `display_restored(gen)` is computable with the proposed added state, but only after those invariants are defined. Existing code has no such generation/phase record.

   **Should-fix:** a wrapping u8 cannot literally guarantee that a superseded generation “never becomes true.” Define token lifetime or use a wider token. Do not compare indefinitely retained generation IDs after wraparound.

3. **Must-fix: complete recovery for Animation and the existing Debug renderers.**

   **Locations:** [Plan:175](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:175), Plan:205,211,255–267; [lcd_bus.c:1116](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1116); `display.c:831–855,905–914,2940–2984`.

   The “any blit lost” row delegates to text that defines DASH, MENU and DEBUG behavior, but **no ANIM behavior**. More fundamentally, Animation currently returns while `blit_done` is false, and the display pump skips it. A missed completion can therefore prevent reaching the give-up/loss path at all.

   Debug also does not currently use C3 slots. Its Health and Camera renderers have separate dirty/shown buffers, and shown characters are advanced when DMA starts. Invalidating menu slots alone cannot repair them.

   **Recommended decision:**

   - Apply bounded busy recovery under ANIM too; after exhausted recovery, explicitly retry/repaint a frame or stop and restore the dashboard.
   - Define Debug recovery using its real Health/Camera shadows and clear cursor, or explicitly migrate those renderers into the new slot system.
   - Establish one consumer of the loss latch and an ownership boundary rule. Quiesce and account for the old owner’s outstanding transfer before changing ownership, or retain its owner/generation identity.

   The migration checklist names the relevant sites, but “each with its own recovery” is still a requirement rather than an implementation contract.

4. **Must-fix: a layout clear must complete successfully, not merely finish advancing its cursor.**

   **Locations:** [Plan:368](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:368), Plan:389; `graphics/display.c:834–838`; `graphics/lcd_bus.c:207–211,1016–1023`.

   The non-superseded clear correctly handles navigation during clearing. It does not specify what happens when a band fails.

   A permitted implementation using today’s `lcd_clear_rect()` can advance past a failed band: that function discards `lcd_blit_wait()`’s boolean result. Repainting the new layout’s slots cannot erase old pixels outside those slots.

   **Recommended decision:** on clear loss, retry the failed band or restart the full banded clear; never declare the clear complete until every band succeeded. Navigation still changes only the target. If the intended clear is exclusively a synchronous CPU stream with a different failure model, say that explicitly and define how quiesce losses are attributed.

   Four bytes **are sufficient per slot** once geometry is const and progress is global. Also specify these inexpensive invariants:

   - Only one slot owns the global partial cursor.
   - Replacing that work resets its cursor or invalidates it; another PARTIAL slot cannot resume using somebody else’s cursor.
   - Repainting covers the complete footprint, including background, absent rows, an absent scrollbar and the inverted-row padding pixel.

   Revision 4’s rule 4 is now loss invalidation, not arbitrary old-rectangle erasure. The earlier erase/storage problem is resolved; successful clear recovery is the remaining issue.

5. **Must-fix: define coalesced-input ordering and session boundaries.**

   **Locations:** [Plan:303](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:303), Plan:316–348.

   Capture independent of capacity, saturating turns and separate control latches fix the earlier queue-full/release problem. They do not define what the model does with simultaneous turns, click, Back and close.

   **Failure:** turns arrive, then a click, then more turns before `menu_task()`. A single net count and click bit cannot preserve that order. Applying the whole count before the click can select the wrong item; applying it afterward can modify the newly entered screen. Pending latches can also survive close and affect a new session.

   **Recommended decision:** choose and test a deterministic policy. A small implementation can:

   - Give close precedence and discard remaining session input on close.
   - Give Back precedence over click.
   - Freeze the preceding turn count when a click is latched, and discard/count later turns until that action is consumed.
   - Clear pending navigation at ownership/session handoffs where it no longer applies.

   Also define disarming while OPEN/PENDING. I recommend cancellation/close, while retaining owed release bits.

   Synthetic holds need a separate logical identity: they must not set or clear physical capture ownership. Otherwise injecting a synthetic press while a real forwarded knob press is held can cause that real release to be swallowed. Alternatively, explicitly reject conflicting synthetic gestures.

6. **Must-fix: `accept_seq`/`done_seq` needs an implementable completion discipline.**

   **Locations:** [Plan:681](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:681), Plan:689–710.

   **Failure:** accept hold sequence 1, then turn sequence 2. The turn can finish before the hold. Advancing `done_seq` to 2 falsely implies the hold is done; later setting it to 1 moves completion backward. Coalesced turns also erase individual command boundaries.

   **Recommended decision:** make synthetic mutations single-flight for S0:

   - Reads remain available.
   - Reject another synthetic mutation while one is outstanding.
   - Define completion separately for click/turn, hold, pattern paint, restore request and loss injection.
   - A hold completes after release or explicit cancellation, not merely after its press is installed.
   - Use exact equality with the outstanding sequence, with defined wrap behavior.
   - Separate “model action applied” from “requested pixels finished.”

   A richer cumulative-completion protocol is possible, but requires additional ordering/outcome state that the current contract does not specify.

7. **Must-fix: make the fixture and final-DMA proof concrete enough to execute.**

   **Locations:** [Plan:689](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:689), Plan:699–714,731–749; `scripts/lockchan_media_test.c:1–29`; `build.sh:25–26`.

   A fixture is the right solution, but “deterministic A and B patterns over fixed slots” does not yet define:

   - The two patterns and alternate layout.
   - Their operation counts and valid `n` range.
   - Whether “stopped after n” waits for operation n’s DMA to complete.
   - What turns, click and Back do.
   - The Diagnostics return destination before P1 exists.
   - How the fixture exercises timeout/hold behavior without the menu tree.

   These are needed for a host script to know what to expect.

   Polling phase and current DMA-busy state also cannot prove that DONE was **never asserted early**. An invalid early DONE can disappear into a valid-looking snapshot once DMA finishes. Sub 5 does not expose outstanding dashboard queues, battery/logo work, or a latched completion-invariant failure.

   **Recommended decision:** define a small fixture table and expected framebuffer outputs, then add a sticky assertion/result captured at DONE/COMMITTED transitions. Include the relevant pending-work/busy/loss conditions. Host tests must run the production state/scheduler code against a fake backend, not a separately reimplemented model.

   Sub 8 tests the response to a loss notification; it does not test the hardware timeout/retry path. The existing `HC_BLITFAULT` mechanism is under `WDT_TEST_HOOKS`, whereas ordinary `build.sh dev` defines `AK820_DEV_HOOKS` without that macro. Explicitly choose a dedicated fault-test build/control or limit the claimed board proof.

**Additional should-fix clarifications**

- **HC_DEVHOOK framing — should-fix.**  
  **Plan:670–714; `hid_protocol.c:1026–1028,1288–1293`; `scripts/devhook.py:43–51`; `scripts/current_map.py:155–164`.**  
  The request and reply fit exactly within 32 bytes. Operation 27 is unused. There is no firmware dispatch collision: VIA sends the modified reply buffer without redispatching byte 0.

  However, existing HC_DEVHOOK success replies retain `0x07` at byte 0. Both cited host helpers reject or ignore the proposed success value zero. Either preserve byte 0 and put op-27 status in an unused payload byte, or explicitly provide a dedicated op-27 codec. The disposition should not imply compatibility with existing helpers.

- **Preserve the rest of `display_band_busy()` — should-fix before S0.**  
  **Plan:241; `display.c:2600–2609`; `power.c:246`.**  
  The new ownership condition is correct as a replacement for the function’s first branch. It is not its entire truth condition: pair hints, alerts and live parameter overlays must still count as busy. Otherwise a power notice can replace them. Say explicitly that those tests remain.

- **Diagnostics Camera selection — should-fix before P1.**  
  **Plan:199.**  
  The row groups “Diagnostics > Health or Camera” but always produces Health. Selecting Camera must enter Camera directly; `DBG_PAGE`/op 1 from MENU can still enter Health.

- **Protocol completeness — should-fix before S0.**  
  **Plan:689–714.**  
  Freeze fixture screen IDs, restore-phase numeric values, early-stage values for S1/P3 fields, pattern-argument validation and time overflow behavior. Declaration order is specified for owner/session only.

- **RAM estimate — nit.**  
  **Plan:470–484.**  
  The table totals 212 B; the following paragraph still says approximately 220 B. More materially, explicitly account for logo stale flags, visibility, loss/wake instrumentation, stream bookkeeping and fixture state. The linked floor is the controlling gate, so this estimate discrepancy is not itself a blocker.

**The remaining C1–C8 checks**

| Contract | Result against this checkout |
|---|---|
| **C1** | The executable old-flag use sites are now covered by the checklist. The separate predicates are the right design, with the `display_band_busy()` qualification above. Slider/state updates, op 1, animation stop and ordinary pending entry have policies. The restore, wake and recovery exceptions above prevent calling the table complete/buildable as written. |
| **C2** | Correct hook and fall-through. `action_exec()` clears weak mods and handles applicable one-shot timeouts before preprocessing. Keycode/source-layer lookup occurs before module and keyboard preprocessing; module preprocessing precedes the keyboard hook. A false keyboard-hook return skips combos, tapping and later record processing. Tick events can still advance pending tapping. See `quantum/action.c:95–138`, `quantum/quantum.c:168–177,258–282`. |
| **C2 encoder/Fn/release details** | `ENCODER_CW_EVENT`/`ENCODER_CCW_EVENT` are event types; index is `event.key.col`, with special rows 253/252. VIA uses the encoder map. Every dequeued detent produces a press/release pair and two configured 1 ms waits: `quantum/keyboard.h:35–97`, `dynamic_keymap.c:93–95`, `encoder.c:38–45`. Reading active Fn layer bits at the knob press is correct; unresolved layer-tap Fn does not count. Under the physical capture rules, neither mismatched press/release routing direction should occur. Preserve that guarantee across synthetic input and disarming. |
| **C3** | Four-byte slots are sufficient for signature/state/generation with fixed const geometry and a serialized cursor. Chunked footprint repaint and banded layout clears can satisfy the one-operation-per-pass rule. Failure recovery and cursor ownership need the additions above. |
| **C4** | The listed current users are complete: AM/PM, battery tile and transport icon via `lcd_blit_ram`; battery outline/fill and padlocks via `lcd_fill_rect`. Those rendering paths are main-thread work. Startup’s deferred callback requests restoration; it does not render using scratch. The DMA callback only updates GPIO/state. The FIFO ISR reads the buffer during `spiSend()`: `hal_spi_v2_lld.c:96–125`. Begin/quiesce/acquire/window, synchronous byte sends, end/release, and no open stream across passes fit the current bus. Keeping quiesce outside `lcd_window()` is essential. |
| **C5** | Plausible and buildable. `__heap_end__ - __heap_base__` from the existing `nm_out` works for dev and daily and accounts for linker alignment. Missing symbols must fail. `arm-none-eabi-size -A` can inspect `.heap`; default aggregate `size` totals cannot establish the free gap because `.heap` reserves remaining RAM. See `build.sh:113` and `rules_memory.ld:309–316`. The cited historical ELF measurements were not remeasured in this round. |
| **C6** | Correct for the named writers. `via_command_kb()` runs before VIA dispatch; returning false preserves processing and reply. RGB-matrix Set/Save are therefore observable before they act. `process_record_kb()` precedes `process_underglow()` and `process_rgb_matrix()`; press-edge UG and release-edge RM interception are correct. Repeat directly calls setters. `consumer_mod` does not write RGB config. Power caps/reinitialization, battery RGB cut, sleep driver operations and lock-light media/clock handling are not RGB-config writes. See `via.c:290–298,708–738`, `quantum.c:355,414–417`, `param_overlay.c:44–58`, `power.c:119–154`, `battery.c:1270–1282`, `ch582f_ajazz.c:512–560`. |
| **C7** | Safe as specified: a pure function over local snapshots of volatile byte/bool scalars, no menu-structure access and no PWM-phase mutation. Individual byte accesses do not tear on M0; volatile does not create a multi-field atomic transaction, but this design does not require one. Publish visibility after entry setup and apply wake hold last. `0x4000` is free in the 16-bit blocker word. Append `"menu"` at index 14 of `ak820battery.py:106`. Neither `ak820health.py` nor the Rust daemon currently decodes that blocker word. |
| **C8** | Matches the mockup for the listed layouts: rows/separator/scrollbar, range value/bar, hue value/envelope, bunny slices/credits, and 99×99 QR at `(14,22)`. Camera’s existing firmware layout remains a separate preserved diagnostic screen. |

**S0’s scope is now appropriate; its proof remains partly specified.**

The round-3 scope recommendations have these dispositions:

| Recommendation | Verdict |
|---|---|
| Physical capture with `MENU_ENABLE` off | **Fixed in principle.** The armed dev mode enables the real hook. Specify disarm and synthetic/physical interaction. |
| Visible test display before P1 | **Partly fixed.** A fixture is included, but its behavior and expected outputs need freezing. |
| Session visibility and sleep safety in S0 | **Fixed.** C7 and `DSB_MENU` moved into S0. |
| Accepted/completed and restore observability | **Partly fixed.** Fields exist; sequence semantics and sticky completion evidence are missing. |
| Fake-framebuffer plus board pixel proof | **Partly fixed.** Appropriate approach; require shared production logic, explicit fixtures and real versus injected-loss distinctions. |
| Physical input proof | **Fixed in scope.** The requested release, Fn-first, hold, remapping and pending-tapping cases are included. They still require actual QMK/physical execution. |
| Timing proof separated from encoder backlog | **Fixed in scope.** Define the exact S0 script; keep real backlog and renderer-budget decisions in S1. |

With `MENU_ENABLE` off, an armed fixture **can** exercise real capture and session behavior. Op 27 alone cannot prove physical encoder draining, QMK’s actual tapping/modifier behavior, real sleep/wake hardware sequencing, or DMA timeout/retry recovery. Those need the separately identified physical tests, fault controls and build configuration.

Keep S0’s scope and stage order. Resolve the seven must-fix contracts above before handing revision 4 to the implementer.
---

## Dispositions (Warren, gremlin, 10-23), fixed in revision 5

The verdict, not ready for S0, is agreed. Five claims were checked in the
source before relying on them:
- the restore dispatch returns before the ordinary `lq`/`gq` drain
  (`display.c:2990-3000`);
- `anim_task()` returns while `!blit_done` (`lcd_bus.c:1116`), and the pump
  skips the animation, so its lost completion is never given up;
- the debug page's `dbg_shown` advances when a glyph's DMA starts
  (`display.c:847-851`), and the camera page keeps `cam_shown` and
  `cam_dirty` of its own;
- HC_DEVHOOK's handled replies keep `0x07` at byte 0, which
  `scripts/devhook.py` checks;
- `HC_BLITFAULT` is built only with `WDT_TEST_HOOKS`, which the
  `instrumented` flavour sets and `dev` doesn't (`build.sh:26`).

The five logo functions are two regions, as codex says: the OS logo
(`mac_mode`) and the connection row (`connection_mode`).

| # | Disposition |
|---|---|
| 1 | **Agreed** (items 2 and 3 below). |
| 2 | **Agreed** (item 1 below). |
| 3, 4, 5, 8, 12, 13, 14, 16, 17 | Fixed, as codex found. 12's accounting is in the redone budget. |
| 6, 7 | Agreed: requirements on P3's own plan. |
| 9 | **Agreed.** PENDING keeps the owner DASH, so a restore requested then runs, and only PENDING's move to OPEN supersedes it. Cancelling PENDING leaves the dashboard's work as it was. |
| 10 | **Agreed.** S0's workload is a named script, `scripts/menu_s0_session.py`, with its mix and pacing written down. The general stall-counter test is marked as P1's gate. |
| 11 | **Agreed** (item 4 below). |
| 15 | **Agreed** (items 6 and 7 below). |
| Item 1, RESIDUAL | **Agreed.** RESIDUAL has its own scheduler, inside the restore dispatch: the busy recovery, then one queued glyph, then one battery part, then one logo, then a damaged generation's restart after the cooldown, then `DONE`. The ordinary painters stay gated until `DONE`. `DONE`'s invariant names every condition. At `DONE`, `wake_batt_due` is cleared, and `wake_clock_due` only if the painted clock generation has reached the wake's target. |
| Item 2, validity | **Agreed.** Leaving DASH sets `WAITING` from any phase, `DONE` included. `display_restored(gen)` requires the owner DASH. `restore_gen` is a u16, and a token is meant only for the restore it was read from. |
| Item 3, recovery | **Agreed.** One consumer of the loss latch, at the pump's top. At an ownership change the bus is quiesced and a latched loss dropped, since every new owner starts with a full clear. The handlers are per owner. DEBUG resets its own shadows (`dbg_shown`, `cam_shown`, both dirty masks, the clear band) and keeps them: the debug renderers don't move into C3's slots. ANIM gets the pump's bounded busy recovery, and a loss stops the animation and restores the dashboard. |
| Item 4, clear success | **Agreed.** Clears go through `lcd_clear_rect_ok()`, and a failed band is retried with the cursor not advanced. This covers the menu's, the restore's and the debug page's clears. The cursor invariants are written: only the slot the cursor names may resume, a slot it leaves becomes `INVALID`, and a repaint covers the whole footprint. |
| Item 5, input order | **Agreed, with codex's policy.** A latch freezes the turns before it, and later turns are dropped and counted. Close outranks Back, which outranks click. `menu_task()` applies the turns, then the latch. Close and every handoff clear the input. Disarming while PENDING or OPEN closes the session. Synthetic input never touches the physical capture bits: a synthetic hold is refused while the knob is down, and a physical press cancels a synthetic hold. |
| Item 6, sequences | **Agreed.** Single flight: one synthetic mutation at a time, the rest answered busy, with reads always answered. Completion is defined per kind, a hold's after its release. `last_seq` is compared exactly and is never 0. "Applied" (`last_state`) is separate from "painted" (`pixels_done`). |
| Item 7, fixture and proof | **Agreed.** C9 defines the fixture: F1's 27-operation A and B, F2's grid, the input, the Diagnostics return, the timeout, and the expected frames from the same tables. A sticky `invariant_fail` mask catches an early `COMMITTED` or `DONE`. The host tests run the production files against a fake backend. A real DMA timeout is tested on a `devfault` build (dev plus `-DWDT_TEST_HOOKS`), and sub 8 is described as a test of the handlers only. |
| Framing (should-fix) | **Agreed.** Byte 0 stays `0x07` on a handled reply; op 27's status is byte 5, read by the tests' own codec. |
| `display_band_busy()` (should-fix) | **Agreed.** Only its first test is replaced; the pair hint, the alert and the param overlay stay. |
| Camera (should-fix) | **Agreed.** Diagnostics > Camera goes straight to the Camera page. |
| Protocol values (should-fix) | **Agreed.** Sub 5 freezes the enum values, the screen ids, the flags, the S1 and P3 placeholders (0), the argument ranges and the time's saturation. |
| RAM (nit) | **Agreed.** The table adds the logos, visibility, instrumentation, stream and fixture state, and totals ~229 B. |
