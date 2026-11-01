#!/usr/bin/env python3
"""Stage 0's measurements for the row ISR rewrite, as one command
(plans/ROW-ISR-PLAN.md, "Stage 0: establish truth", and stage 1's gates): on
the firmware the board is running, record its token and settings, take the
health windows (idle, under an LCD repaint load, under forced PCF
transactions, and across a forced cleanup when the operator can trigger it),
hold the lighting at Solid white, red, green and blue at 64, 128 and 255,
forward and back, with the dark baseline, reading the INA228's rows out of
the drain's power_log CSV for each, then put the lighting and the live
settings back. The same command on the next build, and `compare` reads the
plan's within-3% gates between the two.

    venv/bin/python scripts/rowisr_baseline.py run --label base --out DIR
        [--window 24] [--hold-s 40] [--settle-s 8] [--skip-holds]
        [--cleanup skip|manual] [--power-csv history/power-bench-2026-10-15/power.csv]
    venv/bin/python scripts/rowisr_baseline.py compare DIR/base.json DIR/stage1.json

What it needs: the board on USB data (`uhubctl -l 3-1.3.4 -p 2 -a on -e`
on Buzz's bench), the daemon paused for the whole run (it would seize raw
HID, and its clock sync writes the PCF, which lands in a window), a dev
build (the repaint and PCF loads are HC_DEVHOOK ops 1 and 23), and the
power logger running on the bench QT Py (its CSV is only read, never its
port). The lighting is set over VIA's channel without a save, but the
firmware's own settle saves it anyway, so the run ends by restoring the
lighting it found and the live settings record (ak820profiles.py), which
the Win/Mac side would otherwise keep as Solid white for the rest of the
drain. A run that dies mid-way leaves DIR/settings-before.json and
DIR/lighting-before.json to restore by hand:
    venv/bin/python hostagent/ak820lighting.py restore DIR/lighting-before.json
    venv/bin/python hostagent/ak820profiles.py restore DIR/settings-before.json --live-only

The camera clips and the fixed-exposure optical references are JD's
(stage 0's list): the run prints when each window starts for a clip taken
beside it. Never enumerate HID beyond the house open_device.
"""
import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "hostagent"))
import ak820health as hp   # noqa: E402
import ak820lighting as lp  # noqa: E402

VENV_PY = os.path.join(ROOT, "venv", "bin", "python")
AK820 = os.path.expanduser("~/Library/Application Support/ak820pro/bin/ak820")
STATUS = os.path.expanduser("~/Library/Application Support/ak820pro/ak820-agent.status")
DEFAULT_CSV = os.path.join(ROOT, "history", "power-bench-2026-10-15", "power.csv")
SET_VALUE, HEALTH_CH, HC_DEVHOOK = 0x07, 0x13, 0x76
SOLID = 1   # rgb_matrix's SOLID_COLOR, the mode after NONE; read back after setting

# Hue, sat for the holds; val is the level.
COLOURS = [("white", 0, 0), ("red", 0, 255), ("green", 85, 255), ("blue", 170, 255)]
LEVELS = [64, 128, 255]


