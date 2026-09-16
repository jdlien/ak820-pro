#!/usr/bin/env python3
"""Measure a macOS host agent's CPU overhead by freezing it in alternate windows.

    /usr/bin/python3 scripts/agent_overhead_macos.py AGENT_PID [--window 240] [--out results.jsonl]

Five windows -- run, pause, run, pause, run -- with the agent frozen by SIGSTOP
in the pause windows. It is ALWAYS SIGCONTed on exit, whatever happens; check
`ps -o stat= -p AGENT_PID` afterwards anyway. While it is frozen the keyboard
gets no pushes, and the text band blanks after the firmware's 3 min expiry.

What each number is, and how far to trust it:

- agent_child_cpu_s: the kernel's rusage for every reaped descendant of the
  agent (proc_pid_rusage, RUSAGE_INFO_V4). Exact; it matched `ps` to the
  hundredth when this was written. This is the agent's own cost.
  ⚠️ REAPED descendants only. A child that lives as long as the agent -- the
  Rust daemon's perl MediaRemote helper -- is never reaped, so its CPU is NOT
  in this number; live_cpu_s is.
- live_cpu_s: self CPU of the agent's LONG-LIVED children (alive >= 5 s when
  seen), discovered afresh at each window edge with proc_listchildpids, so a
  helper that restarts mid-window is still counted. A restart is logged in
  live_restarts. Use it from RUN windows only: SIGSTOP freezes the agent, not
  its children, so a helper keeps running (unread) through a pause window.
- top_cpu: `ps` CPU deltas per process per window, top 25 only, so anything
  under a few seconds per window is invisible. System daemons that move only in
  run windows (tccd, launchservicesd, trustd, ...) are the agent's knock-on cost.
- spawns_per_min: the PID counter's movement, system-wide. On a busy machine it
  cannot isolate one agent -- on 2026-09-16 background noise was 1,000-1,600
  per minute and the paused windows were the busier ones.

Written for Phase 5 of plans/AK820-AGENT-CROSSPLATFORM-PLAN.md: the "before"
column was taken with this on 2026-09-16, and the "after" must be taken the
same way. Opens nothing on the keyboard.
"""
import argparse
import ctypes
import json
import os
import signal
import struct
import subprocess
import sys
import time

libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")


