# Codex verification: the build plan, revision 12 (2026-10-24)

Prompt: [`review-prompt-config-menu-build-plan-rev12.txt`](review-prompt-config-menu-build-plan-rev12.txt). Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the disposition.

---

**Revision 12 is ready for S1 to be built from.** It fully addresses revision 11’s remaining must-fix. I found no new inconsistency in the revised contract against `4b899118`.

- **Pending composition:** [C10’s predicate](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:947) now rejects completion when the current second differs from `dbg_sec`. This covers the gap in [draw_debug_page()](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:840), where second changes are detected without setting `dbg_force_recompose`. The [second-edge path](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3482) does not invalidate that reasoning.
- **Correct update identity:** [The procedure](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:966) names `S`, requires a newer generation tagged `S`, and requires **that generation’s** completion. The earlier second’s completed generation can no longer satisfy the test.
- **Consistency:** Reset/loss invalidation and final-transfer requirements remain intact. Sub 10’s added bytes fit the report, and its summary correctly extends through byte 30.

**Note — implementation detail, no plan change required.**  
**Where:** [C10 byte 29](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:943) and [Camera’s clock composition](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1006).  
**Fix:** Implement `dbg_sec` from the same `rtc_get_time()` sample used to compose the clock text. `rtc_get_seconds()` is the free-running edge counter; its value modulo 60 is not the displayed calendar second. This follows the existing “second it shows” requirement.

Static review only; no files changed or board tests run.

---

## Disposition (Warren, 10-24)

**Cleared for S1.** The implementation note is taken into C10 byte 29's row: `dbg_sec` comes from the same `rtc_get_time()` sample that composes the clock text, never `rtc_get_seconds()`.
