#!/usr/bin/env python3
"""The configuration menu's S1 gate: C10 of plans/CONFIG-MENU-BUILD-PLAN.md
(revision 12), measured on a dev build with op 27 sub 10.

    venv-win/Scripts/python.exe scripts/menu_s1_gate.py [--out F] [--repeats 10] < /dev/null

It runs, in one armed interval:
  baseline     three 5 s dashboard windows, and 500 ms ones for transitions
  sustained    5 s windows of paced A/B repaints, each settled in 1,000 ms
  transitions  Fn+D in, Camera, Fn+D out, the menu's open and close, a layout
               change: ten each, in 500 ms windows until completion, plus one
  continuous   one detent every 50 ms for 10 s
and passes or fails on C10's numbers. Every timeout fails the run; a run
that fails any check isn't a measurement and isn't reported as one. Never
enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s0_accept import dash_done, op1, to_dash  # noqa: E402
from ak820health import read_isr, read_stalls  # noqa: E402

BRACKET_S = 0.025          # C10: a read's bracket over 25 ms is retried
RETRIES = 3
SUSTAINED_RATIO = 0.98
CONFIG_RATIO = 1.01
WINDOW_RATIO = 0.95
KIND_MEAN_RATIO = 0.98
SETTLE_S = 1.0
CONT_FINAL_S = 0.5
PASS_MAX_US = 15000
FX_ROWS = 8
M32, M16, M8 = 1 << 32, 1 << 16, 1 << 8


class GateFail(Exception):
    pass


fails = []


def check(ok, what):
    if not ok:
        fails.append(what)
    return ok


def bracketed(fn):
    """(value, midpoint, half bracket): retried past 25 ms, failing on the fourth."""
    for _ in range(RETRIES + 1):
        t0 = time.monotonic()
        v = fn()
        t1 = time.monotonic()
        if t1 - t0 <= BRACKET_S:
            return v, (t0 + t1) / 2, (t1 - t0) / 2
    raise GateFail(f"a read's bracket stayed over {BRACKET_S * 1000:.0f} ms")


def meas(h, arm=0):
    r = xfer(h, 10, bytes([arm]))
    u16 = lambda i: r[i] | (r[i + 1] << 8)
    return {"piece_us": u16(6), "op_us": u16(8), "pass_max_us": u16(10), "over15": u16(12),
            "repaint_ms": u16(14), "tgen": r[16], "settled": r[17], "superseded": r[18],
            "band_ms": r[19], "page": r[20], "dbg_gen": r[21], "dbg_done_gen": r[22],
            "committed": r[23], "passes": u16(24), "token": u16(26), "health_gen": r[28],
            "dbg_sec": r[29], "rtc_sec": r[30]}


class Session:
    """The armed interval: the token and the health-reset generation held."""

    def __init__(self, h):
        self.h = h
        meas(h, 1)
        m = meas(h)
        if not m["token"]:
            raise GateFail("sub 10 issued no session token")
        self.token, self.hgen = m["token"], m["health_gen"]

    def m(self):
        v = meas(self.h)
        if v["token"] != self.token:
            raise GateFail(f"the session token changed ({self.token} -> {v['token']}): a reboot or a re-arm")
        if v["health_gen"] != self.hgen:
            raise GateFail("a health reset inside the measured interval")
        return v


def sample(h):
    """The row ISR's page and the stall page, each bracketed."""
    isr, mid, half = bracketed(lambda: read_isr(h))
    st, _, _ = bracketed(lambda: read_stalls(h))
    return {"t": mid, "half": half, "up": isr["uptime_ms"], "isr": isr["isr_entries"],
            "passes": st["passes"], "ge10": st["count_ge_10ms"], "ge25": st["count_ge_25ms"]}


def window_rate(a, b, label):
    """Entries per second over the board's time, with C10's per-field checks."""
    dup = (b["up"] - a["up"]) % M32
    dhost = b["t"] - a["t"]
    if dup == 0 or dhost <= 0:
        raise GateFail(f"{label}: an empty window")
    dt = dup / 1000.0
    tol = 0.02 * dhost + a["half"] + b["half"]
    check(abs(dt - dhost) <= tol, f"{label}: the timebase, board {dt:.3f} s against host {dhost:.3f} s")
    de = (b["isr"] - a["isr"]) % M32
    rate = de / dt
    check(1000 <= rate <= 10000, f"{label}: the ISR rate {rate:.0f}/s is implausible")
    dp = (b["passes"] - a["passes"]) % M32
    check(dp <= 500 * dt, f"{label}: {dp} passes in {dt:.2f} s")
    check((b["ge10"] - a["ge10"]) % M32 <= dp and (b["ge25"] - a["ge25"]) % M32 <= dp,
          f"{label}: a ge count beyond the passes (a health reset?)")
    return rate


