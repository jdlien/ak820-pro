#!/usr/bin/env python3
"""The configuration menu's S0 workload (plans/CONFIG-MENU-BUILD-PLAN.md, S0's
proof): a fixed 50-step array of op 27 mutations, run ten times, each sent when
the last is terminal, polling sub 5 every 20 ms; then the dashboard for five
minutes, which should have a track playing. It records every outcome and every
transition seen while polling, and the stall counters before and after, with no
reset inside the measured span. It fails on a step's unexpected outcome or
state, a timeout, an invariant failure, a final state other than the dashboard
restored, or any pass of 25 ms or more. Dev builds only (HC_DEVHOOK).

    venv-win/Scripts/python.exe scripts/menu_s0_session.py [--repeats N] [--dashboard-s S] [--out F] < /dev/null

Also the op 27 codec the S0 tests use: `read_state`, `mutate`, `wait`.
Never enumerates HID on Windows (ak820health.open_device)."""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from ak820health import open_device  # noqa: E402

SET_VALUE, CH, HC, OP = 0x07, 0x13, 0x76, 27
OK, BUSY, BAD = 0, 1, 2
STATES = ["none", "pending", "done", "cancelled", "superseded", "refused"]
OWNERS = ["dash", "debug", "menu", "anim"]
SESSIONS = ["none", "pending", "open"]
PHASES = ["splash", "waiting", "clear", "stages", "residual", "done"]
LATCHES = ["none", "click", "back", "close"]
TERMINAL = {2, 3, 4, 5}


def xfer(h, sub, args=b""):
    """One op 27 report; the reply matched by channel, command, op and sub,
    since Windows delivers every input report to every open handle."""
    h.write(bytes([0, SET_VALUE, CH, HC, OP, sub]) + args + bytes(27 - len(args)))
    end = time.monotonic() + 3.0   # a deadline, not a count: other handles' replies land here too
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == OP and r[4] == sub:
            if r[0] != SET_VALUE:
                raise RuntimeError(f"op 27 sub {sub}: unhandled (byte 0 = {r[0]:#x})")
            return bytes(r)
    raise RuntimeError(f"op 27 sub {sub}: no reply")


def u16(b, i):
    return b[i] | (b[i + 1] << 8)


def read_state(h):
    r = xfer(h, 5)
    f = r[16]
    return {
        "last_seq": r[6], "last_state": STATES[r[7]] if r[7] < len(STATES) else r[7],
        "owner": OWNERS[r[8]], "session": SESSIONS[r[9]],
        "restore_gen": u16(r, 10), "phase": PHASES[r[12]], "damaged": bool(r[13]),
        "screen": r[14], "cursor": r[15],
        "armed": bool(f & 1), "edit": bool(f & 2), "pixels_done": bool(f & 4),
        "dma_busy": bool(f & 8), "clearing": bool(f & 16), "wake_hold": bool(f & 32),
        "batt_dirty": bool(f & 64), "logo_stale": bool(f & 128),
        "gq": r[17] & 15, "lq": r[17] >> 4,
        "turns": r[18] - 256 if r[18] > 127 else r[18], "latch": LATCHES[r[19]],
        "dropped": r[20], "unsettled": r[21], "losses": r[22], "capture": r[23],
        "invariant_fail": u16(r, 24), "paint_us": u16(r, 26), "pairing": r[28],
        "ops": r[29], "stopped": bool(r[30] & 1),
    }


def mutate(h, sub, args=b""):
    """(status, seq): 0 accepted, 1 busy, 2 a bad argument or state."""
    r = xfer(h, sub, args)
    return r[5], r[6]


WATCHED = ("owner", "session", "screen", "cursor", "phase", "restore_gen")


def wait(h, seq, timeout=5.0, poll=0.02, seen=None):
    """Until the outstanding mutation `seq` is terminal; its state, and the
    board's state as last read. Every change of the watched fields seen while
    polling is appended to `seen`."""
    end = time.monotonic() + timeout
    last = None
    while True:
        s = read_state(h)
        snap = tuple(s[k] for k in WATCHED)
        if seen is not None and snap != last:
            seen.append(dict(zip(WATCHED, snap)))
            last = snap
        if s["last_seq"] == seq and STATES.index(s["last_state"]) in TERMINAL:
            return s["last_state"], s
        if time.monotonic() > end:
            return "timeout", s
        time.sleep(poll)


