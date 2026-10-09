#!/usr/bin/env python3
"""An unattended B3 trial on the bench's USB relay (docs/test-bench.md,
"The USB relay"; plans/BATTERY-GAUGE-REFINE-PLAN.md, B3 and gate 8).

The keyboard sits on the relay cable: relay 2 carries its 5 V, and its data
wires bypass the relay, so it stays readable over USB whether or not it
charges. Every reading is one `hostagent/ak820battery.py` read, appended to
--out as a CSV row. Every relay switch is confirmed by the board's own
`supply` line, never by IORegistry presence: a relay switch does not make the
board leave USB.

Phases, in order (each optional):
  --wait-cut        read every --poll s (every 60 s once past --fine-after)
                    until the RGB cut shows in `flags` (lights_cut), then dump
                    the log;
  --charge-min N    relay on for exactly N minutes from the switch, then off;
  --relax-min N     read every 60 s for N minutes, then dump the log;
  --full            relay on until the charger stops (CHRG high on USB for two
                    reads 5 min apart), then wait 10 min and dump the log. The
                    relay is left ON.

On any failure the relay is switched OFF (not charging) and the script exits
nonzero. ⚠️ The slider must be on BT or 2.4G: on cable, cutting VBUS is a cold
power-off and the RAM log is lost.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PY = os.path.join(ROOT, "venv", "bin", "python3")
BATT = os.path.join(ROOT, "hostagent", "ak820battery.py")
RELAY = os.path.join(ROOT, "scripts", "usb_relay.py")
FIELDS = ["time", "epoch", "phase", "supply", "level", "pack_mv", "est_c5", "c5_last", "vdd_mv", "chrg", "flags", "note"]


def now_s():
    t = time.time()
    return t, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def run(args, timeout=60):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return -1, "timed out"


def read_board():
    rc, out = run([PY, BATT])
    if rc != 0:
        return None, out.strip()[-200:]
    d = {}
    for line in out.splitlines():
        k, _, v = line.partition(" ")
        d[k.strip()] = v.strip()
    m = re.search(r"(\d+) mV\s+\(estimate 5C (\d+)", d.get("pack", ""))
    c = re.search(r"last (\d+)%", d.get("module", ""))
    v = re.search(r"(\d+) mV", d.get("vdd", ""))
    return {
        "supply": d.get("supply", "").split()[0] if d.get("supply") else "",
        "level": d.get("level", ""),
        "pack_mv": m.group(1) if m else "",
        "est_c5": m.group(2) if m else "",
        "c5_last": c.group(1) if c else "",
        "vdd_mv": v.group(1) if v else "",
        "chrg": "low" if "CHRG low" in d.get("charger", "") else "high" if "CHRG high" in d.get("charger", "") else "",
        "flags": d.get("flags", ""),
    }, ""


class Log:
    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(FIELDS)

    def row(self, phase, b=None, note=""):
        t, s = now_s()
        b = b or {}
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow([s, f"{t:.1f}", phase] + [b.get(k, "") for k in FIELDS[3:-1]] + [note])
        print(f"{s} {phase} {b.get('supply', '')} {b.get('level', '')} {b.get('pack_mv', '')} "
              f"{b.get('flags', '')} {note}", flush=True)
        return t

    def read(self, phase, note=""):
        b, err = read_board()
        if b is None:
            self.row(phase, None, f"read failed: {err} {note}")
            return None
        self.row(phase, b, note)
        return b


def relay(log, on):
    t0 = time.time()
    rc, out = run([PY, RELAY, "on" if on else "off", "2"])
    log.row("relay", None, f"{'on' if on else 'off'} 2 requested {t0:.2f}: rc {rc} {out.strip()[-120:]}")
    return rc == 0, t0


def confirm(log, want, phase, limit=90):
    """Read until the board's supply says `want` (external/battery)."""
    end = time.time() + limit
    while time.time() < end:
        b = log.read(phase, f"confirming {want}")
        if b and b["supply"] == want:
            return True
        time.sleep(10)
    return False


def dump(log, outdir, tag):
    path = os.path.join(outdir, f"log-{time.strftime('%Y%m%d-%H%M')}-{tag}.csv")
    rc, out = run([PY, BATT, "log", path], timeout=120)
    log.row("dump", None, f"{path}: rc {rc} {out.strip().splitlines()[-1] if out.strip() else ''}")
    return rc == 0


def fail(log, why):
    log.row("FAIL", None, why)
    relay(log, False)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="CSV of every reading and action")
    ap.add_argument("--wait-cut", action="store_true")
    ap.add_argument("--poll", type=int, default=300)
    ap.add_argument("--fine-after", default="", help="HH:MM from which --wait-cut reads every 60 s")
    ap.add_argument("--charge-min", type=float, default=0)
    ap.add_argument("--relax-min", type=float, default=0)
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    outdir = os.path.dirname(os.path.abspath(a.out))
    log = Log(a.out)

    b = log.read("start")
    if b is None:
        fail(log, "no board read at the start")
    if b["supply"] != "battery":
        fail(log, f"expected the board on battery at the start, got {b['supply']}")

    if a.wait_cut:
        fine = None
        if a.fine_after:
            hh, mm = map(int, a.fine_after.split(":"))
            lt = time.localtime()
            fine = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
        while True:
            b = log.read("wait-cut")
            if b and "lights_cut" in b["flags"]:
                log.row("CUT", b, "lights_cut seen")
                break
            if b and b["supply"] != "battery":
                fail(log, f"supply {b['supply']} while waiting for the cut")
            time.sleep(60 if fine and time.time() >= fine else a.poll)
        dump(log, outdir, "rgbcut")
        time.sleep(60)

    if a.charge_min:
        ok, t_on = relay(log, True)
        if not ok or not confirm(log, "external", "charge"):
            fail(log, "relay on not confirmed")
        log.row("CHARGE-ON", None, f"charge timed from the relay command at {t_on:.2f}")
        end = t_on + a.charge_min * 60
        while time.time() < end - 75:
            time.sleep(min(300, end - 75 - time.time()))
            log.read("charge")
        time.sleep(max(0, end - time.time()))
        ok, t_off = relay(log, False)
        log.row("CHARGE-OFF", None, f"on {t_off - t_on:.1f} s")
        if not ok or not confirm(log, "battery", "relax"):
            fail(log, "relay off not confirmed")

    if a.relax_min:
        end = time.time() + a.relax_min * 60
        while time.time() < end:
            time.sleep(60)
            log.read("relax")
        dump(log, outdir, "relaxed")

    if a.full:
        ok, t_on = relay(log, True)
        if not ok or not confirm(log, "external", "full"):
            fail(log, "relay on for the full charge not confirmed")
        log.row("FULL-ON", None, f"charging from {t_on:.2f}")
        stopped = 0
        while stopped < 2:
            time.sleep(300)
            b = log.read("full")
            stopped = stopped + 1 if b and b["supply"] == "external" and b["chrg"] == "high" else 0
        log.row("FULL", b, "CHRG high on USB, two reads 5 min apart")
        time.sleep(600)
        log.read("full-end")
        dump(log, outdir, "full")
    log.row("done", None, "")


if __name__ == "__main__":
    main()
