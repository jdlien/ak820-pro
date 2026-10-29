#!/usr/bin/env python3
"""The configuration menu's S1 gate: C10 of plans/CONFIG-MENU-BUILD-PLAN.md
(revision 12), measured on a dev build with op 27 sub 10.

    venv-win/Scripts/python.exe scripts/menu_s1_gate.py [--out F] [--repeats 10] < /dev/null

In one armed interval:
  baseline     three 5 s dashboard windows, and ten of 500 ms
  sustained    5 s windows of paced A/B repaints, each settled in 1,000 ms
  transitions  Fn+D in, Fn+D out, the menu's open, a layout change and the
               close: ten each, 500 ms windows until the completion is seen,
               plus one
  health       the clock second's completion on the Health page, whose
               Uptime and ISR lines change every second, by C10's procedure
               (measured on the camera page until it was removed, 10-28)
  continuous   a detent every 50 ms for 10 s
The instrumentation is the same in every window: one poller reads sub 5 and
sub 10 every 100 ms, bracketed, and completions are judged from its reads
only. Every timeout fails the run; a run that fails any check isn't a
measurement and isn't reported as one. Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from menu_s0_session import mutate, open_device, read_state, xfer  # noqa: E402
from menu_s0_accept import dash_done, op1, to_dash  # noqa: E402
from ak820health import read_isr, read_stalls  # noqa: E402

BRACKET_S = 0.025          # a read's bracket over 25 ms is retried
# time.perf_counter() throughout: on Windows time.monotonic() ticks at ~15.6 ms,
# which failed 500 ms windows' timebase check by that much (the first run).
RETRIES = 3
POLL_S = 0.1               # the poller's period, every window alike
SUSTAINED_RATIO = 0.98
CONFIG_RATIO = 1.01
WINDOW_S = 0.5
WINDOW_RATIO = 0.95
KIND_MEAN_RATIO = 0.98
SETTLE_S = 1.0
DETENT_S = 0.05
BURST_S = 10.0
BUCKET_S = 0.5
CONT_FINAL_S = 0.5
PASS_MAX_US = 15000
FX_ROWS = 8
M32, M8 = 1 << 32, 1 << 8


class GateFail(Exception):
    pass


fails = []


def check(ok, what):
    if not ok:
        fails.append(what)
    return ok


def ensure(ok, what):
    if not ok:
        raise GateFail(what)


def bracketed(fn):
    """(value, midpoint, half bracket): retried past 25 ms, failing on the fourth."""
    for _ in range(RETRIES + 1):
        t0 = time.perf_counter()
        v = fn()
        t1 = time.perf_counter()
        if t1 - t0 <= BRACKET_S:
            return v, (t0 + t1) / 2, (t1 - t0) / 2
    raise GateFail(f"a read's bracket stayed over {BRACKET_S * 1000:.0f} ms")


def decode_meas(r):
    u16 = lambda i: r[i] | (r[i + 1] << 8)
    return {"piece_us": u16(6), "op_us": u16(8), "pass_max_us": u16(10), "over15": u16(12),
            "repaint_ms": u16(14), "tgen": r[16], "settled": r[17], "superseded": r[18],
            "band_ms": r[19], "page": r[20], "dbg_gen": r[21], "dbg_done_gen": r[22],
            "committed": r[23], "passes": u16(24), "token": u16(26), "health_gen": r[28],
            "dbg_sec": r[29], "rtc_sec": r[30], "aliased": bool(r[31] & 1)}


class Board:
    """Every read bracketed; the session's token and health generation held;
    the poller's latest state and measures."""

    def __init__(self, h):
        self.h = h
        self.token = self.hgen = None
        self.st = self.m = None
        self.next_poll = 0.0
        # Which step a pass over 15 ms came in: the poller's own reads, no
        # extra traffic (cbb51ac1's run failed with 20.3 ms from a path the
        # gate's F1 doesn't change).
        self.phase, self.over_log, self._over = "start", [], None

    def meas(self, arm=0):
        r, mid, half = bracketed(lambda: xfer(self.h, 10, bytes([arm])))
        m = decode_meas(r)
        m["t"], m["t1"] = mid, mid + half
        if self.token is not None and arm == 0:
            if m["token"] != self.token:
                raise GateFail(f"the session token changed ({self.token} -> {m['token']}): a reboot or a re-arm")
            if m["health_gen"] != self.hgen:
                raise GateFail("a health reset inside the measured interval")
            if m["aliased"]:
                raise GateFail("a pass of 340 ms or more: the interval's ticks are ambiguous")
        return m

    def arm(self):
        self.meas(1)
        m = self.meas()
        ensure(m["token"] != 0, "sub 10 issued no session token")
        self.token, self.hgen = m["token"], m["health_gen"]

    def state(self):
        s, mid, half = bracketed(lambda: read_state(self.h))
        s["t"], s["t1"] = mid, mid + half
        return s

    def poll(self, force=False):
        """The scheduled read: sub 5 and sub 10, every POLL_S."""
        now = time.perf_counter()
        if force or now >= self.next_poll:
            self.st = self.state()
            self.m = self.meas()
            if self._over is not None and self.m["over15"] != self._over:
                self.over_log.append({"phase": self.phase, "over15": self.m["over15"],
                                      "pass_max_us": self.m["pass_max_us"], "t": round(now, 3)})
            self._over = self.m["over15"]
            self.next_poll = max(self.next_poll + POLL_S, now + POLL_S / 2)
            return True
        return False

    def sample(self):
        isr, mid, half = bracketed(lambda: read_isr(self.h))
        stl, _, _ = bracketed(lambda: read_stalls(self.h))
        return {"t": mid, "half": half, "up": isr["uptime_ms"], "isr": isr["isr_entries"],
                "passes": stl["passes"], "ge10": stl["count_ge_10ms"], "ge25": stl["count_ge_25ms"]}

    def mutate(self, sub, args=b""):
        """A mutation, sent exactly once (never replayed like a read): its
        cause is the bracket's midpoint, and a bracket over 25 ms makes the
        trial uncertain, which fails the run. Its outcome is judged by the
        poller (last_seq, last_state)."""
        return self._once(lambda: mutate(self.h, sub, args), f"op 27 sub {sub}", check_status=True)

    def op1(self):
        return self._once(lambda: op1(self.h), "op 1")[1]

    def _once(self, fn, what, check_status=False):
        t0 = time.perf_counter()
        v = fn()
        t1 = time.perf_counter()
        ensure(t1 - t0 <= BRACKET_S, f"{what}: its bracket was {(t1 - t0) * 1000:.0f} ms, the trial uncertain")
        if check_status:
            st, seq = v
            ensure(st == 0, f"{what} refused: status {st}")
            return seq, (t0 + t1) / 2
        return v, (t0 + t1) / 2


