# Warren's status: the configuration menu (resume here)

Warren is gremlin's session (the Windows test PC). It owns the configuration
menu's build: [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)
(revision 15). Results: [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md) §10-17.
This file is the thread; read it first after a context loss. Updated
2026-10-24 ~16:40.

## Where things stand

- **S0 is complete.** A1-A13 passed on the keyboard on gremlin, with recorded
  exceptions (GREMLIN-RESULTS §10). Firmware branch `gremlin/config-menu`
  (`4b899118`).
  - **Not merged, by agreement with the session on Buzz** (the Mac; its
    session's bridge is listed as "Relay control and power monitoring
    status"). The keyboard on Buzz is mid-drain on `b9555ff3e6` until its RGB
    cut, ~10-31 to 11-02. Then:
    1. a daily build runs on the keyboard on gremlin (needs JD's Fn+Esc to
       get back to dev);
    2. one flash of S0 plus the LED fix goes onto the keyboard on Buzz;
    3. then the merges into `ak820pro-jdlien`, `deps.lock` and main.

    Don't touch `ak820pro-jdlien`, `deps.lock` or main before then.
- **S1 is in progress** on firmware branch `gremlin/s1` (qmk_firmware), on top
  of `gremlin/fill-poll` (the LED fix) on top of `gremlin/config-menu`. The
  chibios-contrib submodule is pinned at branch `gremlin/s1-fifo-ie`
  (`5a1674e905`, the FIFO dispatch respecting IE).
- **The S1 gate PASSES on `a8b98bc0`** (GREMLIN-RESULTS §16): the longest
  pass 13.8 ms, every LED window 0.998-1.000, every completion inside
  1,000 ms. **The failure paths pass, 24 of 24** (§17, devfault).
- **JD's real spin on `a8b98bc0`** (`history/config-menu-s1-20261024/spin-a8b98bc0.json`):
  6 passes over 15 ms, the worst 15.6, nothing dropped, none >= 25. The
  synthetic gate can't see this: op 27's turns bypass `quantum/encoder.c`,
  whose drain waits ENCODER_MAP_KEY_DELAY (1 ms) after each half of every
  detent, captured or not.
- **The encoder fix, `cbcf93b6`** (in every later build): a weak hook,
  `encoder_map_delay_wanted_kb()`, skips `quantum/encoder.c`'s 1 ms waits
  for detents the menu swallowed (`menu/menu_glue.c`). Codex cleared it
  (`review-codex-s1-encoder-2026-10-24.md`); its finding 3 (the knob is
  polled once a pass, so no backlog forms) removed the bounded drain I'd
  added. quantum/encoder.c is now a seventh core file with a local change:
  CLAUDE.md's list needs it at the merge.
- **The mono text, dev `cbb51ac1`** (token
  `0xc10209a3`, gap 240 B). `lcd_blit_mono` through the stream (a halfword
  a pixel), the face `graphics/res/font_small_mono.h` from
  `scripts/gen_mono_font.py`, `menu/menu_text.c` (a cell at a time), and
  the fixture's **F3** (op 27 sub 0 patterns 16-19: lit/half, lit/full,
  inverted/half, inverted/full; a click on rows 0-5 cycles; row 6 F2, row 7
  Diagnostics). Codex: `review-codex-s1-mono-2026-10-24.md` (three rounds).
  GREMLIN-RESULTS §19, §19b:
  - every style keeps every pass under 15 ms (13.1-14.5); a mono piece
    5.1-5.4 ms; a move ~165 ms; failure paths 36 of 36 on devfault;
  - **JD settled: lit text** (plan "Open" 1); **half rows** by efficiency
    ("Open" 2); the face is tiny, kept for now (BACKLOG: a larger face).
- **ON THE KEYBOARD ON GREMLIN NOW: dev `ffa80947`** (token `0x73928d54`,
  gap 232 B): the mono text above plus the dashboard's text slot staged,
  one heavy step a main-loop pass (codex twice,
  `review-codex-s1-textslot-2026-10-24.md`). A track change between two
  lines and one made the gate's 19.6-20.3 ms passes (§19c); now the slot's
  worst is 4.0 ms. **The gate PASSES** (§19d): the longest pass 14.8 ms.
  **JD checked real track changes on the panel: "titles looked clean"**