def say(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def devhook(h, op, args=(), tries=5):
    """One HC_DEVHOOK round trip; the reply's 32 bytes, or None if unhandled."""
    pay = [SET_VALUE, HEALTH_CH, HC_DEVHOOK, op] + list(args)
    h.write(bytes([0] + pay + [0] * (32 - len(pay))))
    for _ in range(tries):
        r = h.read(32, 1000)
        if r and len(r) == 32 and r[1] == HEALTH_CH and r[2] == HC_DEVHOOK and r[3] == op:
            return bytes(r) if r[0] == SET_VALUE else None
    raise SystemExit(f"no reply to dev op {op}")


def token_from_cli():
    """The build token through the daemon's CLI (no enumeration); the handle
    must be closed meanwhile."""
    try:
        out = subprocess.run([AK820, "health", "--json"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return json.loads(out.stdout).get("vitals", {}).get("build_token", "unknown")
        return f"unknown ({out.stderr.strip()[:80]})"
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return f"unknown ({e})"


def daemon_syncs():
    try:
        for line in open(STATUS):
            if line.startswith("clock_syncs="):
                return int(line.split("=", 1)[1])
    except (OSError, ValueError):
        pass
    return None


def power_rows(path, t_from, t_to):
    """(epoch, current_ma, vcell_mv) rows of the logger's CSV between the
    two Mac times, from its tail."""
    rows = []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 1_000_000))
            tail = f.read().decode(errors="replace").splitlines()
    except OSError:
        return rows
    for line in tail[1:]:
        p = line.split(",")
        if len(p) < 9:
            continue
        try:
            t = float(p[1])
            if t_from <= t <= t_to:
                rows.append((t, float(p[5]), float(p[8])))
        except ValueError:
            continue
    return rows


def snapshot(h):
    return {"health": hp.read_health(h), "stalls": hp.read_stalls(h), "rows": hp.read_rows(h),
            "link": hp.read_link(h)}


def window(h, name, secs, load=None, cue=None):
    """One health window: counters reset, page 4 before and after, the other
    pages at the end, the load applied meanwhile through load(h, t_left)."""
    say(f"window '{name}': {secs} s" + (f" ({cue})" if cue else "") + "  <- a 240 fps clip of the board now, if filming")
    syncs0 = daemon_syncs()
    hp.reset_counters(h)
    time.sleep(0.2)
    a = hp.read_isr(h)
    t0 = time.monotonic()
    state = None
    while True:
        left = secs - (time.monotonic() - t0)
        if left <= 0:
            break
        if load:
            state = load(h, left, state)
        time.sleep(min(0.25, max(0.0, left)))
    b = hp.read_isr(h)
    wall = time.monotonic() - t0
    out = {"name": name, "secs": round(wall, 2), "isr": hp.isr_rates(a, b, wall), "page4_before": a, "page4_after": b,
           "end": snapshot(h), "daemon_syncs_during": (daemon_syncs() or 0) - (syncs0 or 0) if syncs0 is not None else None}
    if load:
        out["load"] = load(h, 0, state)   # the load's own summary, stopped
    i = out["isr"]
    say(f"  {i['isr_per_s']} ISR/s, mean {i['isr_mean_us']} us, max {i['isr_max_us']} us, cpu {i['isr_cpu_pct']}%, "
        f"rows {i['row_samples_per_row_per_s']}/row/s; row_gap_max {out['end']['rows']['row_gap_max_ms']} ms, "
        f">=25 ms {out['end']['stalls']['count_ge_25ms']}, loop gap {out['end']['stalls']['loop_gap_max_ms']} ms, "
        f"uart overruns {out['end']['link']['uart_overrun']}, timeouts {out['end']['link']['timeouts']}")
    return out


def load_repaint(h, left, state):
    """The debug page toggled once a second (dev op 1: a full compose and
    the staged restore each way); an even count puts the dashboard back."""
    if state is None:
        state = {"toggles": 0, "next": time.monotonic()}
    if left <= 0:
        if state["toggles"] % 2:
            devhook(h, 1)
            state["toggles"] += 1
        return {"kind": "repaint", "toggles": state["toggles"]}
    if time.monotonic() >= state["next"] and left > 1.2:
        devhook(h, 1)
        state["toggles"] += 1
        state["next"] += 1.0
    return state


def burst_fields(r):
    u16 = lambda o: r[4 + o] | (r[5 + o] << 8)
    return {"left": u16(0), "done": u16(2), "failed": u16(4),
            "exposure_ms": r[10] | (r[11] << 8) | (r[12] << 16) | (r[13] << 24), "active": bool(r[14])}


def load_pcf(secs):
    """Dev op 23 sub 1: a burst of clock-chip transactions, each holding the
    row interrupt off for its ~2.6 ms, at random gaps of 250-300 ms, started
    long enough to outlast the window and stopped at its end."""
    n = int(math.ceil(secs / 0.25)) + 10

    def load(h, left, state):
        if state is None:
            r = devhook(h, 23, [1, n & 0xFF, n >> 8, 250, 255, 0, 0])
            if r is None:
                raise SystemExit("the PCF burst was refused (dev build? another burst running?)")
            return {"started": burst_fields(r)}
        if left <= 0:
            r = devhook(h, 23, [2])
            return {"kind": "pcf_burst", "n_asked": n, "at_stop": burst_fields(r) if r else None}
        return state
    return load


def set_lighting(h, hue, sat, val):
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.EFFECT, SOLID])
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.COLOR, hue, sat])
    lp.xfer(h, [lp.SET_VALUE, lp.RGB_MATRIX_CHANNEL, lp.BRIGHTNESS, val])
    got = lp.read_lighting(h)
    if got["animation_index"] != SOLID or got["val"] != val:
        raise SystemExit(f"the lighting did not take: asked solid {hue}/{sat}/{val}, read {got}")


