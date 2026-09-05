#!/usr/bin/env python3
"""AK820 Pro timekeeper agent (clock-sync plan 3.8). Replaces the 3-hourly
ak820-clocksync.sh job.

Loop every 15 s:
  * sync when the raw-HID interface (re)appears (a slider flip reboots the
    board; a replug too);
  * sync when the loop's own wall-clock gap exceeds 60 s (the Mac slept);
  * sync every SYNC_INTERVAL s regardless;
  * LEARN the SOF bias from the offset that accumulates between periodic
    syncs (the NTP way): the board's frequency loop targets f_sof * (1 + bias),
    so whatever bias makes the residual vanish is the right one, whatever its
    cause. Half-step per sample, only from a slew-sized residual on a settled
    loop (period unchanged since the previous sync), written to ak820ctl's
    cache so the next sync sends it. Before this the bias came from a 15-min
    frame count against the wall clock, which measured -369..+587 ppm on a
    controller the phase-0 test had put at +78 +-3 -- and each new value
    re-steered the clock, giving a 5-minute sawtooth of 150-330 ms
    (2026-09-03). That measurement now only seeds a cache that has no bias.

Every transaction shells out to ak820ctl so exactly one process owns the
raw-HID interface at a time; failures (VIA holding it, no reply) are logged
and retried next round. Log: ~/Library/Logs/ak820pro-timekeeper.log
"""
import json, os, re, subprocess, sys, time

AK820_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WIN = os.name == "nt"
_EXE = ".exe" if _WIN else ""
CTL  = os.environ.get("AK820_CTL") or os.path.join(AK820_ROOT, "time-util-ak820pro",
                                                   "ak820ctl" + _EXE)

# ⚠️ ak820ctl finds its calibration cache with getenv("HOME") (ak820ctl.c:225)
# and falls back to "." when that is unset. Windows does not set HOME at all,
# and an MSYS2 shell sets it to a POSIX path (/home/user) that a NATIVE binary
# cannot resolve -- so ak820ctl would scatter .ak820ctl-cap into whatever the
# current directory happened to be while this agent read %USERPROFILE%. The two
# would never see the same file and the learned bias would silently never
# arrive. Pin one home for both: this value is what run_ctl() exports as HOME.
HOME = (os.environ.get("USERPROFILE") or os.path.expanduser("~")) if _WIN \
       else os.path.expanduser("~")

if _WIN:
    # No ~/Library/Logs on Windows; %LOCALAPPDATA% is the conventional spot for
    # a per-user service log and is writable by a Scheduled Task.
    _LOGDIR = os.path.join(os.environ.get("LOCALAPPDATA") or HOME, "ak820pro")
    LOG = os.path.join(_LOGDIR, "ak820pro-timekeeper.log")
else:
    LOG = os.path.expanduser("~/Library/Logs/ak820pro-timekeeper.log")
BIAS_STATE = os.path.join(HOME, ".ak820ctl-bias.json")
SYNC_INTERVAL = 300      # s (5 min) once the residual is small
SYNC_INTERVAL_FAST = 180 # s while the last residual exceeded FAST_ABOVE_MS: the ILRC drifts
FAST_ABOVE_MS = 60       # hundreds of ppm while the board warms (LED load, room), and the
                         # board's loop tracks that slowly; syncing more often bounds the
                         # visible sawtooth until the drift settles.
                         # ⚠️ MUST leave the board's loop a full clean window between syncs:
                         # a slew writes the period register ~3 times (start, remainder,
                         # restore) and each write restarts the frequency window. At 120 s
                         # with the firmware's old 128-s locked window the window NEVER
                         # completed, the loop froze at a wrong period, the residual stayed
                         # large, and the interval stayed fast: a +300 ms plateau for six
                         # hours on 2026-09-04. 180 s leaves ~150 clean seconds -- one old
                         # window, four of the 32-s windows firmware 8608c4f680 uses.
BIAS_INTERVAL = 900      # s of continuity before a bias re-measurement (seed only, see learn_bias)
CAP = os.path.join(HOME, ".ak820ctl-cap")     # ak820ctl's "proto lead_ms b_ppm" cache
LEARN_MIN_ELAPSED = 90   # s between the two syncs a residual is measured across. Was 240,
                         # which is longer than the fast interval, so the learner could never
                         # fire while the residual was large -- the one time it was needed
