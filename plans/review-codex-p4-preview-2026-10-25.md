# Codex: P4's Battery preview (2026-10-25)

Prompt: `plans/review-prompt-p4-preview.txt`. Diff: qmk_firmware-ak820pro `d56980c9..e0f9a21f`. Verbatim below; then the verify of the fix (`plans/review-prompt-p4-preview-verify.txt`, `e0f9a21f..ab03ab38`); dispositions at the end.

---

**No flash-safety blocker found. One nonblocking UI bug should be corrected:**

- **[P3] Misleading note at the cut:** [menu.c:96](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:96) treats every warmed-up, unavailable estimate as off battery. At `{pct=0, on_battery=true, left_min=0xFFFF, avg_minutes=120}`, both previews correctly show `Low`, but the note says “Hours show only / on battery.” Restrict that wording to `!b.on_battery`; suppress or replace it for Low/unknown-on-battery. [test_p4:3404](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3404) exercises this state but checks only the previews.

The remaining checks:

- **Signatures:** [row_sig:690](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:690)’s `0x1000–0x1FFF` is disjoint from blank, ITEM, TEXT, ABOUT and VALUE. Bullet/lit bits remain intact. Only bit 0 is interpreted; op 27 and board scripts do not decode row-kind bits. Hash collisions remain the accepted possibility of delayed repaint.
- **Scheduler:** [menu_slots.c:265](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:265) resumes partial work first; its subsequent scan compares committed signatures. Thus live changes repaint without retargeting, although “every slot each pass” is not literally true.
- **Notes/navigation:** [row_at:592](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:592) returns notes unlit, without bullets. Cursor stays 0–2, top stays zero, count stays three, scrollbar stays absent, and pops restore the parent. Notes use `MP_WHITE` (`0xFFFF`).
- **Formatting:** Unknown becomes `--`; Low precedes readiness; warm-up subtraction is guarded. Known-level previews share the dashboard formatter, with intentional `--` for unavailable hours. The 24-byte temporary and eight-byte output suffice; `999h` fits.
- **RAM:** The exact dev ELF confirms **128 B**. New constant tables reside in flash. [display.c:1932](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1932)’s three statics are one byte each; current geometry makes their casts safe.
- **Timing:** Getters read cached facts; formatting adds bounded CPU work. Below-15-ms performance still needs board measurement. Inspect `over15`: [the board script:360](/C:/Users/jdlien/code/ak820-pro/scripts/menu_p1a_board.py:360) permits 17 ms despite logging overruns.

On BT, retain [flash.sh:177](/C:/Users/jdlien/code/ak820-pro/flash.sh:177)’s battery-reserve guard. I reviewed source and ELF; tests were not rerun.
---

## The verify

**P3 is resolved.** In [menu.c:94](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:94), the early return suppresses notes on battery at the cut or with an unknown level, including during warm-up. [Line 99](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:99) restricts “Hours show only / on battery.” to off-battery states.

**No new findings** in `e0f9a21f..ab03ab38`; the keyboard subtree changes only `batt_note()`.

The assertions at [menu_s0_test.c:3404](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3404) cover the three stated regression cases. I inspected them but could not rerun tests because process execution was unavailable.
---

## Dispositions

- P3, the note at the cut: fixed in `ab03ab38` (no note on battery at the cut or with no level; "on battery only" only off battery), the test checking the three states; the verify: resolved, nothing new. Flashed as `ab03ab38`.
- Timing: the board's menu pass on `ab03ab38` measures it.
- "Every slot each pass is not literally true": right, a PARTIAL slot resumes first; the committed slots' signatures are compared in the next scan. The design's wording follows.