def hold(h, csv, name, hue, sat, val, hold_s, settle_s):
    set_lighting(h, hue, sat, val)
    t_set = time.time()
    time.sleep(settle_s + hold_s)
    rows = power_rows(csv, t_set + settle_s, time.time())
    cur = [r[1] for r in rows]
    out = {"state": name, "hue": hue, "sat": sat, "val": val, "n": len(rows),
           "mean_ma": round(statistics.mean(cur), 3) if cur else None,
           "sd_ma": round(statistics.pstdev(cur), 3) if len(cur) > 1 else None,
           "vcell_mv": round(statistics.mean(r[2] for r in rows), 1) if rows else None}
    say(f"  hold {name:12s} {out['mean_ma']} mA over {out['n']} rows (sd {out['sd_ma']}), vcell {out['vcell_mv']}")
    return out


def run(a):
    os.makedirs(a.out, exist_ok=True)
    say(f"stage 0 run '{a.label}' -> {a.out}")
    token = token_from_cli()
    say(f"board token {token}")
    h = hp.open_device()
    try:
        if devhook(h, 6) is None:
            raise SystemExit("not a dev build: the repaint and PCF loads need HC_DEVHOOK")
        before = {"lighting": lp.read_lighting(h), "health": hp.read_health(h)}
    finally:
        h.close()
    json.dump(before["lighting"], open(os.path.join(a.out, "lighting-before.json"), "w"), indent=1)
    subprocess.run([VENV_PY, os.path.join(ROOT, "hostagent", "ak820profiles.py"), "dump",
                    os.path.join(a.out, "settings-before.json")], check=True)
    battery = subprocess.run([VENV_PY, os.path.join(ROOT, "hostagent", "ak820battery.py")],
                             capture_output=True, text=True).stdout
    say("settings and lighting saved; battery:\n" + "\n".join("    " + l for l in battery.splitlines()[:8]))
    rec = {"label": a.label, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "token": token,
           "health_version": before["health"]["version"], "lighting": before["lighting"], "battery": battery,
           "window_s": a.window, "windows": {}, "holds": [], "notes": []}
    path = os.path.join(a.out, f"{a.label}.json")

    def save():
        json.dump(rec, open(path, "w"), indent=1)

    h = hp.open_device()
    try:
        rec["windows"]["idle"] = window(h, "idle", a.window)
        save()
        time.sleep(2)
        rec["windows"]["repaint"] = window(h, "repaint", a.window, load_repaint, "the debug page toggled once a second")
        save()
        time.sleep(2)
        rec["windows"]["pcf"] = window(h, "pcf", a.window, load_pcf(a.window), "clock-chip transactions every 250-300 ms")
        save()
        if a.cleanup == "manual":
            input("\n  >>> the cleanup window: press Enter, then within 10 s run Diagnostics > Write test > Cleanup on the board's menu: ")
            rec["windows"]["cleanup"] = window(h, "cleanup", a.window, None, "a forced consolidation, by hand")
            save()
        else:
            rec["notes"].append("the cleanup window was skipped (no HID trigger for the write test's Cleanup; --cleanup manual)")
        if a.skip_holds:
            rec["notes"].append("the INA228 holds were skipped (--skip-holds)")
        else:
            if not os.path.exists(a.power_csv):
                raise SystemExit(f"no power CSV at {a.power_csv}")
            seq = [("dark", 0, 0, 0)]
            for cname, hue, sat in COLOURS:
                for v in LEVELS:
                    seq.append((f"{cname} {v}", hue, sat, v))
            seq.append(("dark", 0, 0, 0))
            back = [s for s in reversed(seq[1:-1])]
            seq = seq + back + [("dark", 0, 0, 0)]
            say(f"holds: {len(seq)} states x {a.settle_s + a.hold_s} s = {len(seq) * (a.settle_s + a.hold_s) / 60:.1f} min")
            for i, (name, hue, sat, v) in enumerate(seq):
                r = hold(h, a.power_csv, name, hue, sat, v, a.hold_s, a.settle_s)
                r["leg"] = "forward" if i <= len(seq) // 2 else "back"
                rec["holds"].append(r)
                save()
            darks = [x["mean_ma"] for x in rec["holds"] if x["state"] == "dark" and x["mean_ma"] is not None]
            dark = statistics.mean(darks) if darks else None
            rec["dark_ma"] = round(dark, 3) if dark is not None else None
            for x in rec["holds"]:
                x["incremental_ma"] = round(x["mean_ma"] - dark, 3) if (dark is not None and x["mean_ma"] is not None) else None
    finally:
        say("restoring the lighting and the live settings")
        try:
            lp.write_lighting(h, before["lighting"])
        finally:
            h.close()
        subprocess.run([VENV_PY, os.path.join(ROOT, "hostagent", "ak820profiles.py"), "restore",
                        os.path.join(a.out, "settings-before.json"), "--live-only"], check=False)
        save()
    say(f"done -> {path}")
    print_summary(rec)