LEARN_MAX_BEFORE  = 400  # ms: larger residuals are convergence or a step, not a rate error
LEARN_GAIN        = 0.25 # low gain: each residual carries the ILRC's wander as noise (see below)
LEARN_MAX_DP      = 6    # ticks (~180 ppm): the ILRC wanders +-300 ppm on 5-min scales and the board's
                         # loop follows it a few ticks per window, so "P unchanged" never happens;
                         # a wider gate plus low gain averages the wander out instead of waiting it out
BIAS_LIMIT        = 600  # ppm, matches the firmware's sanity clamp
LOOP = 15
SLEEP_GAP = 60

VID, PID = 0x0C45, 0x8009


def log(msg):
    # ~/Library/Logs always exists on macOS; %LOCALAPPDATA%\ak820pro does not.
    d = os.path.dirname(LOG)
    if d and not os.path.isdir(d):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def hid_present():
    try:
        import hid
        return any(d.get("usage_page") == 0xFF60 and d.get("usage") == 0x61
                   for d in hid.enumerate(VID, PID))
    except Exception:
        return False


def controller_id():
    """Something that changes when the board moves to another USB controller/hub.

    The value is compared against itself between polls, never parsed, so any
    stable-per-port string will do. macOS reads locationID out of ioreg; Windows
    has no ioreg, but hidapi's device path already encodes the port/hub, which
    is the same signal from a source both platforms already depend on."""
    if _WIN:
        try:
            import hid
            paths = sorted(str(d.get("path", "")) for d in hid.enumerate(VID, PID))
            return "|".join(paths) if paths else "unknown"
        except Exception:
            return "unknown"
    try:
        out = subprocess.run(["ioreg", "-p", "IOUSB", "-w0", "-l"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r'"idProduct" = 32777.*?"locationID" = (\d+)', out, re.S)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


# ⚠️ Windows: ak820ctl is a CONSOLE program and this agent runs under
# pythonw.exe, which has no console -- so every spawn allocates a fresh one and
# a terminal window flashes on screen and TAKES FOCUS. At 2-3 spawns per sync
# that is a visible blink every few minutes, and a focus steal mid-keystroke can
# eat the keypress: the agent for a keyboard would be dropping keys at the OS
# level. CREATE_NO_WINDOW suppresses the console without hiding output, which
# still comes back through the pipes. 0 elsewhere -- POSIX ignores it.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if _WIN else 0


def run_ctl(*args, timeout=30):
    # HOME is exported explicitly: ak820ctl keys its calibration cache off it,
    # and on Windows it is either unset or a POSIX path this native binary
    # cannot use. See the HOME comment at the top.
    env = dict(os.environ)
    env["HOME"] = HOME
    r = subprocess.run([CTL, *args], capture_output=True, text=True,
                       timeout=timeout, env=env, creationflags=_NO_WINDOW)
    return r.returncode, (r.stdout + r.stderr).strip()


def cap_read():
    """ak820ctl's calibration cache: 'proto lead_ms [b_ppm]'."""
    try:
        parts = open(CAP).read().split()
        d = {"proto": int(parts[0]), "lead": float(parts[1])}
        if len(parts) >= 3:
            d["b"] = int(parts[2])
        return d
    except Exception:
        return None


def cap_write_bias(b_ppm):
    c = cap_read()
    if not c:
        return False
    tmp = CAP + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"{c['proto']} {c['lead']:.3f} {int(round(b_ppm))}\n")
    os.replace(tmp, CAP)
    return True


def read_status():
    rc, out = run_ctl("clock", "--read")
    if rc != 0:
        return None
    d = {}
    m = re.search(r"nominal (\d+)", out);                      d["pnom"] = int(m.group(1)) if m else None
    m = re.search(r"offset board-host ([-+\d.]+) ms", out);     d["offset"] = float(m.group(1)) if m else None
    m = re.search(r"ref_state (\d+)", out);                       d["ref_state"] = int(m.group(1)) if m else None
    m = re.search(r"sof_epoch (\d+)\s+sof_frames_total (\d+)", out)
    if m:
        d["epoch"] = int(m.group(1)); d["frames"] = int(m.group(2))
    m = re.search(r"flags 0x([0-9a-f]+)", out);                  d["flags"] = int(m.group(1), 16) if m else None
    return d


def sync(reason):
    """Returns (ok, before_ms, slewing): the residual the board had accumulated
    since the previous sync, and whether it was corrected by a slew (a step
    means the clock was unset, far off, or just flashed -- not a rate sample)."""
    rc, out = run_ctl("clock")
    log(f"sync ({reason}): {out.splitlines()[-1] if out else 'no output'}" + ("" if rc == 0 else f" [rc={rc}]"))
    m = re.search(r"before ([-+\d.]+) ms", out)
    before = float(m.group(1)) if m else None
    slewing = "(slewing)" in out and "warning:" not in out
    return rc == 0, before, slewing


