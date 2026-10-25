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

## JD's decisions, later on 10-24

- **Timing (C10's 15 ms):** (b) for now: menu painting passes of ~16-17
  ms are accepted (the hard line, 25 ms, keeps 8 ms of margin). (a), the
  polled send and the expansion in SRAM, stays on the table for a refinement
  pass "if it's clear it'll work". RAM to find for it, best first: the
  stacks' measured watermarks (C5 owes them); the debug page's two 198 B
  text buffers, shared with the menu (JD: "not going to be visible in normal
  use, just an artifact of when I was chasing down the keyboard eating my
  keystrokes"); the battery log last (likely not in a production build, but
  wanted for now).
- **The hint is a pair** (`1e84bf17`): "Turn + Click Knob", then "Hold to
  Go Back" (JD: the hold "is a very non-obvious gesture").
- **Clock, more options** (with the dashboard's renderer, later): seconds
  first, the default 24 hour with seconds (today's 24H, enum 0, unchanged);
  12 hour with seconds (today's 12H); then new modes appended (the enum is
  persisted): 24 hour and 12 hour without seconds; Date; Off. Fn+C's cycle
  goes once the menu has it ("keep those in the menu"). Rows show a short
  label and an example of the format, e.g. `24h       13:45:01`,
  `12h    1:45:01 PM`, `Date  Oct 24, 2026` (all fit: the longest is 18
  cells; the menu has room for a plain "PM", unlike the dashboard's tiny
  AM/PM glyph). Static examples first; live ones once rows split into half
  slots (P1b), at ~8 pieces a second while the Clock list shows. The top
  level keeps a short label, not a ticking time.

## JD's icons (10-24, evening)

Picked in the icon picker (`scripts/gen_icon_gallery.py`, an artifact: every
icon-like Cozette glyph at the panel's pixels, with the menu's list geometry
as a preview). Built in `925f029b`:

- **The wrench** (U+1F527, double width) before "Configuration".
- **◀ and ▶** (U+25C0, U+25B6) for Back's ‹ and the submenu rows' >.
- **The circled check** (U+F058) for the saved option's dot, in cells 0-1;
  **the squared one** (U+F631) is the fallback if the circle renders badly
  (dev: op 27 sub 14 flips it live).
- **A cursor** (U+1FB6C, the left triangular quarter block, 3 × 11 px) left
  of the selected row, in its colour: a list row's lead is now x 0-3 (the
  cursor's columns 0-2 and a 1 px gap) where it was x 3, so no text moves
  (JD: "It only takes 4px + 1px margin"; the bezel is no concern, the menu is
  read from straight above). The lead only widens chunk 0 (61 → 64 px; the
  same four pieces, 512 B at most).
- **Top-level icons**, label at cell 2: Power the bolt (F0E7), Clock the clock
  (F017), Diagnostics the microchip (F2DB), Help the ? circle (F059), About
  the i circle (F05A), Exit × (F00D). Proposed for the planned items, in the
  picker: Lighting the bulb (F834; the dashboard's power mode is a bulb too,
  so the palette F8D7 is the alternative), Screen the desktop (F108),
  Connection Bluetooth (F293), Indicators the sun (F185, JD: "super bright
  light shining in your eye"), Battery (F240), Bootloader (F498).
- **Spacing:** a mark keeps at least 4 px before the next letter: a space
  follows it unless its own blank right-hand columns give that (JD: "at least
  1px of margin"; a double-width icon can ink all 12 columns). A 7 px icon on
  a 6 px advance (half of Cozette's icons) takes two cells and leaves 5 blank.

After JD's look at `925f029b` ("looking quite good"), in `541a8cbd`:

- **The squared check** is the mark; the circle "doesn't look good", so it
  and its dev switch are gone.
- **A section's icon on its headings** ("keep the consistency"): Power,
  Clock, Diagnostics and Reset counters, Help and its topics, About. The
  flashes and the hints are messages, not headings: no icon.
- **The cursor in its own colour**, `MENU_CURSOR` #A5A2A5, a neutral grey a
  shade under the dim rows (JD: in the lit colour it "kinda blends into" the
  icon beside it); tunable live on dev (op 27 sub 13, `menu_tune.py`'s
  `cursor`). A mono piece has one colour, so a row's lead is its own chunk,
  first and one piece (112 B); the text's chunks are back to 60 and 61 px.
- **The selected row's colour stays `0xFF94`** (#FFF3A5 on the panel). Tried
  live on `541a8cbd`: pure white ("a tint still helps differentiate it"),
  #FFF7C6 ("not bad"), #FFFF00. JD: the original "combines clarity and
  contrast"; "leave it for now".

## Before P1 is accepted: JD's text review (pinned, 10-24)

JD will review and edit **all** the menu's text by hand once P1 nears its
end: Help's four topics (`scripts/gen_menu_text.py`; the "3 min mid-edit"
amendment is approved), every label, value, title, flash and the hint,
About's lines, Reset counters' pages, and P1b-d's words. Nothing here is
final until then.

## P1b: Lighting, Screen and the edit transaction (draft 3, 10-24 night)

The mockup's previewing half of the menu, on P1a's machinery. Everything not
said here is P1a's (the slot rules, the one-lit-row rule, the session
identity, the latched model, the hint and the flash, the icons). **Draft 2
answered codex's first round, draft 3 its second**
([`review-codex-p1b-design-2026-10-24.md`](review-codex-p1b-design-2026-10-24.md),
[`review-codex-p1b-design2-2026-10-24.md`](review-codex-p1b-design2-2026-10-24.md)):
the writers it missed, the lit bit, the rollback's place, the hue bands'
overlap, the RAM, the tests; then the fast turn's clock, external changes as
new targets, and the adapter the tests run.

### The tree, added

The top level becomes the mockup's page one less what is P2/P3's: **Lighting,
Screen, Power, Clock, Diagnostics, Help, About, Exit** (eight rows: one page,
no scrollbar). Connection, Indicators and Battery join with P2/P3.

| Node | Kind | Rows / layout | Value on its parent's row |
|---|---|---|---|
| Lighting | list | ◀ Back, Effect, Brightness, Hue, Saturation, Second color *or* Speed, Lights | ▶ |
| Screen | range editor, 0-23, step 1 | the range layout | `Off`, else `round(level*100/23)%` |
| Effect | previewing choice | ◀ Back, the nine effects (two pages, the scrollbar) | the effect's readout name |
| Brightness, Saturation, Speed | range editor, 0-255; a detent the next percentage, 8% fast (JD, 10-25: was 5 of 255, ×4 fast) | the range layout | `(v*100+127)/255 %` (the readout's rounding) |
| Hue, Second color | hue editor, 0-255 wrapping, step 1 (fast 12; JD, 10-25: was 3) | the hue layout | `h*360/256` degrees; Second color `+` that of `speed` |
| Lights | previewing choice | ◀ Back, Off, On | `On` / `Off` |

- **Second color or Speed** (the row's label and its editor) follows the
  *live* effect: Alphas/Mods uses `speed` as its second colour's hue offset
  (`alpha_mods_anim.h:11`), as the readout says (`fmt_speed`).
- **The effects' names and order:** one table, `{mode, name}` for each enabled
  effect in mode order (Solid, Alphas/Mods, Cycle All, Cycle L-R, Cycle U-D,
  Jellybean, Heatmap, Rainfall, Drift), each entry under its `ENABLE_*` as
  `rgb_mode_short()`'s cases are; `param_overlay.c` and the menu both read it
  (the plan's "moved out of PARAM_OVERLAY"). A mode the table doesn't list
  (none today) shows as its number and has no row: the choice opens on Back.
- **Icons** (the face gains two cells' worth and a third): Lighting the bulb
  (U+F834, one cell, JD's pick; the palette U+F8D7 is the alternative if the
  dashboard's power-mode bulb confuses), Screen the desktop (U+F108, two
  cells). Their headings carry them, as P1a's do.
- **Fast turns:** an input carrying two or more detents, or one within 90 ms
  of the last, takes the fast step (the mockup's rule). `menu_input` has the
  detents and `now`; the last turn's time is new state: **32-bit ms** (a
  16-bit one aliases inside the 180 s backstop: a turn 65,556 ms after the
  last would read as 20 ms), with a flag for "a previous turn in this
  editor", cleared when an editor opens. The predicate (codex, round three):
  `abs(turns) >= 2 || (have_previous_turn && (uint32_t)(now - last_turn_ms)
  < 90)`, so an editor's first single-detent input is never time-accelerated.
  Tests: a long idle, the 32-bit wrap, re-entering an editor.
- **Diagnostics' place** on the top level is computed from its rows, not the
  `2` that `menu_return_from_diag()` pushes today (`menu.c:512`); new title
  ids follow P1a's table.

### Choosing and previewing (the mockup's rules)

- **Previewing choices** (Effect, Lights) open with the cursor on the current
  value, the saved one's square check beside it. Turning previews at once; on
  Back, the value from before the edit. A click on an option saves it
  ("Saved"); a click on Back, or a hold, cancels ("Cancelled").
- **The editors** (range, hue): turning previews; a click saves; a hold
  cancels. The flash shows on the list they return to.
- **The backstop:** while a previewing edit is open, the 24 s idle close
  (`menu_ops.c:155`) becomes 180 s, the same signed elapsed test; 3 minutes
  with no knob input cancels the edit and closes the menu (C8). Typing and
  host traffic still don't count as input (C7). An external cancel after
  more than 24 s of knob idleness may close the returned list at once; the
  idle clock isn't reset to show "Cancelled".
- **Leaving the menu mid-edit, by any route:** the edit rolls back before the
  panel changes hands (C6, "The rollback", below). A loss under the menu
  isn't a leaving. The animation's start is refused during a session
  (`panel_owner.c:170`), so it rolls nothing back.

### C6: the edit transaction, concretely

- **One edit at most,** `edit_t` (10 B, inside C5's 16 B reserve): the field;
  the RGB snapshot (mode, h, s, v, speed, enable, **flags**, which `RM_FLGN`
  and `RM_FLGP` write, `process_rgb_matrix.c:97`) or the LCD level; the
  transaction's state. Opened when an editor or a previewing choice opens;
  closed by Save, Cancel, the rollback or an external write.
- **The rollback, `menu_edit_rollback()`:** restores the snapshot and closes
  the transaction; nothing else (no navigation, no flash, no repaint). Idempotent.
  `panel_owner.c`'s two transitions away from the menu call it **first,
  before `set_owner()` and the session change**: `do_close()`
  (`panel_owner.c:93`: the close, the opener's close, the wake release's)
  and `enter_debug()` (`:107`: the debug page's handoff, dev op 1). Both
  return `PO_ACT_EDIT_CANCEL` today, which is applied only after the owner
  has changed (`display.c:3971`, `menu_ops.c:75`); that action stays as the
  record, the rollback having run.
- **An external write's cancel** is the rollback, then (only while the menu
  owns the panel) the pop to the editor's list and "Cancelled".
- **Re-entrancy:** every hook below runs from a main-loop entry point outside
  `menu_input()` (`process_record_kb`, `via_command_kb`, `command_extra`, the
  `RGBM_*` handler, `param_repeat_step`, the `SCR_*` handler, the dev ops).
  The adapter calls QMK's setters directly, never a hooked entry point, so no
  hook can fire inside `menu_input()`'s call tree; a host test counts the
  hooks across every input path.
- **The RGB adapter's sequencing lives in a new pure module,
  `menu/menu_edit.c`** (the transaction: open, preview, save, cancel,
  rollback, the external cancel), which the host tests build as they build
  `menu.c`. It reaches QMK only through narrow primitives in `menu_env.h`
  (read the config; set mode, HSV, speed, flags, enable, each `_noeeprom` or
  saving; the LCD level, RAM or saved), each a one-line call in
  `menu_glue.c`. The host's fakes of those primitives copy QMK's semantics
  (the early returns while disabled, the dirty flags), so the tests run the
  production sequencing, not a second implementation. The rules it follows:
  - QMK's mode and HSV setters return early while the lights are off
    (`rgb_matrix.c:606, 658`); speed's doesn't. So preview, save and cancel
    each run with `enable` set inside the call and restore it last (C6).
  - **Preview:** the field's `_noeeprom` setter.
  - **Save:** the field's saving setter (it flags the config dirty; QMK's
    flush writes it, once the board's settle rule allows,
    `ak820pro.c:703-758`). Lights: `rgb_matrix_enable()` or
    `rgb_matrix_disable()`, explicitly, never a toggle.
  - **Cancel:** every field of the snapshot back with `_noeeprom` setters,
    `enable` last. A dirty flag set before the edit opened stays set
    (`eeconfig_flag` ORs it, `eeconfig.h:191`), so its pending write still
    happens, with the restored values.
  - Save always calls the saving setter, even when the preview already
    equals the value (the dirty flag is the point); that includes Effect's
    mode. In a *preview* or a *cancel*, mode is set only when it changes, so
    an HSV or speed preview doesn't restart the effect.
  - Persistence follows QMK's flush once the hold lifts, not the instant
    "Saved" shows.
- **The flush hold:** `rgb_matrix_eeprom_flush_allowed()` (the board's
  override) also returns false while an RGB edit is open, so no previewed
  value is ever written.
- **The Screen adapter:** preview `display_set_brightness(level)` (RAM only);
  save that plus `kb_eeconfig_set_lcd_brightness()`; cancel
  `display_set_brightness(before)`. C7's override keeps the panel lit at
  `max(requested, 1)`, so previewing Off shows level 1 until the menu closes.
- **External writers cancel first, then apply** (C6's list, at these sites),
  each through one `menu_edit_external(domain)`:
  - **VIA:** a new `via_command_kb()` on the board (none exists; the weak
    default returns false, and `raw_hid_receive` calls it before dispatching,
    `via.c:286, 296`). It cancels an open RGB edit for **any** custom command
    on the RGB-matrix channel, reads included, and for
    `id_device_indication` (a toggle, `via.c:167`), then returns false, so
    VIA's own processing and reply go on. Reads cancel so a lighting backup
    can't capture a preview (`flash.sh:153`, `ak820lighting.py`); the restore
    after a flash is ordinary set and save packets (`ak820lighting.py:122`).
  - **The magic reset** (both Shifts and Backspace: `command_common()` runs
    `eeconfig_init()`, which writes the RGB defaults and force-flushes them,
    `command.c:346`, `eeconfig.c:122, 163`; command support is on,
    `keyboard.json:22`): the board's `command_extra()`, which
    `command_proc()` calls first (`command.c:71, 75`), cancels for that code
    and returns false. `eeconfig_init_kb()` would be too late.
  - **`RM_*` keys, `RM_FLGN`/`RM_FLGP` included:** `process_record_kb`
    (`ak820pro.c:345`) runs before `process_rgb_matrix` (`quantum.c:355,
    417`); on release, since `RGB_TRIGGER_ON_KEYDOWN` isn't defined.
  - **`UG_*` keys:** the same place, on press (`process_underglow`,
    `quantum.c:414`, runs them into the RGB-matrix setters).
  - **`RGBM_*`** (`ak820pro.c:498-508`, on press) and
    **`param_repeat_step()`** (`param_overlay.c:44`), before each step, so
    the step is computed from the restored value, not the preview.
  - **`SCR_UP`/`SCR_DN`** (`ak820pro.c:386-395`, and their repeat), before
    `display_brightness_up/down()` reads the level (`display.c:335`); dev ops
    4 and 5 (5 sets the power, not the level: kept as C6 lists it).
    `SCR_TOG` isn't a level writer.
  - The list behind the editor then shows the externally written values.
- **Resets aren't writers to roll back:** `QK_CLEAR_EEPROM`, `QK_BOOT`, the
  raw-HID jump and every reboot discard RAM, and no shutdown path flushes the
  RGB config (`quantum.c:208-239`), so the flush hold has left EEPROM at the
  last persisted values (a pending save may be lost, as it always could be;
  `QK_CLEAR_EEPROM` deliberately brings back the defaults). (A rollback at
  shutdown would also undo the bootloader
  splash's full brightness, `display.c:1331`.) VIA's `id_eeprom_reset`
  resets VIA's own storage only (`via.c:120`).
- **Not writers** (C6): the power ladder's caps and scale (`power.c:119`
  restarts an effect without changing its config), the battery's RGB cut,
  deep sleep, `consumer_mod.c`, the lock-light channel, host text and
  now-playing. They cancel nothing. **Excluded:** `HC_STALL` mode 2's
  deliberate write of the persisted LCD data (`kb_eeconfig.c:161`), a
  destructive fault injection.

### The RGB and LCD values: read, not latched

Unlike `model_power`/`model_clock`, the Lighting and Screen rows read the
live config through `env_*` getters as they compose. While an edit is open
the live config *is* the preview, so the list behind an editor is right when
it returns. A value that changes between a slot's pieces changes its
signature, and P1a's rule restarts that slot, so no copy is needed (and none
is kept: RAM). An external change while a list shows repaints the rows whose
signature it changes.

**But a changed signature isn't a new target** (codex, round two):
`menu_slots.c` repaints it (`:265`), yet only `new_target()` (`:100`)
advances the target's generation, resets its settlement, supersedes a
pending stop and marks interrupted timing; `note_settled()` (`:189`) ignores
a later settlement while the old one stands; and `menu_tick()` (`menu.c:673`)
notices only power, clock and the title. So **every external hook, with or
without an open edit, sets a pending-change bit** (in an existing flags
byte), and `menu_tick()`, which runs before the pump in every pass of the
menu's normal path (`menu_ops_task()`; the board's housekeeping runs the
repeats, then the menu's task, then the display pump), consumes it with
`ms_retarget()` (which is `new_target()`): after the write (the hook runs
just before it, in the same main-loop step) and before any painting. The
two passes without a tick are harmless: a fixture doesn't tick, and the
return from Diagnostics (`menu_ops.c:128`) installs a fresh layout, target
and clear through `menu_return_from_diag()`. The menu's own previews go
through `menu_input()`, which already retargets. Tests: an external change
after settlement and during a partial slot, with C10's accounting and a
pending stop.

### Signatures for value rows (exact, still 16 bits)

P1a's item signature has four bits of value; a Lighting row needs eight. A
new class in the About space, which uses only bits 8-10 under `0xC000`:
**`0xE000 | which << 10 | variant << 9 | value << 1 | lit`**, keeping the
scheduler's contract that **bit 0 is lit** (`menu_slots.h:41`; the one-lit-
row rule tests it when it cleans, withholds, starts and commits rows,
`menu_slots.c:271`). `which` is the row (Effect, Brightness, Hue,
Saturation, Speed/Second color, Lights, Screen: seven of eight), `variant`
Speed's label against Second color's (from the live effect), `value` the
field's byte (the full level for Screen, the top level's row too). Exact, no
hashing; codex enumerated all 7,168 against the other classes: none alias
(bit 13 is clear in About's).
- **A previewing choice's check** marks the entry snapshot's value, the
  saved one, not the live preview (P1a's `saved_row()`, `menu.c:138`, reads
  the model; for Effect and Lights it reads `edit_t`).

### The editors' layouts (C8's geometry)

New layouts beside `L_LIST` and `L_CONFIRM`; each slot one bounded op a pass
(C3), whole footprint, background included.

| Layout | Slots, in paint order |
|---|---|
| **Range** | the title; the separator; the **bar** as 7 column bands (x 13-114 in bands of 16, the last 6; y 51-60): each band's signature is where the fill's edge falls in it (empty, full, or the column; the outline and the background are fixed, so that is enough), one piece each (≤ 320 B); the **value** (10 big-face cells at x 14, y 22, centred: one slot of 10 chunks, a glyph each, signature the field and its value); the three **hints** (y 72, 86, 100) |
| **Hue** | the title; the separator; the **envelope** (x 0-127, y 20-40) as 16 column bands of 8: each band composes the strip's hue columns (y 22-35), the marker's white line (y 20-37) and its yellow triangle (5, 3, 1 px, y 38-40, so two columns either side of the line) where they fall in it, over the strip and the background it regenerates beneath; its signature is the strip's presence and **the marker's centre relative to the band, -2 through 9 (the triangle reaches in from two columns outside), or "no overlap"**, from the marker's absolute hue; one piece each (336 B); the **value** (y 44, as the range's); the hints |

- **Bands first, then the value:** the bar or marker moves at once and the
  number follows, as the scrollbar leads the rows (JD).
- **What a step costs:** one detent moves the bar's edge or the marker by a
  few columns, typically one to three bands; a coalesced input (several
  detents in a pass, or a fast turn) can repaint every band. The bounds are
  per pass (one piece), not per step.
- **Layouts change through `ms_set_layout()`, both ways** (list to editor,
  editor to list): its clear; `ms_retarget()` alone can't erase the old
  geometry.
- **The big face** is `FONT_STATUS` (10x23, every ASCII glyph,
  `display.c:72-88`), drawn by a new `mb_glyph_big()` beside `mb_glyph()`:
  one DMA from external flash a pass, armed and completed as `mb_glyph`'s.
- **The strip's colours:** `hsv_to_rgb(h, 255, 255)` per column, RGB565; the
  marker at `4 + round(h*120/256)`, Second color's at `(hue + speed) & 255`.
- **A new primitive, `lcd_blit_gen(x, y, w, h, fn, ctx)` in `lcd_bus.c`**
  (which owns the shared scratch), behind a thin `mb_pixels()` in the
  backend: composes w×h RGB565 pixels from `fn(ctx, col, row)` into the
  scratch in the panel's byte order and sends them polled, with
  `lcd_blit_mono`'s acquire, send, release and failure cleanup
  (`lcd_bus.c:228`), at most `MB_PASS_BYTES`. The bands use it; the host
  tests' fake writes the framebuffer. The big glyph uses flash DMA, not the
  scratch.
- **Slots:** range 13, hue 22, within the 24.

### What is deferred, and why

- **Half-row slots** (a row as two slots, so a value-only change repaints
  half): P1b's rows change value only on an external write or an edit's end,
  and their exact signatures repaint them whole (9 pieces). The ticking
  Clock examples need half rows; they come with the Clock options, after
  P1b.
- **Connection, Indicators, Battery:** P2/P3.

### RAM (from the linked builds, codex's point 5)

The heap gaps of `541a8cbd`, every flavour (floor 128 B): **dev 160**,
devfault 200, instrumented 1,312, fpb 2,312 (daily 2,312 at `925f029b`).
Dev binds. P1a and the
icons took 72 B, not P1a's estimated ~30, so the C5 ledger stands at ~384 of
420 B.

| Item | Bytes | Dev gap after |
|---|---|---|
| P1b: `edit_t` (10) and the last turn's time (4) | +16 | ~144 |
| P1b: the piece-timing instrumentation removed (dev and devfault: `mono_t_*`, `mono_send_sum`, `compose_max`, op 27 sub 12) | -14 | ~158 |
| P1c (reserved) | +12 | ~146 |
| P2/P3 (reserved) | +36 | **~110, under the floor** |

- **No latched copy** of the RGB fields or the LCD level (above): 7 B the
  draft spent, not spent.
- **Before P2 the menu needs RAM back.** Best first: the debug page's two
  198 B text buffers shared with the menu (only one owns the panel at a time;
  JD, 10-24: the debug page "isn't going to be visible in normal use"); the
  stacks' measured watermarks (C5 owes them); the Camera page (JD: it can go
  if RAM is needed). Named here, built with P1c or P2, each with its own
  review.
- **Every build checks its own gap** (`build.sh:196-210`); P1b's code
  review reads every flavour's.

### Tests

The host target excludes `menu_glue.c`, VIA, QMK's RGB core and the display
glue (`menu_s0_test.c:9`), so the hooks' real placement is the board's to
prove; the host proves the logic, `menu_edit.c`'s production sequencing
included, against fakes with QMK's semantics.

- **Host:**
  - every row of Lighting and the top level against the face; each editor's
    frames (the bands, the value, the hints) against a reference render,
    including every hue band boundary, the wrap, a reversal and a large
    jump, for Hue and Second color;
  - turn, fast turn, wrap (hue), clamp (ranges); save, cancel by click,
    hold and Back; the rollback at every `panel_owner` transition, the
    values restored **before** the owner changes; the backstop;
  - against a fake RGB core with QMK's early returns while disabled and its
    dirty flags: clean against already-dirty at entry; Save, then another
    edit, then Cancel; the lights off through preview, save and cancel;
    Lights saved both ways; a forced save (VIA's) mid-preview after the
    cancel; the flush hold;
  - the keycode classification (`RM_*` with the flags, `UG_*`, `RGBM_*`,
    `SCR_*`, the magic reset's code) and that no hook fires inside
    `menu_input()`;
  - piece boundaries for both editors with retarget, loss, close and
    reopen, the glyph DMA's completion and a failed polled send;
  - one lit row and one cursor a pass; no pass over `MB_PASS_BYTES`.
- **On the board** (the plan's P1 exit gates, and C10's): every writer that
  can be driven without destroying JD's state, through its real path, with
  an op 27 count of external cancels, and **the order observed, not only the
  count**: a VIA get mid-preview returns the restored value; an increment
  (`Fn`+arrow, its held repeat) lands on the restored value, not the
  preview; a VIA set and a device indication still apply after the cancel;
  a forced VIA save mid-preview persists the restored config across a
  reboot. VIA set, save, get and device indication packets mid-edit (a
  script over raw HID, never enumerating); dev ops 4 and 5 by script;
  `RM_*` keys by JD's `Fn`+arrows and `Fn`+`\` (on gremlin they replace the
  wake rig's remapped key, which is Buzz's); `SCR_*` by `Fn`+`PgUp`/`PgDn`.
  The magic reset, `RM_FLG*`, `UG_*`, and any `RGBM_*` not bound in JD's
  keymap (they'd reset his EEPROM, or no key sends them) rest on the host
  classification and a named inspection, listed in the code review. A Save with RGB disabled,
  and Lights saved; visibility from Screen Off and from level 0; the session
  through Diagnostics; persistence across a reboot after a settled save and
  after a cancel; C10's LED rate, transitions, continuous-input progress and
  final settlement on both editors; every flavour's linked RAM and the
  stacks' worst watermarks; JD's session.
- **The pass limit:** JD's (b) accepts menu painting passes of ~16-17 ms, so
  the board scripts fail a pass over 17 ms and still count those over 15
  (`menu_p1a_board.py:204` does since `51223f9`; `menu_s1_gate.py:435`
  still fails at 15 ms and any pass over it: both assertions move to 17 ms,
  keeping the count, when the gate runs on the editors).

## The bootloader item (JD, 10-24 night)

JD's idea from his first look (`plans/BACKLOG.md`, "A bootloader item"), asked
for overnight. Built on P1b's tree:

- **The top level gains Bootloader**, after Diagnostics as JD's
  `MENU-TEXT.md` places it: Lighting, Screen, Power, Clock, Diagnostics,
  Bootloader, Help, About, Exit. Nine rows: Exit is on page two, the
  scrollbar shows. Its icon is the picker's proposal, nf-oct-desktop_download
  (U+F498, 7 px, two cells), on its row and its heading.
- **It opens a confirm page** (the confirm geometry, as Reset counters):
  "For a firmware" / "update over USB." / "Click: enter" / "Hold: cancel".
  The words wait for JD's text pass (they're in `MENU-TEXT.md`).
- **A click enters the bootloader exactly as `Fn`+`Esc` does** (`ak820pro.c`,
  `QK_BOOT`): `display_bootloader_splash()`, 1.5 s so it can be read, then
  `reset_keyboard()`, QMK's clean reset into the ROM. Never the direct jump
  to `SN32_BOOTLOADER_ADDRESS`, which made flashing unreliable (the comment
  there, 2026-08-31). Through a new `MENU_BOOTLOADER` result and
  `env_bootloader()`; op 27's synthetic click reaches it too, so the board's
  test needs no hands (dev builds only, as op 27 is).
- **Never on battery in its reserve** (`flash.sh`'s rule: a pack that dies
  mid-write leaves the board half-erased): when `power_lights_cut()`, the
  click shows a second page instead, "Plug in first:" / "the battery is low."
  / "Click: back".
- **What a reset loses** is what `Fn`+`Esc` loses: RAM, and a pending
  EEPROM write. No edit can be open on the top level.
- `Fn`+`Esc` stays bound; whether to free it is JD's call (the backlog's
  note).
- **Tests:** the host: the row, the page, the click's result, the refusal on
  reserve, the hold's cancel. The board: entered by op 27 from the menu, the
  board shows `0C45:7140` (`Get-PnpDevice`, never enumerating HID), and
  `flash.sh` brings it back (it takes an already-entered bootloader: the last
  backups, no jump).

## JD's look at P1b (10-25, ~01:30, on `781d071f`)

- "The UI looks excellent to me." A couple of small quirks in how some
  effects behave: "minor and not worth chasing in general".
- **Fine steps:** "we should be able to make micro-adjustments by one
  value/percent - right now it adjusts by a few percent at a time ... we're
  already doing decent acceleration with quick knob turns." Built with P2a:
  a slow detent is the next percentage for Brightness, Saturation and Speed
  (it was 5 of 255, about 2%), one unit for Hue and Second color (it was
  3); a fast turn stays as fast (8%, or 12 hue units). A host test walks
  0-100% and back by single detents.
- **"Same goes for the screen, obviously":** the Screen's 24 levels are the
  backlight's own (`bkl_duty[]`, 48 ticks), one a detent already, ~4%
  apart. Finer needs the backlight dimmed the way P2a dims the indicators
  (a 0-100 perceptual table spread by the sigma-delta), which touches
  `display.c`'s tick, `SCR_UP`/`SCR_DN`, the saved level's encoding, the
  power ladder's caps, the wake hold, and `battery.c`'s draw model
  (`display_backlight_duty()`). Its own design and codex round, next.

## P2a: Indicators, and the Connection stub (JD, 10-25 night)

JD (10-25): "I'd add those as stubs into the menu sooner than later", "we can
have lights adjustable from 1-100 in 1% increments like with the other light
parameters, just 1-10", and "maybe we can land the lock lights before I
review in the morning". So this is the build plan's P2 Indicators, out of
order, plus a stub for P3's Connection. Battery (P4) isn't added yet.

### The tree, added

- **The top level** takes the build plan's order, eleven rows: Lighting,
  Screen, Connection, Power, Indicators, Clock, Diagnostics, Bootloader on
  page one; Help, About, Exit on page two. Icons, from the picker's
  proposals that JD saw: Indicators the sun (U+F185, JD's pick), Connection
  nf-fa-bluetooth (U+F293). Both rows end in ▶. Each icon is also on its
  section's headings.
- **Indicators** is a list: "◀ Back", "Lock lights", "Charging light". Each
  is a value row, the way Lighting's are: the label, and the live level at
  the right ("Off", or "1%" to "100%").
- **Lock lights** and **Charging light** each open a range editor, the
  same geometry as Brightness: the bar, the big value, the three hints.
  The range is 0-100: 0 is Off. A detent is 1, and a fast turn is 8 (the
  existing fast-turn rule; 8, as Lighting's percentages, JD's fine steps). The bar's edge is `14 + level`.
  - **The preview lights the LEDs.** While a Lock lights edit is open, Caps
    and Win lock both show at the previewed level, whatever their state;
    while a Charging light edit is open, the charging LED does. Otherwise a
    preview would show nothing unless Caps happened to be on. This is a
    force bit per group, set when the edit opens and cleared by every
    close.
- **Connection** opens a stub page in the confirm geometry, as Bootloader's
  does. It shows the link frozen when the page opened (About's line, from
  the same snapshot) and how to change it today:
  - on Bluetooth: "Link BT 2 connected" / "Slots: coming soon" /
    "Fn+Q/W/E: a slot" / "Hold one 2 s: pair";
  - off Bluetooth: the link, then "The slider picks" / "BT, 2.4G or cable."
    (the build plan's "Set by the slider").

  A click or a hold goes back. No edit. The words wait for JD's text pass:
  they go in `MENU-TEXT.md`.

### The indicator levels: 0-100, by pulse-density modulation

Today's indicators have ten levels, `ind_duty[] = {0, 1, 2, 3, 5, 8, 12,
18, 28, 48}` ticks of a 48-tick software PWM period on the 20 kHz CT16B3
tick. A 48-tick period has only 49 distinct duties, and a perceptual curve
needs most of its steps at the bottom, where they're under a tick. A longer
period flickers: the comment in `indicators.c` records 128 ticks (146 Hz)
flickering visibly.

- **The levels are spaced perceptually** (not calibrated to the eye): 1% is
  today's level 1 (one tick in 48, 2.1% duty), which keeps today's tested
  minimum brightness (codex: the comment records a dimmer 64-tick floor
  without flicker, so "the dimmest that doesn't flicker" overstated it; JD
  can judge the floor). 100% is full on.
  Between them each step is ×1.04 (48^(1/99)). Today's levels land at 1%,
  19%, 29%, 42%, 54%, 65%, 75%, 86% and 100%. The default is unchanged:
  the lock lights at 1%, the charging light Off.
- **The duty** is a table of 101 `uint16_t` in flash (202 B), in 1/256
  ticks: `duty(0) = 0`; `duty(p) = round(256 × 48^((p - 1) / 99))`, so
  duty(1) is 256 and duty(100) is 12,288 = `IND_FULL` (48 × 256). A host
  test checks that it's strictly increasing, so every step changes the
  light.
- **The tick spreads the duty** (first-order sigma-delta) instead of
  comparing a phase: per group, `acc += duty; if (acc >= IND_FULL) { acc -=
  IND_FULL; on }`. At duty(1) that is one tick in 48, exactly today's level
  1. Above it the on-ticks are spread evenly, so the longest gap between
  pulses never exceeds 48 ticks (417 Hz) at any level from 1%. The phase
  counter goes; `acc` stays below `IND_FULL`, and `acc + duty` stays below
  2 × `IND_FULL` (24,576), so `uint16_t` holds both.
  - Dithering the pulse width per period instead would beat at the bottom
    (1.04 ticks is a 2-tick pulse every 25th period, ~17 Hz). The
    sigma-delta's pulses are all one tick wide there, and only their spacing
    varies.
- **The tick's cost:** a group's accumulator runs only while that LED is
  lit or forced. The pins are written only when their bit changes, one by
  one; today all three are written when any changes. A lit LED costs one
  add, one compare and one store a tick (~15 cycles). The worst switching
  is at 82-83% (codex: 49-51% electrical duty), about 19,800 toggles a second
  a pin; 50% on this curve is only 14% duty. Typical use (Caps off, the
  charging light Off) costs less than today's phase compares. The board
  measures it (Tests).
- **After a restart** (the light sleep's tick stop drives every pin low),
  every pin is written on the first tick: `ind_pins_to_write()` with
  `IND_OUT_UNKNOWN` (codex: comparing against 0xFF skipped a pin already
  meant to be on, Caps at 100%, and left it dark). The tick's whole decision
  is pure and inline in the generated `indicator_levels.h`
  (`ind_tick_out()`, `ind_pins_to_write()`), so the host tests run it.
- **The live state:** `ind_duty_locks` and `ind_duty_chg` (volatile
  `uint16_t`, one aligned store each, so the ISR never sees a torn value);
  the levels for the getters; `ind_force` (bits 0 and 1). The 10 Hz
  `update_leds()` is unchanged. `indicators_any_lit()` counts a forced
  group, so light sleep's bit 3 won't stop the tick under a preview (the
  menu's `DSB_MENU` already blocks sleep).
- **The API** is `indicator_get_level(which)` and `indicator_set_level(which,
  level)`, which clamps to 100 (`IND_LOCKS`, `IND_CHARGING`), and
  `indicator_force(which, on)`. They replace
  `indicator_get/set_brightness()`, which nothing outside `indicators.c`
  calls (`grep`). `INDICATOR_BRIGHTNESS_DEFAULT` (`config.h`) and
  `CHARGING_LED_BRIGHTNESS` keep their names and become percentages (1 and
  0, the same light).

### Persisting: the settings block's version 5

- **`kb_eeconfig` grows from 7 bytes to 9:** byte 7 is `ind_locks_p1`, byte
  8 `ind_charging_p1`. Each is the level plus one (1-101), and 0 means
  unset, so a saved Off is distinct from unset (the build plan's rule).
  Unset, or over 101, means the compile-time default. `EECONFIG_KB_DATA_SIZE`
  becomes 9 and `EECONFIG_KB_DATA_VERSION` 5. A flash erases the emulated
  EEPROM anyway; VIA's region starts two bytes later, and `flash.sh`
  restores the keymap through VIA's commands, not by address.
- **Deviation from the build plan:** its version 5 also carries byte 9, the
  battery view. That waits for P4, with its own version bump, so nothing
  unused is stored now.
- **Applied at boot:** `indicators_load_saved()`, called right after
  `kb_eeconfig_init()` in `keyboard_post_init_kb()`. `pwm_tick_init()` runs
  earlier with the compile-time defaults, and no indicator lights before
  that point.
- **Saved by `kb_eeconfig`'s deferred write** (5 s settle, coalesced). A
  save within 5 s of losing power isn't kept, as for every field there.

### Flash attribution (`flash_stats.c`)

- **The new fields:** `KBF_LOCKS 0x40`, `KBF_CHG 0x80`, `KBF_COUNT 8`.
  `kb_byte_field[]` gains two entries; its `_Static_assert` against
  `EECONFIG_KB_DATA_SIZE` holds it to the layout. Eight fields still fit
  the `uint8_t` masks, so the build plan's widening to 16 bits waits for
  P4's ninth.
- **Page 1 is frozen** at its six counters. **A new page 3** carries
  `kb_field_sessions[6]` and `[7]` as two `u16` at offsets 0 and 2, the
  rest zero. Old firmware answers page 3 as unhandled.
- **`ak820health.py`** reads page 3 through `_txn_page_optional()`, which
  takes the board's unhandled answer to that command and page (byte 0
  `RTC_UNHANDLED`) as "not answered", shown "-"; no answer at all is still
  an error. The diag simulator's EEPROM stub goes to 9 bytes, and its fake
  no longer invents zero-filled pages for an optional one.

### The edit transaction (C6), extended

- **Two fields,** `ME_LOCKS` (8) and `ME_CHG` (9), in a new domain
  `ME_DOM_IND`. The snapshot is the level when the edit opened (`ed.lcd`
  becomes `ed.level`, shared with the Screen's). Preview: the level, live,
  not saved. Save: live, and `kb_eeconfig_set_ind_level()`. Cancel and the
  rollback: the snapshot back. Opening sets the group's force bit; Save and
  the rollback clear it. Those are the only two ways an edit closes, so the
  bit can't outlive the edit. `panel_owner.c`'s close and debug handoff
  already roll back first.
- **External writers:** none exist. Nothing else sets an indicator level:
  no key, no VIA command, no HID op. The domain match in
  `menu_edit_external()` becomes `domain_of(field) == domain`, which
  covers the new domain.
- **Op 27:** sub 14 reports the new fields by their numbers, and bytes
  12-14 the two live levels and the force bits. A new **sub 15** is the
  bench's writer (codex's timing gate): the force bits and both levels,
  live, not saved; it is an external writer of `ME_DOM_IND`, so it cancels
  an open indicator edit first. Op 27 is dev-only. The screen ids are
  `16 + node`, as before.

### Signatures

- **The value rows:** `0xE000 | which << 10 | variant << 9 | value << 1 |
  lit`. `which` is 3 bits and 0-6 are taken. Both indicator rows are
  `which` 7: Lock lights is variant 0, Charging light variant 1. Variant is
  otherwise only Second color's.
- **The Connection page:** the confirm layout's text slots are
  `0x8000 | link << 4 | line`, with the link from the frozen snapshot. Each
  open is a layout change anyway, so its clear repaints every slot.

### RAM

Two bytes in `kb_config`, 4 in `kb_field_sessions`, and about 7 net in
`indicators.c`: the two groups' accumulators (4), the duties replacing the
three levels (+1), the two levels (2), the force bits (1), with the phase
counter gone (-1). The edit's snapshot is reused, and the tables are
`const`. **Linked (`081d7914`): the dev gap is 144 B** (from 152), above
C5's 128 floor; daily 2,280, devfault 192.

### Tests

- **The host:**
  - the top level's eleven rows and its scrollbar;
  - Indicators' list and value rows;
  - each editor: open (force set), a slow and a fast turn, the clamps at 0
    and 100, the bar's edge, "Off" and "N%", Save (saved, force clear),
    Cancel and a hold (restored, force clear), the close mid-edit
    (restored, force clear);
  - Connection's page on BT, 2.4G and USB, and its click and hold;
  - the duty table: strictly increasing, the ends.
  - The sigma-delta, simulated for every level over 2 × `IND_FULL` ticks:
    the on-ticks exactly the table's duty, the longest dark run at most 47
    ticks and the pulse spacing at most 48, level 1 exactly today's;
    `ind_tick_out()`'s groups and force; `ind_pins_to_write()` for every
    output against every last state and after a restart, and a restart
    with Caps at 100% and a retained accumulator.
  - Sub 15 cancelling an open indicator edit, and refusing a level over 100.
- **The settings block and the counters** (`scripts/diag_sim/`, the
  production files compiled verbatim):
  - `kbee.c` runs `kb_eeconfig.c`: stored bytes 0, 1, 2, 51, 101, 102 and
    255 for each field alone, with the other field garbage; a zero-filled
    block (QMK's answer to an older version); the deferred, coalesced write,
    an unchanged save writing nothing, 101 refused, saved Off and 100 read
    back after a reboot;
  - the flash counters: page 3 for each field alone, an unchanged write,
    both together as mixed, the reset; and, with
    `DIAG_SIM_GOLDEN_BASE=781d071f`, pages 0-2 byte-identical to that
    commit's `flash_stats.c` under the old fields' workload;
  - `ak820health.py`'s decoders over those pages, page 3 missing (older
    firmware: its fields None, the rest unchanged), and the optional-page
    transaction against unhandled replies.
- **The board:**
  - the menu pass over the new rows, with both editors and their sub 14
    readbacks (open, the levels restored, the force gone);
  - the timing (codex's gate), `scripts/ind_timing.py`, 10 s runs: the
    main loop's passes a second, the row ISR's rate and CPU share, passes
    over 10 and 25 ms. The old firmware (`781d071f`) idle and with Caps lit
    from the host; the new idle, Caps at 1% from the host, and all three
    LEDs forced at 1%, 82%, 83% and 100% by sub 15; then the menu's board
    pass with all three at 82%, against C10's 17 ms;
  - the flash counters' page 3 counting a save's write.
- **JD:** the levels by eye, and a saved level surviving his power cycle.

## P2b: the Screen in 1% steps (draft 2, 10-25)

JD (10-25): fine steps for the editors, "same goes for the screen,
obviously", and on P2a's flash: "The screen lighting adjustment is still way
too coarse." The Screen's 24 levels are `display.c`'s `bkl_duty[]` (0-48
ticks of the same 20 kHz tick, a 48-tick period), so the menu can't step
finer than the panel. P2a's indicator method carries over: a level 0-100,
perceptually spaced, the duty spread by the sigma-delta.

- **The level becomes 0-100**, with P2a's table (`indicator_levels.h`'s
  `ind_level_duty[]`, the same 48-tick floor): 1% is today's level 1 (one
  tick in 48), 100% full. `bkl_duty[]` goes; `BKL_MAX_LEVEL` and
  `MENU_LCD_MAX` become 100 (`IND_LEVEL_MAX`), and display.c's assert ties
  them. Today's 24 levels map onto it by their ticks,
  `p = round(1 + 99 × ln(ticks) / ln 48)`: the default
  (`DISPLAY_BRIGHTNESS_DEFAULT`, `config.h`), level 5 (5 ticks), becomes 42
  (4.97 ticks).
- **The menu's Screen editor** steps 1, fast 8 (the indicators' rule) and
  shows the level as its percentage, `Off` at 0. The top level's Screen row
  the same.
- **The tick** (`display_backlight_tick()`): its phase compare becomes a
  sigma-delta with its own accumulator, `ind_sd_step(&bkl_acc,
  ind_level_duty[bkl_effective()])`. Full and zero duty are still written
  without stepping; the pin is written every tick, as now. `bkl_phase` goes.
  `display_set_power()`'s immediate write tests the duty `> 0` as now.
- **`SCR_UP`/`SCR_DN`** (`Fn`+`PgUp`/`PgDn`): JD (10-25): "1% per press on
  the keys would be good if we use the same acceleration we do for lights.
  keep the behaviour the same unless it's physically impossible." So a
  press is still one level, now 1%, and a held key keeps the lighting keys'
  repeat (`param_repeat_task()`: 400 ms, then every 60 ms, then every 12 ms
  after 800 ms more), which crosses 0-100 in about 2.2 s.
  `display_brightness_up()`/`down()` are unchanged but for the range.
- **`param_overlay.c`'s readout** keeps its expression,
  `(lvl * 100u + mx / 2u) / mx`, which with `mx` 100 is the level itself
  (`scripts/power_model.py` checks that string).
- **`power.c`'s dim cap**, `SCREEN_DIM_LEVEL`, 4 of 23 (4 ticks), becomes 37
  (4.09 ticks: never dimmer than today's cap).
- **C7's menu override** (`level >= 1`): unchanged; 1 is still the floor.
- **`battery.c`'s draw model stays as it is:** `display_backlight_duty()`
  keeps its type and its 0-48 ticks, rounded from the fine duty,
  `(duty + 128) >> 8` (at most half a tick, 0.4 mW, off), so `battery.c`,
  `scripts/battery_sim/` and `scripts/power_oracle.c` don't change.
- **The RAM battery log's `bkl` byte** (`log_put()`, the effective level)
  becomes the 0-100 level. `ak820battery.py` prints it raw. Two of the
  battery work's tools read the 0-23 scale and must follow at the merge
  (they read pinned commits, so nothing breaks before): `battery_sim`'s
  replay of a log's level through its own `bkl_duty_sim[]`, and
  `power_model.py`, which parses `display.c`'s `bkl_duty` (24 entries). Both
  are the session on Buzz's; noted for the merge, not edited here.
- **`kb_eeconfig`'s saved LCD level:** the validation goes from `<= 32` to
  `<= 101` (`+1` encoding) and `EECONFIG_KB_DATA_VERSION` to 6, so an old
  0-23 value is never read as a percentage (a flash erases it anyway). The
  watchdog test hook's poison (`0x80 | ...`) stays invalid.
- **Dev ops 4 and 5** set and report the level on the new scale (their state
  reply carries the max, now 100). The host scripts that assume 23
  (`menu_p1b_gates.py`'s `lv < 23`) take the max from the reply.
- **The splash's forced maximum** (`display_get_brightness_max()`) is 100.
- **The cost:** the tick already looks its duty up and writes the pin every
  tick; the sigma-delta replaces the phase compare. Measured with P2a's
  timing gate.
- **RAM:** the accumulator (2), less the phase (1).
- **Tests:** the host (the Screen editor's steps and display, the keys' step
  and its ends, the old levels' mapping); the diag simulator (the saved
  level's bytes 0, 1, 2, 43, 101, 102, 255); the board (the menu pass, the
  dev ops, the timing); JD by eye.

## P3: Connection, the Bluetooth slots and pairing (draft 2, 10-25)

JD (10-25): "can we do the BT channel selection now? If it makes sense,
also pairing, unless that deserves to be a separate wave." Both, in one
wave: pairing is the same few calls as `Fn`+`Q`/`W`/`E`'s hold, and one
hands-on session covers both. And on the stub: "you shouldn't even display
this option if you're not in BT mode (or at least we should show a screen
saying 'Switch to BT mode to change Bluetooth settings' or such)". The row
stays, so the top level keeps its shape whatever the slider says, and off
Bluetooth it opens his screen. Draft 2 takes codex's design review
(`plans/review-codex-p3-design-2026-10-25.md`): the select's outcome as a
driver fact, the pair never sent mid-bounce or after a lost select, an
unsure phase, the whole Pairing page on the backstop, and the stand-in cut
off from the radio.

### The tree, changed and added

- **The top level's Connection row** shows the link where its ▶ was:
  `BT 1`, `BT 2`, `BT 3`, `2.4G` or `USB` (as Power's and Clock's rows show
  theirs). Its signature's `val`: 0 USB, 1 2.4G, 2-4 BT 1-3.
- **Off Bluetooth** (the slider on 2.4G or the cable), the row opens
  `N_CONNINFO`, a page in the confirm geometry, title `Connection`:
  `Switch to BT mode to` / `change Bluetooth` / `settings.` and, at the
  bottom, `Click: back`. Its lines sit at y 22, 36, 50 and 86, so the
  sentence isn't split by the confirm pages' gap. Fixed text, so its
  signatures are `0x8000 | line`; the stub's frozen snapshot goes. A click
  or a hold goes back.
- **On Bluetooth**, the row opens `N_CONN`, a list, title `Connection`:
  - `◀ Back`;
  - `Bluetooth 1`, `Bluetooth 2`, `Bluetooth 3` (`N_BT0`-`N_BT2`), laid out
    as options: the label from cell 2, the current slot's check box in cells
    0-1. The current slot also shows its link at the right, in at most six
    cells: `Linked` (connected), `Trying` (linking), `Pair` (advertising),
    `Failed` (rejected), nothing when idle. The menu hides the status band,
    so this is the only feedback a switch gets while the menu is open. The
    word's state is the row signature's `val` (bits 7-4), beside the bullet
    and lit bits, so a change repaints the row.
  - `Pair a device` ▶ (`N_PAIRLIST`), from cell 0, as the mockup draws it.

  The cursor opens on the current slot's row.
- **Choosing a slot** (a click on `Bluetooth n`):
  - another slot, or the current one while it's rejected, advertising, or
    linking on a lost select: the tap's select (saved, as the key saves it),
    and the title flashes `Now on BT n`. On the current slot that's the
    key's retry, and while it advertises, the key's cancel-pairing bounce
    (`ch582_set_profile()`'s `was_pairing`).
  - the current slot while it's connected, or linking on a select that
    isn't lost: nothing is sent, and the title flashes `Already on BT n`.
    Re-selecting a linked slot drops the link, and re-selecting one
    mid-attempt restarts the attempt, which starves a slow macOS reconnect
    (`docs/wireless.md`, the select backstop). A lost select (its eight
    tries ran out unanswered) leaves the state the optimistic `LINKING`
    for good, so "nothing" there would make the slot impossible to retry
    (codex).

  The page stays, unlike Power's choice: the feedback is on it.
- **`Pair a device`** opens a list, title `Pair a device`: `◀ Back`,
  `Bluetooth 1`, `Bluetooth 2`, `Bluetooth 3` (`N_PAIR0`-`N_PAIR2`, from
  cell 0, no check). The cursor opens on row 1.
- **A click on one starts pairing it** and replaces that list's frame with
  `N_PAIRING`, the slot in the frame's `cursor` (the stack is three deep
  at most). Connection's cursor moves to that slot's row, so leaving the
  page lands there, where the row shows how it ended.
- **The Pairing page**, title `Pairing`, in the confirm geometry, its lines
  by phase (the next section):
  - starting: `Bluetooth n` / `Getting ready...` / `Click or hold: stop`;
  - advertising: `On the computer, add` / `AK820 5.1-n` /
    `Click or hold: stop`. The band's exact advertised name
    (`display.c`'s note: the module appends the slot);
  - connected: `Bluetooth n is` / `connected.` / `Click: back`;
  - ended (advertising stopped with no device, or the slot changed):
    `Pairing ended.` / `Click: back`;
  - failed (nothing confirmed or pending, and not advertising): `Pairing
    didn't` / `start. Try again.` / `Click: back`;
  - unsure (the driver's optimistic `PAIRING`, never confirmed, nothing
    being resent: a lost `5B 31` looks the same as a module that never
    started): `The radio didn't` / `confirm pairing.` /
    `Click or hold: stop`.

  Its signatures: `0xA000 | slot << 8 | phase << 4 | line`.
- **A click or a hold** while starting, advertising or unsure stops it
  (below), flashes `Pairing stopped` and goes back. Otherwise it only goes
  back.
- **The screens follow the slider:** if `N_CONN`, `N_PAIRLIST` or
  `N_PAIRING` shows and the link isn't Bluetooth, or `N_CONNINFO` shows and
  it is, the menu goes back to the top level, the cursor on Connection,
  whose value then shows the new link. (Most slider moves reboot the board
  anyway.)
- **While the Pairing page shows, the idle timeout is the 3-minute
  backstop,** as for an open edit: adding a device on a computer can take
  longer than 24 s, and since the idle time dates from the last knob input,
  a page that turned connected after that would otherwise close the moment
  it did (codex). Any close (the timeout, `Fn` and a click, Exit) leaves
  pairing running, and the band takes over (`Pair with:` /
  `AK820 5.1-n`), as after the key's hold. A start still waiting still
  fires.
- **Known gap, shared with the band:** the end of advertising with no
  device isn't observed. The driver ignores `5B 23` (periodic, in every
  state), so a page left advertising says so until something changes; the
  backstop bounds it.
- **New nodes:** `N_CONNINFO` 39, `N_BT0`-`N_BT2` 40-42, `N_PAIRLIST` 43,
  `N_PAIR0`-`N_PAIR2` 44-46, `N_PAIRING` 47; `N_COUNT` 48 (at most 63).
  Titles: `T_PAIRLIST`, `T_PAIRING`, and the flashes `T_NOW_BT1`-`3`,
  `T_ALREADY_BT1`-`3`, `T_PAIR_STOPPED`. The headings carry the Bluetooth
  icon; the flashes, none.

### Starting, stopping, and the phases

The decisions about the radio live in `bt_ui.c`, beside the key's hold,
and the menu only reads facts.

- **The select** is the slot key's press without its hold:
  `bt_ui_slot_key()`'s press body moves into `select_slot()`, which both
  call (save, `ch582_set_profile()`, the host, the logo). The key keeps its
  hold's arm and progress bar.
- **`bt_ui_pair_slot(slot)`**, nothing off Bluetooth:
  - if the slot is current, confirmed advertising (below) and still
    advertising, nothing: it's already pairable (from the key's hold, or
    if the module advertises a slot by itself, which isn't known to happen
    but would otherwise draw a redundant `A6 51` it might not answer);
  - otherwise, the slot is selected unless it's the current one with a
    select that isn't lost, and a pending pair is armed.
- **The pending pair fires** from `bt_pair_hold_task()` (10 Hz), sending
  `ch582_enter_pairing()` once the module has acted on the select (below)
  and the link isn't linking, or 6 s after the arm if it's still linking
  then. That's when the module listens: `A6 51` is dropped mid-attempt
  (`docs/wireless.md`). And a pair sent at once could lose to the slot's
  old host: its `5B 32` clears the pair's retry, and the menu would show a
  connection that's really the old bond.
  - While the select is still being sent (a bounce, or its retries), it
    waits: a bounce's own `5B 32` says connected, and `A6 51` then would
    replace the bounce (`PA_PAIR` supersedes `PA_BOUNCE`) and pair the
    bounce slot (codex's first must-fix).
  - A lost select disarms it unsent: the module may be on another slot.
    The page reads failed.
  - Confirmed advertising when it would fire: disarmed unsent.
  - The current slot while connected fires on the next tick: `A6 51` on a
    live link is the hold's fast case (a phone's reconnect beats 2 s).
  - A menu select, a slot key's press, `Fn`+`P` and every slider event
    disarm it; a pair re-arms after its own select.
- **`bt_ui_pair_stop()`** disarms it. Then, if the link is advertising (its
  state `PAIRING`, optimistic or confirmed) or the driver's pair retry is
  still pending, it selects the current slot, which is the key's cancel
  (the bounce, or a plain select that supersedes the retry).
- **The driver** (`ch582f_ajazz.c`) gains three reads and two flags:
  - `ch582_pair_retrying()`: `pa.kind == PA_PAIR`, a pair sent and not yet
    confirmed;
  - `ch582_pair_confirmed()`: a `5B 31` has arrived, outside a bounce,
    since the last pair request or select. It's set in `5B 31`'s case and
    cleared by `ch582_enter_pairing()`, `ch582_set_profile()` and
    `ch582_cancel_connect()`. The state alone can't say this: `conn_state`
    goes to `PAIRING` optimistically when the pair is sent, and stays there
    if the module never answers and the retry gives up;
  - `ch582_select_state()`: pending (`PA_BOUNCE` or `PA_SELECT`), acked, or
    lost. Acked (`select_acked`) is a `5B 31`, `32`, `33`, `34` or `36`, or
    the 5A promotion, outside a bounce, since `ch582_set_profile()` or
    `ch582_cancel_connect()`, which clear it. Lost is neither pending nor
    acked: the select's eight tries ran out unanswered.
- **The menu's facts** (`menu_env.h`): `env_link()`, the packed link as
  About's (About now builds its byte from it); `env_bt_select(slot)`,
  `env_bt_pair(slot)`, `env_bt_pair_stop()`; `env_bt_pair_facts()`: bit 0
  waiting (`bt_ui`'s pending pair), bit 1 retrying, bit 2 confirmed, bit 3
  the select lost.
- **The menu latches them** with the power mode and the clock
  (`sync_model()`: `model_link`, `model_pf`), each pass and before
  navigation. A change retargets, as Power's does, so rows and pages
  compose from the latch and never read the radio mid-piece. After a
  select or a pair the menu syncs again before it composes.
- **The phase**, a pure function in `menu.c` of the latch and the page's
  slot, in this order:
  1. the link isn't Bluetooth, or not on this slot: ended;
  2. waiting: starting;
  3. confirmed: advertising if the state is `PAIRING`, connected if
     `CONNECTED`, otherwise ended;
  4. retrying: starting;
  5. the state `PAIRING`: unsure;
  6. otherwise: failed.

### Op 27 (dev)

- **Sub 14** gains `[15]` `env_link()` and `[16]` `env_bt_pair_facts()`.
- **A new sub 16, the bench's stand-in:** `[5]` a link byte, or `0xFF` for
  the live one; `[6]` the facts. While set, `env_link()` and
  `env_bt_pair_facts()` return them, and `env_bt_select()`, `env_bt_pair()`
  and `env_bt_pair_stop()` do nothing: the cable doesn't mean the slider is
  on it (codex). MI_BAD for a transport over 2, a slot over 2, a state over
  4, bit 7 set, or facts over 15.
- **`menu_cursor()`** reports `slot << 4 | phase` for the Pairing page.

### RAM

The latch (2), `bt_ui`'s pending pair (a flag and a 16-bit start, 3), the
driver's two flags (2), and in dev the stand-in (2). **Linked: the dev gap
is 136 B** (from 144; the floor is 128), daily 2,264 (from 2,280).

### Tests

- **The host** (`menu_s0_test.c`): the top level's value for each link; the
  off-Bluetooth page, its lines and back; the list's rows, the check and
  the link word for each state, live through the latch; a click on each
  slot in each state (the select or nothing, the flash, the cursor kept);
  the screens following the slider both ways, from each screen; the pair
  list; the Pairing page in each phase from the facts; stop in each phase
  (the stop or none, the flash, back on that slot's row); the backstop on
  every phase, and a close never stopping; the one-lit-row and pass-bytes
  watches throughout.
- **`bt_ui.c` and the driver, both compiled as they are**
  (`scripts/ch582_sim/btui.c`, on the radio harness's world: recorded
  writes, the module ACKing every frame, the case's `5B` frames; codex: the
  sequences need the real driver). Twelve cases: the tap's select, with no
  pair; a pair on the current slot linked, on the next tick, no select;
  another slot: its select, nothing mid-attempt, the pair after `5B 36`, or
  at 6 s, or on the old host's link; the bounce (the bounce slot's `5B 32`,
  then the target's select at 700 ms, then the pair); a lost select (eight
  tries, no pair, then a re-select); every supersession; a lost `5B 31`
  (twelve tries, still `PAIRING`, the stop's bounce); the 5A promotion; the
  stops; already advertising; off Bluetooth, nothing at all. Two mutants
  (the pair while the select is pending; no re-select of a lost select),
  each caught.
- **The board** (the cable, the stand-in): the menu pass over every
  Connection screen and phase, its timing, and the real off-Bluetooth page.
- **JD:** the slider to BT; a slot switch each way; pairing a device on a
  free slot, and a stop.

## P1b, P1c, P1d

P1b's design is the section above (the earlier note asked it to cover the
rows' values changing under a preview, C6's writers, the editors' slots and
pieces, and the Screen's C7 interplay: all there, half rows deferred with a
reason). Each of P1c and P1d gets its own detailed section and codex round
before its code. P1d's: the bunny as 8-bit grey (1,134 B, amending "Generated
files"' 2,268 B RGB565), expanded by a new `lcd_bus.c` primitive beside
`lcd_blit_mono` with its failure cleanup; image pieces and the credits'
text pieces as separate ops; the QR code's module image (106 B) unpacked and
scaled 3x into a 26 B stack bitmap per 2-row piece, 50 pieces split into
several logical ops (so op latency stays measurable), and the URL frozen
as `https://github.com/jdlien/ak820-pro`.