def print_summary(rec):
    print(f"\n{rec['label']}: token {rec['token']}, {rec['when']}")
    for name, w in rec["windows"].items():
        i = w["isr"]
        e = w["end"]
        print(f"  {name:8s} {i['isr_per_s']:8} ISR/s  mean {i['isr_mean_us']:6} us  max {i['isr_max_us']:7} us  "
              f"cpu {i['isr_cpu_pct']:5}%  rows {i['row_samples_per_row_per_s']:6}/row/s  row_gap_max {e['rows']['row_gap_max_ms']} ms  "
              f">=25ms {e['stalls']['count_ge_25ms']}  loop_gap {e['stalls']['loop_gap_max_ms']} ms  "
              f"overruns {e['link']['uart_overrun']}  timeouts {e['link']['timeouts']}")
    if rec["holds"]:
        print(f"  dark {rec.get('dark_ma')} mA; incremental mA by state (forward / back):")
        by = {}
        for x in rec["holds"]:
            by.setdefault(x["state"], []).append(x.get("incremental_ma"))
        for k, v in by.items():
            if k != "dark":
                print(f"    {k:10s} " + " / ".join(str(z) for z in v))


METRICS = [("isr_per_s", "ISR/s", 3.0), ("isr_mean_us", "mean us", 3.0), ("isr_cpu_pct", "cpu %", 3.0),
           ("row_samples_per_row_per_s", "rows/row/s", 3.0), ("isr_max_us", "max us", None)]


def compare(a):
    A, B = json.load(open(a.a)), json.load(open(a.b))
    print(f"{A['label']} ({A['token']}) -> {B['label']} ({B['token']}); the plan's gate: within 3% of stage 0")
    bad = 0
    for name in A["windows"]:
        if name not in B["windows"]:
            print(f"  {name}: only in {A['label']}")
            continue
        wa, wb = A["windows"][name], B["windows"][name]
        print(f"  window {name}:")
        for key, label, tol in METRICS:
            x, y = wa["isr"].get(key), wb["isr"].get(key)
            if x is None or y is None:
                continue
            d = (y - x) / x * 100 if x else float("nan")
            verdict = "" if tol is None else ("ok" if abs(d) <= tol else "FAIL")
            bad += verdict == "FAIL"
            print(f"    {label:11s} {x:10} -> {y:10}  {d:+6.2f}%  {verdict}")
        for key, label in (("row_gap_max_ms", "row_gap_max ms"), ("count_ge_25ms", ">=25 ms stalls"),
                           ("loop_gap_max_ms", "loop gap ms"), ("uart_overrun", "uart overruns"), ("timeouts", "ack timeouts")):
            src = "rows" if key == "row_gap_max_ms" else "stalls" if key in ("count_ge_25ms", "loop_gap_max_ms") else "link"
            x, y = wa["end"][src][key], wb["end"][src][key]
            worse = y > x and key != "loop_gap_max_ms"
            bad += worse
            print(f"    {label:15s} {x:6} -> {y:6}  {'WORSE' if worse else 'ok'}")
    if A["holds"] and B["holds"]:
        print("  incremental LED power (mA, dark subtracted), within 3%:")
        ha = {(x["state"], x["leg"]): x.get("incremental_ma") for x in A["holds"]}
        hb = {(x["state"], x["leg"]): x.get("incremental_ma") for x in B["holds"]}
        for k in ha:
            if k[0] == "dark" or k not in hb or ha[k] is None or hb[k] is None:
                continue
            x, y = ha[k], hb[k]
            d = (y - x) / x * 100 if x else float("nan")
            verdict = "ok" if abs(d) <= 3.0 or abs(y - x) < 0.3 else "FAIL"
            bad += verdict == "FAIL"
            print(f"    {k[0]:10s} {k[1]:8s} {x:8.3f} -> {y:8.3f}  {d:+6.2f}%  {verdict}")
        print(f"  dark: {A.get('dark_ma')} -> {B.get('dark_ma')} mA")
    print("RESULT:", "every gate within tolerance" if not bad else f"{bad} metric(s) outside the gate")
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--window", type=float, default=24.0)
    r.add_argument("--hold-s", type=float, default=40.0)
    r.add_argument("--settle-s", type=float, default=8.0)
    r.add_argument("--skip-holds", action="store_true")
    r.add_argument("--cleanup", choices=("skip", "manual"), default="skip")
    r.add_argument("--power-csv", default=DEFAULT_CSV)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a)
    else:
        sys.exit(compare(a))


if __name__ == "__main__":
    main()
