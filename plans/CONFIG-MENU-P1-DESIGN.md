# The configuration menu's P1: the design (draft 3.1, 2026-10-24)

Warren's design for stage P1 of [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)
("Stages", 3). The plan's contract (C1-C10, "The settings", "Diagnostics,
About, Help", "Generated files") stays authoritative except where a line
here amends it (marked **amends**); this says how P1 is built on S0 and S1,
in four flashes. The words and behaviour are the mockup's
([`config-menu-mockup.html`](config-menu-mockup.html)) unless amended.
**Draft 3 answers codex's second round; draft 2 answered its first**
([`review-codex-p1-design-2026-10-24.md`](review-codex-p1-design-2026-10-24.md)).

## What S0 and S1 left

- C1's owner, session and restore; C2's capture and coalesced input; C3/C4's
  slot scheduler with pieces; C7's visibility override (`bkl_effective()`,
  published by `po_apply()`): already built and active for any MENU
  session; C10's measures.
- The text: the 1-bit Cozette face, `menu_text.c`, `lcd_blit_mono`. A 61 px
  half-row piece ~5.1 ms; every pass under 15 ms (GREMLIN-RESULTS §19b-d;
  the gate's longest 14.8 ms: thin).
- Settled with JD: lit text (#C8C8C8 rows, #FFF2A0 selected), half rows,
  the 6x14 face.
- The fixture (C9, F1-F3), which the gate, the failure paths and the style
  measures drive through op 27.

## The steps

| Step | What | Gate before the next |
|---|---|---|
| **P1a, the tree** | the session identity; `menu.c` with lists, committing choices (Power, Clock), Help's four topics, About page 1, Reset counters, Diagnostics (Health, Camera), Exit; the latched model; the hint and the flash; one lit row at most; `MENU_ENABLE` on; `power_set_mode()` promoted | codex on the code; host tests; the gate, the failure paths and the LED rate on the menu's screens; JD's session |
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
- **Paging:** lists by page, the top a multiple of 8. Help's topics step by
  8 lines and clamp at `lines - 8`: an 11-line page ends at offset 3 (the
  mockup's rule, kept).
- **Committing a choice:** a click on an option applies it
  (`power_set_mode()`; `display_set_clock_mode()` +
  `kb_eeconfig_set_clock_mode()`), flashes `Saved`, and returns. A click on
  `‹ Back`, or a hold: no write, `Cancelled`, and returns. No preview.
- **Reset counters:** two pages, the mockup's (its own geometry, below):
  `Clear the health` / `counters?` / `Click: reset` / `Hold: cancel`; a
  click calls `health_reset()` and `display_debug_refresh()` and shows
  `Counters reset.` / `Click: back` (the confirmation's lines gone); a
  click there or a hold returns to Diagnostics with the cursor on Reset
  counters. A hold on the first page cancels (`Cancelled`). ⚠️ It changes
  the health-reset generation, which invalidates a C10 interval spanning
  it: the gate runs Reset counters before its measured interval (a later
  interval would need a fresh token, generation and baselines, which
  `Board.arm()` doesn't take today).
- **About page 1:** the mockup's eight lines, from a snapshot taken when the
  page opens and frozen while it shows:

  | Line | Format | Unknown |
  |---|---|---|
  | Firmware | `Firmware <8 hex>`, `+` when dirty (`-DAK820_BUILD_HASH=0x<git rev-parse --short=8>u -DAK820_BUILD_DIRTY=0/1`, appended by `build.sh` after its identity capture) | |
  | Flavour, token | `<flavour>, 0x<token>`: dev, daily, fpb, instr, fault (`instrumented` doesn't fit: 24 cells) | |
  | Uptime | `Up 1d 20h 14m` | |
  | Battery | `Battery 76.7%` | `Battery -` |
  | Pack | `Pack 4017 mV` | `Pack -` |
  | Time left | `Left 64h of use` | `Left -` |
  | Mode | `Mode <power mode, full name>` | |
  | Link | `Link USB`; `Link 2.4G <state>`; `Link BT <n> <state>`, the state one of linking, pairing, connected, rejected, idle (the CH582F's own; never "connected" for all) | |

  The snapshot is compact facts (`uptime_s` u32, `batt_pm` u16, `pack_mv`
  u16, `left_min` u16, mode u8, link u8 packed as transport 2 bits, slot 2,
  state 3: 12 B, 4-aligned), formatted per piece from the frozen copy, so
  every piece of a page shows one sample. Unknowns are sentinels (0xFFFF),
  kept through the minutes-to-hours conversion; `battery_pack_mv()`'s
  unknown, 0, is normalized to the sentinel at capture.
- **Diagnostics:** Health page and Camera page hand off by C1's table
  (MENU to DEBUG, the session OPEN). The return (a click or a hold on the
  page) rebuilds the stack as top (cursor on Diagnostics) -> Diagnostics,
  the cursor on the page's row, including a session that began on the
  Fn+D page (C1's DEBUG/NONE opener).
- **Help:** `scripts/gen_menu_text.py` -> `graphics/res/menu_text_pages.h`
  (built): the four topics, wrapped to 20 columns, checked to fit, blank
  lines and the shortcuts' spelling kept. One amendment for JD's word:
  "Using the menu" says "It closes by itself / after 24 s idle, or / 3 min
  mid-edit." (the mockup's "never mid-edit" contradicts the 3-minute
  backstop).
- **The title:** the screen's title, or a **flash** (`Saved`, `Cancelled`,
  `Counters reset`) for 1.3 s, or the **hint** `Turn + Click Knob` for 1 s
  in every 5 s of knob idleness (from 4 s) on **lists only** (not choices,
  topics or About). A flash wins over the hint. The menu task latches the
  title state and retargets when it changes, so `sig()` and `paint()` read
  one latched state.
- **Timers:** 32-bit elapsed times for the timeouts; 24 s with no knob input
  closes every P1a screen, DEBUG/OPEN and the confirm included (C2/C7: only
  knob input restarts it). The flash and the hint use the 16-bit
  millisecond timer (1.3 s and 5 s, far under its 65 s wrap).

### External changes: the latched model

`Fn`+`B` (`power_cycle_mode()`) and `Fn`+`C` (the clock setters) still work
while the menu is open. The menu task reads the power and clock getters each
pass into a latched model (2 B); a change updates the model and retargets.
Signatures and painters read only the model. In an open choice the cursor is
independent of the saved value: an external change moves the saved bullet;
`‹ Back` or a hold writes nothing (the external value stays); a click
commits the option under the cursor.

### The session identity and the openers

A byte, `menu_kind`: FIXTURE or MENU. It's installed when a new request is
accepted, **before** the opening's synchronous callbacks dispatch, kept
through PENDING and DEBUG/OPEN, and cleared at close **and** at a PENDING
cancel. The owner, restore, scheduler, pump, loss consumer, visibility and
sleep blocker stay shared; the opening, Diagnostics' return, the input, the
invalidation and op 27's report dispatch on it.

| Route | New session's kind |
|---|---|
| the physical opener (`Fn`+knob) with `armed` clear | MENU |
| the physical opener with `armed` set (dev, op 27 sub 6) | FIXTURE (the S0/S1 scripts) |
| op 27 sub 4 | FIXTURE |
| op 27 sub 11 (new) | MENU |

The kind is chosen from `armed` itself; `menu_enabled()` only says whether
the physical opener works at all (always, with `MENU_ENABLE`). Every route
keeps C1's states: PENDING cancels, OPEN closes the current session whatever
its kind, ANIM refuses; a different opener never replaces an open screen.
Disarming (sub 6 0) still closes or cancels a session and keeps owed
releases; the production opener stays on afterwards.

**Op 27:**
- **sub 0:** the fixture's only: refused (2) unless the owner is MENU, the
  session OPEN **and** the kind FIXTURE, then the existing pattern checks.
- **subs 1-3:** the session's input, whatever its kind; DEBUG keeps its
  click/Back return.
- **sub 4:** unchanged. **sub 11: sub 4 exactly, except the kind:** no
  arguments, DONE when the owner event is applied (a PENDING open reports
  DONE, as sub 4 does today, so a second opener can cancel it), refusals as
  sub 4's; painting is observed separately (`pixels_done`, `tgen`).
- **sub 5:** byte 14 keeps the fixture's ids 1-3; a MENU session reports
  `16 + the node` of the list or page showing (unique per screen: Help and
  Diagnostics differ, Power and Clock differ), 0 when not OPEN. Byte 15:
  the cursor on a list or choice, the page's top line on a page, 0xFF when
  the owner isn't MENU.
- **sub 10:** unchanged; every navigation, title change and latched value
  change is a target (`ms_set_layout()` or `ms_retarget()`, never both).
- **The fixture's Diagnostics return** stays F1 row 7; the menu's rebuilds
  its stack.

### `MENU_ENABLE` and the production build

- Defined for every flavour at P1a (C2's "S0's scope" ends). Op 27, HC
  hooks, forced stages and the bench's sleep controls stay dev-only.
- **`power_set_mode()`:** its declaration and body move out of
  `AK820_DEV_HOOKS`; `build.sh`'s daily/fpb forbidden-symbol list loses
  that one symbol (done in `9f8b42da` / `6a75c2a`).
- **Verified on a daily build** (gremlin runs dev, so a daily build is
  flashed for this check, needing JD's `Fn`+`Esc` back to dev): open,
  navigate, commit, close; the forbidden-symbol check.

### Layouts, transitions and signatures (exact, bounded)

**Two layouts:** the **list geometry** (C8: the title, the separator, 8
rows, the scrollbar; for lists, choices, Help's topics and About), and the
**confirm geometry** (Reset counters' two pages: the title, the separator,
text at y 22, 36, 72 and 86 as the mockup, its own slots). **C3 stands:**
moving between lists repaints in place without a clear, so every row
target is unique across the whole tree, not only within one list.

| Change | Scheduler action |
|---|---|
| a cursor move, a wrap, a page change in one list | retarget (unchanged partial work kept) |
| into another list or choice, back to a parent, into a topic or About | retarget (the list geometry stays; globally unique signatures) |
| a page step in a topic | retarget |
| into or out of Reset counters (the confirm geometry) | layout change (its clear) |
| the opening, Diagnostics' return | layout change (fresh) |
| the hint, the flash, a latched value | retarget |

**Signatures, bit fields only, never a hash:**

| Slot | 16-bit signature |
|---|---|
| the title | the title id, enumerated: 1-11 the screens' titles (Configuration, Power, Clock, Diagnostics, Help, About, the four topics, Reset counters), 16-18 the flashes (Saved, Cancelled, Counters reset), 19 the hint |
| the separator | constant |
| a row (one slot, two chunks) | bits 15-14 the kind (0 blank, 1 item, 2 text line, 3 About line). Item: bits 13-8 the row's own node (6 bits), bits 7-4 the value index (15 none), bit 1 the saved bullet, **bit 0 lit**. **Every option is a node of its own** (Power's four, Clock's four), distinct from its parent's setting row: the top level's `Clock 24h` and the choice's `24 hour` never share a signature. Text line: bits 13-11 the topic, bits 10-5 the line. About line: bits 11-8 the line |
| the scrollbar | `0xFFFF` blank (the count fits); else the count in bits 13-8 and the top in bits 5-0 (both at most 63, asserted) |
| the confirm geometry's text | its line ids, constant |

Blank rows past a list's end are kind 0: one signature, the background. An
absent scrollbar paints its track black.

**About's snapshot (draft 3.1, codex's third round):** taking a new snapshot
marks About's row slots INVALID (`ms_invalidate_rows()`, a new call: no
panel clear, `maybe_lit` and the abandonment bookkeeping kept), then
retargets once. A retarget alone would leave a committed row from an earlier
snapshot with an equal signature (a 2-bit generation wraps; any width only
delays it). The host tests reopen About repeatedly before its later rows are
painted.

### One lit row at most (BACKLOG: "at most one row ever lit")

- **`maybe_lit`, an 8-bit mask of row slots that may show yellow pixels.**
  A bit is set when a lit target's first piece is sent (so a partial
  highlight counts), and cleared only when an unlit paint of that row
  completes all its pieces, or a clear completes. A loss, an abandoned
  partial op or an invalidation keeps it. Only row slots (the layout
  declares their range); the title's ids mean nothing here.
- **The scheduler's order, for a layout that declares rows:**
  1. the active PARTIAL slot, if it's a cleanup still unchanged (resume it);
  2. a row in `maybe_lit` whose target is unlit, lowest first;
  3. the active PARTIAL slot (rev 13's resume rule, unchanged);
  4. ascending order, **except a row whose target is lit, which waits
     while any other row is in `maybe_lit`.**

  So at most one row ever shows yellow: the new highlight starts only when
  the old one is fully grey.
- **As built (P1a's code review):** step 1 resumes **any** unchanged active
  PARTIAL slot, not only a cleanup, before step 2 (rev 13's resume rule
  untouched). It can't add a lit row: an active partial is never a second
  highlight, since a lit row starts only when no other row may be lit. It
  only delays a cleanup by the active op's remaining pieces (at most 8).
  The host tests check one lit row at most after every pass, through
  reversals, wraps, a second move and a send given up at every pass of a
  move; removing both the cleanup-first scan and the lit-target wait makes
  them fail (two rows lit); either alone keeps them passing.
- **Abandonment** keeps today's rules: ended DMA bookkeeping settles first;
  an unfinished abandoned op isn't counted; completed ops and reached stops
  are kept; an op resumed across a retarget completes untimed (rev 13). The
  priority changes only which slot is picked; it makes no target or commit.
- **Tests:** after every pass, the fake panel has at most one row with any
  lit-yellow pixel, through moves, reversals, wraps, page changes, losses
  and preemption at every piece boundary. C10's continuous-input rule is
  what the gate checks: a commit in every 500 ms bucket, the final target
  settled within 500 ms, the targets balanced.

### The completion predicate

`ms_settled()` also requires no loss pending (`mb_lost_pending()`): it could
report settled before the loss consumer invalidates the slots (codex).
**Done** (`9f8b42da`), with a host test.

### RAM: the budget, per flavour

Measured: dev `ffa80947` gap 232 B (104 over the floor), devfault
`cbb51ac1` **144 B (16 over)**, daily 2,352.

| Item | Bytes |
|---|---|
| `menu_kind` | 1 |
| the stack (3 x node, cursor, top) | 9 |
| the screen kind, the title state, the confirm's page | 3 |
| the flash's start (u16 ms) | 2 |
| the latched model (power, clock) | 2 |
| `maybe_lit` | 1 |
| About's snapshot (12 B, 4-aligned) | 12 |
| P1a total | **30**, + padding: `sizeof` asserts and the linked delta |
| P1b's edit transaction (C5) | 16 |
| P1c's owed releases (90 keys) | 12 |
| P1 total | **~60** |

- **dev:** 104 - 60 leaves ~44 over the floor.
- **devfault:** 16 - 60 is below it. A dedicated flag, `AK820_DEVFAULT`
  (`build.sh` adds it for devfault only; `WDT_TEST_HOOKS` also covers the
  instrumented flavour), trims `log_buf` by 8 entries: 144 B, 180 h to
  178 h, devfault only. `ak820battery.py` and `flash.sh`'s dump use the
  count the board reports. The battery simulator's `s_log_long` asserts 720:
  it gains a trimmed variant expecting 712 (wrap and oldest-first order),
  and keeps the 720 test.
- **C5's 400 B ceiling (amends):** **420 B**, with this table: S0/S1's 312
  + P1's ~60 + P2/P3's reserved 36 = ~408. The floor stays the hard limit
  for every flavour.
- **Stacks:** watermarks after a worst-case P1a session.

### Costs (corrected)

- A half row is 4 pieces; a row 8; **a cursor move 16 pieces** (~165 ms
  measured on F3), now in order: the old row's 8, then the new row's 8.
- **Opening** a list: 8 clear bands, the title (8 pieces), the separator
  (1), 8 rows (64), the scrollbar (1): ~74 painting passes plus the bands
  and commits, ~0.8 s (F1's open measured 711-793 ms).
- A topic or About: as a list without a highlight.

### Tests (P1a)

- **Host** (`menu_s0_test.c`, a P1 section, the env faked): every node's
  open, move, click and Back; the stack's limits and restored cursors;
  paging (lists by 8, topics clamped); the commits and the cancels (no
  write); external changes (the bullet moves, the cancel keeps them); Reset
  counters' two pages; Diagnostics' handoff and the rebuilt return (also
  from a DEBUG/NONE opener); the session identity's table and op 27 subs
  0-5 and 11 per kind; the 24 s timeout on every screen; the hint (lists
  only) and the flash (wins); the title latch; at most one lit row after
  every pass, with reversals, wraps, losses and preemption at every piece
  boundary; the expected frame of every screen against the face; every
  piece at most 512 B; a retarget, a loss and a close-reopen at every piece
  boundary of an open, a move and a page; `sizeof` asserts.
- **Board:** the gate gains the menu (sub 11): its open, moves both ways and
  wrapping, a choice's commit and cancel, Help's paging, About, Diagnostics'
  round trip, the hint and the flash, with Reset counters' pages run before
  the measured interval; the failure paths gain menu cases; the LED rate
  covers the menu; a real spin (`menu_s1_spin.py --menu`, a new mode: it
  arms the fixture's opener today); visibility from requested power Off and
  level 0, Lights out chosen, Diagnostics, close; persistence of Power and
  Clock across a reboot after a settled save, and no write on a cancel (the
  flash write counters); a daily build's check; JD's session.

## JD's first look at P1a (10-24, ~19:15)

"a fantastic early version ... It appears to work flawlessly, as designed",
with the prototype's other items still to come (P1b-d, P2-P4). His notes:
1. **Back and Exit styled differently**, maybe light red ("not sure if that
   would look wrong or cluttery"); icons are hard at this size. **Tried
   (`22312b44`):** not selected, they're #E08080; selected, the usual lit
   yellow. For his eye on the panel.
2. **A page step should move the scrollbar first,** then the text flow in
   (it moved only after all the text, "a second or two"). **Done
   (`22312b44`):** the scrollbar's slot comes before the rows.
3. **The choice's dot needs breathing room:** **done (`22312b44`):** a
   whole cell, so options read "• Balanced", in line with "‹ Back".
4. **A bootloader item, later** (the polish phase): a standalone item with
   a little text and a click to confirm "Enter Bootloader", saying how to
   leave without flashing (the slider to Bluetooth and back to USB, or
   unplug and replug in wired mode), so `Fn`+`Esc` needn't stay bound. JD:
   "maybe we don't need it at all"; the words wait for his text pass
   ("LLM text is often overly verbose"). BACKLOG.

## Before P1 is accepted: JD's text review (pinned, 10-24)

JD will review and edit **all** the menu's text by hand once P1 nears its
end: Help's four topics (`scripts/gen_menu_text.py`; the "3 min mid-edit"
amendment is approved), every label, value, title, flash and the hint,
About's lines, Reset counters' pages, and P1b-d's words. Nothing here is
final until then.

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
