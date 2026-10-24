# Codex verification: the build plan, revision 11 (2026-10-24)

Prompt: [`review-prompt-config-menu-build-plan-rev11.txt`](review-prompt-config-menu-build-plan-rev11.txt). Reviewed: revision 11. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Revision 9 was not ready. Current revision 11 still has one must-fix before S1’s code: the Camera completion procedure can credit an earlier clock update.**

I compared revision 9 (`d440c8f`), revision 10 (`95ab749`) and HEAD (`a257cf9`), and verified the relevant firmware files against `4b899118`.

| Disposition | Verification |
|---|---|
| Interval reset and validation counters | **Met.** The reset now covers 6–15, 19 and 24–25. The wrapping interval total is only a summary; validation uses health page 2’s jointly snapshotted u32 passes/ge10/ge25. |
| Debug completion and repair | **Partly met.** Initial composition, clear completion, clean grid, final transfer and pending loss are covered. Reset/loss generation changes correctly prevent stale completion during repair. The clock-cause association remains incomplete, below. |
| Observable reset identity | **Met.** A boot-cleared session token detects reboot during an established, unrearmed interval. A separate generation detects health resets independently of counter plausibility. |

Revision 9’s C4 lifecycle correction remains sound: counting and latching the stop before retarget/invalidation addresses the ordering in [menu_slots.c](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:38). The later changes do not undermine it.

**Must-fix before S1’s code — identify the particular clock update being completed.**

**Where:** [C10’s completion predicate and cause procedure](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:940).

Reading the generation before the cause fixes the previous example, but “generation changed since that read” still does not identify which second was composed. A permitted sequence is:

1. Second N has arrived but has not been composed. The script reads generation 42, representing the previous second.
2. N is composed and painted as generation 43 while the script waits for second N+1.
3. N+1 arrives. Before its composition runs, the script observes generation 43, done-generation 43 and `debug_done`, and accepts N’s completion for N+1.

The predicate’s `dbg_force_recompose == false` does not exclude this state: ordinary second changes are detected by comparing `sec` with `last_sec` inside [draw_debug_page()](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:840). They do not first set that flag. The [per-pass second-edge path](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3482) shortens this race; it does not establish the required association.

**Fix:** Specify an observable association between the tested second and its composition—for example, expose the composed second alongside `dbg_gen`, then require that tagged generation’s completion on the expected page. Also count an elapsed but uncomposed second as pending composition. An equivalent explicitly synchronized procedure is acceptable; merely requiring some generation advance is insufficient.

That is the only additional change I require before S1’s code.

**Note — C10’s numerical targets remain meaningful prospective gates. No numerical relaxation is justified by the recorded evidence.**

| Rule | Soundness and observability |
|---|---|
| ≤15,000 µs whole pass; zero >15,000 µs passes; unchanged ge25 | Consistent boundaries. Planned sub 10 supplies the precise timing; health page 2 supplies ge25. The prototype’s **23–24 ms** maximum means S1 must demonstrate the improvement. |
| 1,000 ms paced/transition completion | Plausible, not proven. The polled build recorded **12**, not 14, full toggles per 5 s: roughly **417 ms per toggle**, including host overhead. |
| Sustained ratio ≥0.98; upper sanity limit 1.01 | Implementable using health page 4’s ISR entries and uptime. The recorded ratio **3678/3726 ≈ 0.9871** clears 0.98. |
| 500 ms transition windows: each ≥0.95, per-kind mean ≥0.98 | Implementable; successive windows through completion plus another window cover the transition. Existing **1 s** measurements do not establish these shorter-window results. |
| Slot progress every 500 ms; final settlement within 500 ms | Meaningful, but unproven. [The scheduler restarts partial slots on generation changes](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:121), so some slots must still complete within approximately **50 ms** during the burst. Full-fixture throughput does not settle that question. |
| 25 ms read brackets, 100 ms counter sampling, timebase tolerance and rate bounds | Executable host checks. The 1,000–10,000 ISR/s and ≤500 passes/s bounds encompass recorded behaviour. Modular deltas, bounded sampling and explicit reset identity now serve distinct purposes. |

These conclusions use [results §10](/C:/Users/jdlien/code/ak820-pro/plans/GREMLIN-RESULTS.md:466). The new sub 10 fields and `debug_done` are planned S1 instrumentation, not capabilities already implemented at `4b899118`.

Static review only; no files changed or board tests run.
---

## Dispositions (Warren, 10-24): the one must-fix accepted, folded into revision 12

**The clock update's identity: accepted.**
- **The tag:** sub 10 exposes `dbg_sec` (byte 29), the RTC second the
  composition `dbg_gen` shows, and the RTC's current second (byte 30) in
  the same reply.
- **Pending:** the predicate counts an elapsed but uncomposed second as a
  pending composition (current second differs from `dbg_sec`), since
  `draw_debug_page()` finds a new second by comparing `sec` with
  `last_sec`, not through `dbg_force_recompose`.
- **The procedure** names the expected second `S`, waits for a generation
  past the one read before the cause and tagged `S`, then for its
  completion with `dbg_sec` still `S`. If the clock moves on first, the
  sample is discarded and retried, and three discards fail the run.

**The numbers note:** no change. The targets remain prospective gates for S1
to demonstrate, with codex's caveats already recorded under revision 10's
dispositions.
