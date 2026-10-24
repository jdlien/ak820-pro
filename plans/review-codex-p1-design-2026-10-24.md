# Codex's review of P1's design (draft 1), 2026-10-24

Prompt: [`review-prompt-p1-design.txt`](review-prompt-p1-design.txt). Reviewed:
[`CONFIG-MENU-P1-DESIGN.md`](CONFIG-MENU-P1-DESIGN.md) draft 1. Model
`gpt-6-astra`, reasoning xhigh, read-only. Verdict: not ready to code.

## Dispositions (Warren)

Every finding is answered in **draft 2** of the design:
- **1:** P1a's tree drops Lighting and Screen (six items); C7 is noted as
  already built; P1a's acceptance adds visibility from Off and level 0,
  Lights out, Diagnostics, and persistence/no-write tests.
- **2:** a session identity (`menu_kind`) and the opener table (the armed
  opener keeps the fixture for the scripts); op 27 subs 0-5, 10 and 11
  specified; Diagnostics' return rebuilds the stack.
- **3:** `MENU_ENABLE` on, `power_set_mode()` alone promoted, a daily
  build's check.
- **4:** no hash: exact bit-field signatures over bounded values; About's
  snapshot frozen as compact facts; the title state latched in the task.
- **5:** the art moves to its own step, P1d, with the adapters, the
  pieces, the op split and the URL specified there; the cost figures
  corrected.
- **6:** a per-flavour RAM table; devfault's shortfall met by a
  devfault-only `log_buf` trim; C5's ceiling amended or P3's share
  rebudgeted.
- **7:** un-highlight first (a scheduler rule and its tests), Reset
  counters' two pages as the mockup's, About's eight lines with formats
  that fit, Help's four topics (one wording change for JD), values and
  markers, opening/Back, paging, timers, the hint (lists only) and the
  flash; the completion predicate's loss check.

## The review, verbatim

**P1a is not ready to code from this draft.** The split is viable, but the draft needs explicit decisions on screen routing, target identity, rendering costs, and memory. C7 is already implemented; the more serious omissions are the devfault budget and the requirement to remove old highlights before painting new ones.

1. **Keep the split, but define an executable P1a tree.**

   Power and Clock do **not** need C6: turning changes the proposed choice; clicking applies it; cancelling writes nothing. Power’s Lights out mode changes output caps, not the RGB configuration, so it does not require an RGB transaction.

   Screen does require the Screen part of C6 as soon as turning previews brightness. Lighting likewise cannot be functional without its transaction. The draft exposes both without specifying what selecting them does. My recommendation is to omit them in P1a, producing six top-level items, and add them in P1b. Alternatively, move their necessary implementation forward. An apparently functional Screen row with an unspecified click is not a complete design. [P1 split and tree](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-P1-DESIGN.md:30)

   **C7 must remain active throughout P1a**, including Diagnostics and committing Lights out. It already does: `bkl_effective()` overrides requested power, lifts the cap, and enforces level ≥1; `po_apply()` publishes visibility after setup. P1b adds Screen preview/restore behavior, not the basic visibility override. Correct that distinction in the stage table. [Existing visibility implementation](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:260)

   P1a’s acceptance must include opening from requested power Off and brightness 0, choosing Lights out, visiting Diagnostics, and closing. The menu stays readable while OPEN; close exposes the latest underlying settings. Power/Clock persistence after a settled save and no write on cancellation belong in P1a’s tests.