def timed_window(h, secs, during=None, poll=None):
    """One window: `during` repeatedly, else `poll` every 100 ms."""
    a = sample(h)
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if during:
            during()
        else:
            if poll:
                poll()
            time.sleep(0.1)
    return a, sample(h)


def ensure(ok, what):
    if not ok:
        raise GateFail(what)


def settle_menu(h, s, tgen, deadline_s, label):
    """pixels_done for target `tgen` within the deadline."""
    end = time.monotonic() + deadline_s
    while True:
        st = read_state(h)
        m = s.m()
        if st["pixels_done"] and m["tgen"] == tgen:
            return
        if time.monotonic() > end:
            raise GateFail(f"{label}: not settled within {deadline_s * 1000:.0f} ms")


def run(a):
    h = open_device()
    out = {"windows": [], "transitions": {}, "continuous": {}, "timing": {}}
    try:
        to_dash(h)
        time.sleep(1.0)
        s = Session(h)
        st0 = sample(h)

        # Baseline: three 5 s windows, and ten 500 ms ones, polling as the
        # activity windows do.
        poll = lambda: (read_state(h), s.m())
        base5 = [window_rate(*timed_window(h, 5.0, poll=poll), f"baseline {i}") for i in range(3)]
        base = sum(base5) / len(base5)
        base05 = [window_rate(*timed_window(h, 0.5, poll=poll), f"baseline 500ms {i}") for i in range(10)]
        b05 = sum(base05) / len(base05)
        out["baseline"] = {"rate_5s": base5, "rate_500ms": base05}

        # Sustained: paced A/B repaints, each settled within 1,000 ms.
        st, seq = mutate(h, 4)
        ensure(st == 0 and wait(h, seq)[0] == "done", "the menu didn't open")
        settle_menu(h, s, s.m()["tgen"], SETTLE_S * 3, "the opening")
        pat = [0]

        def toggle():
            pat[0] ^= 1
            st, seq = mutate(h, 0, bytes([pat[0], 0]))
            ensure(st == 0 and wait(h, seq)[0] == "done", "a pattern change was refused")
            settle_menu(h, s, s.m()["tgen"], SETTLE_S, "a paced repaint")

        for i in range(2):
            r = window_rate(*timed_window(h, 5.0, during=toggle), f"sustained {i}")
            ratio = r / base
            out["windows"].append({"kind": "sustained", "rate": r, "ratio": ratio})
            check(ratio >= SUSTAINED_RATIO, f"sustained {i}: ratio {ratio:.3f} < {SUSTAINED_RATIO}")
            check(ratio <= CONFIG_RATIO, f"sustained {i}: ratio {ratio:.3f} > {CONFIG_RATIO}: check the configuration")
        st, seq = mutate(h, 4)   # close
        wait(h, seq)

        # Transitions: windows of 500 ms until the completion is observed,
        # plus one more.
        def transition(kind, cause, done):
            windows = []
            a0 = sample(h)
            t0 = time.monotonic()
            cause()
            completed = False
            extra = False     # the one window after the completion's
            prev = a0
            while True:
                end = time.monotonic() + 0.5
                was_completed = completed
                while time.monotonic() < end:
                    if not completed and done():
                        completed = True
                        ms = round((time.monotonic() - t0) * 1000)
                        out["transitions"].setdefault(kind, {}).setdefault("ms", []).append(ms)
                        check(ms <= SETTLE_S * 1000, f"{kind}: completed in {ms} ms > {SETTLE_S * 1000:.0f}")
                    time.sleep(0.02)
                b = sample(h)
                windows.append(window_rate(prev, b, kind) / b05)
                prev = b
                if was_completed:
                    extra = True
                if extra:
                    break
                if not completed and time.monotonic() - t0 > SETTLE_S:
                    raise GateFail(f"{kind}: no completion within {SETTLE_S * 1000:.0f} ms")
            for w in windows:
                check(w >= WINDOW_RATIO, f"{kind}: a 500 ms window at {w:.3f} < {WINDOW_RATIO}")
            out["transitions"].setdefault(kind, {}).setdefault("windows", []).extend(windows)

        def restore_done(gen0):
            return lambda: (lambda st: st["owner"] == "dash" and st["phase"] == "done"
                            and st["restore_gen"] != gen0)(read_state(h))

        def debug_done(gen0):
            def f():
                m = s.m()
                st = read_state(h)
                return m["dbg_gen"] != gen0 and m["dbg_done_gen"] == m["dbg_gen"] and \
                    xfer(h, 5)[31] & 1 == 1 and st["owner"] == "debug"
            return f

        def menu_done(tg0):
            return lambda: (lambda st, m: st["pixels_done"] and m["tgen"] != tg0)(read_state(h), s.m())

        for i in range(a.repeats):
            to_dash(h)
            time.sleep(0.5)
            g = s.m()["dbg_gen"]
            transition("fnd_in", lambda: op1(h), debug_done(g))
            g = s.m()["dbg_gen"]
            transition("camera", lambda: op1(h), debug_done(g))
            rg = read_state(h)["restore_gen"]
            transition("fnd_out", lambda: op1(h), restore_done(rg))
            tg = s.m()["tgen"]
            transition("open", lambda: wait(h, mutate(h, 4)[1]), menu_done(tg))
            tg = s.m()["tgen"]
            transition("layout", lambda: wait(h, mutate(h, 0, bytes([3, 0]))[1]), menu_done(tg))
            rg = read_state(h)["restore_gen"]
            transition("close", lambda: wait(h, mutate(h, 4)[1]), restore_done(rg))
        for kind, d in out["transitions"].items():
            mean = sum(d["windows"]) / len(d["windows"])
            d["mean"] = mean
            check(mean >= KIND_MEAN_RATIO, f"{kind}: mean {mean:.3f} < {KIND_MEAN_RATIO}")

        # Continuous input: one detent every 50 ms for 10 s.
        to_dash(h)
        st, seq = mutate(h, 4)
        wait(h, seq)
        settle_menu(h, s, s.m()["tgen"], SETTLE_S * 3, "the opening")
        st0m = s.m()
        row0 = read_state(h)["cursor"]
        sent, buckets, last_bucket_c = 0, [], st0m["committed"]
        t0 = time.monotonic()
        next_read = t0
        bucket_end = t0 + 0.5
        while time.monotonic() - t0 < 10.0:
            st, seq = mutate(h, 1, bytes([1]))
            ensure(st == 0, "a detent was refused")
            ensure(wait(h, seq)[0] == "done", "a detent didn't complete")
            sent += 1
            if time.monotonic() >= next_read:
                m = s.m()
                next_read = time.monotonic() + 0.1
                if time.monotonic() >= bucket_end:
                    buckets.append((m["committed"] - last_bucket_c) % M8)
                    last_bucket_c = m["committed"]
                    bucket_end += 0.5
            time.sleep(max(0.0, 0.05 - 0.005))
        t_last = time.monotonic()
        settle_menu(h, s, s.m()["tgen"], CONT_FINAL_S, "the burst's final target")
        m1 = s.m()
        row1 = read_state(h)["cursor"]
        created = (m1["tgen"] - st0m["tgen"]) % M8
        books = ((m1["settled"] - st0m["settled"]) + (m1["superseded"] - st0m["superseded"])) % M8
        out["continuous"] = {"sent": sent, "buckets": buckets, "created": created, "books": books,
                             "final_ms": round((time.monotonic() - t_last) * 1000), "row": [row0, row1]}
        check(all(b > 0 for b in buckets), f"continuous: a 500 ms bucket committed nothing ({buckets})")
        check(row1 == (row0 + sent) % FX_ROWS, f"continuous: the cursor {row1}, expected {(row0 + sent) % FX_ROWS}")
        check(created == books, f"continuous: {created} targets against {books} settled + superseded")
        st, seq = mutate(h, 4)
        wait(h, seq)

        # Timing over the whole armed interval.
        to_dash(h)
        mfin = s.m()
        stfin = sample(h)
        out["timing"] = mfin
        check(mfin["pass_max_us"] <= PASS_MAX_US, f"the longest pass {mfin['pass_max_us']} us > {PASS_MAX_US}")
        check(mfin["over15"] == 0, f"{mfin['over15']} passes over 15,000 us")
        check((stfin["ge25"] - st0["ge25"]) % M32 == 0, "ge25 moved")
    except GateFail as e:
        fails.append(str(e))
    finally:
        h.close()
    out["failures"] = fails
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, default=str)
    if fails:
        print("FAILED, not a measurement:")
        for x in fails:
            print("  -", x)
        return 1
    t = out["timing"]
    print(f"PASS: longest pass {t['pass_max_us']} us, piece {t['piece_us']} us, op {t['op_us']} us, "
          f"repaint {t['repaint_ms']} ms, band {t['band_ms']} ms")
    for k, d in out["transitions"].items():
        print(f"  {k:8} mean {d['mean']:.3f}, min {min(d['windows']):.3f}, completion ms {d.get('ms')}")
    print(f"  continuous {out['continuous']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_s1_gate.json")
    ap.add_argument("--repeats", type=int, default=10)
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