def learn_bias(state, reason, before, slewing):
    """One residual sample per periodic sync. Board behind by `before` ms over
    `elapsed` s means it runs slow by -before*1000/elapsed ppm; the loop's
    target is f_sof*(1+b), so lower b by half of that. Gated on: a periodic
    sync (an enumeration or wake breaks the baseline), a slew-sized residual,
    the SOF reference in use, and the board's nominal period UNCHANGED since
    the previous sync -- while its loop is still moving P the residual is
    convergence, not a rate error, and learning from it would fight the loop."""
    now = time.monotonic()
    st = read_status() or {}
    pnom = st.get("pnom")
    prev = state.get("learn")
    if reason != "periodic":
        state["learn"] = {"t": now, "pnom": pnom}
        return
    settled = prev and pnom and prev.get("pnom") and abs(prev["pnom"] - pnom) <= LEARN_MAX_DP
    if prev and pnom and before is not None and slewing and abs(before) <= LEARN_MAX_BEFORE \
            and st.get("ref_state") == 2 and not settled:
        log(f"bias hold: P {prev.get('pnom')} -> {pnom} since the last sync (loop still moving); residual {before:+.1f} ms not learned")
    if settled and before is not None and slewing and abs(before) <= LEARN_MAX_BEFORE and st.get("ref_state") == 2:
        elapsed = now - prev["t"]
        if elapsed >= LEARN_MIN_ELAPSED:
            e_slow = -before * 1000.0 / elapsed
            c = cap_read()
            if c and "b" in c:
                b_new = max(-BIAS_LIMIT, min(BIAS_LIMIT, c["b"] - LEARN_GAIN * e_slow))
                if cap_write_bias(b_new):
                    log(f"bias learned: before {before:+.1f} ms over {elapsed:.0f} s = board {e_slow:+.0f} ppm slow; "
                        f"b {c['b']:+d} -> {int(round(b_new)):+d} ppm (P {pnom})")
    state["learn"] = {"t": now, "pnom": pnom}


def bias_step(state):
    """SEED ONLY: measure b from the frame count once, for a cache that has no
    bias. It is too noisy to steer with (see the header); learn_bias() owns the
    value from then on."""
    c = cap_read()
    if c and "b" in c:
        state.clear(); return
    st = read_status()
    now = time.time()
    if not st or "epoch" not in st:
        state.clear(); return
    cid = controller_id()
    if state.get("cid") != cid or state.get("epoch") != st["epoch"]:
        state.clear()
        state.update(cid=cid, epoch=st["epoch"], t0=now, f0=st["frames"])
        return
    H = now - state["t0"]
    if H >= BIAS_INTERVAL:
        F = (st["frames"] - state["f0"]) & 0xFFFFFFFF
        b = (F / (1000.0 * H) - 1.0) * 1e6
        if -600 < b < 600:
            run_ctl("clock", "--bias", str(int(round(b))))
            log(f"bias: F={F} H={H:.1f}s b={b:+.1f} ppm (controller {cid}) cached")
            try:
                json.dump({"cid": cid, "b_ppm": b, "t": now}, open(BIAS_STATE, "w"))
            except Exception:
                pass
        state.clear()   # start the next measurement


def main():
    log("timekeeper start")
    last_loop = time.time()
    last_sync = 0.0
    interval = SYNC_INTERVAL
    was_present = False
    bias_state = {}
    learn_state = {}
    while True:
        now = time.time()
        present = hid_present()
        reason = None
        if present and not was_present:
            reason = "enumerated"
        elif now - last_loop > SLEEP_GAP:
            reason = "wake"
        elif now - last_sync >= interval:
            reason = "periodic"
        if present and reason:
            time.sleep(2 if reason == "enumerated" else 0)   # let the board settle after boot
            ok, before, slewing = sync(reason)
            if ok:
                last_sync = time.time()
                interval = SYNC_INTERVAL_FAST if (before is not None and abs(before) > FAST_ABOVE_MS) else SYNC_INTERVAL
                try:
                    learn_bias(learn_state, reason, before, slewing)
                except Exception as e:
                    log(f"bias learn error: {e}")
        if present:
            try:
                bias_step(bias_state)
            except Exception as e:
                log(f"bias step error: {e}")
        else:
            bias_state.clear()
            learn_state.clear()
        was_present = present
        last_loop = time.time()
        time.sleep(LOOP)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
