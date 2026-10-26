# Codex review: the debug page's pump yield (2026-10-24)

Prompt: [`review-prompt-s1-step5.txt`](review-prompt-s1-step5.txt). Reviewed: `gremlin/s1` `4773c826`. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Yes—safe to flash to the test board for validation.** I found no new deadlock, corruption, or recovery blocker. However, this is an incomplete timing fix.

Reviewed `gremlin/s1` **4773c826**, directly after `b245bd84`; the commit changes only `display.c`.

1. **Should-fix — the 10 Hz composition happens after the pump.**  
   Locations: [display.c:3204](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3204), [ak820pro.c:594](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:594), [ak820pro.c:625](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:625).

   Actual order is: second-edge task → menu task → **pump** → 10 Hz housekeeping → pass-end reset. Only the second-edge composition is protected. If an RTC tick arrives after the early check while painting remains pending, or hold-Fn+D requests recomposition in the 10 Hz block, the pump can already have armed a glyph before composition runs. The flag is then cleared without any pump observing it. The declaration’s “both before the pump” comment is incorrect.

   **Fix:** put every composition before the independent pump call—for example, move the pump after the 10 Hz block—or defer late composition to a dedicated pre-pump stage. Preserve unconditional restore pumping and the end-of-pass reset. Simply retaining the flag into the next pass would skip the wrong pass.

2. **Note — C10’s measurement boundary can still combine work from adjacent housekeeping passes.**  
   Location: [menu_glue.c:87](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:87).

   `meas_pass()` runs **after** second-edge composition and **before** the pump. Consequently, its measured interval includes the previous pass’s pump and this pass’s second-edge composition. During an unfinished repaint, those can still combine into a long C10 interval even when the new flag correctly skips this pass’s pump. This placement predates the patch.

   **Fix:** align the measurement boundary with the housekeeping boundary, before second-edge work, retaining complete elapsed intervals; then rerun C10 and HC_ACCT. The new guard alone does not establish that the gate will pass.

The other requested checks passed:

- **Ownership and reset:** `draw_debug_page()` has one actual caller, explicitly guarded by `PANEL_DEBUG` at [display.c:3673](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3673). [ak820pro.c:637](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:637) clears the flag unconditionally after the user hook on every normally completed pass.
- **Painting and completion:** the flag is set only after the second/forced-refresh guard. Normal composition therefore sacrifices one pump opportunity per second, not every pass. Dirty cells remain pending. [debug_painted()](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3522) still requires completed clears, clean grids, current composition, and no DMA or pending loss; read-side completion updates also remain available.
- **Loss, menu, restore:** loss stays latched until taken; skipping does not reset the busy-recovery timer. `menu_task()` can change owners between composition and pumping, so a menu or restore can inherit one skipped pass. Neither can repeatedly set the debug flag under its own ownership.
- **Deadlines:** the prior gate’s slowest Fn+D entry was [924 ms](C:/Users/jdlien/code/ak820-pro/history/config-menu-s1-20261024/gate-b245bd84.json:25), leaving 76 ms against C10’s 1,000 ms limit. A nominal one-pass delay appears tolerable, but requires another board run.

Static review only: source was verified against HEAD; no files changed. Build and hardware tests were not run because process launch was denied.
---

## Dispositions (Warren, 10-24)

Safe to flash. Both findings fixed before the flash:

1. **The 10 Hz composition comes after the pump: fixed.** The pump records
   when it painted (`dbg_pumped_this_pass`), and `draw_debug_page()` defers a
   composition in such a pass, before `last_sec` moves, so it stays pending.
   The second edge composes before the pump, guarded by the original flag.
   The page's first composition after entry runs once the clear's bands are
   done, since the pump reports painting only while it has work. The
   comment now gives the pass's real order.
2. **C10's pass boundary: fixed.** `menu_pass_begin()` runs first in
   `housekeeping_task_kb()`, beside `health_loop_tick()`, so a C10 interval
   is one whole pass. `menu_task()` no longer times it.