def window_rate(a, b, label):
    """Entries a second over the board's time, with C10's per-field checks."""
    dup = (b["up"] - a["up"]) % M32
    dhost = b["t"] - a["t"]
    ensure(dup > 0 and dhost > 0, f"{label}: an empty window")
    dt = dup / 1000.0
    check(abs(dt - dhost) <= 0.02 * dhost + a["half"] + b["half"],
          f"{label}: the timebase, board {dt:.3f} s against host {dhost:.3f} s")
    de = (b["isr"] - a["isr"]) % M32
    rate = de / dt
    check(1000 <= rate <= 10000, f"{label}: the ISR rate {rate:.0f}/s is implausible")
    dp = (b["passes"] - a["passes"]) % M32
    check(dp <= 500 * dt, f"{label}: {dp} passes in {dt:.2f} s")
    check((b["ge10"] - a["ge10"]) % M32 <= dp and (b["ge25"] - a["ge25"]) % M32 <= dp,
          f"{label}: a ge count beyond the passes")
    return rate


def run_window(bd, secs, step=None):
    """A window of `secs`: the poller on schedule, and `step()` (the
    activity, driven by the poller's reads) after each poll."""
    a = bd.sample()
    end = time.perf_counter() + secs
    while time.perf_counter() < end:
        if bd.poll() and step:
            step()
        time.sleep(0.005)
    return a, bd.sample()


def evidence(bd):
    """(midpoint, end): the later of the two reads a judgement rests on."""
    return max(bd.st["t"], bd.m["t"]), max(bd.st["t1"], bd.m["t1"])


