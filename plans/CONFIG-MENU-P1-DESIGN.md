# The configuration menu's P1: the design (draft 1, 2026-10-24)

Warren's design for stage P1 of [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)
("Stages", 3). The plan's contract (C1-C10), "The settings", "Diagnostics,
About, Help" and "Generated files" stay authoritative; this says how P1 is
built on S0 and S1 and splits it into three flashes. The words, the tree and
the behaviour are the mockup's ([`config-menu-mockup.html`](config-menu-mockup.html)).
Codex reviews this before any P1 code.

## What S0 and S1 left

- **The owner and session** (C1, `panel_owner.c`), the coalesced input
  and capture (C2, `menu_input.c`), the slot scheduler with pieces
  (C3/C4, `menu_slots.c`), C10's measures, the restore, Diagnostics'
  handoff (MENU to DEBUG and back).
- **The text:** the 1-bit Cozette face (`font_small_mono.h`),
  `menu_text.c`, `lcd_blit_mono` through the stream. A 61 px half-row piece
  costs ~5.1 ms; every pass stays under 15 ms (GREMLIN-RESULTS §19b).
- **Settled with JD (10-24):** lit text (#C8C8C8 rows, #FFF2A0 selected),
  half rows, the 6x14 face for now.
- **The fixture** (C9, F1-F3) is the MENU owner's only screen; op 27 drives
  it, and the gate, the failure paths and the style measures depend on it.
- **RAM:** the dev build's heap gap is 232 B against the 128 B floor: P1
  has ~100 B of static RAM to spend, all three steps together.

## The steps

| Step | What | Flash after |
|---|---|---|
| **P1a, the tree** | `menu.c`: the tree, lists, choices that commit (Power, Clock), text pages (Help), About (both pages), More info (the QR code), Reset counters' confirm, Diagnostics (Health, Camera) by C1's table, Exit, the title's flash and hint, the 24 s timeout; `MENU_ENABLE` on | codex on the code; host tests; the gate, the failure paths and the LED rate extended to the menu's screens |
| **P1b, the previews** | C6's edit transaction: Lighting (Effect, Brightness, Hue, Saturation, Second color or Speed, Lights) and Screen; the range and hue editors; the 3-minute backstop; C7's visibility for Screen | codex; the plan's P1 exit gates (VIA Set and Save mid-edit, `RM_*` keys, Save with RGB off, Screen from Off and level 0, persistence across a reboot) |
| **P1c, the keycode** | "Open" 3's C2 amendment, appended to the enum and `via.json`; then `Fn`+`D` unassigned on JD's board | codex on the amendment before code, then on the code; the plan's keycode tests |

Connection (P3), Indicators and Battery (P2, P4) stay out of the tree until
their stages: P1's top level is Lighting, Screen, Power, Clock, Diagnostics,
Help, About, Exit (8 items, one page).

## The code

- **`menu/menu.c` (new, pure, host-tested):** the tree as `const` tables,
  the navigation stack, each screen kind as an `ms_layout_t` (C3), the
  input (turns, click, Back) and the timers. No ChibiOS, no QMK: settings
  and facts come through `menu_env.h`, the panel through `menu_backend.h`.
- **`menu_ops.c`:** the task hands `mi_take`'s batch to the current
  screen: `menu_input()` for a menu session, `fx_input()` for the fixture
  (op 27 sub 4, unchanged, so every S0/S1 script keeps working). A new op
  27 sub 11 opens the menu for the scripts. The physical opener opens the
  menu.
- **`menu_glue.c`:** the env and backend on the firmware.
- **`MENU_ENABLE`** is defined for every flavour at P1a, so `Fn`+knob
  opens the menu without op 27's arming (the armed mode stays for the
  fixture's scripts).

### The tree

```
Configuration                      (top: 8 items)
  Lighting            >            P1b: a list
  Screen           75%             P1b: the range editor (0-23, Off)
  Power       Balanced             a choice, committing
  Clock            24h             a choice, committing
  Diagnostics         >            a list
  Help                >            a list
  About               >            a text page, two pages
  Exit                             closes
Diagnostics: ‹ Back, Health page, Camera page, Reset counters
Help: ‹ Back, Using the menu, Customizing, Shortcuts, Pro tips, More info
```

- A node is `{label, kind, payload}`; kinds: `MENU` (a child list),
  `CHOICE` (a committing or previewing list of options), `RANGE`, `HUE`,
  `PAGE` (const lines), `ABOUT`, `QR`, `CONFIRM`, `DIAG_HEALTH`,
  `DIAG_CAMERA`, `EXIT`, `BACK`.
- **The stack:** at most three levels (top, a list, a screen under it):
  each entry a node index, a cursor and a page top: 3 x 3 B.
- **Opening a list** puts the cursor on its first real item (row 1; row 0
  is `‹ Back`). **A choice** opens on the saved option. **The top level**
  opens on row 0.
- **Lists scroll by page** (decided, 10-23). P1's lists fit one page; the
  pages are written so that Help can grow.

### The screens and their slots (C8's geometry, lit text, half rows)

| Kind | Slots | Notes |
|---|---|---|
| list, choice | the title (20 cells), the separator, 8 rows of 2 halves, the scrollbar | `label ... value` in 20 cells, the value right-aligned; `>` for a child list; a choice's saved option has the bullet (U+2022, 0x82) in cell 0, the others a space (the mockup's dot, as a glyph) |
| text page | the title, the separator, 8 lines (one chunk each: plain text isn't highlighted), the scrollbar | scrolls by page; a click or Back returns |
| About, page 2 | the title, 3 bunny slices (27x42 at x 4, 14 rows each) with their text, then lines | the bunny is 8-bit grey (1,134 B of flash), expanded to RGB565 grey through the stream, a slice per op, 2 rows a piece (108 B) |
| More info | the title, the QR code (29 modules x 3 px + a 2-module border: 99 x 99 at x 14, y 22) | 1-bit, through `lcd_blit_mono`, each module 3x3 px: a piece is 2 pixel rows of 99 px (396 B), so 50 pieces (a module row, 3 px, would be 594 B, over the budget) |
| confirm | the title, the separator, 3 text lines, two rows (`‹ Back`, `Reset`) | |

- **The hint:** after 4 s idle the title shows `Turn + Click Knob` for 1 s,
  every 5 s, on lists only (the mockup). A title slot retarget: two title
  repaints in 5 s.
- **The flash:** `Saved`, `Cancelled`, `Counters reset` replace the title
  for 1.3 s.
- **Signatures:** a slot's signature hashes what it shows (text, style,
  selection), 16 bits, as C3 requires distinct targets to differ; a
  collision paints a stale slot until the next change, so the hash is
  checked for collisions over every target the tree can produce, by the
  host tests.

