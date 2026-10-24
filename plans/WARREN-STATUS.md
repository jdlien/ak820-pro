# Warren's status: the configuration menu (resume here)

Warren is gremlin's session (the Windows test PC). It owns the configuration
menu's build: [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md)
(revision 15). Results: [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md) §10-17.
This file is the thread; read it first after a context loss. Updated
2026-10-24 ~16:00.

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
- **The encoder fix, `cbcf93b6`, ON THE KEYBOARD ON GREMLIN NOW** (dev, token
  `0xde3d5c12`, gap 248 B; daily `via-daily-cbcf93b6-20261024-153641.bin`
  builds, gap 2,360): a weak hook, `encoder_map_delay_wanted_kb()`, skips
  the waits for halves the menu swallowed (`menu/menu_glue.c`). Codex
  cleared it (`review-codex-s1-encoder-2026-10-24.md`); its finding 3 (the
  knob is polled once a pass, so no backlog forms) removed the bounded
  drain I'd added. **Waiting on:** JD's spin on it
  (`spin-cbcf93b6.json`, the recorder `scratchpad/spinwatch.py`, stop file
  `spinstop`). quantum/encoder.c is now a seventh core file with a local
  change: CLAUDE.md's list needs it at the merge.
- **The mono text, `3f0275ca`, built, not flashed; codex reviewing**
  (`review-prompt-s1-mono.txt`):
  - `lcd_blit_mono` (C4) through the stream; the face
    `graphics/res/font_small_mono.h` from `scripts/gen_mono_font.py` (the
    shipped atlas, checked against the BDF; five extras checked against the
    mockup); `menu/menu_text.c` composes a band of a line;
  - the fixture's **F3** (screen 3): C8's list in text, op 27 sub 0
    patterns 16-19 = lit/half, lit/full, inverted/half, inverted/full. A
    click on rows 0-5 cycles the style; row 6 goes to F2, row 7 to
    Diagnostics. The title names the style.
  - Host tests: `test_mono` (every style, the selection, every piece
    boundary with a retarget and a give-up); `ms1 frames DIR` writes
    `fixture-F3-<style>.ppm`.
- **Next:**
  1. JD's spin on `cbcf93b6` -> GREMLIN-RESULTS §18.
  2. Codex's mono review, dispositions, flash.
  3. With JD by eye (one action a message): open the fixture, I set
     pattern 16, JD clicks through the four styles and spins: the cursor
     style ("Open" 1) and half or full rows ("Open" 2, also measured: sub
     10's piece and op maxima per style).
  4. Extend `menu_s1_gate.py` / `menu_s0_ledrate.py` to F3's patterns.
  5. Then P1, the real menu, and its keycode (plan "Open" 3).
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
