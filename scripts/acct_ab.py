#!/usr/bin/env python3
"""Gate 3 of plans/BATTERY-GAUGE-REFINE-PLAN.md: what D1's per-task accounting
costs, measured on the board right after flash 1.

N minutes with the accounting ON, then N minutes OFF (the runtime flag), same
conditions -- the dashboard showing, BT position, white at full drive, the
host timekeeper as usual, no VIA, nobody typing unless both halves have it.
For each half: main-loop passes per second and >= 10 ms gaps per hour, from
health page 2 and the firmware's own uptime. The accounting is left ON at the
end (its default).

Pass: passes/s with it on within 1% of off, and the >= 10 ms count no higher
with it on beyond noise (the counts are Poisson-ish: their difference against
2 sqrt(sum) is printed). Rollback criterion: a measured cost above 0.1 ms a
pass, i.e. (1/pps_on - 1/pps_off) > 0.1 ms.

Usage: acct_ab.py [--minutes 30] [--out result.json]
Five raw-HID transactions in all (open, read, close each time).
"""
import argparse, json, math, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
import ak820health as H   # noqa: E402  (re-execs under the venv if hid is missing)


def snap(op=None):
    h = H.open_device()
    try:
        acct = H.read_acct(h, op)
        st = H.read_stalls(h)
    finally:
        h.close()
    return {"wall": time.time(), "uptime_ms": acct["uptime_ms"], "enabled": acct["enabled"],
            "passes": st["passes"], "c10": st["count_ge_10ms"], "c25": st["count_ge_25ms"]}


def half(a, b):
    dt = (b["uptime_ms"] - a["uptime_ms"]) / 1000.0
    return {"seconds": round(dt, 1), "passes": b["passes"] - a["passes"],
            "pps": round((b["passes"] - a["passes"]) / dt, 2),
            "ge10": b["c10"] - a["c10"], "ge10_per_h": round((b["c10"] - a["c10"]) * 3600 / dt, 1),
            "ge25": b["c25"] - a["c25"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    wait = a.minutes * 60

    s0 = snap("on")
    print(f"{time.strftime('%H:%M:%S')} accounting ON; {a.minutes:g} min", flush=True)
    time.sleep(wait)
    s1 = snap("off")
    print(f"{time.strftime('%H:%M:%S')} accounting OFF; {a.minutes:g} min", flush=True)
    time.sleep(wait)
    s2 = snap("on")
    print(f"{time.strftime('%H:%M:%S')} done; accounting back ON", flush=True)

    on, off = half(s0, s1), half(s1, s2)
    rel = (on["pps"] - off["pps"]) / off["pps"]
    cost_ms = (1 / on["pps"] - 1 / off["pps"]) * 1000
    noise = 2 * math.sqrt(max(on["ge10"] + off["ge10"], 1))
    r = {"on": on, "off": off, "pps_rel_change": round(rel, 4), "cost_ms_per_pass": round(cost_ms, 4),
         "ge10_on_minus_off": on["ge10"] - off["ge10"], "ge10_noise_2sqrt": round(noise, 1),
         "pps_within_1pct": abs(rel) <= 0.01, "ge10_not_higher": (on["ge10"] - off["ge10"]) <= noise,
         "rollback": cost_ms > 0.1, "snaps": [s0, s1, s2]}
    print(json.dumps({k: v for k, v in r.items() if k != "snaps"}, indent=1))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(r, f, indent=1)
    return 0 if (r["pps_within_1pct"] and r["ge10_not_higher"] and not r["rollback"]) else 1


if __name__ == "__main__":
    sys.exit(main())
