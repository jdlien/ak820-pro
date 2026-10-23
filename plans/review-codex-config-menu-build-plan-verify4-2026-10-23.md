# Codex review 5: verifying the configuration menu's build plan, revision 5 (2026-10-23)

The plan verified is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md),
revision 5 (`9d2724b`), against the fourth review
([`review-codex-config-menu-build-plan-verify3-2026-10-23.md`](review-codex-config-menu-build-plan-verify3-2026-10-23.md))
and its dispositions. The model was gpt-6-astra at xhigh, read-only, run from
gremlin with the firmware at `b9555ff3e6` and the prompt in
[`review-prompt-config-menu-build-plan-verify4.txt`](review-prompt-config-menu-build-plan-verify4.txt).
Codex's answer follows verbatim, then the dispositions. Revision 6 carries
the fixes.

---

**Revision 5 is not ready to implement S0 as written. Three must-fixes remain:** Camera loss recovery, retaining dashboard losses through the self-heal cooldown, and terminal outcomes for deferred or discarded op-27 work.

The restore scheduler, successful-clear requirement, and physical-input ordering are substantially improved. I would not block S0 over the remaining fixture colours, workload sequencing, or similar implementation choices.

This is static verification against the supplied checkout. I read only inside the repository, changed nothing, and ran no builds or hardware tests. “Fixed” means the plan prescribes a workable implementation.

References below use:

- **P:** [CONFIG-MENU-BUILD-PLAN.md](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md)
- **D:** [graphics/display.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c)
- **L:** [graphics/lcd_bus.c](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c)
- Other board-relative paths start at `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`.

**The remaining must-fixes**

1. **Must-fix — Camera recovery repaints the Health grid over Camera.**

   **Locations:** [P:241](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:241); [D:840](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:840), D:845–853,1000–1014,1162–1166,1183–1191.

   Revision 5 explicitly resets **both** shown grids to nonmatching contents and sets **both** dirty masks. That is unsafe with the existing dispatcher:

   ```c
   if (debug_big && cam_pump_glyph()) return true;
   /* then process dbg_dirty */
   ```

   On Camera, `dbg_text` contains spaces. After recovery clears the panel and finishes the Camera cells, `cam_pump_glyph()` returns false. The invalidated Health shadow then causes its spaces to be painted across the panel, erasing the Camera image. Camera’s shadow still claims its digits are present, so unchanged cells need not return.

   **Fix:** make dispatch exclusive after the clear:

   ```c
   if (debug_big) return cam_pump_glyph();
   ```

   Alternatively, invalidate only the active page and keep the inactive Health grid blank and clean on Camera. Require a framebuffer test that continues pumping **after** Camera has finished, with time and displayed values frozen; otherwise the overwrite can escape the test.

   **Disposition verdict:** partly fixed. Health recovery and Animation recovery are specified adequately; the Camera prescription is wrong.

2. **Must-fix — consuming the loss latch unconditionally loses a dashboard failure during the cooldown.**

   **Locations:** [P:225](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:225), P:238–239; [D:2958](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2958); L:1016–1023.

   Today, the five-second check precedes `lcd_blit_lost_take()`. Consequently, a loss remains latched until healing is allowed.

   Revision 5 moves consumption to every pump pass, but the `DASH/DONE` handler only says to request the rate-limited self-heal. It specifies neither retained pending damage nor a later executor for a request suppressed by the cooldown.

   **Failure:** a self-heal finishes; another ordinary dashboard glyph is given up within five seconds. Its shadow has advanced. The pump consumes the loss, the cooldown prevents another restore, and no specified state remembers the missing pixels. `display_restored(gen)` can remain true.

   **Fix:** rate-limit **starting the repair**, not remembering the damage. For example, record damage immediately and move DONE to damaged RESIDUAL; that existing scheduler can wait out the cooldown and start CLEAR. Keep `display_restored()` false while that repair is owed.

   Test two losses less than five seconds apart, with the first restore already completed before the second loss.

   **Disposition verdict:** partly fixed. Damaged *running* generations are handled; losses after DONE are not fully contracted.