### Choices that commit (P1a)

- **Power:** Always on, Balanced, Power saver, Lights out. A click calls
  `power_set_mode()`, promoted from dev-only (the plan: its declaration and
  body, and `build.sh`'s forbidden-symbol list loses it).
- **Clock:** 24 hour, 12 hour, Date, Off, mapped to the enum's 24H / 12H /
  DATE / OFF. A click calls `display_set_clock_mode()` and
  `kb_eeconfig_set_clock_mode()`.
- Both: `Saved` in the title, back to the parent list with the value
  updated. `‹ Back` or a hold: no change.

### Diagnostics and About (P1a)

- **Health page, Camera page:** C1's handoff (MENU to DEBUG with the
  session OPEN; a click or Back returns to Diagnostics). Unchanged from S0.
- **Reset counters:** the confirm screen; `Reset` calls `health_reset()`
  and `display_debug_refresh()`, then `Counters reset`.
- **About, page 1:** the firmware (the build's short hash), the flavour and
  token, uptime, the battery (`-` when unknown), the power mode, the link.
  Read from the env when the page opens; not live.

### Help (P1a)

- `scripts/gen_menu_text.py` -> `graphics/res/menu_text_pages.h`: the
  mockup's five pages, wrapped to 20 columns, checked to fit, `const`.
- More info: the QR code (`gen_menu_art.py` -> `menu_art.h`, the plan's
  "Generated files"), pointing at the repo's README.

### The edit transaction (P1b)

C6 as written: the RGB config snapshot on entry, previews with
`_noeeprom`, one save on the click, a restore on Back, a hold, a close, an
external write (VIA, `RM_*`, `UG_*`, the board's wrappers) or the
3-minute backstop. The range editor (C8: the big value in the 20 px face
from the flash atlas by DMA, the bar as fills, the hints as mono text) and
the hue editor (the strip as generated pixels through the stream; the
envelope slot). P1b gets its own detailed section before its code.

### The keycode (P1c)

"Open" 3's amendment, unchanged, reviewed before code.

## Costs and limits

- **Every piece at most `MB_PASS_BYTES`** (512): text half rows 488 B,
  bunny pieces 108 B, QR pieces 396 B, fills as before.
- **Opening the menu:** the layout clear (8 bands) and 1 + 1 + 16 + 1 slot
  ops, ~4 pieces a row: ~75 pieces, ~0.8 s at a piece a pass (the fixture's
  open measured 711-793 ms).
- **A cursor move:** two rows, ~8 pieces, ~165 ms.
- **RAM (static, estimate):** the stack 9 B, the screen state (kind, page,
  flash and hint timers, the confirm's choice) ~12 B, About's few values
  read at open ~0 (composed per piece from the env), P1b's edit
  transaction 16 B (C5's table): ~40 B of the ~100 left.
- **Flash:** the help text ~1.2 KB, the bunny 1.1 KB, the QR 106 B, the
  tables ~1 KB, the code ~6 KB.

## Tests

- **Host (`menu_s0_test.c`, a P1 section):** every node's open, move,
  click and Back; the stack's limits; the choices' commit and no-commit
  paths through a fake env; the confirm; Diagnostics' handoff and return;
  the timeouts; the hint and the flash; the signature collision check;
  the expected frame of every screen against the face (as `expect_f3`);
  every piece at most 512 B; a retarget and a loss at every piece boundary
  of an open and of a move.
- **Board:** the gate (`menu_s1_gate.py`) gains the menu's open, a move and
  Diagnostics' round trip by op 27 sub 11; the failure paths gain a menu
  case; the LED rate covers the menu; a real spin with
  `menu_s1_spin.py`; JD's hands-on session (one action a message).

## Questions for the review

1. Is the split into P1a/b/c sound, and is anything in P1a's scope that
   depends on C6 (the edit transaction)?
2. The fixture kept for op 27 (sub 4) beside the menu (sub 11): does
   anything in C1's table or the restore assume one MENU screen?
3. `MENU_ENABLE` on at P1a, for the daily build too: anything in C2's
   "S0's scope" or C7 that must change with it?
4. The signature hash and its collision check: enough, or should slots
   keep their text (RAM) instead?
5. The QR's 50 pieces and the bunny's slices: any piece-rule or C4 stream
   issue?
6. RAM: is ~40 B for P1a+b realistic against C5's budget table?
