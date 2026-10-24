# Codex review: the build plan, revision 7 (2026-10-24)

Prompt: [`review-prompt-config-menu-build-plan-rev7.txt`](review-prompt-config-menu-build-plan-rev7.txt). Reviewed: `plans/CONFIG-MENU-BUILD-PLAN.md` at revision 7 (`50ad9c9`'s parent tree). Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Revision 7 is not ready for S1 implementation as written.** The approach is sound, but the paint subdivision, timing target, and LED acceptance rules need the amendments below. I would keep C2’s current Fn semantics and implement the dedicated menu keycode in P1.

I compared the plan revisions through local Git objects, verified the reviewed menu/display sources against `4b899118` and `f2b107be`, and read the board evidence. All reads stayed inside the repository. This was static review; process creation failed, so I ran no builds or tests.

1. **Must-fix before S1’s code — distinguish logical paint operations from their resumable pieces.**

   **Where:** [C3/C4](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:504), [C9’s operation-count contract](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:754), and [menu_slots.c](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:90).

   **Yes, subdivision is compatible with C3**, provided the scheduler retains progress and actually returns to the main loop. Giving several ≤N-byte pieces separate windows but sending all of them in one pass does not impose a per-pass limit. The sum of payloads sent during that pass must be ≤`MENU_PASS_BYTES`.

   I would **preserve C9’s 27 logical operations**, including its existing stop positions. Add a subpiece cursor beneath the current logical-operation cursor. Today, every successful `layout->paint()` return advances `chunk` and counts an operation; it cannot mean “one piece sent, more of this operation remains.”

   The amendment should specify:

   - Each piece covers a valid RGB565 rectangle, completes its window/stream, releases scratch and CS, and yields. Use complete pixels; split by rows or explicit horizontal subrectangles, respecting source stride.
   - A slot remains `PARTIAL` throughout all pieces. Its signature describes the complete target, including style.
   - Resume only for the same target generation/signature. Retargeting, invalidation or abandoning that cursor discards its subpiece progress; restart the slot from the beginning.
   - Count a logical operation once its final piece completes, or once it terminates in failure. Intermediate pieces, busy retries and wait passes do not increment `ops`.
   - `ms_stop_after(n)` stops after that logical operation terminates, with no transfer outstanding. A reached stop still survives navigation until the specified release.
   - A failed piece stops the operation and leaves loss handling to the existing owner dispatch. No slot commits over a pending loss.

   This preserves `FX_F1_OPS`, pattern 2’s range and the existing reference frames. Counting pieces instead is possible, but would require changing all three deliberately.

   **Add host cases at every new piece boundary:** partial B→A, changed selection, loss, layout change, close/reopen and stop completion. The existing tests interrupt at logical-operation boundaries; they will not exercise these new intermediate states.

2. **Must-fix before S1’s code — define which paints the byte limit covers, especially DMA clears.**

   **Where:** [C4’s “every paint op” wording](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:587), [clear implementation](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:349), and [restore bands](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1426).

   The largest fixture colour operation is 2,048 bytes, but that is **not the largest existing paint**. Each 128×16 clear band represents **4,096 bytes**, and menu layout clears, restore clears and Fn+D clears already use **flash DMA**, followed by a wait. They do not use the prototype’s polled fill path.

   I would define `MENU_PASS_BYTES` as the menu’s synchronous pixel-payload budget, retain flash DMA for clears/glyphs, and give those operations a separately measured wall-time bound. Audit restore and dashboard RAM/fill components against the whole-pass target too; bounding only F1/F2 cannot establish that target.

   If clear bands also need subdivision, retain a band subcursor: advance `clear_band` or `po_restore_advance()` only after every piece of that band succeeded. Retry failed work without skipping pixels; navigation must still finish an existing layout-clear sweep. Keep `PO_CLEAR_BANDS`, `DBG_CLEAR_BANDS`, `MB_BANDS` and probe indexing consistent.

   **Do not implement this by making an existing synchronous drawing function return halfway through its rectangle.** Its callers currently advance shadows and restore state on return. Yielding belongs in a scheduler whose completion contract understands partial work.

3. **Must-fix before S1’s code — frame 15 ms as a measured whole-pass target under a defined workload.**

   **Where:** [C4](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:587), [S1 measurement requirements](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1066), [HC_ACCT](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/loop_acct.h:22), and [encoder draining](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/encoder.c:30).

   **15 ms is a reasonable engineering target**, leaving useful margin below the existing 25 ms regression threshold. It is not a universal guarantee supplied by a byte count.

   HC_ACCT’s timestamp differences measure **elapsed wall time, including preemption**, not exclusive CPU execution time. Correct S1’s “CPU time” wording. With the row ISR consuming roughly 74%, main-thread execution has roughly 26% of the CPU before other interrupts; that explains the sensitivity, but is not a reliable formula for choosing N. Do not multiply measured HC_ACCT durations by that factor again.

   The measurement must include pixel expansion, window commands, quiescing, send/end overhead, row ISR preemption, UART/USB service, main-thread radio parsing/ACK work, QMK work and housekeeping. Smaller rectangles add more windows and interrupt-driven command bytes, so cost does not scale purely with payload size.

   Clock edges also need precise treatment: MENU suppresses dashboard drawing, and the pump already skips a pass when dashboard clock work ran. Preserve those guards. Exercise edges during entry, PENDING, DEBUG and restoration; do not assume a full dashboard clock repaint accompanies every menu piece.

   The encoder is an independent limit: its drain still performs both configured 1 ms waits for every dequeued detent, even when the menu captures the events. A backlog can exceed 25 ms before painting begins. Once S1 defines its supported burst/backlog workload, exceeding the target must require either a bounded drain or an explicit restriction of the claim—not merely “weighing” a fix.

   **Suggested wording:**

   > Choose N from measured piece costs so complete main-loop passes remain ≤15 ms throughout the named normal-operation workload, including its specified encoder backlog and radio traffic. Require zero ≥25 ms passes. Record operation maxima, whole-pass maxima and repaint completion latency. Measure injected faults and recovery separately.

   Keep the physical typing test: neither a byte limit nor a pass counter alone proves lossless input. Also define how maxima are retained; op 27’s **last** paint duration can miss an intervening slow operation.

4. **Should-fix — settle Open 5 by retaining active-layer Fn semantics.**

   **Where:** [C2](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:402), [the current lookup](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:46), and [QMK’s tapping state](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/action_tapping.c:130).

   **My choice for S1: accept and document the miss.** Define Fn as an active `WINFN` or `MACFN` layer at the early hook. An unresolved layer-tap is not yet Fn. This preserves QMK’s decision and the existing capture contract without adding a dependency on private tapping state.

   Describe the consequence as **ordinary mapped knob input being forwarded**, rather than universally harmless: the observed board case was safe, but a different VIA mapping could perform a different action.

   A fixed physical-Fn coordinate is unsuitable here. The default maps already contain multiple Fn assignments, and VIA can move or remove them. It would also treat a tap-hold key as Fn before QMK decides whether its tap or hold action applies.

   A better physical-state variant would track early presses resolved as `MO(WINFN)` or `MO(MACFN)`, retaining their identities through release. That handles moved momentary Fn keys and both platforms, but needs multiple-held-key tracking and a policy for other layer actions. It still cannot infer the intended hold of an unresolved `LT`.

   The tapping-buffer option would need a core accessor over the currently **static** `waiting_buffer`, its head/tail indices and, for broader tap-hold support, `tapping_key`. Keycodes would be inspected with `get_record_keycode(record, false)` to avoid altering the source-layer cache. It must account for queued releases, overflow/clearing and tap-hold decisions; “any queued Fn press” can mean a key already released. QMK also caches the source layer rather than an immutable VIA keycode.

   That is a maintained core patch tied to tapping implementation details and configuration. I would not take that dependency to eliminate this documented window.

5. **Should-fix now; required before P1 implementation — complete the menu-keycode amendment. P1 is the right stage.**

   **Where:** [Open 3](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1175), [input capture](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_input.c:91), and [owner transitions](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:124).

   Match the **resolved menu keycode on press**, then retain the event’s physical identity for release routing. A single additional capture bit is insufficient if VIA binds the code to multiple keys: overlapping presses need independently owed releases. A small matrix-position bitmap is a straightforward option.

   Its press should use the existing session transitions:

   | State | Menu-key press |
   |---|---|
   | DASH/NONE | Open, or enter PENDING during the wake hold |
   | DEBUG/NONE | Hand off to MENU/OPEN |
   | PENDING | Cancel the pending request |
   | MENU/OPEN or DEBUG/OPEN | Close the entire session |
   | ANIM | Refuse, while capturing press and release |

   Its release performs no click, Back or second toggle. Route owed releases before session, enable-state and current-keycode checks, including after disarming or a VIA rewrite.

   A press while the knob is held must preserve the knob’s existing release ownership. If its press was forwarded, forward its release. If captured, consume it. Opening/closing clears old gestures and pending input, so that release cannot click into the new session or fire a delayed Back.

   Keep knob/detent identity routing authoritative during a session, and explicitly document the behavior when this keycode is mapped onto those controls. Do not let one event execute both routes.

   **The Fn issue is conditional:** a menu keycode already resolved on a base layer needs no Fn test and can be captured before unrelated tapping resolves. A menu keycode available only on the buffered Fn layer can still be missed because the early lookup sees the underlying mapping. Correct Open 5’s blanket statement accordingly.

   Append the enum/VIA entry, retain the existing activation policy, and test duplicate bindings, held-key remaps, both platforms, all session states and both kinds of held knob. P1 is appropriate because that is when the real menu becomes available.

6. **Must-fix before S1’s code — make the LED gate executable and define completion during continuous input.**

   **Where:** [S1’s LED gate](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1077) and [menu_s0_ledrate.py](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_ledrate.py:71).

   **Within 2% is a sound sustained-refresh regression gate**, alongside the timing and visual checks. Use a matched baseline and require `activity_rate ≥ 0.98 × baseline_rate`; an unexpectedly higher rate should prompt checking the configuration/timebase.

   It is not sufficient by itself to exclude flicker. A 50 ms interruption diluted over five seconds costs only 1%. The current one-second Fn+D windows similarly dilute short transitions. Retain JD’s spin check and add transition-focused repeated measurements or row-start-gap observations. The reported ISR **duration** maximum does not measure how late the ISR started.

   The script now checks completed A/B toggles, but it does **not** enforce the 2% ratio or ge25, its initial settling timeout is silent, and Fn+D transitions have no completion assertion. Those need explicit failure conditions.

   Include sustained mono repainting, F2, selection changes, real spins and backlog draining, layout clears, open/close, the restore through `DONE`, and Health/Camera entry, updates and exit. Keep lighting configuration, transport load and instrumentation matched between baseline and activity measurements. Validate counter continuity and board-time/host-time agreement.

   Define two completion rules:

   - For paced repaint tests, every requested target must settle successfully within its deadline.
   - During continuous spins, C3 may supersede intermediate targets. Require correct input outcomes, accounted supersession and bounded settlement of the final target after input stops.

   Requiring every intermediate spin target to finish would contradict C3. Conversely, reporting an excellent ISR rate while painting barely progresses must fail the responsiveness/completion gate.

   Exclude boot/reset, counter resets, intentional sleep or lighting-mode changes, and deliberately injected bus faults from the normal matched-rate comparison. Record their recovery separately. **Ordinary restores, Fn+D painting and encoder waits remain included.**

7. **Should-fix — finish the polling hardening and add polling-failure proof.**

   **Where:** [S1’s first step](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1051), [spi0_poll_send](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:158), and [FIFO dispatch](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:105).

   The prototype fixes match the dispositions: failed sends stop, latch loss and share the BUSY failure path. Retain them.

   I would take both hardening items: explicit idle/ownership checks and FIFO dispatch respecting interrupt enable and transfer ownership, while preserving DMA dispatch. An entry check discovering a live transaction must not blindly reset it and strand its owner; use the established bounded abort/quiesce path or refuse safely.

   Correct “only the FIFO interrupt is masked”: `IE = 0` masks **all SPI0 interrupt sources**, including DMA completion. Serialization and quiescence make that safe.

   Add focused tests for a polling failure in a middle piece and at the BUSY tail, verifying loss, cleanup and repaint. Existing HC_BLITFAULT cases exercise DMA completion loss, not this new failure path.

8. **Notes and factual corrections.**

   **Where:** [revision summary/C4](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:11), [Open 1–4](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1167), and [board results §10](/C:/Users/jdlien/code/ak820-pro/plans/GREMLIN-RESULTS.md:318).

   - Replace the current worst-pass figure with **24 ms**, distinguishing the earlier 23 ms LED-test observation. The later prototype workload had no playing track, so it does not establish the loaded media case.
   - Open 4’s “main loop pays the same time” is stale; the recorded repaint throughput decreased. Its suggestion that restore/Fn+D clear bands share the polled-fill mechanism is also incorrect: those clears use DMA.
   - The cursor correction is right **for equal footprints**: opaque mono painting sends foreground and background pixels either way. Half-row scheduling reduces each operation’s size; it does not halve the total area required to repaint two complete selected/unselected rows.
   - Preserve the distinction between **S0 accepted with recorded exceptions** and every case independently proved. A4 remains open, animation recovery was not exercised with populated frames, and the original A11 acceptance included the documented media-gate exception.
   - A13’s prose should say: after stop 13, row 0 is B, row 1 has its first half repainted, and row 2 onward remains A. The stored reference pixels agree with that; “rows 0–2 in B” is the inaccurate description. This correction does not itself require rerunning the board case.
---

## Dispositions (Warren, 10-24): every finding accepted, folded into revision 8

1. **Logical ops versus pieces (must-fix): accepted.** C4's budget now keeps
   C9's 27 logical ops, the stop positions and the op count. It adds a piece
   cursor under the slot's op cursor, with codex's rules: each piece whole
   and yielding; the slot `PARTIAL` with a whole-target signature; a resume
   only for the same generation; an op counted once; the stop after a whole
   op; a failed piece leaving the loss to the owner. Host cases at every
   piece boundary.
2. **What the byte limit covers (must-fix): accepted.** `MENU_PASS_BYTES`
   is the menu's CPU-fed pixel payload per pass, summed over its pieces.
   DMA clears and glyphs keep their own measured bound, with the
   band-subcursor rules if a band ever needs splitting. The restore's and
   the dashboard's RAM tiles are audited too. "No draw function returns
   halfway" is written in.
3. **15 ms as a measured whole-pass target (must-fix): accepted,** in
   codex's wording:
   - HC_ACCT's time is wall time, and the plan says so;
   - maxima are kept over the run;
   - the clock-edge guards stay, and the edges are exercised;
   - the encoder drain becomes required if the named backlog breaks the
     target, or the claim is narrowed;
   - the physical typing test stays.
4. **"Open" 5 (should-fix): accepted.** Settled as documented: Fn is an
   active WINFN or MACFN layer at the early hook. The miss is described as
   forwarded mapped input, not "harmless", and the three rejected options
   are recorded with codex's reasons.
5. **The menu keycode (should-fix): accepted, P1.** The amendment is
   written into "Open" 3:
   - matched by its resolved keycode on the press, with owed releases per
     key (a bitmap), not one bit;
   - the state table;
   - a release that does nothing;
   - the held-knob rules, and the knob's routing authoritative;
   - the conditional Fn question.
6. **An executable LED gate (must-fix): accepted.** The gate is now:
   - a ratio of at least 0.98 against a matched baseline;
   - the coverage list, and transition windows or row-start gaps;
   - the script's explicit failure conditions;
   - the two completion rules (paced repaints, continuous spins);
   - the exclusions.
7. **Polling hardening and its failure proof (should-fix): accepted.** Both
   hardening items are taken: an entry check that refuses or takes the
   bounded abort path, never a blind reset; and an IE- and ownership-aware
   FIFO dispatch, as a chibios-contrib patch. A dev/devfault hook will fail
   a poll mid-op and at the BUSY tail. C4 now says `IE = 0` masks every
   SPI0 source, DMA completion included.
8. **Notes and corrections: accepted.**
   - The worst pass is 24 ms (A11's workload on the prototype), and 23 ms
     was the earlier LED test.
   - "Open" 4's stale lines are gone: the clears never used the fill path.
   - The cursor note says "for the same footprint", and half rows don't
     halve a move's area.
   - The status says "accepted with recorded exceptions" and lists them.
     A4 has since passed (`GREMLIN-RESULTS.md` §10, 10-24).
   - A13's prose is corrected in `GREMLIN-RESULTS.md`: row 0 B, row 1's
     first half, and rows 2-7 A.
