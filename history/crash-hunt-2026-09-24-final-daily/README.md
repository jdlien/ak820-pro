# Ten-hour hunt on the campaign's final daily build (2026-09-23 18:56 → 2026-09-24 04:57)

`scripts/crash_hunt.py --hours 10 --pause-agent` against
`via-daily-44e7314e65-20260923-185609.bin`, token `0xa887132e`. It carries v7
and every fix of 2026-09-23:

- the fault record's lost write;
- the SPI0 lost completion (ChibiOS `c57623d0d2`);
- the serial and USB lock nesting (ChibiOS `a3fdffe26d`, `c212e20dd2`);
- the CH582F TX pump order.

It ran under the same stress as the
[2026-09-22 hunt that ran v7](../crash-hunt-2026-09-23-v7/). The owner was on
another keyboard.

## Result

**Ten hours, no reset, no blit timeout of any kind.**

| | v7 daily, 2026-09-22 | this build |
|---|---|---|
| blits | 1,960,093 | 1,964,044 |
| blit timeouts (never started, stalled, IRQ lost, unknown) | 53 | **0** |
| busy-waits (the overlap guard) | 7 | **0** |
| non-flash stalls ≥ 25 ms | 8 | **0** |
| stalls ≥ 25 ms marked flash | — | 28, worst 43 ms (inside the 60 ms budget) |
| worst row gap | 12 ms | 12 ms |
| deepest stack use: interrupt / main | 464 / 680 of 1024 / 2048 | 464 / 720 |

The run sent 162,388 text pushes, 16,797 playback flips, 1,800 effect
changes, 1,200 keymap flips and 1,200 synchronous RGB saves. Keymap, encoders
and lighting matched the backup at exit.

The agent had been booted out before the run for fault testing. The hunt
restores only an agent it paused itself, so it was restored by hand at 04:57.
It resynced the clock and wrote a health row with this build's token.

`deps.lock` moved to firmware `44e7314e65` on the strength of this run.

## Files

- `hunt.csv`: all 1,201 readings, 30 s apart.
- `events.log`, `run.json`: the run's log and arguments.
