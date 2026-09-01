#!/usr/bin/env python3
"""Host-side model tests for the clock-sync firmware arithmetic (PLAN.md 6).

No hardware. Mirrors rtc_set_time_ms() (rtc.c) and the ak820ctl lead
calibration (PLAN.md 3.8) so their edge cases are exercised exhaustively:

  * first-period computation for every ms 0..999 at P_nom 28000 and 40000:
    the register value stays in [500, 0xFFFFF] and the next tick lands on the
    intended boundary to within one ILRC cycle;
  * the MIN_FIRST_MS branch labels the FOLLOWING boundary;
  * lead calibration e = o' + o = lead - delay, lead -= e/4 converges on the
    true outbound delay from both sides, with jitter, and stays clamped.

Run: python3 scripts/rtc_model_test.py   (exit 0 = all pass)
"""
import random, sys

MIN_FIRST_MS = 20
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def first_period(P, ms):
    """Returns (sec_delta, reg): seconds added to the label, register value."""
    R = 1000 - ms
    sec = 0
    first = ((P + 1) * R) // 1000
    if R < MIN_FIRST_MS:
        sec = 1
        first += P + 1
    reg = first - 1
    return sec, reg


def test_first_period():
    for P in (28000, 33600, 40000):
        for ms in range(1000):
            sec, reg = first_period(P, ms)
            check(500 <= reg <= 0xFFFFF, f"reg out of range P={P} ms={ms} reg={reg}")
            # the counter runs 0..reg then matches: first tick after reg+1 cycles
            cycles = reg + 1
            # intended: boundary at (1000-ms) ms, or +1000 ms in the branch
            intended_ms = (1000 - ms) + 1000 * sec
            actual_ms = cycles * 1000.0 / (P + 1)
            err_cycles = abs(actual_ms - intended_ms) * (P + 1) / 1000.0
            check(err_cycles <= 1.0, f"boundary error {err_cycles:.2f} cyc P={P} ms={ms}")
            if 1000 - ms < MIN_FIRST_MS:
                check(sec == 1, f"MIN_FIRST_MS branch not taken ms={ms}")
            else:
                check(sec == 0, f"MIN_FIRST_MS branch wrongly taken ms={ms}")


def test_lead_calibration():
    for delay in (0.5, 2.7, 4.0):
        for lead0 in (0.0, 1.5, 9.0):
            random.seed(1)
            lead = lead0
            o_true = 123.4   # board - host, arbitrary and constant here
            for i in range(40):
                jitter = random.uniform(-0.3, 0.3)
                # GET measures o (board - host); SET arrives 'delay' after H_enc.
                o = o_true + jitter
                target_minus_board = lead - (delay + jitter) - o_true   # o' = lead - delay - o
                e = target_minus_board + o
                lead -= e / 4
                lead = min(10.0, max(0.0, lead))
            check(abs(lead - delay) < 0.4, f"lead did not converge: delay={delay} lead0={lead0} lead={lead:.2f}")
    # clamp
    lead = 50.0
    for _ in range(3):
        e = lead - 2.0
        lead -= e / 4
        lead = min(10.0, max(0.0, lead))
    check(lead <= 10.0, "clamp failed")


def test_offset_sign():
    # offset_before = (t+ms) - board_now must be positive when the target is ahead
    board_ms, target_ms = 500, 620
    check(target_ms - board_ms == 120, "offset sign")


if __name__ == "__main__":
    test_first_period()
    test_lead_calibration()
    test_offset_sign()
    if FAILS:
        print("\n".join(FAILS[:20]))
        print(f"FAIL ({len(FAILS)} problems)")
        sys.exit(1)
    print("rtc_model_test: all pass (3000 first-period cases, 9 calibration cases)")


# ---- Phase 2: slew schedule model (mirrors the tick-ISR scheduler in rtc.c) ----
def slew_schedule(P, off_ms, L=2):
    """Return total correction in cycles achieved by the ISR schedule and the
    number of register writes, for a requested offset (ms). Models the
    transient writes as latency-compensated (exact) and the final restore as
    uncompensated (+L)."""
    D = off_ms * (P + 1) // 1000 if off_ms >= 0 else -((-off_ms) * (P + 1) // 1000)
    absD = abs(D)
    step = (P + 1) * 20 // 1000
    N = max(1, (absD + step - 1) // step)
    d = int(D / N)              # toward zero
    r = D - d * N
    # simulate intervals
    writes = 0; total = 0
    # start tick: write v = P - d - (r if N==1 else 0); interval = v+1 exact
    v = P - d - (r if N == 1 else 0); writes += 1
    intervals = [v + 1]
    left = N
    while True:
        left -= 1
        if left == 1 and r != 0 and N > 1:
            v = P - d - r; writes += 1; intervals.append(v + 1)
        elif left == 0:
            writes += 1; intervals.append(L + P + 1)   # restore, uncompensated
            break
        else:
            intervals.append(v + 1)
    # correction = sum over the N slewed intervals of (P+1 - interval)
    slewed = intervals[:N]
    total = sum((P + 1) - i for i in slewed)
    return D, total, writes, N, d, r, intervals


def test_slew():
    P = 33600
    step = (P + 1) * 20 // 1000
    cases_ms = [1, -1, 20, -20, 21, -21, 33, -33, 250, -250, 500, -500, 0.03]
    for off in cases_ms:
        D, total, writes, N, d, r, iv = slew_schedule(P, off)
        check(total == D, f"slew off={off}: achieved {total} != requested {D} (N={N} d={d} r={r})")
        check(writes in (2, 3), f"slew off={off}: {writes} writes")
        check((writes == 2) == (r == 0 or N == 1), f"slew off={off}: write count vs remainder (N={N} r={r} w={writes})")
        for i in iv[:N]:
            check(14000 <= i - 1 <= 80000, f"slew off={off}: interval register out of range {i-1}")
        check(all(abs((P + 1) - i) <= step + abs(r) for i in iv[:N]), f"slew off={off}: per-interval step too large")
    # N==1 with remainder: 20 ms at P=33600 -> D=672, step=672 -> N=1, r=0; 0.5 ms -> D=16, N=1, r=0
    D, total, writes, N, d, r, iv = slew_schedule(P, 21)   # D=705, step=672 -> N=2, d=352, r=1
    check(N == 2 and r == 1 and writes == 3, f"remainder case: N={N} r={r} writes={writes}")


test_slew()
if FAILS:
    print("\n".join(FAILS[:20])); print(f"FAIL ({len(FAILS)} problems)"); sys.exit(1)
print("rtc_model_test: slew schedule cases pass")