3. **Must-fix — op 27 has accepted commands with no defined terminal outcome.**

   **Locations:** [P:823](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:823), P:833–837,853–854; P:179–190,229–233,393–395.

   Single-flight fixes out-of-order sequence completion, but introduces two unresolved lifecycle cases:

   - **Deferred restore:** sub 7 under MENU, DEBUG or ANIM records WAITING without starting a new generation. Its completion rule nevertheless waits for “the restore it started.” A following op-27 close is busy. MENU may eventually time out, but standalone DEBUG/ANIM has no session timeout, and the request has no defined generation to await.
   - **Discarded injected loss:** sub 8 is accepted, then an ownership change quiesces the bus and drops its latched loss before the pump’s handler consumes it. The required completion event never occurs. The outstanding sequence can permanently block subsequent mutations.

   Clearing coalesced input at a handoff needs the same accounting if an accepted synthetic action was among the discarded input.

   **Fix:** define terminal outcomes for every disposal path. My recommended S0 policy is:

   - Sub 7 completes when the restore request is **installed**, including a deferred request. Observe actual restoration separately through phase/generation.
   - A boundary that discards an outstanding injected loss or synthetic action completes its sequence as `superseded` or `cancelled`.
   - Busy/bad-argument replies leave the outstanding command’s sequence and state unchanged.
   - Sub 6 completes when arming/disarming and any resulting session transition have been applied.

   This preserves single-flight while allowing the host to request, interrupt and observe restoration.

   **Disposition verdict:** partly fixed. Ordinary input and hold completion are now workable; deferred and discarded work still require decisions.

**The 17 carried findings**

For fixed rows, severity is the carried severity, not an outstanding blocker.

| # | Verdict / severity | Verification, failure addressed, and treatment |
|---|---|---|
| 1 | **Partly fixed — must-fix** | **P:179–337.** Migration coverage, separate predicates, animation admission/stop, ownership invalidation and default refusals are workable. Camera recovery and dashboard cooldown recovery still fail as described in must-fixes 1–2. Retain the transition architecture and correct those handlers. |
| 2 | **Partly fixed — must-fix** | **P:192–224; D:1394–1434,1873–1878,2990–3023.** RESIDUAL now has a real executor and the required completion conditions. The original stranded-queue/unfinished-battery failure is fixed. The DONE-loss cooldown hole still permits false current-dashboard validity; apply must-fix 2. |
| 3 | **Fixed — original must-fix** | **P:368–403; `ak820pro.c:425–431`.** Release routing precedes enable/session checks; capture survives close; gestures do not. Synthetic input no longer changes physical capture ownership. This prevents a swallowed press’s remapped release from executing after close. Retain these rules. |
| 4 | **Fixed — original must-fix** | **P:345–367,404–421,922–925; `quantum/action.c:95–138`, `quantum/quantum.c:277–282`.** Actual preprocessing order, user-hook fall-through, weak-mod clearing and tapping limitations match the code. The relevant physical tests remain. Do not expect captured events to interrupt another pending tap-hold. |
| 5 | **Fixed before P1 — original must-fix** | **P:593–623; `quantum/process_keycode/process_underglow.c:17–30`, `quantum/via.c:708–738`, `param_overlay.c:44–58`.** Shared UG press actions, RM release actions, wrappers, repeat and VIA Set/Save are covered. This prevents Cancel or forced Save from mishandling an intervening external RGB write. Retain the whole-config conflict policy and enabled-last adapter. |
| 6 | **Fixed for P3 deferral — must-fix in P3’s plan** | **P:744–755; `bluetooth/ch582f_ajazz.c:1530,1587,1755`.** Driver-owned operations and a separate reviewed plan are sufficient now. The existing bounce/select overwrite remains real. Completion evidence, cancellation destinations and retirement of queued retries remain P3 requirements. “Cancelling is defined” still states a requirement, not a supplied implementation. |
| 7 | **Fixed for P3 deferral — must-fix in P3’s plan** | **P:756–765; `bluetooth/ch582f_ajazz.c:1501–1513`.** Suspending forwarding and requiring successful release delivery addresses presses reaching an intermediate host. Delivery tracking, failure exits and cancellation cleanup remain for P3; queue emptiness must not substitute for delivery success. |
| 8 | **Fixed — original must-fix** | **P:625–651; D:135,214–242,283–312; `sleep.c:240–267`.** Visibility follows OPEN, including Diagnostics; PENDING only blocks sleep. Requested settings remain separate, and the ISR reads scalar snapshots. This handles requested Off/zero without altering persisted preferences. |
| 9 | **Partly fixed — remaining should-fix** | **P:179–188 versus P:275.** The substantive PENDING policy is fixed, but the startup row still says “not DASH, **or a session** → WAITING.” Applied literally, that recreates DASH/PENDING/WAITING and strands restoration after cancellation. Change the row to “owner is not DASH.” The intended decision is already explicit, so I treat this stale row as a should-fix. |
| 10 | **Partly fixed — should-fix** | **P:928–938; `quantum/encoder.c:30–45`.** S0 is correctly a measurement, and physical backlog is correctly deferred to S1. The named script supplies a mix, not the actual fixed sequence or polling cadence. Freeze those in the script so results are reproducible and commands reach the intended screens. |
| 11 | **Fixed — original must-fix** | **P:451–499; L:207–211,1016–1023.** Successful-band retry, fixed footprints, full background coverage and exclusive cursor ownership repair the old clear/partial-paint holes. Return the clear transfer’s actual success result and advance only on success. |
| 12 | **Fixed — original should-fix** | **P:506–589; L:131–188,214–220,689–712; `build.sh:113`.** Scratch lifetime and stream ordering fit the synchronous CPU paths and ISR reader. No stream crosses passes. Linker-symbol accounting is implementable. The expanded estimate is still an estimate; linked allocation and stack measurements remain authoritative. |
| 13 | **Fixed for P2 — original must-fix** | **P:723–742; `flash_stats.c:31–32,38,58,128–142`.** Element-count assertion, widened masks, frozen page 1, new page 3 and simulator/host updates address the compile and reply-overflow failures. Encoding and non-migration policy are specific enough for P2. |
| 14 | **Fixed before P1 — original should-fix** | **P:709–721; `power.h:68–76`, `power.c:329–335`, `build.sh:146–149`.** Promotion includes declaration, body and the forbidden-symbol guard. Clock mapping, effect names, second-colour semantics and indicator initialization are specified. |
| 15 | **Partly fixed — must-fix** | **P:805–875,894–938.** Framing, sequence equality, single-flight, sticky checks and fault-build scope are major improvements. Deferred/discarded mutations still lack terminal outcomes—must-fix 3. Completion-observation clarifications below remain should-fixes. |
| 16 | **Fixed — original should-fix** | **P:774–784; `keyboard.json:200`; `scripts/keymap_to_c.py:7–31`.** JD’s map remains authoritative; `KC_NO`, readback, regeneration and the exact two-key diff are retained. This avoids transparent fall-through or replacement of unrelated mappings. |
| 17 | **Fixed before P1 — original should-fix** | **P:653–663; `config-menu-mockup.html:472–589`.** QR placement, inverted-row padding and the hue marker envelope agree with the visual spec. Retain the complete footprints, including background padding. |

