# Codex review 2: verifying the configuration menu's build plan, revision 2 (2026-10-23)

The plan verified is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md),
revision 2 (`54456fb`), against the first review
([`review-codex-config-menu-build-plan-2026-10-23.md`](review-codex-config-menu-build-plan-2026-10-23.md)).
The model was gpt-6-astra at xhigh, read-only, with the prompt in
[`review-prompt-config-menu-build-plan-verify.txt`](review-prompt-config-menu-build-plan-verify.txt).
Codex's answer follows verbatim, then the dispositions. Revision 3 carries
the fixes.

---

**The plan is not ready to implement S0 as written.** Revision 2 fixes much of revision 1, but S0 still requires decisions about ownership transitions, early input capture, partial repaint invalidation, and memory limits. The settings and Bluetooth sections also contain unresolved implementation contracts.

I inspected only files inside the requested repository. I made no changes and ran no hardware operations. “Fixed” below means the revised prescription resolves the original finding—not that firmware implementing it already exists.

**Verification of the 15 original findings**

1. **Partly fixed — must-fix: panel ownership needs a transition contract and complete migration list.**  
   Plan: [ownership, line 161](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:161).

   The enum, explicit handoffs, shared-buffer reset, and animation exclusion address the original simultaneous-owner problem. However, `display_panel_owned()` cannot replace all existing checks indiscriminately: some distinguish Debug from Animation; others must also recognize dashboard restoration.

   The migration must explicitly cover these existing uses:

   | Existing use | Required treatment |
   |---|---|
   | `display.c:136–148` — flags and `display_set_paused()` | Replace ownership flags; preserve animation start/stop side effects. |
   | `display.c:1170–1220` — debug query and three-step toggle | Preserve Health → Camera → Dashboard outside a menu session; define its behavior inside one. |
   | `display.c:1447` — deferred dashboard redraw | Do not start a restore underneath Menu, Debug, or Animation. |
   | `display.c:2601` — band busy | Include restoration as well as non-dashboard owners. |
   | `display.c:2963,2974,2982` — self-heal and pump branches | Dispatch by owner; retain owner-specific recovery and rendering. |
   | `display.c:3316,3330` — wake painting/completion | Preserve the distinction between panel owner and pending wake work. |
   | `display.c:3362–3377` — housekeeping | Keep Debug composition distinct from dashboard painting and restoration. |
   | `display.c:3431–3455` — five logo painters | Update RAM, mark stale, and schedule painting when permitted. |
   | `ak820pro.c:374`; `power.c:246` | Animation admission and Minimal-mode visibility need different predicates. |
   | `lcd_bus.c:1097,1112` | Migrate animation ownership without diverging from `anim_on`. |
   | `hid_protocol.c:1029` | Route op 1 through the same defined debug transition policy. |

   Concrete failure: a mechanical replacement makes Animation qualify for Debug’s Minimal-mode exception, or a generic “owned” early return prevents the Debug/Menu painter from running. Independently retaining `anim_on` and the new owner without an invariant can leave animation DMA running after ownership changes.

   **Fix:** specify a transition table, including refusal and cleanup. Recommend refusing Animation while Menu/Debug owns the panel; retaining a separate menu-session state during Diagnostics; and defining `DBG_PAGE`/op 1 during a session as session-controlled diagnostics transitions. Require animation ownership and `anim_active()` to agree. Keep restoration as explicit pending work, not an implicit fifth interpretation of `PANEL_DASH`.

2. **Partly fixed — must-fix: `display_restored()` still does not mean restored.**  
   Plan: [line 188](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:188). Code: [queue draining](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3000), [battery restoration](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1865).

   Refreshing connection status, retaining stale logos, re-priming overlays, and adding menu-local DMA recovery are good fixes. But “restore ended and both queues drained” remains insufficient:

   - The pump removes a glyph when its DMA is **started**. Both queues can be empty while the last transfer is running.
   - The restore battery stage paints only the outline. `batt_dirty` still represents the bolt, text, and bar.
   - The proposed stale-logo work can remain pending after the numbered restore stages.

   Concrete failure: a waiter sees “restored,” changes ownership or releases visibility, and exposes an incomplete dashboard.

   **Fix:** define completion for a particular restore generation, including successful final DMA completion, battery components, and stale logos. At minimum, include `!lcd_blit_busy()` and the outstanding restore-owned damage. Keep `display_bus_idle()` separate. Do not gate the work needed to finish restoration on `display_restored()` itself.

   Overlay classification also needs a decision: the existing [`display_set_param_status(const char *)`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2560) cannot identify whether a post came from a menu adapter or an external hotkey. I recommend suppressing all parameter overlays during the menu session, including its Diagnostics handoff, while retaining alerts and other underlying state.

