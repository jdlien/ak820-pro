#!/usr/bin/env python3
"""site/power/power.json, the power page's numbers (plans/POWER-CHARTS-PLAN.md).

    python3 scripts/power_model.py            # write site/power/power.json
    python3 scripts/power_model.py --check    # regenerate; exit 1 if the file has drifted
    python3 scripts/power_model.py --oracle <dir>   # build the C oracle, write its fixtures

Everything firmware comes from the commit deps.lock pins, read with
`git show <sha>:<path>`, never a branch head or the working tree: the model's
constants (battery.c), the sleep's draw (battery.h), the low cap, the
ladders and the ceilings (power.c), the backlight's duty table
(graphics/display.c), the LED count (keyboard.json's rgb_matrix layout), QMK's
CIE table (quantum/led_tables.c) and the screen readout's rounding
(param_overlay.c). A missing or ambiguous definition, or a table of the wrong
size, is fatal: the page must never show a number the board does not use.

The measured side is the knobs sweep's results.json (current_map.py --set
knobs: each hold's setting as read back, its charge-register mA and the pack's
VCELL, so mW = mA x VCELL), and scripts/power_evidence.json for the figures
that live only in the docs. Standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FW = os.path.join(ROOT, "qmk_firmware-ak820pro")
KB = "keyboards/a_jazz/ak820pro"
OUT = os.path.join(ROOT, "site", "power", "power.json")
EVIDENCE = os.path.join(ROOT, "scripts", "power_evidence.json")
ORACLE_C = os.path.join(ROOT, "scripts", "power_oracle.c")
SCHEMA = 1


def die(msg):
    sys.exit(f"power_model: {msg}")


def pinned_sha():
    for line in open(os.path.join(ROOT, "deps.lock")):
        f = line.split()
        if f and f[0] == "qmk_firmware-ak820pro":
            if len(f) < 4 or not re.fullmatch(r"[0-9a-f]{40}", f[3]):
                die(f"deps.lock's firmware line has no full SHA: {line.strip()}")
            return f[3]
    die("deps.lock has no qmk_firmware-ak820pro line")


def show(sha, path):
    r = subprocess.run(["git", "-C", FW, "show", f"{sha}:{path}"], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"cannot read {path} at {sha[:10]}: {r.stderr.strip()}")
    return r.stdout


def define(src, name, where):
    m = re.findall(rf"^#\s*define\s+{name}\s+\(?\s*(\d+)u?\s*\)?", src, re.M)
    if len(m) != 1:
        die(f"{where}: expected one #define {name}, found {len(m)}")
    return int(m[0])


def c_array(src, name, n, where):
    m = re.findall(rf"\b{name}\s*\[[^\]]*\][^=]*=\s*\{{([^}}]*)\}}", src, re.S)
    if len(m) != 1:
        die(f"{where}: expected one array {name}, found {len(m)}")
    vals = [int(v, 0) for v in re.findall(r"0x[0-9a-fA-F]+|\d+", re.sub(r"/\*.*?\*/|//[^\n]*", "", m[0], flags=re.S))]
    if len(vals) != n:
        die(f"{where}: {name} has {len(vals)} entries, expected {n}")
    return vals


def ladders(src, saver_val):
    """power.c's ladders: {mode: {dim, lights_off, screen_off, sleep (ms, None = never), active_val}}."""
    out = {}
    for mode in ("FULL", "NORMAL", "SAVER", "MINIMAL"):
        m = re.findall(rf"\[POWER_MODE_{mode}\]\s*=\s*\{{([^}}]*)\}}", src)
        if len(m) != 1:
            die(f"power.c: expected one ladder for {mode}, found {len(m)}")
        f = [t.strip() for t in m[0].split(",")]
        if len(f) != 5:
            die(f"power.c: the {mode} ladder has {len(f)} fields, expected 5")

        def val(t):
            if t == "NEVER":
                return None
            if t == "SAVER_VAL":
                return saver_val
            if not re.fullmatch(r"\d+u?", t):
                die(f"power.c: the {mode} ladder has an unexpected field {t!r}")
            return int(t.rstrip("u"))
        dim, lights_off, screen_off, sleep, active = (val(t) for t in f)
        out[mode.lower()] = {"dim_ms": dim, "lights_off_ms": lights_off, "screen_off_ms": screen_off,
                             "sleep_ms": sleep, "active_val": active}
    return out