**The seven outstanding S0 findings from round 4**

| Round-4 finding | Verdict | Revision-5 check |
|---|---|---|
| 1. RESIDUAL executor and DONE | **Fixed — original must-fix** | **P:192–219.** Queue draining runs inside the restore dispatch. `lq`, then `gq`, battery and the two actual logo regions have an executor. Busy recovery precedes painting; damage prevents DONE. The wake flags have an explicit retirement policy. The separate post-DONE loss problem is must-fix 2. |
| 2. Ownership/session restore validity | **Partly fixed — should-fix remains** | **P:184–223,275.** Leaving DASH invalidates DONE; the query requires DASH; tokens are u16 with a stated lifetime. PENDING preservation is explicit, except for the contradictory startup row. Correct that row. The old wraparound clarification is fixed. |
| 3. Animation and Debug loss recovery | **Partly fixed — must-fix remains** | **P:225–248.** Animation now reaches bounded recovery and stops/restores on exhausted recovery. Health’s real shadows are addressed. Camera’s prescribed reset causes the overwrite in must-fix 1. Boundary dropping is pixel-safe under the required fresh clear, but must retire synthetic work too. |
| 4. Successful layout clear | **Fixed — original must-fix** | **P:451–487.** A failed band cannot advance the cursor; the rule includes Menu, restore and Debug. Full-footprint repaint and serialized partial progress are explicit. |
| 5. Coalesced-input order/boundaries | **Fixed — original must-fix** | **P:381–403,425–429.** A latch freezes preceding turns; later turns are discarded; close outranks Back, which outranks click. Handoffs clear navigation. Disarming closes/cancels while preserving owed releases. Synthetic holds are isolated from physical capture. |
| 6. Sequence completion discipline | **Partly fixed — must-fix remains** | **P:823–837.** Single-flight resolves overlapping hold/turn completion. Per-kind completion exists, but deferred restores and discarded work need must-fix 3. |
| 7. Concrete fixture/final-DMA proof | **Fixed in substance — should-fixes remain** | **P:673–703,488–493,894–925.** C9 gives usable layouts, operation counts, input and return behaviour. Production state machines, fake pixels and sticky transition checks address the old proof gaps. `devfault` enables the real recovery path. Partial-stop observability and the scope of `pixels_done` need the clarifications below. |

**The four additional should-fixes, and the RAM nit**

