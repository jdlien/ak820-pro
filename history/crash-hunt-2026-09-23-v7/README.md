# Second crash hunt — the fix held (2026-09-22 23:00 → 2026-09-23 09:00)

`scripts/crash_hunt.py --hours 10 --pause-agent` against the v7 daily
firmware with the hang fix: `via-daily-1b7f781887-20260922-225845.bin`,
build token `0xebb930f8`. Same stress as the
[first hunt](../crash-hunt-2026-09-22/), whose v6 firmware hung 13 minutes in.
Plan and analysis: [`plans/CRASH-HUNT-PLAN.md`](../../plans/CRASH-HUNT-PLAN.md).

## Result

**Ten hours, no reset.** 1,960,093 blits; 161,965 text pushes, 16,797
playback flips, 1,800 effect changes, 1,200 keymap flips and 1,200
synchronous RGB saves. Keymap, encoders and lighting matched the pre-run
backup at exit; the agent was restored.

| page-6 counter | start | end |
|---|---|---|
| `blit_busy_waits` | 0 | **7** |
| `blit_never_started` | 1 | 53 |
| `blit_retry_successes` | 1 | 53 |
| `blit_stalled`, `blit_irq_lost`, `blit_unknown` | 0 | 0 |

- **Every busy-wait (7 of 7) fell in the same 30 s window as a never-started
  blit.** That is the predicted mechanism: a transfer the pump armed never
  started, a synchronous draw arrived inside the pump's 50 ms grace, and
  `bus_quiesce()` waited it out -- where v6 ran `Prepare()` under it and hung.
  Seven in ten hours is about one per 86 minutes; the v6 hang at 13 minutes
  was early, not implausible.
- **Every blit timeout was a transfer that never started** (53), and every
  retry succeeded. None stalled partway, lost its interrupt, or was
  unclassifiable.
- **Eight non-flash stalls ≥ 25 ms, all 25–26 ms, all in a never-started
  window** (five also with a busy-wait): the recovery's millisecond or two on
  top of synchronous draws that sit at 21–24 ms under this stress.
- Worst loop gap 43 ms, marked flash: wear-levelling consolidations the hunt
  drives on purpose, inside the 60 ms budget. Worst row gap 12 ms.
- Deepest stack use, paint watermark: interrupt stack 464 of 1024 bytes, main
  thread 680 of 2048.

## What it means

The fix closes the hang the first hunt provoked, and the counters show the
overlap it guards against happening -- always alongside a DMA that never
started. That DMA-never-starts quirk (about 5 per hour under this stress) is
now the root of both the hang and the only stalls left, and the next thing to
understand.

## Files

- `hunt.csv` -- all 1,201 readings, 30 s apart (the `v_` columns are page 6).
- `events.log`, `console-tail.log` -- the run's log and summary.
- `run.json` -- arguments and the stressed values' originals.