3. **Fixed — original severity must-fix: matching-release ownership.**  
   Plan: [line 255](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:255).

   Revision 2 explicitly consumes the release of every captured press after closing, Fn release, timeout, or long Back; forwards releases of previously forwarded presses; and handles the 600 ms release boundary exactly once. That resolves the original stray-release scenario in [`DBG_PAGE`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:425).

   Implement the state by physical control identity, not keycode. Preserve the capture bits through close and handoff; clear each only on its matching release.

4. **Partly fixed — must-fix: early capture is useful, but its guarantees are misstated.**  
   Plan: [line 252](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:252). Code: [`action_exec()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/action.c:95), [`pre_process_record_quantum()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/quantum.c:243).

   The actual contract is:

   - `get_record_keycode(record, true)` already performs layer/keymap lookup. With VIA, that includes the dynamic mapping. It returns the encoded MT/LT/one-shot keycode, before tapping interprets it.
   - Press lookup updates the source-layer cache. Release lookup uses the cached layer.
   - Encoder records resolve through the encoder map; they do not arrive with a special “volume detent” keycode. Identify them using event type, encoder index, and `KEYLOC_ENCODER_CW/CCW`.
   - Module preprocessing precedes the keyboard hook. Combo processing follows it. Returning false prevents combos and tapping from seeing that event.
   - **Weak modifiers have already been cleared** on a press. One-shot timeout handling has also already run. “Weak mods and one-shots are untouched” is false.
   - A consumed event also bypasses the later board hook: health key counts, USB wake attempts, user processing, and other board-side effects there do not run.

   Concrete failures include using `KC_MUTE`/volume codes to recognize remapped controls, expecting an unresolved Fn layer-tap to have activated its layer already, and expecting a captured click to interrupt another pending tap-hold or incomplete combo.

   **Fix:** retain position-based preprocessing, but document these semantics. Define Fn as an already-active `WINFN`/`MACFN` layer bit. Forward uncaptured events through `pre_process_record_user()`. Decide explicitly whether captured controls count toward health counters and USB wake.

   If preserving weak modifiers before any QMK side effect is a strict requirement, this hook cannot provide it: an earlier hook in **`quantum/action.c`**, before `clear_weak_mods()`, is required. Otherwise remove that guarantee and test the accepted behavior. Repeat cancellation and continued `modified_consumer_task()` service are correctly included.

