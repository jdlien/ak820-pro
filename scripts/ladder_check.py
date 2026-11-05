#!/usr/bin/env python3
"""Phase 2's ladder on the board (plans/PHASE2-BUILD-PLAN.md, validation), and
Power saver's ceiling (plans/POWER-MODES-REVISION-PLAN.md, validation 4):
every enabled lighting effect, its stages and its ceiling forced over
HC_DEVHOOK op 14, with the board's own LED drive read back (the committed
frames, ak820battery's `led drive`).

    venv/bin/python scripts/ladder_check.py [--rig | --presser] [--out DIR]

Two parts, on USB (the cable): a held stage ignores the battery-only rule, and
so does the ceiling it takes, so the relay can stay on. Every effect runs at
speed 255, so the animated ones cycle within a sample's second.

1. **The stages**, in Always on at hue 191, sat 255, value 255: active, dim,
   off, dark, active again. Codex's implementation review, must-fix 1: an
   effect that rewrites only some LEDs a frame (Jellybean Raindrops) must
   still go dark at once on the off stages, and come back whole on the wake.
   Pass: active lit (at least MIN_LIT); off and dark exactly 0.0%; dim below
   active; the second active within 20% of the first (a fixed tolerance:
   animated effects move).
2. **Power saver's ceiling:** ACTIVE held in Always on (the reference) and in
   Power saver, at value 255 and at 100. Pass, the reference lit in both:
   - at 255, Saver at or below Always on (within ANIM_TOL for the animated
     effects), and for the effects that convert at the user's value (solid,
     Alphas/Mods, the cycles, Jellybean) at most CAPPED_MAX of it (QMK's CIE
     curve's ceiling is 18.6% of full light); DRIFT the same since D9,
     at most DRIFT_MAX;
   - at 100, under the ceiling, Saver matches Always on for every effect,
     DRIFT included (within ANIM_TOL for the animated effects);
   - solid white at 255 in Saver within 5% of solid white at Saver's ceiling in Always on,
     itself at least MIN_WHITE.

Every hold also reads op 14 back after a tick: the mode, the stage held, and
the ceiling the firmware says it applies (255, DIM_CAP, SAVER_CAP).

Drive is the mean of a hold's samples, each a separate second of committed
frames (the board updates the figure once a second, so samples are spaced
SPACING s). Typing Heatmap lights only keys that are pressed: with --rig the
relay's key (relay 1, F19 to the Mac) is tapped before each of its samples
and its reference must be lit; without, its readings are printed, not judged,
and the run ends INCOMPLETE (exit 2), not passed.

JD's lighting, the stage held at the start (usually none) and the mode are
restored in a `finally`, each step on its own; a failed restore exits 1.
Needs a dev build with op 14. The LEDs change visibly for ~18 minutes.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import current_map as cm  # noqa: E402  (set_rgb, read_rgb, force_stage, power_mode, power_state, led_drive)
import deep_sleep as ds  # noqa: E402  (with_dev: the board's raw HID, retried)
import sleep_baseline as sb  # noqa: E402  (attempt, the relay)

EFFECTS = {1: "solid", 2: "alphas mods (JD's)", 3: "cycle all", 4: "cycle left-right", 5: "cycle up-down",
           6: "jellybean raindrops", 7: "typing heatmap", 8: "rain (custom)", 9: "rain rgb (custom)", 10: "drift (custom)"}
CONVERTED = {1, 2, 3, 4, 5, 6}   # every LED at the user's value, so the CIE ratio holds
HEATMAP, RAIN, RAINRGB, DRIFT = 7, 8, 9, 10
FULL, SAVER = 0, 2               # power.c's POWER_MODE_FULL, POWER_MODE_SAVER
STAGES = ["active", "dim", "off", "dark", "active"]
DIM_CAP, SAVER_CAP = 102, 191    # power.c's DIM_VAL and SAVER_VAL on the row ISR branch (64 and 128 through v0.3.1)
PRESSER_START = 10               # s: presser_repl.py pausing the logger and entering the REPL
UNDER = 180                      # a value under Saver's ceiling, bright enough for the Heatmap's one key to read
STAGE_CAP = {"active": 255, "dim": DIM_CAP, "off": 255, "dark": 255}   # op 14's value ceiling, in Always on
SPEED = 255
SETTLE = 3
SPACING = 1.2                    # s between samples: the drive figure is a second's
SAMPLES_STAGE = 3
SAMPLES_SAVER = 8
ANIM_TOL = 0.25                  # and 15 per mille: two holds of a moving or random field
CAPPED_MAX = 0.35                # expected 18.6% of full light
DRIFT_MAX = CAPPED_MAX            # the flush caps every effect alike since D9
MIN_LIT = {255: 20, UNDER: 2}    # per mille: a lit reference at each value (purple at 255 reads ~500)
# The Heatmap lights only the rig's one tapped key of 81: measured 10-20 at
# 6.7 per mille over a stage's holds and 1.9 at value 100, so the floor that
# fits a field of lit keys can never pass it.
MIN_LIT_HEATMAP = {255: 4, UNDER: 0.5}


# Drift's stops top out near a quarter of full chroma and most of its field is dark:
# measured 16-25 per mille at 255 and about 2 at UNDER.
MIN_LIT_DRIFT = {255: 10, UNDER: 1}


def min_lit(eff, v):
    return (MIN_LIT_HEATMAP if eff == HEATMAP else MIN_LIT_DRIFT if eff == DRIFT else MIN_LIT)[v]
MIN_WHITE = 100                  # per mille: white at Saver's ceiling (measured 186)


def tol(eff, ref):
    return max(15, ref * ANIM_TOL) if eff in ANIMATED else max(2, ref * 0.03)


class Bench:
    def __init__(self, press=None, presser=False):
        self.rig = press   # a key tap through relay 1, or None
        self.presser = presser   # the logger's presser on Delete

    def set(self, rgb=None, mode=None, stage=0):
        def go(h):
            if rgb is not None:
                cm.set_rgb(h, dict(rgb, speed=SPEED))
            if mode is not None:
                cm.power_mode(h, mode)
            cm.force_stage(h, stage)
        ds.with_dev(go)

    def state(self):
        time.sleep(0.3)   # op 14's set lands at power.c's next 10 Hz tick
        return ds.with_dev(cm.power_state)

    def drive(self, eff, n):
        """The hold: SETTLE s, then n samples SPACING s apart, per mille; the
        Heatmap's key tapped before each if there is a rig. The presser's tool
        takes seconds to start and to leave (it pauses the logger on the same
        QT Py), and the heat decays in 6 s, so it presses through the samples."""
        pressing = None
        if self.presser and eff == HEATMAP:
            count = int((PRESSER_START + SETTLE + n * SPACING + 2) * 10)   # 100 ms a press
            pressing = subprocess.Popen([sys.executable, os.path.join(HERE, "presser_repl.py"), "batch", "A1", str(count), "40", "60"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(PRESSER_START)
        time.sleep(SETTLE)
        got = []
        for k in range(n):
            if k:
                time.sleep(SPACING)
            if self.rig is not None and eff == HEATMAP:
                for _ in range(4):
                    self.rig()
            got.append(cm.led_drive())
        if pressing is not None:
            pressing.wait()
        if None in got:
            raise SystemExit("the board's LED drive did not read back")
        return sum(got) / len(got)


def judged(eff, b):
    return eff != HEATMAP or b.rig is not None or b.presser


def stages_pass(b, rows):
    bad = 0
    for eff, name in EFFECTS.items():
        got, caps = [], []
        for k, stage in enumerate(STAGES):
            want = STAGES.index(stage) if stage != "active" else 0
            b.set({"effect": eff, "h": 191, "s": 255, "v": 255} if k == 0 else None, FULL if k == 0 else None, want)
            st = b.state()
            caps.append(st["mode"] == FULL and st["stage"] == want and st["forced"] == want
                        and st["val_cap"] == STAGE_CAP[stage])
            got.append(b.drive(eff, SAMPLES_STAGE))
        act, dim, off, dark, back = got
        drive_ok = (act >= min_lit(eff, 255) and off == 0 and dark == 0 and dim < act
                    and abs(back - act) <= max(20, act * 0.2))
        ok = all(caps) and (drive_ok or not judged(eff, b))
        bad += not ok
        rows.append({"part": "stages", "effect": eff, "name": name, "active": act, "dim": dim, "off": off,
                     "dark": dark, "wake": back, "op14": all(caps), "judged": judged(eff, b), "ok": ok})
        print(f"{eff} {name:22} active {act / 10:5.1f}%  dim {dim / 10:5.1f}%  off {off / 10:4.1f}%  "
              f"dark {dark / 10:4.1f}%  wake {back / 10:5.1f}%  op 14 {'ok' if all(caps) else 'WRONG'}  "
              f"{'ok' if ok else 'FAIL'}{'' if judged(eff, b) else ' (not judged: no --rig)'}")
    return bad


def held(b, rgb, mode, want_cap, n=SAMPLES_SAVER):
    """ACTIVE held in `mode` at `rgb`: (drive, op 14 agrees)."""
    b.set(rgb, mode, 0)
    st = b.state()
    agree = st["mode"] == mode and st["stage"] == 0 and st["forced"] == 0 and st["val_cap"] == want_cap
    return b.drive(rgb["effect"], n), agree


def saver_pass(b, rows):
    bad = 0
    for v in (255, UNDER):
        for eff, name in EFFECTS.items():
            rgb = {"effect": eff, "h": 191, "s": 255, "v": v}
            ref, ok1 = held(b, rgb, FULL, 255)
            sav, ok2 = held(b, rgb, SAVER, SAVER_CAP)
            t = tol(eff, ref)
            if v == 255:
                drive_ok = sav <= ref + t
                if eff in CONVERTED:
                    drive_ok = drive_ok and sav <= ref * CAPPED_MAX + 2
                if eff in (RAIN, RAINRGB, DRIFT):
                    drive_ok = drive_ok and sav <= ref * DRIFT_MAX + 2
            else:
                drive_ok = abs(sav - ref) <= t
            drive_ok = drive_ok and ref >= min_lit(eff, v)
            ok = ok1 and ok2 and (drive_ok or not judged(eff, b))
            bad += not ok
            rows.append({"part": "saver", "value": v, "effect": eff, "name": name, "full": ref, "saver": sav,
                         "op14": ok1 and ok2, "judged": judged(eff, b), "ok": ok})
            print(f"v{v:<3} {eff} {name:22} Always on {ref / 10:5.1f}%  Power saver {sav / 10:5.1f}%"
                  f"  ({sav / ref if ref else 0:4.2f})  op 14 {'ok' if ok1 and ok2 else 'WRONG'}  "
                  f"{'ok' if ok else 'FAIL'}{'' if judged(eff, b) else ' (not judged: no --rig)'}")
    w128, ok1 = held(b, {"effect": 1, "h": 0, "s": 0, "v": SAVER_CAP}, FULL, 255)
    w255, ok2 = held(b, {"effect": 1, "h": 0, "s": 0, "v": 255}, SAVER, SAVER_CAP)
    ok = ok1 and ok2 and w128 >= MIN_WHITE and abs(w255 - w128) <= w128 * 0.05
    bad += not ok
    rows.append({"part": "white", "full_128": w128, "saver_255": w255, "op14": ok1 and ok2, "ok": ok})
    print(f"white: Always on at {SAVER_CAP} {w128 / 10:5.1f}%, Power saver at 255 {w255 / 10:5.1f}%  {'ok' if ok else 'FAIL'}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rig", action="store_true", help="tap the relay's key through the Heatmap's holds")
    ap.add_argument("--presser", action="store_true", help="the same with the logger's presser on Delete (scripts/presser_repl.py); the relay's key is broken since the move to Buzz")
    ap.add_argument("--only", default=None, help="comma-separated effect numbers: a rerun of a few, not the whole check")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "history", "ladder-check-" + time.strftime("%Y%m%d-%H%M")))
    a = ap.parse_args()
    jd_rgb, jd_mode = ds.with_dev(cm.read_rgb), ds.with_dev(cm.power_mode)
    if jd_mode is None:
        sys.exit("no HC_DEVHOOK op 14 on this firmware: flash a dev build first")
    jd_forced = ds.with_dev(cm.power_state)["forced"]
    print(f"start: lighting {jd_rgb}, power mode {jd_mode}, stage held {jd_forced}")
    relay = None
    if a.rig:
        import hid
        devs = hid.enumerate(sb.VID, sb.PID)
        if len(devs) != 1:
            sys.exit(f"expected one USB relay, found {len(devs)}")
        relay = hid.Device(path=devs[0]["path"])   # one handle: macOS opens it exclusively
    rows, bad, restored = [], 0, True
    try:
        if a.only:
            keep = {int(x) for x in a.only.split(",")}
            for e in [e for e in EFFECTS if e not in keep]:
                del EFFECTS[e]
        b = Bench((lambda: sb.press(relay, 40, 120)) if relay is not None else None, presser=a.presser)
        bad += stages_pass(b, rows)
        bad += saver_pass(b, rows)
    finally:
        # Each step on its own, so one failure cannot skip the rest.
        steps = []
        if relay is not None:
            steps.append(sb.attempt("relay 1 open", sb.bounded, sb.relay1, relay, False))
            steps.append(sb.attempt("the relay closed", relay.close))
        steps += [
            sb.attempt("the stage", ds.with_dev, cm.force_stage, None if jd_forced == 0xFF else jd_forced),
            sb.attempt("the lighting", ds.with_dev, cm.set_rgb, dict(jd_rgb)),
            sb.attempt("the mode", ds.with_dev, cm.power_mode, jd_mode),
        ]
        restored = all(steps)
        try:
            st = ds.with_dev(cm.power_state)
            print(f"restored: lighting {ds.with_dev(cm.read_rgb)}, power mode {st['mode']}, stage held {st['forced']}"
                  + ("" if restored else "  ⚠️ NOT every step"))
        except BaseException as e:
            restored = False
            print(f"⚠️ the restore could not be read back: {e}")
    os.makedirs(a.out, exist_ok=True)
    incomplete = not (a.rig or a.presser)
    with open(os.path.join(a.out, "ladder-check.json"), "w") as f:
        json.dump({"rows": rows, "rig": a.rig or a.presser, "restored": restored, "incomplete": incomplete,
                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
    if bad or not restored:
        print("ladder check:", f"{bad} FAILED" if bad else "passed, but the restore FAILED")
        sys.exit(1)
    if incomplete:
        print("ladder check: INCOMPLETE -- everything judged passed, but the Heatmap was not judged (no --rig or --presser)")
        sys.exit(2)
    print("ladder check: all pass")
    sys.exit(0)


if __name__ == "__main__":
    main()