def firmware(sha):
    bc = show(sha, f"{KB}/battery.c")
    bh = show(sha, f"{KB}/battery.h")
    pc = show(sha, f"{KB}/power.c")
    dc = show(sha, f"{KB}/graphics/display.c")
    po = show(sha, f"{KB}/param_overlay.c")
    kj = json.loads(show(sha, f"{KB}/keyboard.json"))
    lt = show(sha, "quantum/led_tables.c")
    if "(lvl * 100u + mx / 2u) / mx" not in po:
        die("param_overlay.c: the LCD readout's rounding is not (lvl * 100u + mx / 2u) / mx any more")
    if "hsv.v > val_cap" not in pc:
        die("power.c: rgb_matrix_hsv_to_rgb no longer caps the value before hsv_to_rgb")
    duty = c_array(dc, "bkl_duty", 24, "graphics/display.c")
    full = define(bc, "BKL_DUTY_FULL", "battery.c")
    if duty[-1] != full:
        die(f"display.c's top duty {duty[-1]} is not battery.c's BKL_DUTY_FULL {full}")
    saver = define(pc, "SAVER_VAL", "power.c")
    try:
        leds = len(kj["rgb_matrix"]["layout"])
    except (KeyError, TypeError):
        die("keyboard.json has no rgb_matrix layout")
    return {
        "sha": sha,
        "led_count": leds,
        "p_base_uw": define(bc, "P_BASE_UW", "battery.c"),
        "p_usb_uw": define(bc, "P_USB_UW", "battery.c"),
        "p_bkl_full_uw": define(bc, "P_BKL_FULL_UW", "battery.c"),
        "bkl_duty_full": full,
        "p_rgb_a_uw": define(bc, "P_RGB_A_UW", "battery.c"),
        "p_rgb_nw": [define(bc, f"P_RGB_{c}_NW", "battery.c") for c in "RGB"],
        "e_cap_mwh": define(bc, "E_CAP_MWH", "battery.c"),
        "p_sleep_uw": define(bh, "BATTERY_P_SLEEP_UW", "battery.h"),
        "low_cap_pm": define(pc, "LOW_CAP_PM", "power.c"),
        "saver_val": saver,
        "dim_val": define(pc, "DIM_VAL", "power.c"),
        "screen_dim_level": define(pc, "SCREEN_DIM_LEVEL", "power.c"),
        "ladders": ladders(pc, saver),
        "backlight_duty": duty,
        "cie1931": c_array(lt, "CIE1931_CURVE", 256, "quantum/led_tables.c"),
    }


HUE = {"white": (0, 0), "red": (0, 255), "green": (85, 255), "blue": (170, 255)}


def mean(xs):
    return round(sum(xs) / len(xs), 2)


def family(effect, h, s, level):
    """A knobs state's family, from its setting as read back, never its name."""
    if effect == 0:
        return "dark" if level is None else "screen"
    if effect != 1:
        return "animated"
    if level is not None:
        return "combined"
    for colour, (hh, ss) in HUE.items():
        if s == ss and (s == 0 or h == hh):
            return colour
    return "held out"


def knobs_sweep(ev):
    """Each state's passes from a `--set knobs` run's results.json, at full
    precision: the setting each hold read back, the pack power (mA x VCELL),
    the LED drive and the board's own modelled draw."""
    rel = ev["dir"]
    res = json.load(open(os.path.join(ROOT, rel, "results.json")))
    if res.get("set") != "knobs":
        die(f"{rel}/results.json: set {res.get('set')!r}, not knobs")
    by = {}
    for s in res["steps"]:
        m = s.get("measured")
        if not m or not m.get("vcell_mv"):
            die(f"{rel}: hold {s['i']} ({s['name']}) has no measurement")
        by.setdefault(s["name"], []).append(s)
    rows = []
    for name, ss in by.items():
        # With the RGB off, VIA still reads back the colour the last state left,
        # which differs between the passes; it lights nothing, so it is dropped.
        got = {(s["rgb_effect"], *((0, 0, 0) if s["rgb_effect"] == 0 else (s["rgb_h"], s["rgb_s"], s["rgb_v"])),
                s["lcd_effective"] if s["lcd_on"] else None) for s in ss}
        if len(got) != 1:
            die(f"{rel}: {name}'s passes read back different settings: {sorted(got, key=str)}")
        effect, h, sat, v, level = got.pop()
        mw = [s["measured"]["q_ma"] * s["measured"]["vcell_mv"] / 1000 for s in ss]
        rows.append({"name": name, "family": family(effect, h, sat, level),
                     "lighting": {"effect": effect, "h": h, "s": sat, "v": v}, "screen_level": level,
                     "passes": [round(x, 2) for x in mw], "mw": mean(mw),
                     "ma": mean([s["measured"]["q_ma"] for s in ss]),
                     "led_pm": [int(s["led_pm"]) for s in ss],
                     "board_model_mw": [s["model_mw"] for s in ss]})
    return {**ev, "hold_s": res["hold_s"], "settle_s": res["settle_s"], "rows": rows}


def collapse_numbers(text):
    """json.dumps(indent) puts each number of an array on its own line; one line reads better."""
    return re.sub(r"\[\s*\n\s*(-?[\d.]+(?:,\s*\n\s*-?[\d.]+)*)\s*\n\s*\]",
                  lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text)