def wait_poll(bd, pred, deadline, what):
    """Poll on schedule until pred(st, m), with its evidence's reads ended
    by the deadline; returns the evidence's midpoint."""
    while True:
        bd.poll()
        if pred(bd.st, bd.m):
            mid, end = evidence(bd)
            ensure(end <= deadline, what)
            return mid
        if time.perf_counter() > deadline:
            raise GateFail(what)
        time.sleep(0.005)


def mutation_done(bd, seq, cause, what):
    wait_poll(bd, lambda st, m: st["last_seq"] == seq and st["last_state"] == "done",
              cause + SETTLE_S, f"{what}: not done within {SETTLE_S * 1000:.0f} ms")


def to_dash_checked(bd):
    ok, _ = to_dash(bd.h)
    ensure(ok, "the dashboard didn't come back to DONE")
    bd.poll(force=True)


def open_menu(bd):
    seq, cause = bd.mutate(4)
    mutation_done(bd, seq, cause, "the opening")
    tg = bd.m["tgen"]
    wait_poll(bd, lambda st, m: st["pixels_done"] and m["tgen"] == tg, cause + 3 * SETTLE_S,
              "the opening didn't settle")


def close_menu(bd):
    seq, cause = bd.mutate(4)
    mutation_done(bd, seq, cause, "the close")
    wait_poll(bd, lambda st, m: dash_done(st), cause + 5 * SETTLE_S, "the close's restore didn't finish")