5. **Partly fixed — must-fix: transaction hooks, transaction scope, and Lights commit need correction.**  
   Plan: [line 284](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:284), [Lights adapter, line 310](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:310).

   The cancellation-before-external-write policy and enabled-last RGB restoration are sound. The plan must name the actual interception points:

   - **VIA:** the board’s existing `via_custom_value_command_kb()` does **not** see standard RGB requests. [`via_custom_value_command()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:254) dispatches those and returns first.
   - A board-only solution is to implement **`via_command_kb()`**, recognize RGB Set/Save, cancel the RGB transaction, and return **false** so normal VIA processing and its reply continue. The call occurs before VIA dispatch at [`via.c:294`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:294).
   - Alternatively, override the weak `via_custom_value_command()` dispatcher, preserving its routing and delegating RGB commands to `via_qmk_rgb_matrix_command()`.
   - **Fn RGB keys:** observe standard RGB keycodes in `process_record_kb()` before returning them to QMK. Mirror [`process_rgb_matrix()`’s trigger edge](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_rgb_matrix.c:10): press with `RGB_TRIGGER_ON_KEYDOWN`, otherwise release. Also cover board `RGBM_*` wrappers and each repeat step.

   No quantum edit is necessary for those named writers. A universal interception policy for arbitrary direct RGB API callers would instead require hooks in `quantum/rgb_matrix/rgb_matrix.c`.

   Two further corrections:

   - Treat **the whole RGB configuration** as the conflict domain. “The setting being edited” is too narrow: a hue edit plus an external speed/effect change can still lose that change when a whole snapshot is restored. VIA Save has no individual setting.
   - **Do not commit Lights by toggling again.** Previewing Off → On and then invoking the saving toggle returns to Off. Save the chosen state with explicit enable/disable.

   The disabled-RGB adapter must cover Save as well as Preview/Cancel; otherwise the saving mode/HSV setter can still return without marking the edit dirty.

6. **Partly fixed — must-fix before P3: Bluetooth state names do not define the operation.**  
   Plan: [line 329](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:329). Code: [pending action state](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:179), [pair entry](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1587).

   Revision 2 correctly rejects the immediate select-then-pair sequence. However, `bt_ui.c` cannot currently observe enough to implement the promised states: the driver’s `pa` is private, public pairing status is optimistic, and retry exhaustion merely clears `pa.kind`.

   Concrete failure: a UI timer guesses selection has completed, calls `ch582_enter_pairing()`, and again overwrites a live bounce/select operation. A stale connection indication can also be mistaken for success on the requested slot.

   **Fix:** extend the driver’s existing control-operation machinery, exposing an operation ID, phase, and terminal result. Specify when selection permits pairing, how `5B 31` confirms advertising, how retry exhaustion becomes failure, and how superseding requests invalidate old results.

   Cancellation needs an explicit destination and sequence for every phase. Slider changes and existing Fn slot/pair keys must supersede the same operation. Merely citing the A6 documentation does not define how pending retries and already-queued commands are retired.

7. **Partly fixed — must-fix before P3: the report handoff still has a race.**  
   Plan: [line 322](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:322). Code: [report forwarding](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:595), [TX queue behavior](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1459).

   Waiting for held keys and settling releases address the original problem, but checking “no keys held” once is insufficient. A new press can arrive during release draining, selection, or the 700 ms bounce and reach an intermediate host.

   **Fix:** define a bounded sequence:

   1. Wait for the required all-up condition.
   2. Suspend A1/A3 forwarding for the transition.
   3. Send explicit outgoing releases and verify delivery success.
   4. Perform selection/bounce/pairing.
   5. Resume according to a defined all-up/resynchronization policy.

   [`ch582_send_releases()` and `ch582_tx_idle()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.h:37) are useful starting points. Idle alone is not success: a frame can leave the queue through give-up. Do not use the blocking drain helper for this UI operation. Test new presses during the transition, not just a key held before selection.

8. **Partly fixed — must-fix: visibility and sleep must follow the session, not the panel owner.**  
   Plan: [line 342](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:342). Code: [PWM/effective brightness](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:238), [sleep blockers](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:240).

   The requested-versus-effective distinction, three-minute policy, and explicit blocker fix the main original omissions. Missing details can still produce an invisible or permanently powered menu:

   - Diagnostics changes the owner to `PANEL_DEBUG` while the menu session remains open.
   - Setting `display_powered = true` on entry would lose the user’s previous Screen Off state unless separately preserved.
   - The PWM callback runs in ISR context; it should not traverse menu state or call transition logic.
   - [`display_set_power()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:308) directly writes the backlight GPIO, bypassing the PWM calculation.

   **Fix:** use a small ISR-safe visibility flag derived from session lifetime, and one effective-level calculation shared by PWM, reporting, and immediate GPIO updates. Apply the session power/cap/floor override without changing requested power or brightness; apply wake hold last.

   Allocate **`DSB_MENU = 0x4000`**, which fits the existing 16-bit masks, and test session activity rather than `owner == PANEL_MENU`. Update the blocker decoder in [`hostagent/ak820battery.py:106`](/Users/jdlien/code/ak820-pro/hostagent/ak820battery.py:106); it currently stops at Charge. Cover pending entry, Diagnostics, cancellation, and every exit. Keep bus-idle reporting independent.

9. **Fixed — original severity should-fix: defer entry during wake recovery.**  
   Plan: [line 183](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:183). Code: [`display_wake_release()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3335).

   Waiting until the wake hold is released avoids stranding hidden battery repaint work. This is a valid resolution of the original finding.

   S0 still needs the pending-entry API: there is currently no public “wake hold released” query. Recommend consuming and remembering the opener immediately, preserving its release ownership, then activating after release of the wake hold. Define a second opener as cancellation of that pending request.

