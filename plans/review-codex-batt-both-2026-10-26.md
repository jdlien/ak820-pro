# Codex: the battery readout's Both (2026-10-26)

JD (10-26): "could we add an option to show hours & percent on the battery
for the battery options? ... do the math, see if it fits with the battery +
power/charge icon." qmk_firmware-ak820pro `1f3c79e9..18faf312` (branch
`gremlin/batt-both`): `graphics/batt_text.c` composes "85% 160h" (8 cells) or
the level alone at 9; `draw_battery()` closes an 8-cell text's space to 4 px
to fit the 76 px slot; kb_eeconfig's byte 3 = both; profiles accept it; the
menu's Battery page gains its row (N_BV2) and its note moves to rows 5-7.
The prompt: `plans/review-prompt-batt-both.txt`; the raw reply:
`plans/review-codex-batt-both-raw.md`.

## The reply, verbatim

No flash-safety blocker found in `1f3c79e9..18faf312`; one minor defect:

- **P3 — stale Both preview:** [menu.c:1091](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1091), hashed at line 1186: with 80%, `left_min=3420`, and average maturity 59→60 minutes, `80% --` and `80% 57h` both produce `0x1768` for unchecked, unselected Both. Hours and the note update; Both remains stale. Invalidate on readiness changes and add this regression.
- [display.c:2120](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2120): positions, vacated clears, interrupted paints and three-glyph budgeting check out.
- [batt_text.c:11](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/batt_text.c:11): 100%, `<1h`, 999h and unavailable-estimate boundaries are correct.
- Menu rows/cursor/commit are consistent. [kb_eeconfig.c:202](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:202) and [profiles.c:98](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:98) preserve older encodings.

Artifact hashes match; ELF confirms 136 B ≥128 B. Native tests weren’t rerun: execution denied.

## Dispositions

- **P3, the stale Both preview: FIXED** in `295e359c`. Reproduced first:
  codex's case (80%, 3420 min, the average 59 then 60) added to
  `scripts/menu_s0_test.c`'s `test_p4` failed on `18faf312`
  ("80% --" stayed), then passed. The Battery page notes whether the hours
  are ready as it opens (the page-scoped union `pg`, no new RAM) and,
  on a flip, `menu_tick()` invalidates its rows whole, as the Clock's jump
  does. Both host builds pass; the dev build's heap gap is still 136 B.
  Codex's check of the fix: `plans/review-codex-batt-both-fix-raw.md`.
- **The rest: no change.**

## Codex's check of the fix, verbatim

**P3 — quick re-entry remains:** [menu.c:1838](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1838) resets readiness without invalidation. Back → readiness flips → reopen before Both’s slot repaints can preserve colliding `80% --`. Invalidate on entry too; add that regression.

The original open-page case is fixed. [menu.c:2297](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2297) correctly invalidates slots 4–10 outside scheduler scans. [menu.c:259](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:259): union users remain confined to their pages and initialized on entry; size stays 12 B.

No flash-safety blocker found in this diff. Native tests weren’t rerun: execution denied.

### Dispositions

- **P3, the quick re-entry: FIXED** in `0ada282c`. Reproduced first: the
  case (on Battery at "80% --", Back, the average 59 to 60, reopened before
  the top level painted) failed on `295e359c` and passes on `0ada282c`. The
  Battery page's rows are invalidated as it opens, as the Clock's examples
  are. Both host builds pass; heap gap 136 B. The second check:
  `plans/review-codex-batt-both-fix2-raw.md`.

## Codex's second check, verbatim

Closed: [menu.c:1842](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1842) invalidates slots 4–10 before `push()` and `show()`, matching [Clock’s order:1833](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1833). This forces repaint despite the colliding signature.

[menu_s0_test.c:3504](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3504) covers the quick re-entry regression.

No flash-safety blocker found in this diff for gremlin; no added persistent RAM or synchronous drawing. Host builds weren’t rerun: execution was denied.

### Disposition

- **Closed; no blocker:** flashed (`via-dev-0ada282c-20261026-220900`,
  token `0x96be043a`, heap gap 136 B).