- **Scripts made today:** `menu_s1_spin.py STOP OUT [--style N]` (arms the
  opener; sub 10 from the menu's opening; the ring for passes over 15 ms),
  `menu_s1_styles.py` (each style's cost, no hands), `menu_s1_dashwatch.py`,
  and `menu_s1_fault.py`'s 12 mono cases.
- ⚠️ **With JD looking at the panel:** put the screen up and LEAVE it
  there (a held session; switch only when asked). An automated demo that
  moves on by itself frustrated JD (10-24).
- **P1a, the real menu, ON THE KEYBOARD ON GREMLIN NOW: dev `5527c898`**
  (token `0x69ff475f`, gap 192 B). Fn+knob opens it in every flavour.
  Design: `CONFIG-MENU-P1-DESIGN.md` draft 3.1 (codex three rounds); code:
  codex two rounds (`review-codex-p1a-code-2026-10-24.md`). Host tests: the
  S0 suite plus `test_menu`, `test_menu_stress`, and a `-DMENU_ENABLE`
  build's `test_menu_enable`. On the board (GREMLIN-RESULTS §20,
  `scripts/menu_p1a_board.py`): every screen right in 9 runs; **timing
  misses C10 marginally** (one pass of 15.1-16.8 ms in about two runs of
  three): a text piece is ~5.6 ms. Since then (all in GREMLIN-RESULTS
  §20-20c and the design doc's "JD's first look" and "JD's decisions"):
  JD's first look ("flawless, as designed"), his tweaks (`22312b44`,
  `62bb64f9`: the scrollbar first, #FF9A9A for Back and Exit, the dot's
  space), the piece's time measured (§20b; JD chose (b), ~16-17 ms
  accepted), the hint pair and the `report_kind` fix (`1e84bf17`, on the
  board from ~20:00, dev token `0xd0254b00`).
