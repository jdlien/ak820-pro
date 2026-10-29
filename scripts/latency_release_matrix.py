#!/usr/bin/env python3
"""The UART-latency build's release matrix, the parts that need no hands
(plans/UART-LATENCY-PLAN.md, the handoff's step 6):

    venv/bin/python scripts/latency_release_matrix.py stuck [--n 20] [--json OUT]
    venv/bin/python scripts/latency_release_matrix.py restore [--n 20] [--json OUT]

`stuck`: op 23 sub 5, one ordinary PCF read with SCL held low by injection,
into its real 10 ms deadline and the driver's restart; --n times, 2 s apart.
Each must fail (the bus is stuck), take no more than ~12 ms whole, and leave
no pass >= 25 ms; afterwards five ordinary reads (a burst) must all succeed.

`restore`: --n cycles of two Fn+D taps (op 1: the debug page, back to the
dashboard), 1.5 s apart, so the staged restore runs --n times, the path the
animation's stop and the boot redraw now share. No pass >= 25 ms; the longest
blit is reported. (Three taps until the camera page was removed on 10-28.)
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deep_sleep as ds  # noqa: E402
import overrun_diag as od  # noqa: E402
import ak820health as health  # noqa: E402


def stalls():
    s = ds.with_dev(health.read_stalls)
    return {k: s.get(k) for k in ("count_ge_25ms", "count_ge_10ms", "passes", "blit_gap_max_ms", "i2c_gap_max_ms",
                                  "loop_gap_max_ms")}


def stuck(a, checks):
    runs = []
    for i in range(a.n):
        s0 = stalls()
        ds.with_dev(lambda h: od.burst(h, 5))
        for _ in range(50):
            b = ds.with_dev(lambda h: od.op(h, 23, [0]))
            if not b[16]:
                break
            time.sleep(0.1)
        else:
            raise SystemExit("the stuck test never ran")
        s1 = stalls()
        r = {"ok": bool(b[17]), "ms": int.from_bytes(b[18:22], "little"),
             "ge25": s1["count_ge_25ms"] - s0["count_ge_25ms"], "ge10": s1["count_ge_10ms"] - s0["count_ge_10ms"]}
        runs.append(r)
        print(f"stuck {i + 1}: read {'succeeded (!)' if r['ok'] else 'failed, as it must'} in {r['ms']} ms; "
              f"passes >= 25 ms +{r['ge25']}, >= 10 ms +{r['ge10']}", flush=True)
        time.sleep(2)
    checks.append(("every stuck read failed", all(not r["ok"] for r in runs)))
    checks.append((f"every stuck read <= 12 ms whole (longest {max(r['ms'] for r in runs)})",
                   all(r["ms"] <= 12 for r in runs)))
    checks.append(("no pass >= 25 ms", all(r["ge25"] == 0 for r in runs)))
    b = ds.with_dev(lambda h: od.burst(h, 1, 5, 40, 80))
    time.sleep(1.5)
    b = ds.with_dev(od.burst)
    checks.append((f"five ordinary reads after: {b['done']} done, {b['failed']} failed",
                   b["done"] == 5 and b["failed"] == 0 and not b["active"]))
    return {"runs": runs, "after_burst": b}


def restore(a, checks):
    s0 = stalls()
    for i in range(a.n):
        for _ in range(2):   # the debug page, then the dashboard
            ds.with_dev(lambda h: od.op(h, 1, [0]))
            time.sleep(1.5)
    s1 = stalls()
    d = {k: s1[k] - s0[k] for k in ("count_ge_25ms", "count_ge_10ms", "passes")}
    print(f"restore x{a.n}: passes >= 25 ms +{d['count_ge_25ms']}, >= 10 ms +{d['count_ge_10ms']}; "
          f"longest blit since boot {s1['blit_gap_max_ms']} ms", flush=True)
    checks.append((f"{a.n} staged restores: no pass >= 25 ms", d["count_ge_25ms"] == 0))
    return {"before": s0, "after": s1, "delta": d}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["stuck", "restore"])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--json")
    a = ap.parse_args()
    checks = []
    res = (stuck if a.cmd == "stuck" else restore)(a, checks)
    for name, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {name}", flush=True)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "args": vars(a), **res,
                   "checks": [{"check": n, "ok": ok} for n, ok in checks]}, open(a.json, "w"), indent=1)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == "__main__":
    main()
