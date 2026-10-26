# Codex: the Clock options, and P4's preview keyed (2026-10-25)

Prompt: `plans/review-prompt-clock-code.txt`. Diff: qmk_firmware-ak820pro `ab03ab38..8ce81e5d`. Verbatim below; then the verify (`plans/review-prompt-clock-verify.txt`, `8ce81e5d..22ec0d3d`); dispositions at the end. JD asked for `8ce81e5d` on the board before this review finished ("Just flash it now"); it was flashed at 14:47.

---

I would fix **one functional bug before flashing**. I found no new BT-specific or flash-safety blocker.

**[P2] The unset clock signature aliases valid times** — [menu.c:758](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:758). The fixed unset tick, `127`, is also a valid masked tick. If the RTC becomes valid at **02:07 on March 31**, both minute-only rows and Date retain exactly their unset signatures. Committed rows therefore keep their dashes: the minute rows until another minute, Date until another day or another cause of repaint. Date’s full-row rule cannot help because the scheduler never picks it.

Give unset examples signatures disjoint from valid examples. Extend [test_clock:3596](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3596) with this unset→valid transition without moving the cursor.

The remaining checks look sound, with these qualifications:

- **Scheduler:** [menu_slots.c:308](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:308) safely skips a committed prefix under the layout’s promise. Layout changes and losses invalidate it; unrelated list-page signatures cannot masquerade as examples. Clears retain priority, rev-13 resume remains intact, and skipped chunks count as **zero operations**. Stops and timing still apply to operations actually attempted. C3’s literal whole-footprint wording should explicitly acknowledge this exception.
- **Clock prefix:** [menu.c:944](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:944) correctly handles split chunk 3, bullet/lit changes and Date. With `wide` unchanged, the 12h:ss row’s cell 9 is always `1` or always blank. Consecutive natural second/minute/day ticks differ, including rollover.
- **Battery:** [menu.c:708](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:708) preserves equal-key/equal-text for each row, including unknown, cut, readiness, hour clamping and countdown minutes. The subsequent truncated hash still permits collisions, as already documented; the 120-state sweep is not exhaustive proof.
- **Dashboard/menu wiring:** `_HM` widths, centering, AM/PM retirement, moved-path relayout, playback precedence, Off/Date, six-mode cycling, EEPROM values 4/5, appended nodes, saved selection, commits and green boxes check out. Fn+C’s longest names are exactly 12 characters.
- **Measurement:** an idle Clock scheduler scan performs six RTC conversions, with additional reads during painting/probes. Measure C10 on gremlin/BT. Piece/op/pass measures remain applicable; autonomous ticks do not advance `tgen`, so target-latency counters do not measure each tick.

I inspected the exact revisions and working tests. Process execution was unavailable, so builds, mutant runs and the 128 B gap remain your supplied results.
---

## The verify

**Resolved. No new finding in the exact scoped diff.**

- **Signatures:** Unset uses row field 7; valid examples use 0–4, so they cannot alias. [menu.c:761](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:761)
- **`l_first()` always returns 0 for either validity transition.** The row-field difference survives `~0x01FC`; neither direction can skip chunks. An exhaustive in-memory check confirmed this. [menu.c:946](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:946)
- **The longest row fits exactly:** checkbox 2 + `12h:ss` 6 + space 1 + `12:45:01 PM` 11 = **20 cells**. The label occupies cells 2–7, separator 8, value 9–19. [menu.c:694](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:694)
- The six labels and top-level enum mapping agree. [menu.c:68](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:68)
- C3 now correctly documents the committed-prefix exception. [CONFIG-MENU-BUILD-PLAN.md:620](C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:620)

The regression exercises the collision time without moving the cursor. [menu_s0_test.c:3604](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3604) Process execution was blocked; passing test and mutant results remain user-supplied.
---

## Dispositions

- P2, the unset tick aliasing a valid one: fixed in `22ec0d3d` (unset takes the row field 7); test_clock checks the unset-to-valid change at 02:07:59 on March 31, and a mutant restoring a fixed tick fails it. The verify: resolved, `l_first()` returns 0 for either change (checked exhaustively). Flashed as `22ec0d3d`.
- C3's whole-footprint wording: rule 6 in `plans/CONFIG-MENU-BUILD-PLAN.md` states the `first_chunk` exception.
- The cost of the RTC conversions in the scans, and C10 per tick: the board pass's dwells on the Clock list and the Battery preview measure the passes; `tgen` not advancing per tick is noted (target latency doesn't measure ticks).
- Batt_key's hash: collisions only delay a repaint, as documented; the sweep isn't proof, as codex says.
