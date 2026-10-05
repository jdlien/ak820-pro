#!/usr/bin/env python3
"""The charging model's tail, checked over B1's parameter grid (plan B, revision 6).

From the knee the model approaches an asymptote A, M = A - (A - L_KNEE) e^(-t/tau),
starting at K_CC (A - L_KNEE = K_CC tau) and reaching 990 exactly T_TAIL after the
knee. This script solves tau and A at every grid point, reports feasibility, and
measures what the firmware's table costs: nodes every 60 s in 1/16 pm, linear
interpolation, the output rounded to whole pm (half up, as the C does:
(x16 + 8) / 16). It also checks the integer start-above-the-knee entry, in X16
units. Every integer second of every tail is checked, not a sample (codex,
round 6). Run it with no arguments; it prints the worst cases (~10 s).
"""
import itertools
import math

K_RANGE = range(160, 235, 5)          # pm/h
TKNEE = [3.9, 4.0, 4.1, 4.25]         # h, plug-in to the VDD rise
R_RANGE = [0, 30, 60]                 # pm, the reserve refilled below 0%
TTAIL = [5.0, 5.2, 5.35, 5.5, 5.6]    # h, knee to termination
NODE_S = 60
FRAC = 16                             # node resolution: 1/16 pm


def solve(k, lk, t_h):
    """tau (h) with k tau (1 - e^(-t/tau)) = 990 - lk; None if infeasible."""
    need = 990.0 - lk
    if not 0.0 < need < k * t_h:
        return None
    lo, hi = 1e-9, 1e9
    for _ in range(400):
        mid = math.sqrt(lo * hi)
        if k * mid * (-math.expm1(-t_h / mid)) < need:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def table(k, lk, t_h):
    ts = round(t_h * 3600 / NODE_S) * NODE_S          # T_TAIL rounded to the minute
    tau = solve(k, lk, ts / 3600)
    a = lk + k * tau
    curve = lambda s: a - (a - lk) * math.exp(-(s / 3600) / tau)
    n = ts // NODE_S
    nodes = [round(curve(i * NODE_S) * FRAC) for i in range(n + 1)]
    nodes[-1] = 990 * FRAC                               # exactly 990
    return tau, a, ts, curve, nodes


def m_fw(nodes, s):
    """The firmware's M at tail-clock second s, in 1/16 pm (index saturates)."""
    i = min(s // NODE_S, len(nodes) - 1)
    if i == len(nodes) - 1:
        return nodes[-1]
    f = s - i * NODE_S
    return nodes[i] + (nodes[i + 1] - nodes[i]) * f // NODE_S


def show_pm(x16):
    """Whole pm for display, half up, exactly as the firmware rounds."""
    return (x16 + 8) // 16


def enter(nodes, l0):
    """First tail-clock second whose M >= l0 (pm): node search, then integer solve."""
    target = l0 * FRAC
    for i in range(len(nodes) - 1):
        if nodes[i + 1] >= target:
            if nodes[i] >= target:
                return i * NODE_S
            d = nodes[i + 1] - nodes[i]
            return i * NODE_S + -(-(target - nodes[i]) * NODE_S // d)   # ceil
    return (len(nodes) - 1) * NODE_S


def main():
    worst_interp = worst_out = worst_entry = worst_rate = 0.0
    where = {}
    infeasible = n = 0
    max_nodes = 0
    for k, tk, r, t_h in itertools.product(K_RANGE, TKNEE, R_RANGE, TTAIL):
        lk = k * tk - r
        n += 1
        if solve(k, lk, round(t_h * 60) / 60) is None:
            infeasible += 1
            continue
        tau, a, ts, curve, nodes = table(k, lk, t_h)
        max_nodes = max(max_nodes, len(nodes))
        fw = [m_fw(nodes, s) for s in range(ts + 3601)]      # X16, every second
        for s in range(ts + 1):
            exact = curve(s)
            e1 = abs(fw[s] / FRAC - exact)
            e2 = abs(show_pm(fw[s]) - exact)
            if e1 > worst_interp:
                worst_interp, where['interp'] = e1, (k, tk, r, t_h, s)
            if e2 > worst_out:
                worst_out, where['out'] = e2, (k, tk, r, t_h, s)
        # firmware 1-hour rise from every start second, against K_CC (pm/h)
        for s in range(ts + 1):
            rise = (fw[s + 3600] - fw[s]) / FRAC
            if rise - k > worst_rate:
                worst_rate, where['rate'] = rise - k, (k, tk, r, t_h, s)
        # past T_TAIL the index saturates: exactly 990, no read past the table
        assert fw[ts] == fw[ts + 3600] == 990 * FRAC, (k, tk, r, t_h)
        # integer entry above the knee, in X16: the FIRST second at or above L0
        for l0 in range(int(math.ceil(lk)), 990):
            s = enter(nodes, l0)
            assert fw[s] >= l0 * FRAC, (k, tk, r, t_h, l0)
            assert s == 0 or fw[s - 1] < l0 * FRAC, (k, tk, r, t_h, l0)
            over = (fw[s] - l0 * FRAC) / FRAC
            if over > worst_entry:
                worst_entry, where['entry'] = over, (k, tk, r, t_h, l0)
    print(f"grid points {n}, infeasible {infeasible}, max table length {max_nodes}")
    print(f"interpolated 1/16-pm table vs curve: worst {worst_interp:.6f} pm at {where.get('interp')}")
    print(f"  ... shown in whole pm, half up: worst {worst_out:.6f} pm at {where.get('out')}")
    print(f"firmware 1 h rise above K_CC, every start second: worst +{worst_rate:.6f} pm at {where.get('rate')}")
    print(f"entry above the knee (X16, first crossing): overshoot at most {worst_entry:.6f} pm at {where.get('entry')}")
    print("index saturation past T_TAIL: exactly 990 at every grid point")
    k, tk, r, t_h = 160, 4.1, 30, 5.35
    tau, a, ts, _, _ = table(k, k * tk - r, t_h)
    print(f"round 3's set: L_KNEE {k*tk-r:.1f}, tau {tau:.5f} h, A {a:.3f}, "
          f"end rate {(a-990)/tau:.3f} pm/h (T_TAIL rounded to {ts/3600:.4f} h)")


if __name__ == "__main__":
    main()