class _Timebase(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


_tb = _Timebase()
libc.mach_timebase_info(ctypes.byref(_tb))
NS_PER_TICK = _tb.numer / _tb.denom

# struct rusage_info_v4, after the 16-byte uuid.
_FIELDS = ["user", "sys", "pkg_idle", "intr", "pageins", "wired", "resident", "footprint",
           "start", "exit", "c_user", "c_sys", "c_pkg_idle", "c_intr", "c_pageins", "c_elapsed",
           "dbr", "dbw", "q_def", "q_maint", "q_bg", "q_util", "q_legacy", "q_ui", "q_uint",
           "billed_sys", "serviced_sys", "lwrites", "life_max_fp", "instr", "cycles",
           "billed_energy", "serviced_energy", "int_max_fp", "runnable"]
RUSAGE_INFO_V4 = 4
LONG_LIVED_S = 5.0
PID_WRAP = 99999          # macOS: pids run 1..99998, then wrap to the lowest free
libc.mach_absolute_time.restype = ctypes.c_uint64


def rusage(pid):
    buf = ctypes.create_string_buffer(1024)
    if libc.proc_pid_rusage(ctypes.c_int(pid), ctypes.c_int(RUSAGE_INFO_V4), buf) != 0:
        raise OSError(f"proc_pid_rusage({pid}) failed -- not our process, or gone")
    return dict(zip(_FIELDS, struct.unpack_from("<16x" + "Q" * len(_FIELDS), buf.raw)))


def cpu_s(r, child=False):
    ticks = (r["c_user"] + r["c_sys"]) if child else (r["user"] + r["sys"])
    return ticks * NS_PER_TICK / 1e9


def long_lived_children(pid):
    """{child pid: (self cpu s, start abstime)} for children alive >= LONG_LIVED_S."""
    buf = (ctypes.c_int * 1024)()
    n = libc.proc_listchildpids(ctypes.c_int(pid), buf, ctypes.c_int(ctypes.sizeof(buf)))
    now = libc.mach_absolute_time()
    found = {}
    for child in (buf[i] for i in range(max(0, n))):
        try:
            r = rusage(child)
        except OSError:                         # exited between the list and the read
            continue
        if (now - r["start"]) * NS_PER_TICK / 1e9 >= LONG_LIVED_S:
            found[child] = (cpu_s(r), r["start"])
    return found


def live_delta(before, after):
    """CPU spent in the window by long-lived children, and any set change."""
    spent, restarts = 0.0, []
    for child, (cpu, start) in after.items():
        if child in before and before[child][1] == start:
            spent += cpu - before[child][0]
        else:                                   # new since the window opened: all of it is in-window
            spent += cpu
            restarts.append(f"+{child}")
    restarts += [f"-{c}" for c in before if c not in after]
    return round(spent, 3), restarts


def ps_table():
    out = subprocess.run(["ps", "-Ao", "pid=,time=,comm="], capture_output=True, text=True).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, tm, comm = parts
        secs = 0.0
        for part in tm.split(":"):              # M:SS.ss, or H:MM:SS for long runners
            secs = secs * 60 + float(part)
        table[int(pid)] = (secs, os.path.basename(comm))
    return table


def pid_probe():
    p = subprocess.Popen(["/usr/bin/true"])
    p.wait()
    return p.pid


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("agent_pid", type=int)
    ap.add_argument("--window", type=int, default=240, help="seconds per window (default 240)")
    ap.add_argument("--out", default="agent-overhead.jsonl")
    args = ap.parse_args()
    agent = args.agent_pid

    def resume(*_):
        try:
            os.kill(agent, signal.SIGCONT)
        except ProcessLookupError:
            pass

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, lambda *_: (resume(), sys.exit(1)))

    rusage(agent)                               # fail before freezing anything
    with open(args.out, "w") as log:
        try:
            for i, mode in enumerate(["run", "pause", "run", "pause", "run"]):
                if mode == "pause":
                    os.kill(agent, signal.SIGSTOP)
                else:
                    resume()
                time.sleep(2)                   # let a resumed loop settle
                a0, ps0, t0 = rusage(agent), ps_table(), time.monotonic()
                l0 = long_lived_children(agent)
                pids = [pid_probe()]
                probes = 1
                while time.monotonic() < t0 + args.window:
                    time.sleep(min(60, max(0.0, t0 + args.window - time.monotonic())))
                    pids.append(pid_probe())
                    probes += 1
                a1, ps1, t1 = rusage(agent), ps_table(), time.monotonic()
                l1 = long_lived_children(agent)
                live_cpu, live_restarts = live_delta(l0, l1)
                probes += 1                     # the closing ps
                dur = t1 - t0
                launched = (pids[-1] - pids[0]) % PID_WRAP
                top = sorted(((round(ps1[p][0] - ps0[p][0], 2), ps1[p][1], p)
                              for p in ps1 if p in ps0 and ps0[p][1] == ps1[p][1]
                              and ps1[p][0] - ps0[p][0] > 0.05), reverse=True)[:25]
                rec = {"window": i + 1, "mode": mode, "start": time.strftime("%H:%M:%S"),
                       "dur_s": round(dur, 1),
                       "spawns_per_min": round((launched - probes) / dur * 60, 1),
                       "agent_child_cpu_s": round(cpu_s(a1, True) - cpu_s(a0, True), 3),
                       "agent_self_cpu_s": round(cpu_s(a1) - cpu_s(a0), 3),
                       "agent_rss_kb": a1["resident"] // 1024,
                       "live_cpu_s": live_cpu, "live_restarts": live_restarts,
                       "top_cpu": top}
                log.write(json.dumps(rec) + "\n")
                log.flush()
                print(f"{rec['window']} {mode:5} {rec['dur_s']:6.1f}s  agent child cpu "
                      f"{rec['agent_child_cpu_s']:7.2f}s  self {rec['agent_self_cpu_s']:5.2f}s  "
                      f"live {rec['live_cpu_s']:5.2f}s{' RESTART ' + ','.join(live_restarts) if live_restarts else ''}  "
                      f"launches/min (system-wide) {rec['spawns_per_min']}")
        finally:
            resume()
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(agent)], capture_output=True, text=True)
    print(f"agent state after: {state.stdout.strip() or 'gone'}  (T would mean still stopped)")


if __name__ == "__main__":
    main()
