#!/usr/bin/env python3
"""The waveform witness, Mac side (plans/ROW-ISR-PLAN.md, "The key-press rig",
item 4; docs/test-bench.md, "The waveform witness"): arm the presser board's
PIO capture of up to four of the keyboard's lines, keep the capture, and read
the pulses out of it. The board side is scripts/presser/witness.py.

    venv/bin/python scripts/witness.py info
    venv/bin/python scripts/witness.py levels
    venv/bin/python scripts/witness.py cap --out DIR/NAME [--lines 1|2|4] [--rate HZ|full]
                                   [--ms MS | --words N] [--trig none|rise:I|fall:I] [--wait MS]
    venv/bin/python scripts/witness.py analyze DIR/NAME [--active 0:low,1:high,...] [--marker I]
                                   [--slot-us US] [--edges CSV] [--json]

`cap` writes NAME.bin (the raw words) and NAME.json (the rate the board
actually ran at, the lines, the trigger, the board's stall flag and clock
stamps, and the CRC check) and prints the report. The rate: `full` is the
board's system clock (125 MHz on a QT Py RP2040, 150 on a Pico 2, one
sample every 8 or 6.7 ns), the width resolution the plan's narrowest gates
need on one line; four lines at the full rate push a FIFO word every two
cycles, which the DMA cannot keep up with (the board says stall=1 and the
capture is not continuous), so four lines run at a quarter of it or less.
The buffer is what the board's heap gave (`info` says), 32/lines samples a
word: a QT Py's ~48k words is 12 ms of one line at the full rate, or 12 ms
of four lines at 31 MHz.

The lines are bit 0 first: on a QT Py SDA, SCL, A3, A2; on a Pico GP2 to
GP5. The plan's assignment: 0 a column (active LOW during the PWM: the LED's
on-time is the low pulse), 1 a mux row (active high), 2 the marker, the Caps
LED's pin D15 (high through a dev hold-off, op 28), 3 the inner marker C15.
`analyze` takes the polarity per line with --active; the default is
0:low and the rest high.

The qualification before any gate is read (the plan): with the probe on, the
released column still reads high (`levels` with the keyboard scanning: bit 0
set), VIA's key tester shows no phantom on that column, and the PWM waveform
is unchanged against an unprobed neighbour.
"""
import argparse
import base64
import binascii
import json
import os
import statistics
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import presser  # noqa: E402

TRIG_NAMES = {"none": "N", "rise": "R", "fall": "F"}


class WitnessError(Exception):
    pass


# The wire ------------------------------------------------------------------

def info(p):
    f = p.cmd("W,V", "W")
    if f[1] != "V":
        raise WitnessError("expected W,V, got " + ",".join(f))
    return {"version": int(f[2]), "lines": int(f[3]), "pins": f[4], "sys_hz": int(f[5]),
            "max_words": int(f[6]), "ready": f[7] == "1"}


def levels(p):
    f = p.cmd("W,P", "W")
    return int(f[2])


def capture(p, lines, hz, words, trig, wait_ms, progress=None):
    """-> (meta, raw bytes). hz 0 is the board's full rate."""
    p._send(f"W,C,{lines},{hz},{words},{trig},{wait_ms}")
    f = p._line(wait_ms / 1000 + 10.0)
    if f[0] != "W" or f[1] != "C":
        raise WitnessError("expected W,C, got " + ",".join(f))
    meta = {"hz": int(f[2]), "lines": int(f[3]), "words": int(f[4]), "trig": f[5],
            "stall": int(f[6]), "t_arm_us": int(f[7]), "t_done_us": int(f[8])}
    chunks = []
    while True:
        f = p._line(10.0)
        if f[0] == "W" and f[1] == "D":
            chunks.append(base64.b64decode(f[2]))
            if progress:
                progress(sum(len(c) for c in chunks))
        elif f[0] == "W" and f[1] == "E":
            raw = b"".join(chunks)
            n, crc = int(f[2]), f[3]
            if len(raw) != n:
                raise WitnessError(f"the board sent {n} bytes, {len(raw)} arrived")
            if crc != "-" and crc != f"{binascii.crc32(raw) & 0xFFFFFFFF:08x}":
                raise WitnessError("CRC mismatch on the capture")
            meta["crc_checked"] = crc != "-"
            return meta, raw
        else:
            raise WitnessError("unexpected during the capture: " + ",".join(f))