| Finding | Verdict | Verification |
|---|---|---|
| HC_DEVHOOK framing | **Fixed — should-fix** | **P:807–822; `hid_protocol.c:1026–1028,1288–1293`; `scripts/devhook.py:43–51`; `scripts/current_map.py:155–164`.** Keeping byte 0 at `0x07` fixes framing compatibility. Status at byte 5 and sequence at byte 6 fit. The dedicated codec is still needed to send arguments and interpret op-27 fields; existing helpers are not a complete op-27 client. |
| Preserve `display_band_busy()` tests | **Fixed — should-fix** | **P:306; D:2600–2609.** The text now explicitly replaces only the first branch and retains pair hints, alerts and parameter overlays. Power notices therefore cannot displace them merely because ownership is DASH. |
| Diagnostics Camera selection | **Fixed before P1 — should-fix** | **P:263–266.** Camera is a direct destination; `DBG_PAGE`/op 1 can still enter Health. This entry fix is separate from Camera’s loss-recovery bug. |
| Protocol completeness | **Partly fixed — should-fix** | **P:844–875.** Numeric owners, phases, screens, flags, placeholders and timing saturation are supplied. Remaining details include sub-6 completion, unused pattern arguments and partial-stop observation. Specify these without changing the underlying architecture. |
| RAM estimate | **Fixed — nit** | **P:570–589.** The entries total 229 B and include the previously omitted categories. This is not linked evidence. Apply the floor to `devfault` too: `WDT_TEST_HOOKS` adds state beyond the ordinary dev build, including the injection and trace arrays in `bluetooth/ch582f_ajazz.c:247–282`. |

**Checks of the new mechanisms**

The **RESIDUAL schedule itself is now buildable**. `draw_battery(false)` samples its state and advances an incremental component without checking dashboard ownership internally; its pass guard resets in `display_pass_end()`—D:1796–2012,3341–3344. “One component” can contain several synchronous primitives, particularly battery text; it does not mean one DMA arm.

The logo interpretation is correct: the OS image and connection strip are two regions, driven by `mac_mode` and `connection_mode`—D:1533–1537,3429–3455. The connection digit is separate. Both queues must drain before completion because their entries are retired when DMA starts, not when it finishes.

The **wake retirement rule** is consistent with existing clock-generation tracking: `draw_clock()` records the generation at D:1252, while the wake flags remain separate at D:3308–3338. Keep the existing wrap-aware generation comparison. A later correction remains pending for `wake_paint_step()` after DONE.

The **ownership-boundary loss drop** is sound for pixels provided the stated ordering is followed: quiesce, account for/drop the old loss, then start the new owner’s complete replacement. A new owner’s clear failure remains its own failure and must be retried. Dropping the notification must also finish any corresponding op-27 command.

The **clear wrapper** is a workable fix. One wording correction: L:211 discards the result of waiting for the clear’s own DMA, not merely a preceding quiesce. `lcd_clear_rect_ok()` must propagate that result. An idle bus after exhausted recovery is not successful clearing.

The **devfault proposal uses the correct mechanism**:

- `build.sh:25–26` currently separates dev hooks from `WDT_TEST_HOOKS`.
- `hid_protocol.c:978–982` supplies HC_BLITFAULT when the latter is defined.
- L:651–659,786–789 suppresses completion interrupts.
- **N=1** exercises retry success; **N=2** exercises give-up and owner recovery.

Implement `devfault` as the complete dev configuration plus that macro, including dev structural checks and the heap-floor check. This proves lost-completion recovery; it does not by itself simulate every hardware fault class.

**Remaining ambiguities and recommended decisions**

These are should-fixes or ordinary implementation decisions, rather than additional S0 blockers.