def wait_restored(h, timeout=10.0, poll=0.02, seen=None):
    """Until the dashboard's restore is DONE under the dashboard, no session.
    Every change of the watched fields is appended to `seen`."""
    end = time.monotonic() + timeout
    last = None
    while True:
        s = read_state(h)
        snap = tuple(s[k] for k in WATCHED)
        if seen is not None and snap != last:
            seen.append(dict(zip(WATCHED, snap)))
            last = snap
        if s["owner"] == "dash" and s["session"] == "none" and s["phase"] == "done":
            return True, s
        if time.monotonic() > end:
            return False, s
        time.sleep(poll)


# The fixed 50 steps (CONFIG-MENU-BUILD-PLAN, S0): 28 turns, 10 clicks (two
# A/B toggles, two trips to F2 and back, two Diagnostics handoffs and
# returns), 4 holds of 650 ms, 4 Fn plus a click, 2 restores, 2 losses. Each
# starts and ends with the fixture open on F1 at row 0. A step is (kind, arg,
# the owner, screen and cursor expected after it; None: not checked).
F1, F2 = 1, 2
STEPS = [
    ("turns", 3, ("menu", F1, 3)), ("turns", -3, ("menu", F1, 0)),
    ("click", 0, ("menu", F1, 0)), ("click", 0, ("menu", F1, 0)),              # A to B, B to A
    ("turns", 4, ("menu", F1, 4)), ("turns", 2, ("menu", F1, 6)),
    ("click", 0, ("menu", F2, None)), ("click", 0, ("menu", F1, 6)),           # F2 and back
    ("turns", 1, ("menu", F1, 7)),
    ("click", 0, ("debug", None, None)), ("click", 0, ("menu", F1, 7)),        # Diagnostics and back
    ("turns", 1, ("menu", F1, 0)),
    ("restore", 0, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),          # Back closes; Fn+click opens
    ("turns", 2, ("menu", F1, 2)), ("turns", -4, ("menu", F1, 6)),
    ("click", 0, ("menu", F2, None)), ("click", 0, ("menu", F1, 6)),
    ("turns", 1, ("menu", F1, 7)),
    ("click", 0, ("debug", None, None)), ("click", 0, ("menu", F1, 7)),
    ("loss", 0, ("menu", F1, 7)),
    ("turns", -3, ("menu", F1, 4)), ("turns", -4, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),
    ("turns", 1, ("menu", F1, 1)), ("turns", 1, ("menu", F1, 2)), ("turns", -2, ("menu", F1, 0)),
    ("turns", 3, ("menu", F1, 3)), ("turns", -3, ("menu", F1, 0)),
    ("loss", 0, ("menu", F1, 0)),
    ("turns", 4, ("menu", F1, 4)), ("turns", -4, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),
    ("turns", 2, ("menu", F1, 2)), ("turns", 2, ("menu", F1, 4)),
    ("turns", -2, ("menu", F1, 2)), ("turns", -2, ("menu", F1, 0)),
    ("restore", 0, ("menu", F1, 0)),
    ("turns", 1, ("menu", F1, 1)), ("turns", -1, ("menu", F1, 0)),
    ("turns", 4, ("menu", F1, 4)), ("turns", -4, ("menu", F1, 0)),
    ("hold", 650, ("dash", None, None)), ("fn", 0, ("menu", F1, 0)),
    ("turns", 3, ("menu", F1, 3)), ("turns", -3, ("menu", F1, 0)),
]
assert len(STEPS) == 50
# The outcomes a step may end with. A 650 ms hold latches Back at 600 ms, which
# closes the fixture, and the close cancels the hold before its release: a
# legitimate terminal outcome (codex's S0 code review).
ALLOWED = {"hold": {"done", "cancelled"}}
_mix = [k for k, _, _ in STEPS]
assert (_mix.count("turns"), _mix.count("click"), _mix.count("hold"), _mix.count("fn"),
        _mix.count("restore"), _mix.count("loss")) == (28, 10, 4, 4, 2, 2)


def send(h, kind, arg):
    if kind == "turns":
        return mutate(h, 1, bytes([arg & 0xFF]))
    if kind == "click":
        return mutate(h, 2)
    if kind == "hold":
        return mutate(h, 3, bytes([arg & 0xFF, arg >> 8]))
    if kind == "fn":
        return mutate(h, 4)
    if kind == "restore":
        return mutate(h, 7)
    if kind == "loss":
        return mutate(h, 8)
    raise ValueError(kind)


