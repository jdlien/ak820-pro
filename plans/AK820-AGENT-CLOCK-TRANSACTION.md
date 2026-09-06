# The clock transaction — what `ak820ctl clock` actually does

Status: **REFERENCE, written 2026-09-05.** Transcribed from
`time-util-ak820pro/ak820ctl.c` (pinned at `7f92889f`) after the Codex review
pointed out that [AK820-AGENT-CLOCK-PARITY.md](AK820-AGENT-CLOCK-PARITY.md) documented
only the Python scheduler and omitted the component that actually delivers the
precision.

**The oracle is Python *plus* this C utility, not Python alone.** A Rust port
could reproduce every bias decision in the parity doc perfectly and still inject
several milliseconds — or much more — on every SET, because all of the
arithmetic below lives here.

Protocol constants: `RTC_CHANNEL 0x10`, `RTC_GET_TIME 0x02`,
`RTC_SET_TIME_MS 0x03`, `RTC_PROTO_VERSION 2`.

## The capability cache

`$HOME/.ak820ctl-cap`, one line: `proto lead_ms [b_ppm]`.

| | |
|---|---|
| Defaults when absent/short | `proto 0`, `lead_ms 1.5`, no bias |
| `fscanf` returns < 2 | reset to `proto 0`, `lead_ms 1.5` |
| `has_bias` | true only when all **three** fields parsed |
| `lead_ms` outside `0..10` | reset to **1.5** |
| `b_ppm` outside `-600..600` | `has_bias` cleared (value kept but unused) |
| Written back | `%d %.3f %d` with bias, `%d %.3f` without |

⚠️ Lead is persisted to **three decimals**; bias as an integer. A port that
keeps more precision in memory must still round-trip identically through this
file while `ak820ctl` remains installed, or the two will disagree.

## GET reply layout

| Byte | Meaning |
|---|---|
| `[3]` | clock-set flag; `0` means unset |
| `[4] [5] [6]` | year−2000, month, day |
| `[7]` | weekday |
| `[8] [9] [10]` | hour, minute, second |
| `[11]` | protocol version |
| `[12..15]` | `SECCNT`, u32 LE |
| `[16..17]` | active period, u16 LE |
| `[18..19]` | nominal period, u16 LE (`0` → use active) |
| `[20]` bit 1 | slewing |

### ⚠️ The fraction formula is not the obvious one

```
frac = 1.0 - ((active + 1) - cnt) / (nominal + 1)
```

It is the cycles *remaining* to the next boundary, measured in **nominal**
seconds. In steady state (active == nominal) that reduces to `cnt/(P+1)`, but
inside the **shortened first period after a phase set** it is still correct,
where the naive `cnt/(active+1)` reads the fraction of the remaining window
instead. That mistake produced an "after" residual **growing to −790 ms across
ten syncs**. Port this expression literally.

`board_sod = hour*3600 + min*60 + sec + frac`, and day wrap is
`if d > 43200: d -= 86400; if d < -43200: d += 86400`.

## ⚠️ Before porting any of this: `xfer()` cannot tell whose reply it got

Measured 2026-09-05. Windows delivers HID input reports to **every** open
handle, and a process holding one received this whole transaction — five
`RTC_GET_TIME`, the `RTC_SET_TIME_MS`, the verify GET, the status read —
without having written a single clock command.

`xfer()` returns the first report that arrives. For a *text* echo that fails
safe by accident, because `rep[11]` lands a bogus protocol version and the
version check refuses to act. **For a clock reply it does not fail at all**: a
foreign `RTC_GET_TIME` reply has the right channel, the right command, protocol
version 2 and entirely plausible fields. It is accepted, and the arithmetic
below then pairs *another process's* board sample with *this* process's `t0`
and `t1`.

The result is not an error. It is a wrong `off` with a plausible `rtt`, which
may well win the min-RTT selection precisely *because* it did not include our
own round trip — and it flows straight into the lead learner and the cache.

Correlation does not fix this and cannot; two processes issuing the same
command produce interchangeable replies. **The only fix at this layer is that
exactly one process performs clock transactions at a time.** A port that keeps
the arithmetic below perfect and drops that property is not a correct port.

## One GET

```
t0 = now
xfer(GET)
t1 = now
rtt = (t1 - t0) * 1000
off = wrap_day(board_sod - host_sod((t0 + t1) / 2)) * 1000     # board - host
```

NTP arithmetic with `T3 == T2`: the host timestamp is the **midpoint** of the
transaction, not either end. `host_sod` is **local** seconds-of-day, fractional,
via `localtime` — so DST and timezone come from the host, and midnight wrap is
handled by `wrap_day`, not by date arithmetic.

## The measurement: five GETs, keep the minimum RTT