| Severity | Location / concrete risk | Recommended decision |
|---|---|---|
| **Should-fix** | **P:173,275:** the stale startup row can put DASH/PENDING into WAITING despite the corrected prose. | Only a non-DASH owner defers restoration. Update the WAITING description and table accordingly. |
| **Should-fix** | **P:839–841,865; D:831–855,1000–1014:** `pixels_done` is described for the “current owner,” but Debug has shadows rather than C3 slots, and DASH has queues/battery/logo work. A slot-only test can report completion between Debug glyphs or between restore stages. | For S0, define this bit as **MENU fixture pixels settled**, false for other owners. Use restore phase/generation for DASH. If a global bit is wanted, specify a separate predicate per owner. |
| **Should-fix** | **P:835,846,860–875:** pattern 2’s sequence completes when its target is installed, while `pixels_done` stays false. Neither tells the host that operation `n` has actually finished and the fixture has stopped. | Expose a completed-operation count and stopped flag, or give pattern 2 a distinct completion rule ending at that stop. Otherwise a script can request A before reaching the intended interruption point. |
| **Should-fix** | **P:680–703,846:** the 27-operation count does not explicitly say how clear bands, DMA-completion passes, or an already-B target are counted. | Count completed logical paint operations, excluding layout clear and polling passes. Require settled A before the partial-B test, or explicitly force a fresh 27-operation paint. Choose and freeze colours and scrollbar construction in const tables during S0. |
| **Should-fix** | **P:928–938:** the command mix alone does not guarantee the eight clicks visit F2 and Diagnostics, or that restore requests occur in a useful state. Timing also depends on polling cadence. | Commit an explicit 50-step array, initial state, expected destinations and fixed polling cadence; repeat it ten times. Record accepted outcomes and actual transitions, not just 500 transmissions. The script is currently a planned artifact. |
| **Should-fix** | **P:826–837,852:** arm/disarm completion and mutation rejection bookkeeping are incomplete. | Complete sub 6 when applied; preserve the outstanding sequence on busy/bad-argument responses; initialize sequence/state to zero/none. Include cancellation and supersession tests from must-fix 3. |
| **Nit** | **P:392–395:** “apply turns, then latch” could be read before the close exception. | Check close first and discard turns; otherwise apply the frozen turns followed by Back/click. The intended policy is already sufficiently clear. |

The dispositions accurately describe most improvements, but overstate completion for **the Debug loss handler, dashboard loss handling, and op-27 completion**. The P2/P3 deferrals remain appropriate.

**S0’s structure is buildable, but its current contract is not yet correct and provable as written. Resolve the three must-fixes before implementation begins.**
---

## Dispositions (Warren, gremlin, 10-23), fixed in revision 6

The verdict, three must-fixes left, is agreed. Three claims were checked in
the source first:
- the debug pump falls through to the Health grid when `cam_pump_glyph()`
  has nothing to paint (`display.c:840-845`);
- today's self-heal tests the 5 s cooldown before `lcd_blit_lost_take()`, so
  the loss stays latched until a repair is allowed (`display.c:2963-2964`);
- `lcd_clear_rect()` discards the result of waiting for its own DMA
  (`lcd_bus.c:207-211`).

| Finding | Disposition |
|---|---|
| Must-fix 1, Camera | **Agreed, both parts.** A loss invalidates only the page showing (on Camera, Health's grid stays blank and clean), and the debug pump's dispatch becomes exclusive, `if (debug_big) return cam_pump_glyph();`, as a migration item. The host test pumps Camera on after its cells finish, with the time and values frozen. |
| Must-fix 2, a loss after `DONE` | **Agreed.** The damage is recorded at once: `DONE` goes back to `RESIDUAL` with `restore_damaged`, so `display_restored()` is false from that pass, and the scheduler starts the repair when the cooldown allows. Tested with two losses under 5 s apart, the first restore done before the second. |
| Must-fix 3, op 27's outcomes | **Agreed, with codex's policy.** Sub 7 completes when the request is installed, `WAITING` included; restoration is watched through the phase and generation. Discarded work ends as superseded or cancelled. Busy and bad-argument replies leave the outstanding sequence alone. Sub 6 completes when applied. At boot the sequence is 0 and the state none. |
| 1, 2, 15 (carried) | Agreed: must-fixes 1-3. |
| 9 and round 4's item 2 | **Agreed.** The startup row and `WAITING`'s description now say only an owner other than DASH defers a restore. |
| 10 | **Agreed.** `scripts/menu_s0_session.py` is a fixed 50-step array run ten times, from a stated start, with each step's expected screen and owner, a 20 ms poll of sub 5, and every outcome recorded. |
| 11 | **Agreed.** `lcd_clear_rect_ok()` returns the clear's own transfer result, and only success advances the band. |
| The rest of the 17 | Fixed, as codex found. |
| `pixels_done` | **Agreed.** It means the MENU fixture's pixels are settled, and is false under any other owner. DASH is read from the restore's phase and generation. |
| Pattern 2's stop | **Agreed.** Pattern 2 completes when the fixture has stopped; sub 5 adds the completed-operation count (byte 29) and the stopped flag (byte 30). |
| The count | **Agreed.** Completed logical paint operations, not clear bands or waiting passes. Pattern 2 needs A settled first, so each partial B is a fresh 27-operation paint. The colours and the scrollbar are fixed in `const` tables in S0's first commit. |
| `devfault` | **Agreed.** The whole dev configuration plus `-DWDT_TEST_HOOKS`, with dev's checks and the heap floor; N=1 for a retry that succeeds, N=2 for the give-up. |
| The nit, close first | **Agreed.** `menu_task()` checks close first and discards the turns. |