STATUS_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ak820pro", "ak820-agent.status")
STATUS_FRESH_S = 15      # the daemon rewrites its status every few seconds
PUSH_FRESH_S = 60        # and pushes the board's now-playing while a track plays
SMTC_FRESH_S = 10        # smtc_stale_s is the age of its last good SMTC read (it polls every 3 s)


def parse_status(text):
    """The daemon's status file: one `key=value` a line (ak820-agent's
    status.rs). Split at the first `=` only: values hold spaces and `=`."""
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            out[k.strip()] = v
    return out


def _age_s(stamp, now):
    try:
        return now - time.mktime(time.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, AttributeError):
        return None


def playing(status, now):
    """(ok, why): a track playing, from a fresh status and a fresh push. The
    playback state is the text's first word exactly ("play" or "pause")."""
    if not status:
        return False, "no status file"
    text = status.get("media_last_text")
    if text is None:
        return False, "no media_last_text"
    if text.split(" ", 1)[0] != "play":
        return False, f"not playing: {text!r}"
    age = _age_s(status.get("updated", ""), now)
    if age is None or age > STATUS_FRESH_S:
        return False, f"the status is stale ({age} s)"
    push = _age_s(status.get("media_last_push", ""), now)
    if push is None or push > PUSH_FRESH_S:
        return False, f"no fresh push to the board ({push} s)"
    try:
        smtc = int(status.get("smtc_stale_s", "").strip())
    except ValueError:
        return False, f"no SMTC age: {status.get('smtc_stale_s')!r}"
    if smtc > SMTC_FRESH_S:
        return False, f"SMTC stale {smtc} s"
    return True, text


def read_status():
    try:
        return parse_status(open(STATUS_PATH, encoding="utf-8", errors="replace").read())
    except OSError:
        return None


def media_text():
    s = read_status()
    return s.get("media_last_text") if s else None


def _selftest():
    now = time.mktime(time.strptime("2026-10-23 16:00:30", "%Y-%m-%d %H:%M:%S"))
    base = "updated=2026-10-23 16:00:25\nmedia_last_push=2026-10-23 16:00:10\nsmtc_stale_s=0\n"
    ok = lambda text: playing(parse_status(base + "media_last_text=" + text), now)[0]
    assert ok("play  Artist - Title")
    assert not ok("pause play something")
    assert not ok("pause Cosmic Cadet = Europa")
    assert not playing(parse_status(base), now)[0]                       # missing
    assert not playing(None, now)[0]
    stale = parse_status("updated=2026-10-23 15:59:00\nmedia_last_push=2026-10-23 16:00:10\n"
                         "media_last_text=play x\n")
    assert not playing(stale, now)[0]                                    # a departed daemon
    nopush = parse_status("updated=2026-10-23 16:00:25\nmedia_last_push=2026-10-23 15:58:00\n"
                          "media_last_text=play x\n")
    assert not playing(nopush, now)[0]
    aged = lambda s: parse_status("updated=2026-10-23 16:00:25\nmedia_last_push=2026-10-23 16:00:10\n"
                                  f"smtc_stale_s={s}\nmedia_last_text=play x\n")
    assert playing(aged(2), now)[0]                                       # a healthy read 2 s old
    assert not playing(aged(45), now)[0]                                  # SMTC genuinely stale
    print("media check: self-test passed")


