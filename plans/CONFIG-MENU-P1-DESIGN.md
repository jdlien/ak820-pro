# The configuration menu's P1: the design (draft 2, 2026-10-24)

Warren's design for stage P1 of [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)
("Stages", 3). The plan's contract (C1-C10, "The settings", "Diagnostics,
About, Help", "Generated files") stays authoritative; this says how P1 is
built on S0 and S1, in four flashes. The words and behaviour are the
mockup's ([`config-menu-mockup.html`](config-menu-mockup.html)) unless a
line here amends them. **Draft 2 answers codex's review of draft 1**
([`review-codex-p1-design-2026-10-24.md`](review-codex-p1-design-2026-10-24.md)).

## What S0 and S1 left

- C1's owner, session and restore; C2's capture and coalesced input; C3/C4's
  slot scheduler with pieces; C7's visibility override (`bkl_effective()`,
  published by `po_apply()`): already built and active for any MENU
  session; C10's measures.
- The text: the 1-bit Cozette face, `menu_text.c`, `lcd_blit_mono`. A 61 px
  half-row piece ~5.1 ms; every pass under 15 ms (GREMLIN-RESULTS §19b-d,
  the gate's longest 14.8 ms: thin).
- Settled with JD: lit text (#C8C8C8 rows, #FFF2A0 selected), half rows,
  the 6x14 face.
- The fixture (C9, F1-F3), which the gate, the failure paths and the style
  measures drive through op 27.

## The steps

| Step | What | Gate before the next |
|---|---|---|
| **P1a, the tree** | the session identity; `menu.c` with lists, committing choices (Power, Clock), text pages (Help's four topics), About page 1, Reset counters, Diagnostics (Health, Camera), Exit; the hint and the flash; un-highlight first; `MENU_ENABLE` on; `power_set_mode()` promoted | codex on the code; host tests; the gate, the failure paths and the LED rate on the menu's screens; JD's session |
| **P1b, the previews** | C6: Lighting and Screen, the range and hue editors, the backstop; their rows join the top level | codex (a detailed section first); the plan's P1 exit gates |
| **P1c, the keycode** | "Open" 3's amendment (its RAM reserved now) | codex on the amendment, then the code; then `Fn`+`D` unassigned on JD's board |
| **P1d, the art** | About page 2 (the bunny, the credits, the link) and Help's More info (the QR code) | codex; the gate on both pages |

## P1a

### The tree

```
Configuration                       (opens on row 0)
  Power           Balanced          a choice, committing ("Saver" for Power saver)
  Clock                24h          a choice, committing
  Diagnostics            >
  Help                   >
  About                  >          a page
  Exit                              closes
Diagnostics: ‹ Back, Health page >, Camera page >, Reset counters >
Help:        ‹ Back, Using the menu >, Customizing >, Shortcuts >, Pro tips >
Power:       ‹ Back, • Always on, Balanced, Power saver, Lights out
Clock:       ‹ Back, • 24 hour, 12 hour, Date, Off
```

- **Values:** the parent shows the short form (Power: Always on, Balanced,
  Saver, Lights out; Clock: 24h, 12h, Date, Off), the choice the full one
  (Power saver; 24 hour, 12 hour). Clock's rows map to the enum explicitly:
  24 hour = 24H, 12 hour = 12H, Date = DATE, Off = OFF.
- **Markers:** `>` on every row that opens something (lists and pages);
  in a choice, the saved option has the bullet (0x82) in cell 0 and the
  others a space, so the marker is never the selection.
- **Opening and Back:** the top level opens on row 0; a child list on its
  first real item (row 1); a choice on its saved option (its index + 1,
  past `‹ Back`). Back (the row, or a hold) returns to the parent with the
  parent's cursor and page restored. Back at the top level, and Exit,
  close the session through C1.
- **Paging:** lists by page, the top a multiple of 8. Text pages (Help's
  topics) step by 8 lines and clamp at `lines - 8`: an 11-line page ends at
  offset 3 (the mockup's rule, kept).
- **Committing a choice:** a click on an option applies it
  (`power_set_mode()`; `display_set_clock_mode()` +
  `kb_eeconfig_set_clock_mode()`), flashes `Saved`, and returns. A click on
  `‹ Back`, or a hold: no write, `Cancelled`, and returns. No preview.
- **Reset counters:** two pages, the mockup's: `Clear the health` /
  `counters?` / `Click: reset` / `Hold: cancel`; a click calls
  `health_reset()` and `display_debug_refresh()` and shows `Counters
  reset.` / `Click: back`; a click there or a hold returns to Diagnostics
  with the cursor on Reset counters. A hold on the first page cancels
  (`Cancelled`). ⚠️ It changes the health-reset generation, which ends a C10
  interval: the scripts keep it out of measured intervals.
- **About page 1:** the mockup's eight lines, from a snapshot taken when the
  page opens and frozen while it shows:

  | Line | Format | Unknown |
  |---|---|---|
  | Firmware | `Firmware <10-char hash>` (`AK820_BUILD_HASH`, a new `-D` from `build.sh`; `-dirty` shown as a trailing `+`) | |
  | Flavour, token | `<flavour>, 0x<token>`: flavour dev, daily, fpb, instr, fault (`instrumented` doesn't fit: 24 cells) | |
  | Uptime | `Up 1d 20h 14m` | |
  | Battery | `Battery 76.7%` | `Battery -` |
  | Pack | `Pack 4017 mV` | `Pack -` |
  | Time left | `Left 64h of use` | `Left -` |
  | Mode | `Mode <power mode, full name>` | |
  | Link | `Link BT 1 connected`, `Link 2.4G`, `Link USB` | |

  The snapshot is compact facts (`uptime_s` u32, `batt_pm` u16, `pack_mv`
  u16, `left_h` u16, mode u8, link u8: 12 B), formatted per piece from the
  frozen copy, so every piece of a page shows one sample.
- **Diagnostics:** Health page and Camera page hand off by C1's table
  (MENU to DEBUG, the session OPEN). The return (a click or a hold on the
  page) rebuilds the stack as top (cursor on Diagnostics) -> Diagnostics,
  the cursor on the page's row, including a session that began on the
  Fn+D page (C1's DEBUG/NONE opener).
- **Help:** `scripts/gen_menu_text.py` -> `graphics/res/menu_text_pages.h`:
  the four topics, wrapped to 20 columns, checked to fit, blank lines and
  the shortcuts' spelling kept. One amendment for JD's word: "Using the
  menu" says "It closes by itself / after 24 s idle, or / 3 min mid-edit."
  (the mockup's "never mid-edit" contradicts the 3-minute backstop).
- **The title:** the screen's title, or a **flash** (`Saved`, `Cancelled`,
  `Counters reset`) for 1.3 s, or the **hint** `Turn + Click Knob` for 1 s
  in every 5 s of knob idleness (from 4 s) on **lists only** (not choices
  or pages). A flash wins over the hint. The menu task latches the title
  state and retargets when it changes, so `sig()` and `paint()` read one
  latched state.
- **Timers:** 32-bit elapsed times; 24 s with no knob input closes every P1a
  screen, DEBUG/OPEN and the confirm included (C2/C7: only knob input
  restarts it). The flash and hint use the 16-bit millisecond timer (1.3 s
  and 5 s, far under its 65 s wrap).

### The session identity and the openers

A byte, `menu_kind`: FIXTURE or MENU, chosen when a new request is
accepted, kept through PENDING and DEBUG/OPEN, cleared at close. The owner,
restore, scheduler, pump, loss consumer, visibility and sleep blocker stay
shared; the opening, Diagnostics' return, the input, the invalidation and
op 27's report dispatch on it.

| Route | New session's kind |
|---|---|
| the physical opener (`Fn`+knob), the opener not armed | MENU |
| the physical opener, dev builds, armed (op 27 sub 6) | FIXTURE (the S0/S1 scripts: `menu_s1_spin.py`) |
| op 27 sub 4 | FIXTURE |
| op 27 sub 11 (new) | MENU |

Every route keeps C1's states: PENDING cancels, OPEN closes the current
session (whatever its kind), ANIM refuses. A different opener never
replaces an open screen. Disarming (sub 6 0) still closes or cancels a
session and keeps owed releases; afterwards the production opener stays on.

**Op 27:**
- **sub 0:** the fixture's only: refused (2) unless the session is OPEN
  with kind FIXTURE.
- **subs 1-3:** feed the session's input, whatever its kind; DEBUG keeps
  its click/Back return.
- **sub 4:** as now (FIXTURE). **sub 11:** sub 4's exact framing,
  single-flight, completion (DONE when the session is OPEN and settled, or
  PENDING's resolution), refusal and toggling, with kind MENU.
- **sub 5:** byte 14 keeps the fixture's ids 1-3; the menu reports its
  screen id from 16 (16 list, 17 choice, 18 text page, 19 About, 20
  confirm, 21 done page); byte 15 the active cursor.
- **sub 10:** unchanged: the shared scheduler's targets and timing; every
  menu navigation and title change is a retarget, so it shows.

### `MENU_ENABLE` and the production build

- Defined for every flavour at P1a (C2's "S0's scope" ends). Op 27, HC
  hooks, forced stages and the bench's sleep controls stay dev-only.
- **`power_set_mode()`:** its declaration and body move out of
  `AK820_DEV_HOOKS`; `build.sh`'s daily/fpb forbidden-symbol list loses
  that one symbol.
- **Verified on a daily build** (the flavour rule: gremlin runs dev, so
  a daily build is flashed for this check, needing JD's `Fn`+`Esc` back
  to dev): open, navigate, commit, close; the forbidden-symbol check.

### Slots and signatures (exact, bounded)

Every slot's signature is built from bit fields of bounded values, never a
hash, so two targets of a slot are equal exactly when they paint the same
pixels. A layout change (a new screen kind or a new list) is a C3 layout
change, so a signature only has to be unique within one layout's life.

| Slot | Signature fields |
|---|---|
| the title | the title id (the screen's node, or a flash id, or the hint): 7 bits |
| the separator | constant |
| a list row (two chunks, one slot) | the item's node index (6 bits; 63 = blank past the end), the value index (4 bits; 15 = none), lit (bit 0) |
| a text page or About line | the line index (6 bits); the text is const, About's from the frozen snapshot |
| the scrollbar | the page top and the count (blank when the count fits) |

**A row is one slot of two chunks** (eleven slots, not nineteen): a value
change repaints the row (two chunks). P1a's values change only from their
own choice, after which the parent is a new layout anyway. P1b's previews
change values while a list shows: it may split rows into two slots then,
measured.

### Un-highlight first (BACKLOG, "Fast spins leave old menu rows highlighted")

- **Convention:** bit 0 of a row slot's signature is "lit".
- **The scheduler's pick** (`menu_slots.c`), for layouts that declare it:
  first, any slot whose shown signature (COMMITTED, or PARTIAL's) is lit and
  whose target isn't, lowest first; then the active PARTIAL slot (rev 13's
  resume rule, unchanged); then ascending order.
- A PARTIAL new highlight whose target changes to unlit (a reversal) is,
  by that rule, shown-lit/target-unlit: it repaints first. At most one row
  stays lit once the queue drains, and a fast spin never shows more than
  the old and the new highlight together.
- **Tests:** rapid reversals and wraps at every piece boundary; C10's
  progress (5 commits a bucket in continuous input) kept.

### The completion predicate

`ms_settled()` also requires no loss pending (`mb_lost_pending()`): today it
can report settled before the loss consumer invalidates the slots (codex).
Fixed in P1a, with a host test.

### RAM: the budget, per flavour

Measured: dev `ffa80947` gap 232 B (104 over the floor), devfault
`cbb51ac1` **144 B (16 over)**, daily 2,352. C5's 400 B ceiling has ~88 B
left; its later reservations (P2's `flash_stats` 12, P3's Bluetooth 24)
take 36.

| Item | Bytes |
|---|---|
| `menu_kind` | 1 |
| the stack (3 x node, cursor, top) | 9 |
| the screen kind, the title state, the confirm's page | 3 |
| the flash's start (u16 ms) | 2 |
| About's snapshot | 12 |
| P1a total | **27** (+ padding, checked by `sizeof` asserts and the linked delta) |
| P1b's edit transaction (C5) | 16 |
| P1c's owed releases (90 keys: 12 B) | 12 |
| P1 total | **~55** |

- **dev:** 104 - 55 leaves ~49 over the floor.
- **devfault:** 16 - 55 is below the floor. **Devfault only**
  (`WDT_TEST_HOOKS`): `log_buf` loses 8 entries (144 B, two hours of a
  bench-only build's 180 h log), the plan's C5 fallback, recorded in
  `PATCHES`-style notes beside it. Production flavours keep 720 entries.
- **C5's 400 B ceiling:** 312 + 55 + 36 = 403: over by 3. The ceiling was
  a planning figure; the floor is the hard limit. Amend C5 to 410 B with
  this table, or take P3's 24 B from its own stage's budget then.
- **Stacks:** watermarks after a worst-case P1a session (every screen,
  About formatting), as C5 requires.

### Costs (corrected)

- A half row is 4 pieces; a row 8; **a cursor move 16 pieces** (~165 ms
  measured on F3).
- **Opening** a list: 8 clear bands, the title (8 pieces), the separator
  (1), 8 rows (64), the scrollbar (1): ~74 painting passes plus the bands
  and commits, ~0.8 s (F1's open measured 711-793 ms).
- A text page: as a list without a highlight.

### Tests (P1a)

- **Host** (`menu_s0_test.c`, a P1 section, the env faked): every node's
  open, move, click and Back; the stack's limits and restored cursors;
  paging (lists by 8, pages clamped); the commits and the cancels (no
  write); Reset counters' two pages; Diagnostics' handoff and the rebuilt
  return (also from a DEBUG/NONE opener); the session identity's table and
  op 27 subs 0-5 and 11 per kind; the 24 s timeout on every screen; the
  hint (lists only) and the flash (wins); the title latch; un-highlight
  first at every piece boundary with reversals and wraps; the completion
  predicate; the expected frame of every screen against the face; every
  piece at most 512 B; a retarget, a loss and a close-reopen at every piece
  boundary of an open, a move and a page; `sizeof` asserts.
- **Board:** the gate gains the menu (sub 11): its open, moves both ways and
  wrapping, a choice's commit and cancel, Help's paging, About, Reset
  counters' pages (outside the measured interval), Diagnostics' round
  trip, the hint and the flash; the failure paths gain menu cases; the LED
  rate covers the menu; a real spin (`menu_s1_spin.py`, unarmed: the
  menu); visibility from requested power Off and level 0, Lights out
  chosen, Diagnostics, close; persistence of Power and Clock across a
  reboot after a settled save, and no write on a cancel (the flash write
  counters); a daily build's check; JD's session.

## P1b, P1c, P1d

Each gets its own detailed section and codex round before its code. P1b's
must cover the rows' values changing under a preview (slots per half),
C6's writers, the editors' slots and pieces, and the Screen item's C7
interplay (the requested level previewed while the override keeps it
visible). P1d's: the bunny as 8-bit grey (1,134 B, amending "Generated
files"' 2,268 B RGB565), expanded by a new `lcd_bus.c` primitive beside
`lcd_blit_mono` with its failure cleanup; image pieces and the credits'
text pieces as separate ops; the QR code's module image (106 B) unpacked and
scaled 3x into a 26 B stack bitmap per 2-row piece, 50 pieces split into
several logical ops (so op latency stays measurable), and the URL frozen
as `https://github.com/jdlien/ak820-pro`.