# The decode ----------------------------------------------------------------

def transitions(raw, lines):
    """-> (initial levels bitmask, [[(sample, level), ...] per line], samples).
    Words little-endian; the first sample of a word is its low `lines` bits."""
    per = 32 // lines
    mask = (1 << lines) - 1
    trans = [[] for _ in range(lines)]
    last = None
    rep = None
    idx = 0
    initial = 0
    for (w,) in struct.iter_unpack("<I", raw):
        if w == rep:
            idx += per
            continue
        for k in range(per):
            v = (w >> (k * lines)) & mask
            if v != last:
                if last is None:
                    initial = v
                else:
                    d = v ^ last
                    for i in range(lines):
                        if (d >> i) & 1:
                            trans[i].append((idx, (v >> i) & 1))
                last = v
                rep = sum(v << (j * lines) for j in range(per))
            idx += 1
    return initial, trans, idx


def pulses(initial_level, trans, samples, active):
    """(start, end) sample pairs of the active level, complete ones only, plus
    whether a pulse was cut by the capture's start or its end."""
    out = []
    start = None
    cut_first = initial_level == active   # under way at sample 0: not kept
    skipping = cut_first
    for s, lv in trans:
        if lv == active:
            start = s
        else:
            if skipping:
                skipping = False
            elif start is not None:
                out.append((start, s))
            start = None
    cut_last = start is not None
    return out, cut_first, cut_last


def describe(vals, ns_per_sample):
    if not vals:
        return None
    v = sorted(vals)
    return {"n": len(v), "min_ns": round(v[0] * ns_per_sample, 1),
            "median_ns": round(statistics.median(v) * ns_per_sample, 1),
            "max_ns": round(v[-1] * ns_per_sample, 1),
            "min_samples": v[0], "max_samples": v[-1]}


def analyze(raw, meta, active=None, marker=None, slot_us=None):
    lines = meta["lines"]
    hz = meta["hz"]
    ns = 1e9 / hz
    initial, trans, samples = transitions(raw, lines)
    active = active or {}
    rep = {"hz": hz, "lines": lines, "samples": samples, "duration_ms": round(samples * ns / 1e6, 3),
           "stall": meta.get("stall", 0), "line": []}
    per_line = []
    for i in range(lines):
        act = active.get(i, 0 if i == 0 else 1)
        pl, cut_first, cut_last = pulses((initial >> i) & 1, trans[i], samples, act)
        widths = [e - s for s, e in pl]
        periods = [pl[k + 1][0] - pl[k][0] for k in range(len(pl) - 1)]
        gaps = [pl[k + 1][0] - pl[k][1] for k in range(len(pl) - 1)]
        d = {"line": i, "active": "low" if act == 0 else "high", "initial": (initial >> i) & 1,
             "transitions": len(trans[i]), "pulses": len(pl), "cut_first": cut_first, "cut_last": cut_last,
             "width": describe(widths, ns), "period": describe(periods, ns), "gap": describe(gaps, ns)}
        if gaps:
            k = max(range(len(gaps)), key=lambda j: gaps[j])
            d["longest_gap"] = {"ns": round(gaps[k] * ns, 1), "after_pulse": k,
                                "at_us": round(pl[k][1] * ns / 1e3, 3)}
        if slot_us and periods:
            slot = slot_us * 1e3 / ns
            ks = [round(pp / slot) for pp in periods]
            hist = {}
            for kk in ks:
                hist[kk] = hist.get(kk, 0) + 1
            d["periods_in_slots"] = {str(kk): hist[kk] for kk in sorted(hist)}
            d["off_grid"] = sum(1 for pp, kk in zip(periods, ks) if kk == 0 or abs(pp - kk * slot) > 0.1 * slot)
        rep["line"].append(d)
        per_line.append(pl)
    if marker is not None and 0 <= marker < lines:
        act = active.get(marker, 1)
        mpl, _, _ = pulses((initial >> marker) & 1, trans[marker], samples, act)
        rep["marker"] = {"line": marker, "intervals": []}
        for s, e in mpl:
            iv = {"start_us": round(s * ns / 1e3, 3), "end_us": round(e * ns / 1e3, 3),
                  "length_us": round((e - s) * ns / 1e3, 3), "inside": {}}
            for i in range(lines):
                if i == marker:
                    continue
                inside = [(a, b) for a, b in per_line[i] if a >= s and b <= e]
                straddle = sum(1 for a, b in per_line[i] if (a < s < b) or (a < e < b))
                before = [b for a, b in per_line[i] if b <= s]
                after = [a for a, b in per_line[i] if a >= e]
                iv["inside"][str(i)] = {
                    "pulses": len(inside), "straddling": straddle,
                    "first_after_start_us": round((inside[0][0] - s) * ns / 1e3, 3) if inside else None,
                    "last_before_end_us": round((e - inside[-1][1]) * ns / 1e3, 3) if inside else None,
                    "last_pulse_before_us": round((s - before[-1]) * ns / 1e3, 3) if before else None,
                    "first_pulse_after_us": round((after[0] - e) * ns / 1e3, 3) if after else None}
            rep["marker"]["intervals"].append(iv)
    return rep, trans, initial


