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

## P1b: Lighting, Screen and the edit transaction (draft 2, 10-24 night)

The mockup's previewing half of the menu, on P1a's machinery. Everything not
said here is P1a's (the slot rules, the one-lit-row rule, the session
identity, the latched model, the hint and the flash, the icons). **Draft 2
answers codex's first round**
([`review-codex-p1b-design-2026-10-24.md`](review-codex-p1b-design-2026-10-24.md)):
the writers it missed, the lit bit, the rollback's place, the hue bands'
overlap, the RAM, the tests.

### The tree, added

The top level becomes the mockup's page one less what is P2/P3's: **Lighting,
Screen, Power, Clock, Diagnostics, Help, About, Exit** (eight rows: one page,
no scrollbar). Connection, Indicators and Battery join with P2/P3.

| Node | Kind | Rows / layout | Value on its parent's row |
|---|---|---|---|
| Lighting | list | ◀ Back, Effect, Brightness, Hue, Saturation, Second color *or* Speed, Lights | ▶ |
| Screen | range editor, 0-23, step 1 | the range layout | `Off`, else `round(level*100/23)%` |
| Effect | previewing choice | ◀ Back, the nine effects (two pages, the scrollbar) | the effect's readout name |
| Brightness, Saturation, Speed | range editor, 0-255, step 5 (×4 fast) | the range layout | `(v*100+127)/255 %` (the readout's rounding) |
| Hue, Second color | hue editor, 0-255 wrapping, step 3 (×4 fast: 12) | the hue layout | `h*360/256` degrees; Second color `+` that of `speed` |
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
  detents and `now`; the last turn's time is new state (2 B, 16-bit ms,
  compared as a signed difference).
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
- **The RGB adapter** (`menu_glue.c`, behind `menu_env.h`):
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
    equals the value (the dirty flag is the point). Mode is set only when it
    changes, so an HSV or speed preview doesn't restart the effect.
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
  saved values. (A rollback at shutdown would also undo the bootloader
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
devfault 200, instrumented 1,312, daily and fpb 2,312. Dev binds. P1a and the
icons took 72 B, not P1a's estimated ~30, so the C5 ledger stands at ~384 of
420 B.

| Item | Bytes | Dev gap after |
|---|---|---|
| P1b: `edit_t` (10) and the last turn's time (2), padded | +16 | ~144 |
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
prove; the host proves the logic.

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
  an op 27 count of external cancels: VIA set, save, get and device
  indication packets mid-edit (a script over raw HID, never enumerating);
  `RM_*` keys by JD's `Fn`+arrows and `Fn`+`\` (on gremlin they replace the
  wake rig's remapped key, which is Buzz's); `SCR_*` by `Fn`+`PgUp`/`PgDn`.
  The magic reset and `RM_FLG*` (they'd reset JD's EEPROM, or aren't bound)
  rest on the host classification and inspection. A Save with RGB disabled,
  and Lights saved; visibility from Screen Off and from level 0; the session
  through Diagnostics; persistence across a reboot after a settled save and
  after a cancel; C10's LED rate, transitions, continuous-input progress and
  final settlement on both editors; every flavour's linked RAM and the
  stacks' worst watermarks; JD's session.
- **The pass limit:** JD's (b) accepts menu painting passes of ~16-17 ms, so
  the board scripts fail a pass over 17 ms and still count those over 15
  (`menu_p1a_board.py:202` fails at 15 today).

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
