# The title garble's split: protocol and how to read it

The firmware: `lcd-diag` `1bc39c8281` (never merged), a daily build,
`ak820pro-builds/out/via-daily-1bc39c8281-20261109-172920.bin`, token
`0x6d970a9b`. Codex's review and verify:
[`review-codex-lcd-diag-split-raw.md`](review-codex-lcd-diag-split-raw.md),
[`review-codex-lcd-diag-split-verify-raw.md`](review-codex-lcd-diag-split-verify-raw.md)
(the firmware passes; the reading rules below are the verify's P2). The
switch is `scripts/lcd_diag.py` (`read`, `zero`, a mode, `n N`, `div D`).

## Why a split

On 11-09, in one build on white, the old send (`4790208267`'s) garbled the song
title over Bluetooth and fix A's did not. In A's mode none of A's checks ever
fired (strays, late and give-ups 0 over 534 windows; every window began idle).
So, as far as the counters show, A differed from the old send only in time:
a few STAT reads before the first byte and after the last. Each split mode is
the old send plus one part of A:

| Mode | What it adds to the old send |
|---|---|
| `old` | nothing: `4790208267`'s send, the same instructions as `5688b2a975`'s |
| `dly-after` | N discarded STAT reads after the BUSY wait (time alone, exit side) |
| `dly-before` | N discarded STAT reads before the first byte (time alone, entry side) |
| `exit` | A's exit: three idle STAT reads in a row, and `exit_extra` |
| `entry` | A's entry: TX empty required, the RX drain |
| `acct` | A's accounting: own entries only, bounded, every byte answered |
| `a` | fix A, every boot's default |

A delay read costs about 7 cycles, so the delay is 7N - 2 cycles plus about
8 of setup (N = 0 still adds about 8). These are nominal estimates, not
measured SN32 cycles: wait states and interrupts are not counted. N = 10, the
default, is about 76-80 cycles, over A's extra exit time in mode 2 (about
+61) and its extra prefix (about +54); against full A's whole exit (about +83),
sweep above 10.

## Keeping white awake

Power saver sleeps white after 3 min with no key. Track changes on the Mac are
not keys. A deep sleep's wake clears the title, and a change sent while white
sleeps is lost. For the session: `Fn`+`B` to Always on (from Power saver,
twice: Lights out, then Always on), and back to Power saver at the end (twice
from Always on).

## The order

One mode switch per message (a ~3 s data-line window: daemon out, data on,
read, zero, switch, data off, daemon back). JD changes track on the Mac at
their own pace and reports only "garble at change k" or "clean x8". A garble
is any artifact in the artist and title lines, or a title that never paints.
Each mode stops at its first garble.

1. `old`, up to 10 changes. It must garble: this re-establishes the fault on
   this build. If clean x10, stop; the build changed something.
2. `dly-after` (N 10), up to 8.
3. `dly-before` (N 10), up to 8. If the baseline needed more than 3 changes
   to garble, use 12 instead of 8 for every mode.
4. Then by the result:
   - after clean, before garbles: exit side. Run `exit`, then sweep after's N
     down (4, 1, 0) to bracket it.
   - before clean, after garbles: entry side. Run `entry`, then sweep
     before's N down.
   - both clean: either side's time is enough. Sweep both.
   - neither clean: not time alone, within ~80 cycles. Run `exit`, `entry`,
     `acct`.
5. `old` again, up to 10. It must still garble.
6. `a`, for daily use.

At each switch the counters are read first and saved under
`history/lcd-speckle-20261109/`, then zeroed.

## How to read it (codex's verify, P2)

- Record each mode's result as a bracket (clean after k changes, or garbled
  at change k) and the N values tried, with the cycle figures labelled
  estimates.
- **N = 0 curing, a result that does not move one way with N, or overlapping
  margins are inconclusive.** Old garbling and `dly-after` at N 0 clean
  cannot rule out mode 4's incidental cycles.
- **A logic mode clean beyond both delay controls supports that compiled
  variant, not its check's meaning.** The variants differ by a few incidental
  cycles outside their named part (the first review's table):
  - every variant feeds TX one instruction per byte faster than `old`;
  - `entry` adds about 4 cycles between XS's completion and DC low;
  - `exit` samples STAT before counting `rx`, where `old` counts first, which
    can change how RX entries drain within an iteration;
  - after RAMWR, `exit` and `dly-after` take 2 more cycles than `old` before
    DC high, `entry`, `dly-before` and `acct` 3 more;
  - `old`'s window is shorter than `5688b2a975`'s at CASET (DC to the call:
    8 to 0) and after RAMWR (9 to 3); the XS-to-RASET sequence is the same.
  A clean `entry` with strays and give-ups 0 is no evidence that draining or
  refusing anything mattered. A mechanism needs a matched control or a bus
  capture.
- The SCK divider (`div`) is for a later capture: see SCK's rate on the
  analyser before relying on it, and re-establish old's garble at the slow
  rate before using a capture to explain the 24 MHz fault.
