# Codex's review of the staged text slot, 2026-10-24

Prompt: [`review-prompt-s1-textslot.txt`](review-prompt-s1-textslot.txt). Reviewed:
qmk_firmware-ak820pro `gremlin/s1` commit `f78e1157`. Model `gpt-6-astra`,
reasoning xhigh, read-only. **Not flashed as reviewed.**

## Dispositions (Warren)

- **1 [P1], line 1's retirement clips an already-painted line 0:** fixed in
  the follow-up commit: a sequence that retires line 1 (one line, the
  overlay, none) retires it first, then paints line 0; two lines keep 0
  then 1 (line 1's clears stay in its own row). The comment above the
  sequence now says the order is about pixels, not calls. The pre-existing
  weakness it noted (retire_line skips an invalid shadow unless `dropped`)
  is left as it was: the reorder removes the deterministic clip that
  exposed it.
- **2 [P2], one heavy step a call, not a pass:** fixed: `ts_heavy_this_pass`,
  cleared by `display_pass_end()`, as `batt_painted_this_pass` is.
- **`band_mark_painted` from the captured layout:** fixed: it uses the
  layout as it stands at line 0 (an expired message retires, BAND_NONE).
- **Wake completion doesn't wait for a staged sequence:** deferred. Adding
  `ts_step` to `display_bus_idle()` could hold sleep while the 10 Hz block
  isn't running; a stale icon or text for up to ~0.5 s after a wake is
  accepted.
- **Latency (~400-500 ms for two lines <-> one line):** accepted for now;
  measured on the board next.
- **DP_TEXT_SLOT now measures one call:** noted; whole passes stay measured
  by sub 10 and HC_ACCT.

## The review, verbatim

**I would not flash `f78e1157` as-is.** There is a deterministic permanent-clipping regression and a gap in the intended per-pass work limit.

I verified that the working `display.c` matches the commit and that the commit changes only that file. This was a static review plus an in-memory model of the clear/queue/pump ordering; no firmware build or board test ran.

1. **[P1 — fix before flash] Line 1 can erase line 0 after its glyphs have finished painting.**  
   Location: [display.c:3493](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3493), particularly the transition to `TS_LINE1` and its call at line 3498.

   A normal two-line → short-one-line transition is sufficient:

   - Initially, line 0 occupies `y=27..40`; line 1 occupies `y=41..54`.
   - The icon moves through its clear and draw steps.
   - `TS_LINE0` clears the old small-font line, queues the new big-font text at `(14,29)`, and yields because it cleared.
   - The pump paints that text, whose cell occupies `y=29..51`.
   - On the next eligible call, `TS_LINE1` retires the old second line. Its clear at `y=41..54` erases the bottom of the **already-painted** new line 0.
   - `band_clear()` invalidates shadow 0, but does not request another text repaint. `TS_ICON_FIX` repairs only the icon. The sequence finishes with `text_dirty == false`.

   The title stays clipped until another real change or forced repaint. Identical host keepalives do not repair it. Two-line → status overlay fails the same way: the overlay at `(4,29)` loses its lower portion.

   The parent’s ordering avoided this immediate clipping because line 0’s glyphs remained queued until **after** line 1’s clear. Preserving the order of function calls did not preserve the order of pixel writes.

   There is also an existing cleanup weakness exposed here: [retire_line():3410](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3410) skips an invalid shadow unless `dropped` is set. If the clipped title subsequently expires or is explicitly cleared, its surviving upper fragment can remain. That invalid-retirement weakness predates this commit; the deterministic clipping is new.

   **Smallest promising fix:** for layouts that retire line 1, retire it before painting the replacement line 0, retaining icon-first ordering and the final icon repair. Otherwise, explicitly track and repair previously painted rows damaged by later steps. Merely setting `text_dirty` on invalidation does not solve retirement of an invalid but still partly occupied row.

2. **[P2 — fix before the C10 flash] “One heavy step” is per invocation, not per main-loop pass.**  
   Location: [display.c:3514](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3514).

   `housekeeping_task_kb()` invokes the display through the RTC edge at [ak820pro.c:584](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:584), then potentially through the 10 Hz block at line 626 in the **same pass**.

   Concrete case: clock off, no playback, queues empty, and `"Connected"` releasing to `"SHORT"` with an icon:

   - The edge call draws the new icon and yields. It queues no glyphs.
   - The clock-off path queues nothing, so the queue gate does not prevent the second call.
   - The 10 Hz call runs `TS_LINE0`. Moving from `(4,29)` to `(14,29)` clears both the left strip and the vacated right strip.

   That pass contains **one icon plus two clears**. The measurements suggest potentially about 9 ms of slot work before the rest of the pass, although this exact case needs board measurement. A changing clock often masks this by leaving queued glyphs; clock-off, unchanged date, or frozen playback can expose it.

   Add a per-pass heavy-work latch, cleared by `display_pass_end()`, analogous to `batt_painted_this_pass`. The current code does not establish the intended whole-pass bound.

The remaining checks:

- **Queued line 0 versus line 1’s clear:** if line 0 queues glyphs without clearing, both steps can execute in the same invocation. Line 1’s clear then precedes the glyph pump, preserving the old behavior. Finding 1 occurs specifically when line 0 yields and its glyphs drain before line 1 runs.

- **A new sequence cannot bypass `TS_ICON_FIX`.** The active-sequence branch at [display.c:3527](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3527) runs before dirty consumption. Ordinary updates cannot reset `icon_clobbered` or start another sequence before the fix step. A forced repaint cancels the sequence and repaints from the cleared panel. I found no independent permanent clipped-icon regression from this mechanism.

- **Producer `text_dirty` is preserved during a sequence.** Continuations return before the assignment clearing it at line 3537. Host changes, overlay appearance/release, expiry, and `icon_guess_expire()` therefore request another sequence. The missing repaint in finding 1 is an invalidation that never sets dirty, rather than a producer’s dirty flag being lost.

- **The snapshot is only partial.** `ts_layout` and the icon are frozen, but strings—and the big/small decision within `TS_ONE`—are read live. Mid-sequence changes can temporarily show mixed generations or an icon positioned for the earlier text size. Overlay appearance waits behind the current sequence; release/expiry takes the retirement fallback. These converge through the retained dirty flag, subject to finding 1 and invalid-retirement cleanup.

- **Panel hand-backs are sound.** Fn+D exit, menu close, and animation stop all start the restore. Housekeeping remains gated through CLEAR, STAGES, and RESIDUAL. The text stage calls [draw_text_slot(true):1581](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1581), cancelling staged work before ordinary housekeeping resumes. `display_redraw_dashboard()` requests that same restore. RESIDUAL cannot finish successfully by skipping the text stage; damaged restores restart.

- **The blank-shadow optimization remains valid.** The final successful clear band marks everything blank. Intermediate restore painters stay outside the text rows; the clock maintains its own shadow. The forced text stage consumes `shadows_trusted` without discarding those valid blank states.

- **Plain sleep/wake is different:** `display_sleep_wake()` does **not** force a dashboard restore or cancel staged work. It retains the panel and shadows, expires host content, and sets dirty. Continuing the sequence therefore does not target a newly cleared or reowned panel. However, `display_bus_idle()` and wake completion do not include `ts_step`, so wake can release while text cleanup remains pending. The resulting temporary stale text/icon is longer-lived now; this can wait if that latency is acceptable.

- **Individual-step accounting is otherwise correct.** A moved line can clear two strips; unknown or shortened lines clear once; retirement clears at most once. These paths all increment `band_clears`. A heavy line step returns before an icon step. Clears elsewhere between invocations do not confuse the local counter comparison. Zero-area clears are conservatively counted as heavy, adding an unnecessary delay.

- **Other consumers do not introduce overlapping damage.** Clock/playback occupy `y=56..78`; locks begin at `y=82`; text ends before `y=56`. `playback_title_gone()` changes playback ownership and requests clock work without resetting the text sequence. The icon bookkeeping has no external readers. `band_mark_painted()` is a message-generation/backlight notification, rather than panel ownership: it currently uses the captured layout before the fallback decides to retire, so an expired message can spuriously count as painted. That is a smaller, deferrable correction.

**Latency:** the alternating two-line/short-one-line workload typically takes five eligible calls: old-icon clear, new-icon draw, line 0, line 1, icon repair. That is roughly **400–500 ms from the request**, before queue deferrals. One-line → two-line usually paints its final glyphs during the fourth interval and completes the no-op tail on the fifth call. Same-layout changes with no clears or icon changes still queue everything in one call. Mid-sequence updates can require another sequence.

**Can wait:** notification bookkeeping, latency tuning, and comment cleanup. `DP_TEXT_SLOT` now measures one invocation’s work, not complete repaint latency; two invocations in one pass are not summed by its maximum. Keep whole-pass accounting alongside it. Update the “same tick” overlay comment, the “first pass” clear/icon comment, and the claim that layout is fully decided once. The recorded measurements are now in `GREMLIN-RESULTS.md §19c`.

Before flashing the corrected version, verify two-line → short and two-line → overlay **after all queues drain**, then clear/expire them and check for surviving fragments. Also exercise coincident RTC/10 Hz calls with the clock off.
## The follow-up on `ffa80947`, verbatim

Prompt: [`review-prompt-s1-textslot-2.txt`](review-prompt-s1-textslot-2.txt). No fix required before the flash.

**I found no additional fix required before flashing `ffa80947` to the test board.** The two blockers from the previous review are resolved. I found no persistent clipped glyph/icon or surviving fragment after the staged work converges and is subsequently cleared or expired.

I checked all **25 directed transitions** among two lines, one big line, one small line, status, and none, including unchanged/moving/changing icons. The in-memory model covered fully drained and partially drained queues, coincident housekeeping calls, **151,145 interruption branches**, and 5,000 repeated-change traces. As controls, restoring the previous ordering reproduced both the clipped title and its surviving fragment; removing the pass latch reproduced two heavy steps in one pass.

The important conclusions:

- **Retiring line 1 first fixes both centered single-line sizes and the overlay.** Its `y=41..54` clear finishes before replacement line 0 can paint across that row. `TS_TWO` retains disjoint small-font rows at `27..40` and `41..54`. See [the sequence ordering](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3483).

- **The `TS_TWO → TS_NONE` fallback does not require reversing the captured order.** If expiry occurs before line 0 runs, a previously centered line 0 can clear into `y=41..51`, but there is no live old line 1 alongside that centered layout, and the sequence has not painted a new one. If line 0 has already run, it occupies `27..40`; retiring line 1 at `41..54` cannot clip it. The retained dirty flag then retires the now-expired line 0 in the following sequence. The invalid-shadow retirement weakness remains in the code, but I found no reachable case in these transitions that strands pixels through it.

- **Mid-sequence changes converge.** New text, big/small changes, expiry, overlay appearance/release, and `icon_guess_expire()` preserve the request for another sequence. Continuations finish the current icon-repair step before consuming that request. Temporary mixed text or an icon partially erased by a text clear can still appear during staging; I found no case where that damage survives completion.

- **The pass limit holds for staged text work.** The latch blocks further steps in the second housekeeping invocation and resets only at [display_pass_end()](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3786). Maximum observed: **one heavy step per pass**. A line step can still perform two strip clears; this is not a one-transfer limit or a limit on other display painters.

- **Queue and notification ordering are sound.** Pending glyph/label queues defer housekeeping. When the final glyph has left the queue but its DMA is still running, [bus serialization](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:996) preserves the required pixel order. `band_mark_painted()` now uses the layout after fallback, so retirement reports `BAND_NONE`.

I verified the reviewed working files against the commit through Git objects because process launching was unavailable. This was source review and a conservative glyph-cell model, **not a firmware build or board test**. The previously accepted staging latency and wake-completion behavior remain unchanged.