# One pass of 10 ms or more every second (read 14:56 10-22, `36afff30e8`)

JD's `Fn`+`D` page showed `stall>10` climbing by about one a second (79,897 and counting). One read over the data alone answered it: port 2 on from 14:56:38 to 14:58:02, relay 2 off throughout, so the untethered drain was not broken.

**The counters** (`health-1456.json`, `--stalls`), at 23.0 h of uptime:
- `count_ge_10ms` was 80,024 across 15.7 M passes. At 23:14 10-21 the daemon's status file had 24,202, so that is ~1.0 a second of wall time.
- `count_ge_25ms` was 6, all of them non-flash, the same 6 as at 23:14 10-21: none overnight or today.
- `loop_gap_max_ms` was 29 (`blit`), with 35,047 key presses.

**What each slow pass was** (HC_ACCT's ring, the last 16; ms per scope):
- **The once-a-second one:** `ch582 1, blit_pump 2, second_edge 3, unaccounted 4`, a 10 ms pass at the same point in each second (x.5 s of uptime). That is the clock's second edge:
  - `display_second_edge_task`, then `display_housekeeping_task`'s 1 Hz `draw_clock` and `draw_battery`;
  - the blit pump moving a glyph in the same pass;
  - QMK's core outside the scopes.
- **The others:** `ch582 1-3, battery 1-3, display_hk 1, unaccounted 4-6`, at irregular times.

Every pass in the ring was 10-13 ms. As on 10-20
([`../uart-latency-20261020/`](../uart-latency-20261020/README.md), "ge10"),
these are passes built by stacking, landing just over the threshold.

**Shares of the slow passes' time:**

| Scope | Share |
|---|---|
| unaccounted | 45.0% |
| second_edge | 15.6% |
| ch582 | 12.5% |
| blit_pump | 10.2% |
| battery | 8.6% |
| display_hk | 5.1% |

**What it means:** `count_ge_10ms` is a latency count. A key isn't lost in a 10 ms pass: the row ISR samples the matrix whatever the main loop is doing, and 25 ms is the line for loss. At worst, a press landing in that pass goes out a few ms later, about 1% of the time.

**The rate against earlier builds:**

| Build | Rate | Conditions |
|---|---|---|
| `b2a07e0d37` | 0.18 a second | 6.4 h overnight on USB, 10-20 |
| `7ae8575c1a` | 0.49 a second | 20 min of sleep cycles |
| `36afff30e8` | ~1.0 a second | now |

With a pass sitting right at 10 ms, a fraction of a millisecond decides how many cross the line. The counter now ticks at the clock's cadence, which drowns the signal it exists for.

The fix is in `plans/BACKLOG.md`: keep the pump off the second edge's pass.

**Why the rate rose: the same pass, a slower loop.** The comparison is
against `../uart-latency-20261020/stalls-0742-before-bt.json`
(`b2a07e0d37`, 6.4 h overnight, 2.4G, on USB):
- **The pass is old.** The clock has shown seconds since the first firmware
  (`DISPLAY_CLOCK_SHOW_SECONDS`). On 10-20 the same pass was already in the
  ring: `second_edge 2, blit_pump 2, unaccounted 3-5`, at 10-11 ms.
- **The loop is slower:** 189.5 passes a second against 210.0, or 5.28 ms a
  pass on average against 4.76.

| Scope | 10-20 | Now |
|---|---|---|
| `ch582` | 980 us a pass | 1213 us a pass |
| unaccounted | 3349 us a pass | 3593 us a pass |
| `battery` | 43 us a pass | 63 us a pass |
| `display_hk` | 31 us a pass | 45 us a pass |

- **The rest held within a few us a pass.**
- **The row ISR is unchanged** (`isr-on-battery.txt`, 15:06 10-22): 3775 a
  second, 194 us mean, 73.3% of the CPU, against 3876, 188 us and 72.8% on
  09-03.
- **Not pinned:** the conditions differ (BT against 2.4G, the pack against
  USB, the build), so the extra ~0.5 ms a pass isn't pinned on any one of
  them.
- **Not the power-mode bulb:** `draw_bolt_slot` repaints only when the mode,
  the charger or the pack's presence changes.

**The stacks** (`health-crash.txt`, paint watermarks):
- **interrupt:** 568 of 1024 bytes free, 456 used (464 on 09-23);
- **main:** 968 of 2048 bytes free, 1080 used (680 on 09-23).

**Not chased: uptime runs behind the wall clock.** The uptime read 82,987 s, against ~88,500 s of wall time since the 14:22 flash. The reset flags were 0x01, and the daemon's log shows no reset, since the board never left USB. So the ms count runs ~6% behind the wall.

**The same day, the data cut works:** 11:40-13:10 asleep at 3.1 mA (the logger).