- **Icons (10-24 evening):** the icon picker
  (https://claude.ai/artifact/CQcZf9LUWnyvUQyMaCa8PM, made by
  `scripts/gen_icon_gallery.py`); JD's picks built in `925f029b` (dev token
  `0x58ddeb40`): the wrench, ◀ ▶, the circled check, the cursor in x 0-2,
  top-level icons. After JD's look ("looking quite good"): **`541a8cbd` ON
  THE KEYBOARD ON GREMLIN NOW** (dev token `0xbe41a355`, flashed at JD's
  word before codex finished; codex then: no must-fix): the squared check,
  each section's icon on its headings, the cursor in its own grey
  (`MENU_CURSOR` #A5A2A5, its own chunk). The selected row's yellow stays
  (white, #FFF7C6, #FFFF00 tried live). Design doc: "JD's icons".
  Scratchpad helpers: `setcolor.py NAME RRGGBB` (op 27 sub 13, live).
- 📌 **PINNED, JD (10-24): a manual review of ALL the menu's text before P1
  is accepted** -- Help's topics (`gen_menu_text.py`, its one amendment "3
  min mid-edit" approved), the labels, values, titles, flashes, the hint,
  About's lines, Reset counters' pages. JD will edit them himself.
  **JD is editing `plans/MENU-TEXT.md` now (uncommitted, his): don't touch
  it.** When he's done: carry his edits into the code in one batch, and
  bring the file's glyphs up to date (◀ ▶, the check, the icons; it still
  shows ‹ > •). One of his lines is cut off: "JD: I wonder if we can".
- **Next:**
  1. P1b: designed (draft 3, codex three rounds, cleared) and **built**:
     `feeb9aa3` (groundwork) and `8cb713e3` (P1b) on gremlin/s1; host
     tests pass (`test_p1b`, both builds); dev heap gap 152 B. Codex's code
     review is running (`plans/review-prompt-p1b-code.txt`). Then the
     flash, `menu_p1a_board.py` (its P1b pass), the plan's P1 exit gates
     (VIA packets mid-edit by script, JD's Fn keys, Save with RGB off,
     visibility from Screen Off, persistence across a reboot), JD's
     session. Sub 14 reads the edit (open, field, value, saved, external
     cancels).
  2. The Clock options (the design doc's "JD's decisions"), with half-row
     slots for the live examples.
  3. JD's text edits; then P1c and P1d.
- **The gate procedure (each run):**
  1. flash the build (`./flash.sh` in MSYS2);
  2. `venv-win/Scripts/python.exe scripts/devhook.py reset < /dev/null`;
  3. `venv-win/Scripts/python.exe scripts/menu_s1_gate.py --out
     history/config-menu-s1-20261024/gate-<build>.json < /dev/null`;
  4. record the result in GREMLIN-RESULTS.

## What S1 has done so far (all codex-reviewed before each flash)

- **The LED flicker fix:** colour fills held off the RGB row ISR (-18%).
  Bulk SPI0 sends are polled with SPI0's IE cleared (`spi0_poll_send`); since
  revision 14 their window is polled too (`lcd_window_polled`), and since
  revision 15 the DMA arm's. The row ISR now keeps ~99.4-100% of its rate
  during menu activity. JD by eye: "no flicker", "feels responsive, not
  instant".
- **`MB_PASS_BYTES` (512):** a slot's op is sent in pieces, one a pass.
  - `end_op()` counts an op and latches a reached stop together. That closed
    a real S0 race: navigation could cancel a just-reached stop.
  - A failed piece ends its op.
  - Revision 13: a PARTIAL slot resumes while its own signature is
    unchanged. Revision 8's "same generation" starved spins. An op cut by a
    retarget is counted when it ends, untimed, and a glyph in flight is kept.
- **C10's instrumentation:** op 27 sub 10, read by `scripts/menu_s1_gate.py`:
  - **timing:** piece, op and repaint latency, the longest pass in an armed
    interval, the count over 15 ms, the clear bands;
  - **targets:** `tgen`, settled, superseded, committed;
  - **the debug page:** its generations, `dbg_sec`, the RTC's second, and
    `debug_done` (sub 5 byte 31);
  - **the session:** a boot-cleared token and the health-reset generation,
    with byte 31 flagging an aliased interval;
  - **where it lives:** `menu/menu_meas.c` holds the extended tick and the
    pass timing, which `menu_pass_begin()` takes first in the pass. DMA ends
    are timed at CS release (`lcd_blit_end_tick16`).
- **Dashboard timing fixes found by the gate (affect every build):**
  - after the restore's clear, the text lines' and clock's shadows are marked
    blank (`shadow_mark_all_blank`); the text slot stage went from 16 ms to
    0.5;
  - the restore's battery outline is one edge a pass, and the connection row
    and clock come in two passes;
  - the debug page composes only the page showing;
  - the pump yields in a pass where the debug page composed, and the 10 Hz
    composition defers in a pass where the pump painted.
- **The entry check and hardening:**
  - `spi0_poll_send` refuses unless DMA is idle, `SPID0` is READY, BUSY is
    clear and RX is empty;
  - HC_POLLFAULT (0x75, devfault) takes `n, mode, skip` to fault a window
    send or the payload; `scripts/menu_s1_fault.py` runs the 24 cases.
- **Findings recorded for later:**
  - the Fn timing miss inside a tap-hold's tapping term, settled as
    documented (plan "Open" 5);
  - the "100%" ghost on gremlin's LCD (BACKLOG);
  - the housekeeping text slot can reach 16 ms on a track change: a
    dashboard path, not yet staged.

## Working rules (from JD and the handoff)

- **Codex before every flash.** `codex exec -m gpt-6-astra -c
  model_reasoning_effort=xhigh -s read-only -C <repo> -o <out> "$(cat
  prompt)" < /dev/null`. Save each review verbatim with dispositions as
  `plans/review-codex-*.md`, and keep its prompt as `plans/review-prompt-*`.
- **Flash only the keyboard on gremlin.** JD has given a standing go. Never
  flash or touch the keyboard on Buzz. Name the keyboards "the keyboard on
  gremlin" and "the keyboard on Buzz": both are JD's.
- **One hands-on action per message to JD.**
- **Never enumerate HID.** Never use `python -` (stdin); write scripts to
  files and run them with `< /dev/null`. Use the Edit tool for C with `\n`:
  heredocs collapse the backslashes.
- **Builds:** MSYS2 for build and flash
  (`/c/msys64/msys2_shell.cmd -mingw64 -defterm -no-start -here -c "..."`).
  Git Bash for git. Never `find /`.
- **Host tests:** `gcc -std=c11 -Wall -Wextra -DMENU_HOST_TEST -I $D/menu
  scripts/menu_s0_test.c $D/menu/{panel_owner,menu_input,menu_slots,
  menu_fixture,menu_ops}.c`, with mingw64's gcc first on `PATH`.
- **Scrub family words before pushing.** Push freely; tags and releases need
  JD.