def print_report(rep):
    print(f"{rep['samples']} samples at {rep['hz'] / 1e6:.4f} MHz = {rep['duration_ms']:.3f} ms, "
          f"{rep['lines']} line(s)" + ("  ⚠️ FIFO STALL: not continuous" if rep.get("stall") else ""))
    for d in rep["line"]:
        print(f"line {d['line']} (active {d['active']}, starts {d['initial']}): {d['transitions']} transitions, "
              f"{d['pulses']} complete pulses" + (" (first cut)" if d["cut_first"] else "") + (" (last cut)" if d["cut_last"] else ""))
        for key in ("width", "period", "gap"):
            s = d[key]
            if s:
                print(f"    {key:6s} min {s['min_ns']:10.1f} ns  median {s['median_ns']:10.1f} ns  max {s['max_ns']:10.1f} ns  (n={s['n']})")
        if "longest_gap" in d:
            g = d["longest_gap"]
            print(f"    longest gap {g['ns'] / 1e3:.3f} us, after pulse {g['after_pulse']} at {g['at_us']:.3f} us")
        if "periods_in_slots" in d:
            print(f"    periods in slots: {d['periods_in_slots']}, off-grid {d['off_grid']}")
    if "marker" in rep:
        m = rep["marker"]
        print(f"marker line {m['line']}: {len(m['intervals'])} interval(s)")
        for iv in m["intervals"]:
            print(f"  {iv['start_us']:.3f} .. {iv['end_us']:.3f} us ({iv['length_us']:.3f} us)")
            for i, x in iv["inside"].items():
                print(f"    line {i}: {x['pulses']} pulse(s) inside, {x['straddling']} straddling; "
                      f"last before {x['last_pulse_before_us']} us, first after {x['first_pulse_after_us']} us")


def write_edges(path, trans, initial, hz):
    with open(path, "w") as f:
        f.write("time_us,line,level\n")
        rows = []
        for i, t in enumerate(trans):
            rows.append((0, i, (initial >> i) & 1))
            rows.extend((s, i, lv) for s, lv in t)
        rows.sort()
        for s, i, lv in rows:
            f.write(f"{s * 1e6 / hz:.4f},{i},{lv}\n")


def parse_active(s):
    out = {}
    if s:
        for part in s.split(","):
            i, pol = part.split(":")
            out[int(i)] = 0 if pol.lower().startswith("l") else 1
    return out