- Five iterations. `-1` (no reply) aborts the whole command.
- `proto != 2` breaks out immediately.
- `-2` (clock unset) **continues** — it is still fine to set.
- `rep[20] & 0x02` on **any** sample sets `was_slewing`, which disqualifies the
  lead calibration: a slew moves the board 20 ms/s and is not a calibration
  sample.
- Keep the sample with the **lowest RTT** as `best_off`.
- `U = (rtt_max - rtt_min) / 2 + 0.5`, or `0` if no good sample.

`proto == 0` → legacy whole-second set, and the cache is written with
`proto 0`. Any other unknown version → **refuse to act**.

## The SET

`target = t_enc + lead_ms/1000`, where `t_enc` is read **immediately before**
building the packet. Fifteen bytes:

```
[0]=0x07 SET_VALUE  [1]=0x10 RTC  [2]=0x03 SET_TIME_MS
[3]=year-2000 [4]=month [5]=day [6]=weekday
[7]=hour [8]=min [9]=sec
[10..11]=ms u16 LE (clamped to 999)
[12]=flags (0)
[13..14]=sof_bias s16 LE, or 0x7FFF when the bias is unknown
```

⚠️ `0x7FFF` is the **unknown-bias sentinel**, not a zero bias. Sending `0`
would tell the firmware the SOF reference is perfect.

Reply: `[3]` status, `[4..5]` `o'` as **s16 LE**.

| Status | Meaning |
|---|---|
| `0` | applied as a step |
| `1` | applied as a **slew** — this is what prints `(slewing)` |
| `0xFE` | busy / stale read — **retry the whole SET once**, then fail |
| `0xFF` | firmware rejected validation — fail |

⚠️ The Python learner keys on the literal string `(slewing)` in stdout, which
is emitted **only when status == 1**. That coupling is invisible from the Python
side and must survive the port.

## The outbound-lead learner

Separate from, and in addition to, the SOF-bias learner in the parity doc.

```
gate: good && !was_slewing && st != 0 && -500 < best_off < 500
e    = o_prime + best_off              # = lead - delay
adj  = clamp(-e / 4.0, -1.0, +1.0)     # at most 1 ms per update
lead = clamp(lead + adj, 0.0, 10.0)
```

- Gain **¼**, converging on the true one-way delay.
- The `±500 ms` gate exists because a step — e.g. just after a flash, while the
  clock still drifts ~10 ms/s — **blew the lead to its clamp once**.
- `st != 0` means the lead is learned only from a *slewed* correction.

The cache is then written with `proto = 2` **regardless of whether the lead
moved**.

## Verify, and the reported line

One more GET, then:

```
clock set (sub-second): before %+.1f ms, after %+.1f ms, rtt %.1f ms,
U ~%.1f ms, lead now %.2f ms, bias {sent|unknown}{ (slewing)}
```

A warning is appended when `rc == 0 && good && st == 0` and
`|after| > 3U + 3`.

⚠️ Two couplings the Python side depends on, both invisible from Python:

- `before` is the **min-RTT** sample, printed to **one decimal**. Python parses
  that string and compares it against `FAST_ABOVE_MS` (60) and
  `LEARN_MAX_BEFORE` (400). A merged Rust daemon has the full-precision value
  and **will decide differently near those boundaries** unless it rounds first.
  Decide deliberately; do not let it happen by accident.
- The `warning:` substring suppresses `slewing` in Python's parse
  (`slewing = "(slewing)" in out and "warning:" not in out`).

## What the port must prove

Fixtures, not live hardware, for all of this:

1. `board_sod` against captured GET replies including a shortened active period
   — the −790 ms bug reproduced and then fixed.
2. `wrap_day` either side of midnight.
3. Min-RTT selection and `U` from five synthetic samples.
4. SET packet bytes for a known `t_enc`/lead, including `ms` clamping, the
   `0x7FFF` sentinel, and a negative bias.
5. Lead learner: sign, the ¼ gain, the ±1 ms adjustment clamp, the 0–10 clamp,
   and each gate rejecting (slewing, `st == 0`, `|best_off| ≥ 500`).
6. `0xFE` retried exactly once; `0xFF` fails without retry.
7. Cache round-trip: short file, out-of-range lead, out-of-range bias, absent
   file, and the two write forms.
8. The reported line reproduced byte for byte, because Python parses it.

## Port status (2026-09-06): proven, and where

All eight, over the fake wire (`hid::exchange::fake`), a scripted host clock
(`clock::host::FakeHost`) and an in-memory cache (`clock::cache::MemCache`).
The fixtures are the **pinned C's own output**, produced by
`scripts/clock_oracle.c` — the functions above copied verbatim and compiled
with the mingw64 gcc that builds `ak820ctl.exe` — rather than a reading of the
C.