2. **Add an explicit fixture/menu session identity and an opener table.**

   C1’s **owner and restore machinery can stay shared**. Neither needs another panel owner. However, the surrounding implementation assumes that every MENU session is the fixture:

   - `screen_open()` always calls `fx_open()` or `fx_return_from_diag()`.
   - Input always reaches `fx_input()`.
   - Invalidation calls `fx_invalidate()`.
   - Sub 5 reports `fx_screen()` and `fx_cursor()`.
   - Sub 0 admits fixture operations based on `OWNER_MENU_OPEN()`, including unconditional layout/style changes.

   Changing only input dispatch would therefore be insufficient. [Current integration points](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:38)

   Specify a session identity, retained through **PENDING and DEBUG/OPEN**, and dispatch opening, Diagnostics return, input, and reporting through it. The scheduler, pump, restore, loss consumer, visibility, and sleep blocker remain shared.

   I recommend this rule:

   | Entry route | New session |
   |---|---|
   | Physical opener, unarmed | Real menu |
   | Physical opener, dev fixture mode armed | Fixture |
   | Sub 4 | Fixture |
   | Sub 11 | Real menu |

   For all opener routes, preserve C1’s state behavior: PENDING cancels; OPEN closes the current session; ANIM refuses. Select the session identity only when accepting a new request. A different opener must not silently replace an already-open screen.

   That armed exception matters: `menu_enabled()` returns true unconditionally with `MENU_ENABLE`, while `menu_s1_spin.py --style` arms the physical opener and then sends a fixture pattern. “Every S0/S1 script keeps working” is false unless you preserve that routing or explicitly revise the scripts. Disarming must still close/cancel an existing session and retain owed releases; afterward the production opener remains enabled. [Physical spin script](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_spin.py:47)

   Define the other subs explicitly:

   - **0:** fixture session only. Otherwise stale `fx_screen()` can authorize a pattern, and patterns 3/16–19 can replace the real menu’s layout.
   - **1–3:** feed the active session; DEBUG retains click/Back return semantics.
   - **5:** retain fixture IDs 1–3, assign real-menu IDs ≥16, report the active cursor and shared scheduler’s current target.
   - **10:** retain shared timing/target counters; real-menu navigation and title changes must create observable targets.
   - **11:** specify arguments, sequence completion, refusal, pending cancellation, and close behavior—not merely “opens the menu.”

   Diagnostics’ return is **not unchanged from S0**: today it explicitly installs F1 row 7. For the real menu, establish a valid top→Diagnostics stack, including when `DBG_PAGE` or op 1 entered DEBUG from elsewhere. Specify the selected return row. Preserve the fixture’s existing return behavior separately.

3. **`MENU_ENABLE` on every flavour is sound, with production boundaries preserved.**

   C2’s disabled opener is explicitly **S0’s scope**, not a permanent prohibition. Enabling it for a functional P1a is consistent with the plan.

   The proposed `power_set_mode()` promotion is correct: move **only its declaration and body** outside the dev guard, and remove **only that symbol** from the daily/fpb forbidden list. Keep forced stages, bench sleep controls, injection, HC_DEVHOOK, and op 27 dev-only. Do not enable `AK820_DEV_HOOKS` to obtain a setter. [Setter and neighbouring dev functions](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:329), [build enforcement](C:/Users/jdlien/code/ak820-pro/build.sh:133)

   Add production-build verification of opening/navigation/closing and the existing forbidden-symbol checks. A large daily heap gap does not establish dev or devfault feasibility.

   Open 5’s Fn/tap-hold limitation remains accepted and documented. P1a does not need a new Fn detector.

4. **Reject the general “16-bit hash, exhaustively collision-tested” claim.**

   This is a correctness issue, not merely a small chance of an imperfect repaint. The scheduler uses signature equality both to skip committed slots and to **resume a PARTIAL slot across retargets**. A collision can produce mixed old/new pixels and falsely report completion; recovery is not guaranteed by “the next change.” [Signature-dependent scheduler](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:222)

   Exhaustive checking can establish safety for a **finite, fully enumerated target set**. It cannot establish the draft’s claim for arbitrary formatted uptime and other runtime facts. Uniqueness only needs to hold among targets that can be compared for the same slot without intervening invalidation, but that restriction must be designed and proved.

   Two workable approaches are:

   - Exact semantic signatures for bounded targets—text IDs, bounded values, style, selection, saved marker—with explicit invalidation when replacing an About snapshot.
   - Exact text comparison using the existing text storage, with style tracked separately.

   **Keeping text need not allocate another screen buffer.** C3 already proposes using `dbg_text` and `dbg_shown`; the implementation has two 198-byte arrays. Refactor their ownership/access rather than add new copies. Define how a partial target is retained and compared, and preserve the reset at MENU↔DEBUG handoffs. [Existing buffers](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:768)

   About’s specification is internally contradictory: “read when the page opens; not live” versus “~0 RAM, composed per piece from the env.” Choose a frozen snapshot, either compact facts or formatted text in shared storage. Otherwise separate pieces can show different uptime/battery/link samples.

   Likewise, latch the hint/flash title state in the menu task. `sig()` and `paint()` must observe the same target, rather than independently consult a clock that can cross an expiry between calls. External setting changes must update the model and retarget explicitly; fetching changing values only inside signature callbacks bypasses C10’s target accounting.