def run(a):
    h = open_device()
    bd = Board(h)
    out = {"windows": [], "transitions": {}, "health_second": [], "continuous": {}, "timing": {}}
    try:
        to_dash(h)
        time.sleep(1.0)
        bd.arm()
        bd.poll(force=True)
        s_first = bd.sample()

        # Baseline: the poller alone.
        bd.phase = "baseline"
        base5 = [window_rate(*run_window(bd, 5.0), f"baseline {i}") for i in range(3)]
        base = sum(base5) / 3
        base05 = [window_rate(*run_window(bd, WINDOW_S), f"baseline 500ms {i}") for i in range(10)]
        b05 = sum(base05) / len(base05)
        out["baseline"] = {"rate_5s": base5, "rate_500ms": base05}

        # Sustained: paced A/B repaints, each settled within 1,000 ms of its cause.
        bd.phase = "sustained"
        open_menu(bd)
        pace = {"pat": 0, "cause": None, "tgen": None}

        def toggle_step():
            now = time.perf_counter()
            if pace["cause"] is not None:
                if bd.st["pixels_done"] and bd.m["tgen"] == pace["tgen"]:
                    ensure(evidence(bd)[1] <= pace["cause"] + SETTLE_S,
                           "a paced repaint settled after 1,000 ms")
                    pace["cause"] = None
                elif now > pace["cause"] + SETTLE_S:
                    raise GateFail("a paced repaint didn't settle within 1,000 ms")
                else:
                    return
            pace["pat"] ^= 1
            t0 = bd.m["tgen"]
            seq, cause = bd.mutate(0, bytes([pace["pat"], 0]))
            pace["cause"], pace["tgen"] = cause, (t0 + 1) % M8

        for i in range(2):
            r = window_rate(*run_window(bd, 5.0, toggle_step), f"sustained {i}")
            ratio = r / base
            out["windows"].append({"kind": "sustained", "rate": r, "ratio": ratio})
            check(ratio >= SUSTAINED_RATIO, f"sustained {i}: ratio {ratio:.3f} < {SUSTAINED_RATIO}")
            check(ratio <= CONFIG_RATIO, f"sustained {i}: ratio {ratio:.3f} > {CONFIG_RATIO}: check the configuration")
        if pace["cause"] is not None:
            wait_poll(bd, lambda st, m: st["pixels_done"], pace["cause"] + SETTLE_S,
                      "the last paced repaint didn't settle")
        close_menu(bd)

        # Transitions: 500 ms windows from the cause until the completion is
        # seen, then one more.
        def transition(kind, cause_fn, done):
            rec = out["transitions"].setdefault(kind, {"ms": [], "windows": []})
            bd.phase = kind
            prev = bd.sample()
            cause = cause_fn()
            completed, extra = None, False
            while True:
                end = time.perf_counter() + WINDOW_S
                was = completed is not None
                while time.perf_counter() < end:
                    if bd.poll() and completed is None and done(bd.st, bd.m):
                        completed, ended = evidence(bd)
                        ensure(ended <= cause + SETTLE_S, f"{kind}: completed after {SETTLE_S * 1000:.0f} ms")
                    time.sleep(0.005)
                b = bd.sample()
                rec["windows"].append(window_rate(prev, b, kind) / b05)
                prev = b
                if was:
                    break
                if completed is None and time.perf_counter() > cause + SETTLE_S:
                    raise GateFail(f"{kind}: no completion within {SETTLE_S * 1000:.0f} ms")
            ms = round((completed - cause) * 1000)
            rec["ms"].append(ms)
            check(ms <= SETTLE_S * 1000, f"{kind}: completed in {ms} ms")

        def debug_done_after(g0):
            return lambda st, m: st["owner"] == "debug" and m["dbg_gen"] != g0 and \
                m["dbg_done_gen"] == m["dbg_gen"] and st["debug_done"]

        def restore_after(rg0):
            return lambda st, m: dash_done(st) and st["restore_gen"] != rg0

        def menu_after(tg0, screen=None):
            return lambda st, m: st["pixels_done"] and m["tgen"] != tg0 and \
                (screen is None or st["screen"] == screen)

        for i in range(a.repeats):
            to_dash_checked(bd)
            g = bd.m["dbg_gen"]
            transition("fnd_in", bd.op1, debug_done_after(g))
            bd.poll(force=True)
            rg = bd.st["restore_gen"]
            transition("fnd_out", bd.op1, restore_after(rg))
            bd.poll(force=True)
            tg = bd.m["tgen"]
            transition("open", lambda: bd.mutate(4)[1], menu_after(tg))
            bd.poll(force=True)
            tg = bd.m["tgen"]
            transition("layout", lambda: bd.mutate(0, bytes([3, 0]))[1], menu_after(tg, screen=2))
            bd.poll(force=True)
            rg = bd.st["restore_gen"]
            transition("close", lambda: bd.mutate(4)[1], restore_after(rg))
        for kind, d in out["transitions"].items():
            d["mean"] = sum(d["windows"]) / len(d["windows"])
            check(d["mean"] >= KIND_MEAN_RATIO, f"{kind}: mean {d['mean']:.3f} < {KIND_MEAN_RATIO}")
            check(min(d["windows"]) >= WINDOW_RATIO, f"{kind}: a window at {min(d['windows']):.3f} < {WINDOW_RATIO}")

        # The Health page's clock second, by C10's procedure.
        bd.phase = "health_second"
        to_dash_checked(bd)
        bd.op1()
        wait_poll(bd, lambda st, m: m["page"] == 1 and st["debug_done"], time.perf_counter() + 3 * SETTLE_S,
                  "Health didn't settle")
        for _ in range(5):
            discards = 0
            while True:
                bd.poll(force=True)
                g0 = bd.m["dbg_gen"]
                S = (bd.m["rtc_sec"] + 1) % 60
                arrived = wait_poll(bd, lambda st, m: m["rtc_sec"] == S, time.perf_counter() + 1.5,
                                    "the expected second never came")
                wait_poll(bd, lambda st, m: m["dbg_gen"] != g0 and m["dbg_sec"] == S,
                          arrived + SETTLE_S, "no composition tagged with the second")
                done_at = wait_poll(bd, lambda st, m: (m["rtc_sec"] != S) or
                                    (m["dbg_done_gen"] == m["dbg_gen"] and st["debug_done"] and m["dbg_sec"] == S),
                                    arrived + SETTLE_S, "the second's composition wasn't painted in time")
                if bd.m["rtc_sec"] != S:   # the clock moved on first: discard, retry
                    discards += 1
                    ensure(discards < 3, "Health's second: three discards")
                    continue
                out["health_second"].append(round((done_at - arrived) * 1000))
                break
        bd.op1()   # Health to the dashboard
        wait_poll(bd, lambda st, m: dash_done(st), time.perf_counter() + 5 * SETTLE_S, "Health's exit didn't restore")

        bd.phase = "continuous"
        # Continuous: exactly 200 detents, one every 50 ms on absolute
        # deadlines; the committed count read by a forced poll at each 500 ms
        # boundary, the last before the post-burst settling.
        open_menu(bd)
        m0, row0 = bd.m, bd.st["cursor"]
        n_detents = int(round(BURST_S / DETENT_S))
        n_buckets = int(round(BURST_S / BUCKET_S))
        t0 = time.perf_counter()
        sent, late, t_last = 0, 0, t0
        marks = [m0["committed"]]   # the committed count at each boundary
        while sent < n_detents or len(marks) <= n_buckets:
            now = time.perf_counter()
            if sent < n_detents and now >= t0 + sent * DETENT_S:
                if now - (t0 + sent * DETENT_S) > DETENT_S / 2:
                    late += 1
                _, t_last = bd.mutate(1, bytes([1]))
                sent += 1
                continue
            if len(marks) <= n_buckets and now >= t0 + len(marks) * BUCKET_S:
                bd.poll(force=True)
                marks.append(bd.m["committed"])
                continue
            bd.poll()
            time.sleep(0.002)
        buckets = [(marks[i + 1] - marks[i]) % M8 for i in range(n_buckets)]

        def final_done(st, m):
            return st["pixels_done"] and st["cursor"] == (row0 + sent) % FX_ROWS
        settled_at = wait_poll(bd, final_done, t_last + CONT_FINAL_S,
                               "the burst's final target didn't settle in 500 ms")
        m1 = bd.m
        created = (m1["tgen"] - m0["tgen"]) % M8
        books = ((m1["settled"] - m0["settled"]) + (m1["superseded"] - m0["superseded"])) % M8
        final_ms = round((settled_at - t_last) * 1000)
        out["continuous"] = {"sent": sent, "late": late, "buckets": buckets, "created": created,
                             "books": books, "final_ms": final_ms}
        check(sent == n_detents, f"continuous: {sent} detents, not {n_detents}")
        check(late == 0, f"continuous: {late} detents more than 25 ms late")
        check(all(x > 0 for x in buckets), f"continuous: a 500 ms bucket committed nothing ({buckets})")
        check(final_ms <= CONT_FINAL_S * 1000, f"continuous: the final target in {final_ms} ms")
        check(created == books, f"continuous: {created} targets against {books} settled + superseded")
        close_menu(bd)

        # Timing over the whole armed interval.
        bd.phase = "end"
        to_dash_checked(bd)
        mfin = bd.meas()
        s_last = bd.sample()
        out["timing"] = mfin
        check(mfin["pass_max_us"] <= PASS_MAX_US, f"the longest pass {mfin['pass_max_us']} us > {PASS_MAX_US}")
        check(mfin["over15"] == 0, f"{mfin['over15']} passes over 15,000 us")
        check((s_last["ge25"] - s_first["ge25"]) % M32 == 0, "ge25 moved")
    except GateFail as e:
        fails.append(str(e))
    finally:
        h.close()
    out["over15_phases"] = bd.over_log
    out["failures"] = fails
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, default=str)
    if fails:
        print("FAILED, not a measurement:")
        for x in fails:
            print("  -", x)
        t = out.get("timing") or {}
        if t:
            print(f"  (timing read: longest pass {t.get('pass_max_us')} us, over 15 ms {t.get('over15')})")
        for o in out["over15_phases"]:
            print(f"  over 15 ms during {o['phase']}: count {o['over15']}, longest so far {o['pass_max_us']} us")
        return 1
    t = out["timing"]
    print(f"PASS: longest pass {t['pass_max_us']} us, piece {t['piece_us']} us, op {t['op_us']} us, "
          f"repaint {t['repaint_ms']} ms, band {t['band_ms']} ms")
    for w in out["windows"]:
        print(f"  sustained ratio {w['ratio']:.3f}")
    for k, d in out["transitions"].items():
        print(f"  {k:8} mean {d['mean']:.3f}, min {min(d['windows']):.3f}, completion ms {d['ms']}")
    print(f"  health second ms {out['health_second']}")
    print(f"  continuous {out['continuous']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_s1_gate.json")
    ap.add_argument("--repeats", type=int, default=10)
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