10. **Fixed for the original measurement recommendation — should-fix follow-up on the performance guarantee.**  
    Plan: [paint budget, line 203](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:203), [S1, line 441](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:441).

    Half-row default, whole-pass measurements, HC_ACCT timing, retained RTC deferral, and corrected wall-time estimates address the original finding.

    However, half-row budgeting does not bound an entire input-heavy pass. [`encoder_handle_queue()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/encoder.c:30) drains the queue with two 1 ms waits per detent. The board allows a 32-entry queue. A sufficiently large backlog exceeds 25 ms before painting begins, even when every encoder event is swallowed.

    **Fix:** distinguish the renderer budget from the end-to-end pass bound. Measure real encoder bursts and backlog. If the latter bound is mandatory, add a bounded encoder-drain change in `quantum/encoder.c`, or explicitly limit the supported workload. An op-27 injection sweep cannot prove that bound.

    Also define one big-value operation as one glyph arm/completion step—not the entire multi-glyph region.

11. **Partly fixed — must-fix: damage needs invalidity and erasure semantics.**  
    Plan: [line 213](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:213). Visual source: [marker geometry](/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:539).

    Regions, styles, chunking, and delayed “shown” updates solve much of the original problem. They do not fully specify interruption:

    - Panel contains A; half of B is painted; navigation requests A again. If the saved signature still says A, comparison skips repainting and leaves half of B.
    - A region disappears or moves. Comparing only newly composed regions never erases its previous footprint.
    - Restoring the gradient under the hue marker does not erase its pixels **outside** the strip: the mockup’s vertical line and triangle extend beyond it.

    **Fix:** invalidate a region before its first partial write, track the target generation, and retain invalidity until all chunks and DMA complete. Superseding an incomplete target must repaint even when the new signature equals the old committed signature. Define old-footprint erasure and overlap invalidation, including the complete hue marker. Give the separator and scrollbar explicit treatment too.

    Add A → partial B → A and long-value → short-value cases to the renderer tests.

12. **Fixed for the original RAM correction — should-fix: make the new allocation budget and scratch contract concrete.**  
    Plan: [line 399](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:399). Code: [`tx_pixels()` and `lcd_fill_rect()`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:131).

    The log arithmetic and fixed-stack explanation are corrected. Sharing the two 512-byte buffers is credible against the current call graph:

    - `tx_pixels()` serves RAM blits, including AM/PM tiles, battery-slot art, and text icons.
    - The fill buffer serves battery outlines/fills and lock shapes.
    - The DMA completion callback updates GPIO/state; the backlight ISR updates PWM. Neither paints through these buffers.

    SPI’s ISR **reads the source buffer during `spiSend()`**, so sharing is safe only while the synchronous caller retains exclusive ownership through completion.

    **Fix:** specify main-thread-only, non-reentrant ownership; no pointer retention; no painting from callbacks/ISRs; interrupts remain enabled. Add an internal panel-order byte-stream emitter for generated chunks. Do not generate into the shared scratch and then pass that same storage through the existing byte-swapping `tx_pixels()` loop: its writes can overwrite source bytes before subsequent reads.

    The new region model also needs a maximum count and actual storage layout. A generic desired/shown descriptor array can consume the reclaimed 512 bytes by itself. Prefer generated-on-demand descriptors, compact shadows, and one active chunk cursor.

    Using the plan’s cited 32-byte baseline, sharing gives roughly 544 bytes before additions. Recommend an explicit minimum remaining gap—e.g. 128 bytes—and a corresponding aggregate budget, with log trimming if necessary. Include later-stage EEPROM, attribution, test-hook, and Bluetooth state. A map cannot budget structures that do not exist yet; use `sizeof` estimates first and verify the linked result.

13. **Partly fixed — must-fix before P2: EEPROM and flash-stat changes need an exact wire/layout contract.**  
    Plan: [line 417](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:417). Code: [`flash_stats.c`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_stats.c:12).

    The plan now recognizes the overflow, masks, offset shift, and erase/restore workflow. Specify the remaining details:

    - Append bytes 7, 8, 9 in a stated order; use level-plus-one encodings and define the battery-view default.
    - Widen **all** field-mask carriers: `kb_byte_field[]`, `pending_mask`, local `mask`, and local `m`. Widening only the declared masks still truncates bit 8.
    - Freeze page 1 at its original six field counters. Do not leave its loop bounded by the enlarged `KBF_COUNT`.
    - Recommend page **3**, containing the three new `u16` counters at payload offsets 0, 2, 4, with the rest reserved.
    - Define old-firmware handling for the new host query.

    The Python decoder currently reads pages 0–2 and unpacks `<4I6H` at [`ak820health.py:309`](/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:309). The Rust [`health.rs`](/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:24) does not currently implement HC_FLASHW; this is new decoder/request-path work, not simply extending an existing field list.

    Also update the diagnostic simulator: its [EEPROM stub still says six bytes](/Users/jdlien/code/ak820-pro/scripts/diag_sim/stubs/nvm_eeprom_eeconfig_internal.h:6).

    The `flash.sh` workflow is a valid migration policy for keymap and lighting. State plainly that it is **not a migration of the keyboard configuration block**; those values reset. Reserve the battery-view byte in P2 so P4 does not move VIA storage again.

14. **Fixed — original severity should-fix: setting adapters.**  
    Plan: [line 305](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:305).

    Explicit Clock mapping, all nine effects, ALPHAS_MODS’ speed-field meaning, promotion of the existing power setter, and indicator getters/validation resolve the original mismatch. The [mockup now lists the nine effects](/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:304).

    Implementation should promote both the power setter’s definition and declaration, and apply persisted indicator values during initialization. Keep effect names in one shared table; today `rgb_mode_short()` is static and conditional on `PARAM_OVERLAY`.

15. **Partly fixed — should-fix: tests are substantially better, but the integration proof is incomplete.**  
    Plan: [line 472](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:472).

    Reboot-based persistence, physical input testing, asynchronous injection, pixel checks, and isolated Bluetooth testing resolve most of the original weaknesses.

    Still specify:

    - Op 27 subcommand numbers, packet layouts, queue capacity, overflow behavior, completion/error replies, and daily-build rejection.
    - Tests using actual VIA RGB Set/Save packets and actual QMK `RM_*` handling, rather than only calls to `menu_external_write()`.
    - One-shot mappings, an unrelated pending tap-hold, and combo behavior where enabled.
    - A → partial B → A rendering, final-DMA restore completion, and menu-session lifetime during Diagnostics.
    - Separation of counter-reset tests from measured sessions.

    Concrete failure: model tests pass while the real VIA hook is never called, or QMK’s release-triggered lighting write occurs after the test’s assumed cancellation point.

**Additional findings**

16. **Should-fix — Fn+D unassignment must specify the exact edit and source board.**  
    Plan: [line 375](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:375). Code: [generated VIA layout](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/keymaps/via/keymap.c:40), [generator contract](/Users/jdlien/code/ak820-pro/scripts/keymap_to_c.py:7).

    The dump/regenerate workflow is correct. “Clear the key,” however, can mean `KC_NO` or `KC_TRNS`; the latter falls through and types D. Regenerating from the bench board can also import unrelated bench mappings into JD’s default.

    **Fix:** choose `KC_NO` for an inert unassigned chord; identify the authoritative board/dump; derive the two coordinates from `keyboard.json`; read back the writes; regenerate with an explicit dump path; and require a diff containing only the two intended key changes. Preserve encoders and QK_BOOT. Do this after Diagnostics is usable, not during S0. Existing owners’ stored mappings should otherwise remain intact.

17. **Should-fix — the build plan and visual spec still disagree on geometry and choice behavior.**  
    Plan: [editor layout, line 245](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:245), [preview policy, line 26](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:26). Mockup: [edit rendering](/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:529).

    The range editor’s big value is at y=22; the hue editor’s is at **y=44**, below the strip. Applying y=22 to both overwrites the hue strip. The mockup also treats every choice as an edit and previews it, whereas the plan says non-lighting choices apply only on click.

    **Fix:** provide per-screen coordinates and classify each choice as previewing or commit-on-click. Define the timeout for non-preview choice screens. Recommend 24 seconds for selection-only Power/Clock/Battery lists and 180 seconds of inactivity for actual preview editors.

    **Nit:** the stated QR footprint is also inconsistent. With 29 modules, scale 3, and the mockup’s two-module border, it is **99×99**, not approximately 95×95. Make the generated module count and chosen border authoritative.

**Stage order and proof**

The broad order is right: foundations → measured renderer → ordinary settings → persistence expansion → Bluetooth → battery view. The stage exits need tightening.

| Stage | Assessment and required proof |
|---|---|
| **S0** | Keep it first. Prove the ownership transition table, animation refusal/stop, startup and interrupted restores, stale-logo repair, physical release ownership, and partial-damage supersession. Record linked RAM usage for dev and daily builds. “Fn+D and animation behave as before” is insufficient. |
| **S1** | Correct placement. Measure CPU operation time and whole-pass time separately, including real encoder bursts, RTC/clock edges, and radio traffic. The test painter needs explicit panel ownership and restoration; “dashboard live” must not mean two painters writing the same pixels. |
| **P1** | Add actual VIA/Fn transaction integration, disabled-RGB Save, Lights commit, visibility from Screen Off/zero, Diagnostics session lifetime, and reboot persistence as explicit exit gates. Unassign Fn+D only after these Diagnostics paths work. |
| **P2** | Keep EEPROM, mask widening, reply page, host handling, and simulator updates together. Prove old pages remain byte-compatible, writes to each new field are attributed correctly, and unset/zero/invalid values boot correctly. |
| **P3** | Correct as a separate stage. Require driver-state tests for bounce/select/pair/cancel and transport tests for A1/A3 delivery, failures, and new input during transition. |
| **P4** | Correct dependency on the time-left view. Use the byte reserved in P2; verify unknown estimates and sleep/wake updates. |

Before S0 starts, I recommend adding a short implementation contract containing these decisions:

- The owner transition table, session lifetime, and complete migration checklist.
- The precise preprocessor input semantics, including deferred entry and uncaptured-event forwarding.
- A fixed-size damage representation with invalid/partial/complete states and old-footprint handling.
- The scratch-buffer ownership and byte-order API.
- A numerical RAM ceiling and minimum remaining headroom.
- S0’s runtime scope: capture and scheduler machinery may be built and tested, but **normal firmware must not swallow Fn+knob into an invisible menu before P1**.
- The per-pass task location: process queued menu events/timeouts before painting, while keeping the pump independent of gated display housekeeping.

Those are design decisions the implementing agent should receive, rather than discover while coding S0.
---

## Dispositions (ak820-pro-32, 10-23), fixed in revision 3

The verdict, not ready for S0 as written, is agreed. Four claims were checked
in the source before relying on them:
- `via_command_kb()` is called before VIA dispatches any command
  (`quantum/via.c:286-296`);
- weak mods are cleared on every press in `action_exec()`, before
  `pre_process_record_quantum()` (`quantum/action.c:95-97`);
- the sleep blockers end at `DSB_CHARGE = 0x2000`, so `0x4000` is free
  (`sleep.c:152-154`);
- `hostagent/ak820battery.py`'s `SLEEP_DSB` list ends at "charge".

Revision 3 adds "The implementation contract", the decisions codex listed,
which S0 builds from. Each finding:

| # | Disposition |
|---|---|
| 1 | **Agreed.** A transition table, with a menu session separate from the panel owner. Codex's migration table is in the contract. The animation is refused while a menu or debug page owns the panel, and the owner and `anim_active()` must agree. |
| 2 | **Agreed.** `display_restored(gen)`: the restore's stages done, both queues empty, `!lcd_blit_busy()`, `!batt_dirty`, and no stale logos. All param overlays are suppressed for the whole session; alerts are kept. |
| 3 | Fixed already. The contract adds that capture bits are keyed to physical controls and survive close and handoff. |
| 4 | **Agreed.** The real semantics are written down. Weak mods are already cleared on a press, which is accepted: it's what any key press does. Captured events skip the board's later effects, which is also accepted: no health key count, no USB wake. Fn is a `WINFN` or `MACFN` layer bit already active. Uncaptured events go on to `pre_process_record_user()`. |
| 5 | **Agreed.** The conflict domain is the whole RGB config. `via_command_kb()` sees VIA's RGB set and save, cancels an open RGB edit, and returns false. `RM_*` keys at QMK's trigger edge, the `RGBM_*` wrappers and each repeat step cancel it too. Lights saves by explicit enable or disable, never a toggle. The disabled-RGB adapter covers Save. No core file changes. |
| 6 | **Agreed.** P3 gets an operation API in `ch582f_ajazz.c`: an id, a phase and a terminal result, with superseding and cancelling defined per phase. P3 also gets its own short plan and codex round before any code. |
| 7 | **Agreed.** The handoff sequence: all keys up, suspend A1 and A3, releases delivered (acknowledged, not just an idle queue), the operation, then resume with the current report. Tested with presses made mid-transition. |
| 8 | **Agreed.** An ISR-safe override flag for the session's lifetime, and one effective-level function shared by the PWM, the reporting and `display_set_power()`'s GPIO write. The requested power and level are untouched, and the wake hold is applied last. `DSB_MENU = 0x4000`, from the session, decoded by `ak820battery.py`. |
| 9 | Fixed already. The contract adds the pending-entry state: the opener is consumed and remembered, and a second opener cancels it. |
| 10 | **Agreed.** The renderer's budget and the pass's whole bound are separate measurements. The encoder drain's 2 ms a detent is existing behaviour, measured in S1 with real spins; a bounded drain (a core change) only if the numbers demand it. A big value's step is one glyph. |
| 11 | **Agreed.** Regions carry a state of invalid, partial or committed, plus a target generation. Superseding an incomplete paint always repaints. Old footprints are erased, the hue marker's whole footprint is one region, and the separator and scrollbar are regions. Tests include A to partial B to A. |
| 12 | **Agreed.** The scratch contract: main thread only, not reentrant, held through `spiSend`'s completion, with a panel-order stream emitter, and generated bytes never passed back through `tx_pixels`' swap. The RAM ceiling: the menu and every later stage at most 400 B of BSS, with at least 128 B of heap gap left in the dev build. `build.sh` enforces it. |
| 13 | **Agreed.** The exact layout: bytes 7-9; every mask carrier widened; page 1 frozen; page 3 for the new counters; `ak820health.py` and the simulator's stub updated. The Rust daemon doesn't implement HC_FLASHW, so that stays out of scope. The battery-view byte is reserved in P2. `flash.sh` restores the keymap and lighting, but not this block, whose values reset. |
| 14 | Fixed already. The contract adds promoting `power_set_mode()`'s declaration as well as its body, applying the indicators at init, and one shared effect-name table outside `PARAM_OVERLAY`. |
| 15 | **Agreed.** Op 27's packet layout, subs, queue and replies are specified. The tests use real VIA packets (`ak820lighting.py`), and real `RM_*` keys through the wake rig's key, remapped for the test and put back. Also A to partial B to A, the final DMA, the session through Diagnostics, and counter resets kept apart. |
| 16 | **Agreed.** `KC_NO`, not `KC_TRNS`. The dump is JD's board's. The positions come from `keyboard.json`, the writes are read back, and the diff must show exactly two changes. It happens at the end of P1. |
| 17 | **Agreed.** Coordinates per screen kind, from the mockup. Choices are classed as previewing (Effect, Lights) or committing on the click (Power, Clock, Battery, the slots). The committing lists take the 24 s timeout, and the previewing editors the 3-minute backstop. The mockup follows. The QR code is 99x99. |

**Stages:** codex's exit proofs per stage are adopted. S0 builds the capture
and the scheduler, but the normal firmware doesn't capture `Fn` plus the knob
until P1 (`MENU_ENABLE` off). The menu's task runs each pass before the pump,
independent of the gated display housekeeping.
