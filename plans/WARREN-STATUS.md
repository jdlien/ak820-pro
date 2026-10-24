# Warren's status: the configuration menu (resume here)

Warren is gremlin's session (the Windows test PC). It owns the configuration
menu's build: [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md) (now
revision 14). Results: [`GREMLIN-RESULTS.md`](GREMLIN-RESULTS.md) §10-14. This
file is the thread; read it first after a context loss. Updated 2026-10-24
~13:40.

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
  - **Latest built:** `9902ff5b`, `via-dev-9902ff5b-20261024-133753.bin`,
    token `0x2a2e20e9`, heap gap 256 B (devfault 152 B, floor 128). It has
    codex's clearance from its review of `4773c826`, plus that review's two
    fixes. **Not yet flashed.**
  - **On the keyboard on gremlin now:** `b245bd84` (dev).
- **Now on the keyboard on gremlin: `9902ff5b`.** Its gate run (§15) passed
  every timing check it reached, but aborted when Fn+D entry took over
  1,000 ms (755-940 ms in the seven repeats before). **Next: revision 15.**
  `lcd_blit_flash()` sends its window with `lcd_window_polled()` BEFORE
  `blit_done = false` and `spiSN32FlashDmaPrepare()` (SPI0 still plain 8-bit
  FIFO then), so every DMA arm sheds ~1.8 ms of byte-at-a-time `spiSend`.
  **Built as `7c157834`** (`via-dev-7c157834-20261024-134754.bin`, token
  `0x3158f628`, heap gap 256 B; devfault 152). Then: codex (the DMA arm has a crash history: `docs/hardware.md`, the
  2026-09-22/23 campaign), host tests, build, flash, rerun the gate.
- **The gate procedure (each run):**
  1. flash the build (`./flash.sh` in MSYS2);
  2. `venv-win/Scripts/python.exe scripts/devhook.py reset < /dev/null`;
  3. `venv-win/Scripts/python.exe scripts/menu_s1_gate.py --out
     history/config-menu-s1-20261024/gate-9902ff5b.json < /dev/null`;
  4. record the result as GREMLIN-RESULTS §15.

  The last run (`b245bd84`) failed only on timing: 2 passes over 15 ms, the
  longest 17.5 ms. Everything else in C10 passed.
- **If the gate still fails on timing:**
  - read `scripts/devhook.py read` (each stage's worst) and
    `scripts/menu_s1_acct_transitions.py` (HC_ACCT's worst passes per
    transition);
  - the remaining levers are a cheaper polled payload loop, and splitting
    the Health page's composition.
- **After the gate passes:** S1 proper.
  - `lcd_blit_mono` and the generated font, as op 27 sub 0 mono patterns on
    the fixture.
  - With JD by eye: the cursor style (lit text or inverted) and half or full
    rows.
  - Real encoder spins and backlog measurement, with a bounded drain in
    `quantum/encoder.c` if the 15 ms target fails.
  - Then P1, the real menu, and the menu keycode in P1 (plan "Open" 3).

## What S1 has done so far (all codex-reviewed before each flash)

- **The LED flicker fix:** colour fills held off the RGB row ISR (-18%).
  Bulk SPI0 sends are polled with SPI0's IE cleared (`spi0_poll_send`); since
  revision 14 their window is polled too (`lcd_window_polled`). The DMA arm
  keeps its spiSend window. The row ISR now keeps ~99.4-100% of its rate
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
    send or the payload. **The failure tests with it are still to run.**
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