def build():
    ev = json.load(open(EVIDENCE))
    sha = pinned_sha()
    doc = {
        "schema": SCHEMA,
        "generated_by": "scripts/power_model.py from deps.lock's firmware and scripts/power_evidence.json; do not edit",
        "firmware": firmware(sha),
        "evidence": {
            "knobs_sweep": knobs_sweep(ev["sweeps"]["knobs"]),
            **ev["measured"],
        },
        "assumptions": ev["assumptions"],
        "scenarios": ev["scenarios"],
    }
    return collapse_numbers(json.dumps(doc, indent=1, ensure_ascii=False)) + "\n"


def oracle(outdir):
    """Build scripts/power_oracle.c against the pinned color.c, led_tables.c and battery.c's
    model_nj (extracted verbatim), and write hsv.bin and model.json for model.test.js."""
    sha = pinned_sha()
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as b:
        for path in ("quantum/color.c", "quantum/color.h", "quantum/led_tables.c", "quantum/led_tables.h"):
            open(os.path.join(b, os.path.basename(path)), "w").write(show(sha, path))
        open(os.path.join(b, "progmem.h"), "w").write(
            "#pragma once\n#define PROGMEM\n#define pgm_read_byte(p) (*(const unsigned char *)(p))\n")
        open(os.path.join(b, "util.h"), "w").write("#pragma once\n#define PACKED __attribute__((packed))\n")
        bc = show(sha, f"{KB}/battery.c")
        defs = re.findall(r"^#\s*define\s+(?:P_\w+_(?:UW|NW)|BKL_DUTY_FULL)\b.*$", bc, re.M)
        fn = re.findall(r"^static uint64_t model_nj\(.*?^\}\n", bc, re.M | re.S)
        if len(defs) != 8 or len(fn) != 1:
            die(f"battery.c: expected 8 model #defines and one model_nj, found {len(defs)} and {len(fn)}")
        open(os.path.join(b, "model_extract.h"), "w").write("\n".join(defs) + "\n\n" + fn[0])
        exe = os.path.join(b, "oracle")
        cc = subprocess.run(["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-DUSE_CIE1931_CURVE", f"-I{b}",
                             "-o", exe, ORACLE_C, os.path.join(b, "color.c"), os.path.join(b, "led_tables.c")],
                            capture_output=True, text=True)
        if cc.returncode != 0:
            die("the oracle did not build:\n" + cc.stderr)
        with open(os.path.join(outdir, "hsv.bin"), "wb") as f:
            f.write(subprocess.run([exe, "hsv"], capture_output=True, check=True).stdout)
        cases = model_cases()
        out = subprocess.run([exe, "model"], input="\n".join(" ".join(map(str, c)) for c in cases) + "\n",
                             capture_output=True, text=True, check=True).stdout.split()
        if len(out) != len(cases):
            die(f"the oracle answered {len(out)} of {len(cases)} model cases")
        json.dump({"sha": sha, "cases": [{"dt": c[0], "rgb_ms": c[1:4], "lit_ms": c[4], "duty": c[5], "usb": c[6],
                                          "nj": int(n)} for c, n in zip(cases, out)]},
                  open(os.path.join(outdir, "model.json"), "w"))
    print(f"oracle: fixtures for {sha[:10]} in {outdir}")


def model_cases():
    """dt, the three drive x ms sums, lit ms, duty, USB: one second, every duty, lit and dark,
    sums from nothing to every channel full, uneven ones, and a partly lit second."""
    leds = 81 * 255
    sums = [(0, 0, 0), (81, 81, 81), (leds, 0, 0), (0, leds, 0), (0, 0, leds), (leds, leds, leds),
            (81 * 48, 81 * 48, 81 * 48), (81 * 12, 0, 81 * 200), (12345, 678, 9), (1, 2, 3)]
    cases = []
    for duty in range(0, 49):
        for r, g, b in sums:
            for usb in (0, 1):
                lit = 0 if (r, g, b) == (0, 0, 0) else 1000
                cases.append((1000, r * 1000, g * 1000, b * 1000, lit, duty, usb))
    cases.append((1000, leds * 400, 0, 0, 400, 5, 0))   # lit for 400 ms of the second
    cases.append((60000, leds * 60000, leds * 60000, leds * 60000, 60000, 48, 1))   # a minute at full
    return cases


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if site/power/power.json differs from a fresh build")
    ap.add_argument("--oracle", metavar="DIR", help="build the C oracle and write its fixtures to DIR")
    a = ap.parse_args()
    if a.oracle:
        oracle(a.oracle)
        return
    text = build()
    if a.check:
        if not os.path.exists(OUT) or open(OUT).read() != text:
            die(f"{os.path.relpath(OUT, ROOT)} has drifted from a fresh build; run scripts/power_model.py")
        print("power.json: current")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