| # | Proven by |
|---|---|
| 1 | `clock::tests::inside_a_shortened_period_the_naive_fraction_would_be_wrong`; and `read_lines_match_the_c_for_captured_replies` — three real replies rendered identically by the C and the port |
| 2 | `clock::tests::midnight_wraps_both_ways`, `the_wrap_boundary_is_exactly_half_a_day` |
| 3 | `clock::tests::the_lowest_round_trip_wins`, `uncertainty_is_half_the_spread_plus_a_half`, `any_slewing_sample_flags_the_whole_burst`; end to end in `transaction::tests::a_clean_transaction_end_to_end` (rtts 4, 6, 2, 5, 7 → the third, `U = 3.0`) |
| 4 | `clock::set::tests::the_packet_for_a_known_target` (all fifteen bytes), `milliseconds_are_little_endian_and_clamped`, `an_unknown_bias_is_the_sentinel_not_zero`, `a_negative_bias_is_twos_complement_little_endian` |
| 5 | `clock::lead::tests`, one test per gate and per clamp |
| 6 | `transaction::tests::a_stale_read_retries_the_set_once_with_a_fresh_timestamp` (the retry carries a **new** `t_enc`), `a_stale_read_twice_fails_without_a_third_attempt`, `a_rejected_set_is_not_retried` |
| 7 | `clock::cache::tests::parse_matches_the_c_on_every_oracle_row` and `resaving_what_was_loaded_matches_the_c_byte_for_byte` — forty inputs through the real `fscanf`; plus `the_lead_prints_like_printf_percent_point_3f` for the ties |
| 8 | `transaction::tests::the_line_matches_one_the_oracle_actually_logged` (a line from the timekeeper's log), `the_formats_round_like_printf` (the CRT's `%+.1f` / `%.2f` on the boundary values), `python_sees_the_rounded_before_not_the_measured_one` |

The two couplings called out above are types, not comments:
`Outcome::as_reported()` derives `before` and `slewing` **from the printed
text** by Python's own rules — regex for one, the two substring tests for the
other — so a scheduler port cannot accidentally decide on the full-precision
value.

### ⚠️ `xfer()` did it, and the log shows it

The hazard described under "Before porting any of this" has an instance in the
oracle's own log. On 2026-09-05 at 23:20:34 the timekeeper recorded

```
warning: residual +2365966.0 ms exceeds 3U -- lead still calibrating, or a slew is in progress
```

`+2365966.0 ms = (86400 − 84034.034) × 1000`: a board seconds-of-day of
exactly zero against a host at 23:20:34.034. A SET reply has every time field
zeroed, so decoded **as a GET** it reads as a set clock at 00:00:00 with
`cnt = per = pnom = 0` — seconds-of-day zero, exactly. So: the SET's `xfer()`
took a foreign report (a now-playing echo with `0` at `[3]`, read as "stepped",
`o' = 0`), and the verify GET took the board's **real SET reply** — same
channel, command byte unchecked. Nothing was learned only because `st == 0`
closed the lead gate, and Python saw `slewing = False` only because the
warning fired. `scripts/clock_oracle.c decode` reproduces the number from those
bytes; `transaction::tests::the_oracles_2365966_ms_line_reproduced` pins what
the port does with the same traffic (drains the echo, takes both real replies)
and why the oracle printed what it did.

### Where the port deliberately differs

| The C | The port | Why |
|---|---|---|
| a `nan` lead passes both range checks (NaN compares false), is used as `t_enc + nan/1000`, and is written back as `nan` | reset to 1.5, like `inf` | the C's path is undefined behaviour at `(time_t)` |
| `%lf` reads hexadecimal floats | the scan stops at the `x` | no writer of the file emits one |
| a `0xFF` unhandled echo of our own SET: `st = rep[3]` read off the echoed request | the transaction aborts | unreachable on matching firmware; recorded so nobody restores it as parity |
| `cap_save` before the verify GET | after it | unobservable; the outcome carries the saved value |
| `%d` reads `12.5` as `12` | same as the C | ⚠️ the *Python* oracle's `int("12.5")` raises here, so the two oracles already disagree; the file's owner wins |

Kept although an improvement is obvious: the round trip is a **wall-clock**
difference (`now_s()` twice), so a wall-clock step during a GET produces the
same nonsense in both. A monotonic RTT is a change to land after parity is
proven, not before.

### Not ported

The legacy whole-second set (`cmd_clock_legacy`), taken when the board reports
protocol version 0. The port reproduces the C's side effect — the cache is
written with `proto 0` — and then declines with `Error::LegacyFirmware`.
`ak820ctl clock` still performs it, and no firmware in this tree reports
version 0.
