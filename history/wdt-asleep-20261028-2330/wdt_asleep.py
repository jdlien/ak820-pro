#!/usr/bin/env python3
"""Does the watchdog count in Deep-sleep? (gremlin's WDT reset in deep_sleep(),
23:02 10-28.) Long unfed armed sleeps on the pack, mid-drain, after
scripts/deep_sleep.py --no-feed but with relay 2 NEVER touched (the drain runs
on the pack): the data cut by uhubctl, op 14 sub 4's arm with no_feed and a
cap, entry and any early rise seen in the INA228 log. A reset ~12 s in means
it counts (the retained record names site 27); the cap reached unfed means it
does not. Each run's cleanup: data on, the arm cancelled, the stage released.

    venv/bin/python wdt_asleep.py --caps 120 120 600 --out DIR"""
import argparse, json, os, subprocess, sys, time

R = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, os.path.join(R, "scripts"))
import deep_sleep as ds  # noqa: E402

sb, cm = ds.sb, ds.cm
LOG = os.path.join(R, "history", "power-bench-2026-10-15", "power.csv")


def health_json():
    try:
        out = subprocess.run([ds.AK820, "health", "--json"], capture_output=True, text=True, timeout=15).stdout
        return json.loads(out)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"error": str(e)}


def one(cap, fed=False):
    res = {"cap": cap, "t0": time.time()}
    res["before"] = ds.with_dev(ds.deep)
    ds.with_dev(ds.light_off)
    ds.with_dev(cm.force_stage, sb.SCREEN_OFF)
    time.sleep(8)
    base = [c for _, c in ds.tail_ma(LOG, 8)]
    res["awake_ma"] = sum(base) / len(base) if base else None
    ds.with_dev(ds.deep, 1, ds.DELAY_S, cap, not fed, 0)
    t_arm = time.time()
    cm.say(f"armed {'fed' if fed else 'unfed'}, cap {cap} s ({ds.DELAY_S} s delay); data off")
    ds.uhub("off")
    time.sleep(max(0.0, t_arm + ds.DELAY_S - 1 - time.time()))
    off = [c for t, c in ds.tail_ma(LOG, 12) if t_arm + 5 < t < t_arm + ds.DELAY_S - 1]
    res["awake_dataoff_ma"] = sum(off) / len(off) if off else None
    t_asleep = None
    if res["awake_dataoff_ma"] is not None:
        while time.time() < t_arm + ds.DELAY_S + 30:
            cur = [c for t, c in ds.tail_ma(LOG, 3) if t > t_arm + ds.DELAY_S + 1]
            if len(cur) == 3 and all(c < res["awake_dataoff_ma"] - 2.0 for c in cur):
                t_asleep = time.time()
                break
            time.sleep(1)
    res["asleep_seen_at"] = t_asleep
    rise = None
    if t_asleep is None:
        cm.say("no fall in the current: it did not sleep (the record will say why)")
    else:
        cm.say("asleep (the current fell); watching for a rise")
        # Counted seconds run ~13% slow asleep: the cap is ~1.15 x cap real.
        end = t_asleep + cap * 1.25 + 20
        while time.time() < end:
            for t, c in ds.tail_ma(LOG, 5):
                if rise is None and t > t_asleep + 2 and c >= ds.SLEEP_EDGE_MA:
                    rise = t
                    cm.say(f"the current rose {t - t_asleep:.1f} s after entry ({c:.1f} mA)")
            if rise is not None and time.time() > rise + 10:
                break
            time.sleep(1)
    res["rise_after_s"] = None if rise is None or t_asleep is None else round(rise - t_asleep, 1)
    t_lo, t_hi = (t_asleep or t_arm) + 3, (rise or time.time()) - 2
    asleep = [c for t, c in ds.tail_rows(LOG, kb=160) if t_lo < t < t_hi]
    res["asleep_ma"] = round(sum(asleep) / len(asleep), 3) if asleep else None
    cm.say("data on")
    ds.uhub("on")
    ds.need_bus(40)
    rec = ds.with_dev(ds.deep)
    res["record"] = rec
    hj = health_json()
    res["watchdog_record"] = hj.get("watchdog_record", hj)
    wr = res["watchdog_record"] if isinstance(res["watchdog_record"], dict) else {}
    reset_asleep = rec["state"] == 0 and bool(wr.get("valid")) and wr.get("site_id") == 27
    slept_through = rec["slept"] and rec["reason"] == "cap"
    res["watchdog_counts_asleep"] = True if reset_asleep else (False if slept_through else None)
    cm.say(f"record: {rec}")
    cm.say(f"watchdog record: {wr}")
    cm.say(f"VERDICT cap {cap}: " + {True: "RESET asleep: the watchdog counts in Deep-sleep",
                                     False: f"slept to the cap unfed ({rec['secs']} s counted): it does not count",
                                     None: "inconclusive (see the record)"}[res["watchdog_counts_asleep"]])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", type=int, nargs="+", default=[120, 120, 600])
    ap.add_argument("--out", required=True)
    ap.add_argument("--fed", action="store_true", help="the watchdog fed (an ordinary sleep)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if cm.relay_on():
        sys.exit("relay 2 is ON: this run is for the pack (the drain); not touching it")
    if not os.path.exists(LOG):
        sys.exit("the power logger's CSV is missing")
    ds.need_bus(10)
    runs = []
    try:
        for cap in a.caps:
            cm.say(f"== run {len(runs) + 1} of {len(a.caps)}: cap {cap} s, unfed")
            try:
                runs.append(one(cap, a.fed))
            finally:
                for what, fn, *args in (("data on", ds.uhub, "on"),):
                    sb.attempt(what, fn, *args)
                if sb.attempt("the board on USB", ds.need_bus, 60):
                    sb.attempt("arm cancelled", ds.with_dev, ds.deep, 2)
                    sb.attempt("stage released", ds.with_dev, cm.force_stage, None)
                with open(os.path.join(a.out, "runs.json"), "w") as f:
                    json.dump(runs, f, indent=1, default=str)
            time.sleep(5)
    finally:
        cm.say("done: " + ", ".join(f"cap {r['cap']}: {r['watchdog_counts_asleep']}" for r in runs))


if __name__ == "__main__":
    main()