def health_json():
    py = sys.executable
    tool = os.path.join(os.path.dirname(__file__), "..", "hostagent", "ak820health.py")
    out = subprocess.run([py, tool, "--stalls", "--json"], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=30)
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--dashboard-s", type=int, default=300, help="the dashboard interval after the steps")
    ap.add_argument("--smoke", action="store_true",
                    help="a shortened or trackless run: reported, never S0's proof")
    ap.add_argument("--out", default="menu_s0_session.json")
    ap.add_argument("--selftest", action="store_true", help="test the media check, then exit")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return 0

    failures = []
    before = health_json()
    media_before = media_text()
    h = open_device()
    log, outcomes = [], {}
    t0 = time.monotonic()
    try:
        s = read_state(h)
        if s["session"] != "none":
            st, seq = mutate(h, 4)   # close whatever is open
            wait(h, seq)
        restore_seen = []
        ok, s = wait_restored(h, seen=restore_seen)
        if not ok:
            sys.exit(f"the dashboard isn't restored to start from: {s}")
        st, seq = mutate(h, 4)       # open the fixture
        state, s = wait(h, seq)
        if st != OK or state != "done" or (s["owner"], s["screen"], s["cursor"]) != ("menu", F1, 0):
            sys.exit(f"the fixture didn't open ({st}, {state}): {s}")
        for rep in range(a.repeats):
            for i, (kind, arg, want) in enumerate(STEPS):
                st, seq = send(h, kind, arg)
                if st != OK:
                    failures.append(f"rep {rep} step {i} {kind}: status {st}")
                    log.append({"rep": rep, "step": i, "kind": kind, "status": st})
                    continue
                seen = []
                state, s = wait(h, seq, seen=seen)
                outcomes[state] = outcomes.get(state, 0) + 1
                got = (s["owner"], s["screen"], s["cursor"])
                ok_state = all(w is None or w == g for w, g in zip(want, got))
                ok_outcome = state in ALLOWED.get(kind, {"done"})
                if not ok_state:
                    failures.append(f"rep {rep} step {i} {kind}: {got}, want {want}")
                if not ok_outcome:
                    failures.append(f"rep {rep} step {i} {kind}: outcome {state}")
                log.append({"rep": rep, "step": i, "kind": kind, "arg": arg, "state": state,
                            "got": got, "want": want, "ok": ok_state and ok_outcome,
                            "seen": seen, "invariant_fail": s["invariant_fail"],
                            "dropped": s["dropped"], "losses": s["losses"]})
        st, seq = mutate(h, 4)       # the last returns to the dashboard
        state, s = wait(h, seq)
        if st != OK or state != "done":
            failures.append(f"the final close: status {st}, outcome {state}")
        ok, final = wait_restored(h, seen=restore_seen)
        if not ok:
            failures.append(f"the dashboard wasn't restored after the close: {final}")
        steps_s = time.monotonic() - t0
        # The dashboard interval, inside the measured span: no counter reset.
        # A track must be playing through it, checked every 30 s from the
        # daemon's now-playing line.
        print(f"steps done in {steps_s:.0f} s; the dashboard for {a.dashboard_s} s ...", flush=True)
        media_samples = []
        end = time.monotonic() + a.dashboard_s
        while True:
            ok_play, why = playing(read_status(), time.time())
            media_samples.append([time.strftime("%H:%M:%S"), ok_play, why])
            if not a.smoke and not ok_play:
                failures.append(f"no track playing in the dashboard interval: {why}")
                break
            left = end - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(30.0, left))
        final = read_state(h)
    finally:
        h.close()
    elapsed = time.monotonic() - t0
    after = health_json()
    media_after = media_text()
    ge25 = [before.get("count_ge_25ms"), after.get("count_ge_25ms")]
    ge10 = [before.get("count_ge_10ms"), after.get("count_ge_10ms")]
    if None in ge25 or None in ge10 or ge25[1] < ge25[0] or ge10[1] < ge10[0]:
        failures.append(f"the measured span is invalid (a counter reset or missing): ge25 {ge25}, ge10 {ge10}")
    elif ge25[1] - ge25[0] > 0:
        failures.append(f"passes of 25 ms or more: {ge25}")
    if not a.smoke and (a.repeats != 10 or a.dashboard_s < 300):
        failures.append("a shortened run is a smoke test: pass --smoke")
    if final["invariant_fail"]:
        failures.append(f"invariant_fail {final['invariant_fail']:#x}")
    if (final["owner"], final["session"], final["phase"]) != ("dash", "none", "done"):
        failures.append(f"the final state: {final['owner']}/{final['session']}/{final['phase']}")
    result = {
        "repeats": a.repeats, "dashboard_s": a.dashboard_s, "elapsed_s": round(elapsed, 1),
        "failures": failures, "outcomes": outcomes, "final": final,
        "smoke": a.smoke,
        "media": [media_before, media_after], "media_samples": media_samples,
        "restore_seen": restore_seen,
        "count_ge_10ms": ge10,
        "count_ge_25ms": ge25,
        "loop_gap_max_ms": after.get("loop_gap_max_ms"),
        "acct_after": after.get("acct"),
        "log": log,
    }
    with open(a.out, "w") as f:
        json.dump(result, f, indent=1)
    print(f"{a.repeats} x 50 steps, then {a.dashboard_s} s of the dashboard: {len(failures)} failures, "
          f"outcomes {outcomes}")
    print(f"ge10 {result['count_ge_10ms']}, ge25 {ge25}, invariant_fail {final['invariant_fail']:#x}, "
          f"final {final['owner']}/{final['session']}/{final['phase']}")
    print(f"media: {media_before!r} -> {media_after!r}")
    if a.smoke:
        print("SMOKE TEST: not S0's proof (shortened, or no track required)")
    for f in failures[:20]:
        print("FAIL", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