5. **The art is feasible, but specify the adapters and correct the cost model.**

   **Bunny:** 27×2 RGB565 pixels are indeed 108 bytes. Grayscale expansion is reasonable, but it changes “Generated files,” which currently specifies **27×42 RGB565: 2,268 bytes**, not 1,134. Amend that contract and verify the converted pixels against the intended image. [Generated-file contract](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:1175)

   Put expansion beside `lcd_blit_mono()` in `lcd_bus.c`, exposed through a small backend call. The scratch and `stream_broken` are private there; `lcd_stream_begin()` can return true after a failed window, and `bytes/end` return void. A caller outside that implementation cannot infer success from `begin()` alone. Mirror mono’s cleanup and boolean failure result. [Stream implementation](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:368)

   Define the credit text’s pieces too. “A bunny slice with its text” cannot send a whole 14-row credit line alongside a 108-byte image piece and claim that pass costs 108 bytes. C4 limits the **sum of CPU-fed payloads per pass**, including multiple windows. Two image rows are legal, but conservative: a separate 27-pixel-wide image piece can fit nine rows within 512 bytes.

   **QR:** 50 pieces is correct: 49×396 bytes plus a final 198-byte row. Each piece must independently open/end its stream; derive module coordinates from the absolute output row so the 2-row pieces preserve 3-row modules.

   Existing `lcd_blit_mono()` takes an already rasterized, byte-strided bitmap; it neither scales modules nor accepts an arbitrary bit offset. The 106-byte module image is tightly packed; byte-aligned 29-pixel rows would occupy 116 bytes. Specify an unpack/scale adapter, for example a **26-byte stack bitmap** for two 99-pixel rows, then call mono.

   Freeze the mockup’s exact URL, `https://github.com/jdlien/ak820-pro`. A longer literal README URL cannot be assumed to retain 29 modules.

   Fifty pieces means fifty painting passes, plus clears/title/commits. That is plausible within C10’s second, but needs measurement. One logical op spanning all fifty pieces will saturate the wire’s 65,535 µs op-latency field; define whether that is intentional or split it into several logical chunks.

   Correct these draft estimates:

   - A 61×14 half-row takes **four pieces**.
   - A full row takes eight half-row pieces.
   - A two-row cursor move takes **16 pieces, not eight**.
   - Eight rows plus title/separator/scrollbar take approximately **73–74 painting pieces**, then eight clear-band passes and separate slot-commit passes.

   Also decide whether there are **19 independently signed slots** or eleven slots whose rows have two chunks. Only the former naturally skips an unchanged left half when the right-hand value changes.

6. **Replace the RAM estimate with a complete, per-flavour budget. Flash appears comfortable.**

   I read the archived ELF sections and heap symbols:

   | Archived build | Heap gap | Above 128 B floor |
   |---|---:|---:|
   | dev `ffa80947` | 232 B | 104 B |
   | dev `cbb51ac1` | 240 B | 112 B |
   | devfault `cbb51ac1` | **144 B** | **16 B** |
   | daily `cbb51ac1-dirty`, 16:57 build | 2,352 B | 2,224 B |

   The matching `cbb51ac1` dev/devfault difference is 96 bytes. There is no corresponding archived `ffa80947` devfault build in the files inspected, so its exact remaining margin is unmeasured. The draft cannot budget all P1 work against dev’s 104 bytes when its required fault testing uses devfault. [Devfault ELF](C:/Users/jdlien/code/ak820-pro/ak820pro-builds/out/via-devfault-cbb51ac1-20261024-162904.elf)

   Against C5’s stated baseline, current dev `.data + .bss` is 29,448 bytes; baseline minus the freed 512-byte scratch is 29,136. That puts the accumulated increase at approximately **312 of the 400 bytes**, leaving **88**, not 104, under that separate ceiling.

   The ~40-byte estimate is plausible only with deliberate reuse and packing. It currently omits or leaves uncertain:

   - Fixture/menu identity and pending-request lifetime.
   - About’s snapshot.
   - Exact target/style storage and highlight-cleanup state.
   - Explicit timer fields and target ABI padding.
   - P1c’s owed-release bitmap: about **12 bytes** for this 6×15 matrix.
   - C5’s later P2/P3 reservations: **36 bytes**.

   After the proposed 40, those latter reservations alone consume the remaining 48 bytes under the 400-byte accounting. Reconcile both limits before implementation. Use actual `sizeof` assertions and linked deltas; if necessary use C5’s documented log reduction, **18 bytes per entry**, with the capacity tradeoff recorded. Measure stacks after art rendering and formatting.

   Flash is less concerning: the current dev ELF’s load image ends at 180,056 bytes against its 262,144-byte flash region. The proposed roughly 9–10 KB addition looks feasible, though the 6 KB code estimate remains unverified. Const tables, pointer tables, and generated assets must actually remain in flash.