# The commands --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("levels")
    c = sub.add_parser("cap")
    c.add_argument("--out", required=True, help="DIR/NAME: NAME.bin and NAME.json are written")
    c.add_argument("--lines", type=int, default=1, choices=(1, 2, 4))
    c.add_argument("--rate", default="full", help="samples a second, or full")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--ms", type=float, help="the capture's length (default: the whole buffer)")
    g.add_argument("--words", type=int)
    c.add_argument("--trig", default="none", help="none, rise:I or fall:I (line I's edge starts it)")
    c.add_argument("--wait", type=int, default=2000, help="ms to wait for the trigger")
    c.add_argument("--active", default=None)
    c.add_argument("--marker", type=int, default=None)
    c.add_argument("--slot-us", type=float, default=None)
    a_ = sub.add_parser("analyze")
    a_.add_argument("name", help="DIR/NAME as given to cap")
    a_.add_argument("--active", default=None, help="polarity per line, e.g. 0:low,1:high")
    a_.add_argument("--marker", type=int, default=None)
    a_.add_argument("--slot-us", type=float, default=None)
    a_.add_argument("--edges", default=None, help="write every transition to this CSV")
    a_.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "analyze":
        raw = open(a.name + ".bin", "rb").read()
        meta = json.load(open(a.name + ".json"))
        rep, trans, initial = analyze(raw, meta, parse_active(a.active), a.marker, a.slot_us)
        if a.edges:
            write_edges(a.edges, trans, initial, meta["hz"])
        if a.json:
            print(json.dumps(rep, indent=1))
        else:
            print_report(rep)
        return

    with presser.Presser() as p:
        inf = info(p)
        if a.cmd == "info":
            print(f"witness v{inf['version']} on {p.port}: {inf['lines']} lines ({inf['pins']}), "
                  f"system clock {inf['sys_hz'] / 1e6:.3f} MHz, buffer {inf['max_words']} words "
                  f"({inf['max_words'] * 4 // 1024} KB), {'ready' if inf['ready'] else 'NOT READY (rp2pio, pins or memory)'}")
            return
        if a.cmd == "levels":
            b = levels(p)
            print("lines now: " + " ".join(f"{i}={(b >> i) & 1}" for i in range(inf["lines"])))
            return
        if not inf["ready"]:
            sys.exit("the board has no witness ready (witness.py info)")
        hz = 0 if a.rate == "full" else int(float(a.rate))
        eff = inf["sys_hz"] if hz == 0 else hz
        per = 32 // a.lines
        if a.words:
            words = a.words
        elif a.ms:
            words = -(-int(a.ms * 1e-3 * eff) // per)
        else:
            words = inf["max_words"]
        if words > inf["max_words"]:
            sys.exit(f"{words} words asked, the board holds {inf['max_words']} "
                     f"({inf['max_words'] * per / eff * 1e3:.3f} ms at this rate and line count)")
        if a.trig == "none":
            trig = "N"
        else:
            kind, _, idx = a.trig.partition(":")
            if kind not in ("rise", "fall") or not idx.isdigit() or int(idx) > 3:
                sys.exit("--trig is none, rise:I or fall:I, I one of the four lines (0-3)")
            trig = TRIG_NAMES[kind] + idx
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        t0 = time.time()
        meta, raw = capture(p, a.lines, hz, words, trig, a.wait)
        meta.update({"board": inf, "requested_hz": hz, "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "mac_time": t0, "trig_request": a.trig, "wait_ms": a.wait})
        with open(a.out + ".bin", "wb") as f:
            f.write(raw)
        with open(a.out + ".json", "w") as f:
            json.dump(meta, f, indent=1)
        print(f"captured {len(raw)} bytes at {meta['hz'] / 1e6:.4f} MHz, trig {meta['trig']}, "
              f"{(meta['t_done_us'] - meta['t_arm_us']) / 1e3:.3f} ms arm to done"
              + ("  ⚠️ FIFO STALL" if meta["stall"] else "") + f" -> {a.out}.bin/.json")
        rep, _, _ = analyze(raw, meta, parse_active(a.active), a.marker, a.slot_us)
        print_report(rep)


if __name__ == "__main__":
    main()