7. **Resolve the visual and behavioral omissions before P1a, and strengthen its gate.**

   **Old highlights are a missing P1 requirement.** Warren’s status and BACKLOG require removing the old highlight before or with the new one. The current scheduler resumes its active slot, then scans slots in ascending order; that cannot guarantee this for reverse movement, wrapping, or repeated partial highlights. Specify a cleanup priority that also covers partially painted selections, then test rapid reversals and wraps at piece boundaries. Preserve C10 progress while doing so. [Recorded requirement](C:/Users/jdlien/code/ak820-pro/plans/BACKLOG.md:53)

   The remaining concrete discrepancies are:

   | Area | Required clarification/correction |
   |---|---|
   | Reset confirmation | The mockup uses “Clear the health” / “counters?”, click-to-reset and hold-to-cancel, followed by a result page. The draft invents Back/Reset rows and a title flash. Choose one and update both specifications; define initial selection and post-reset destination. |
   | About page one | Preserve or explicitly revise the eight mockup lines, including **Pack … mV** and **Left … of use**. Define unknown values and actual flavour naming. `instrumented, 0x12345678` is **24 columns**, so the proposed metadata format does not fit every flavour. |
   | About page two / QR | The slot table omits page two’s separator/scrollbar and the QR page’s separator. Include their geometry and damage behavior. Preserve the credits and GitHub lines. |
   | Help | There are **four text topics plus More info/QR**, not five text pages. Preserve deliberate blank lines and shortcut spelling. Resolve “never mid-edit” against the three-minute backstop in both specs. |
   | Values and markers | Use the mockup’s parent value **“Saver”**, full choice **“Power saver”**, parent clock **“24h”**, choice **“24 hour”**, and explicit Clock enum mapping. Page entries also receive `>`, not just child lists. Keep the saved bullet distinct from selection. |
   | Opening and Back | Top cursor 0; child lists first real item; choices current option plus the Back-row offset; returning restores the parent cursor/page. Text pages return on click/hold. Top-level Back and Exit close the session through C1. |
   | Paging | Lists use pages beginning at multiples of eight. Mockup text pages instead step by eight and clamp at `line_count − 8`: an 11-line page ends at offset 3. Specify this distinction or amend the mockup. |
   | Timers and feedback | Use 32-bit elapsed times. All P1a screens, including DEBUG/OPEN and confirmation, have the 24-second inactivity rule. Only knob input resets it. Hints apply to actual lists, **not choices merely sharing the layout**. Flash wins over hint; cancelling a committing choice must show `Cancelled` as well as perform no write. |

   [Mockup navigation and wording](C:/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:383)

   The board gate must exercise **About’s bunny, QR, Help paging, confirmation, hint/flash transitions, and reverse/wrapped selection changes**, not just opening, one move, and Diagnostics. Measure new composition/signature work together with painting; §19d’s 14.8 ms maximum leaves little demonstrated margin.

   Keep Reset counters outside a C10 measurement interval: changing the health-reset generation intentionally invalidates that interval. Add loss/retarget/close-reopen tests throughout the new art pieces and tests for the new stream adapter’s failure cleanup.

   One existing correctness gap should be included in that work: `ms_settled()` checks busy but not `mb_lost_pending()`. It can report settled before the loss consumer invalidates the slots. Make its completion predicate match the contract. [Current predicate](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:263)

**Can wait:** RGB/Screen transaction implementation, preview editors, and their external-writer conflict tests can remain P1b once those controls are absent from P1a. The keycode implementation and its C2 amendment can remain P1c, with RAM reserved now. Keep Fn+D assigned until the end-of-P1 procedure; then perform the two `KC_NO` writes, readback, dump, and regeneration exactly as planned. P2–P4 and the larger-font redesign remain deferred.

This was a read-only review. No files changed and no builds or hardware tests ran.