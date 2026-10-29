#!/usr/bin/env python3
"""The radio link's UART overruns, measured (plans/OVERRUN-CAPS-PLAN.md,
plans/UART-LATENCY-PLAN.md): HC_DEVHOOK ops 20-26, and the RX tap (15), on a
dev build that carries overrun_diag.c.

    venv/bin/python scripts/overrun_diag.py status [--json OUT]
    venv/bin/python scripts/overrun_diag.py reset
    venv/bin/python scripts/overrun_diag.py mode transaction|byte|unlocked
    venv/bin/python scripts/overrun_diag.py prio 0|1
    venv/bin/python scripts/overrun_diag.py mon on|off|zero
    venv/bin/python scripts/overrun_diag.py burst N [--lo MS] [--hi MS] | burst stop
    venv/bin/python scripts/overrun_diag.py ab [--arms tb,ub,...] [--secs 180] [--n 2000] [--json OUT]
    venv/bin/python scripts/overrun_diag.py sweep [--us 50,100,...] [--n 500] [--secs 60] [--json OUT]

`status` prints the OE counts and their contexts, each PCF kind's spans, the
burst, the OE ring, the gap monitor and its ring, the RX tap's count and the
deep sleep's last eight wakes. `ab` runs arms, each named for its settings:

    arm  lock         UART2  burst    monitor
    tn   transaction  1      none     off
    tb   transaction  1      N reads  off
    un   unlocked     1      none     off
    ub   unlocked     1      N reads  off
    pn   unlocked     0      none     off      (the build's defaults)
    pb   unlocked     0      N reads  off
    mn   unlocked     0      none     on
    mb   unlocked     0      N reads  on

each for --secs under stage 2's load (mac_raw81_s2.py load: health reads
back to back over the Mac's dongle), the settings set and read back, the
board's figures and the RX tap zeroed at the arm's start and read at its
end. The cable's raw HID is shared with the load's own reads through the
retrying opener (macOS's is exclusive). `sweep` measures the receiver's
depth: per span, a burst of masked spans of that length (no I2C), at the
defaults. Afterwards the board is put back to its defaults: unlocked,
UART2 at 0, the monitor off, the tap disarmed, no burst.
Needs the Mac's dongle, the slider on 2.4G and the cable's data.
"""
import argparse, json, os, selectors, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deep_sleep as ds  # noqa: E402

cm = ds.cm
TICK_HZ = 187500
KINDS = ["read 1 (4 B)", "read 7 (10 B)", "write 1 (3 B)", "write 8 (9 B)"]
LOCKS = ["transaction", "byte", "unlocked"]
SCOPES = ["ch582", "batt", "disp_hk", "pump", "rtc", "rtc_fast", "leds", "health", "eecfg", "edge",
          "anim", "hk_other", "none"]
WAKES = ["none", "key", "backstop", "strays", "blocked", "knob", "charge"]
U16 = lambda b, o: int.from_bytes(b[o:o + 2], "little")
U32 = lambda b, o: int.from_bytes(b[o:o + 4], "little")
ms = lambda ticks: round(ticks * 1000.0 / TICK_HZ, 3)


def op(h, n, args=()):
    r = cm.xfer(h, [cm.SET_VALUE, cm.HEALTH_CH, cm.HC_DEVHOOK, n] + list(args) + [0] * (28 - len(args)))
    if len(r) < 32 or r[3] != n:
        sys.exit(f"op {n}: unhandled or another op's reply ({bytes(r[:8]).hex()}); a build with overrun_diag?")
    return bytes(r[4:32])


def summary(h, sub=0):
    b = op(h, 20, [sub])
    return {"oe_obs": U32(b, 0), "oe_drain": U32(b, 4), "rx_drop": U32(b, 8), "ring_seq": U16(b, 12),
            "lock": LOCKS[b[14]] if b[14] < 3 else b[14], "uart_prio": b[15], "usb_max_ms": ms(U16(b, 16)), "st_max_ms": ms(U16(b, 18)),
            "ctx_pcf": U16(b, 20), "ctx_flash": U16(b, 22), "ctx_none": U16(b, 24), "rx_off": U16(b, 26)}


def kinds(h):
    out = []
    for k in range(4):
        b = op(h, 22, [k])
        out.append({"kind": KINDS[k], "count": U32(b, 0), "fails": U16(b, 4), "max_span_ms": ms(U16(b, 6)),
                    "max_whole_ms": ms(U16(b, 8)), "spans_ge_1ms": U32(b, 10), "spans_ge_1_4ms": U32(b, 14),
                    "spans": U32(b, 18)})
    b = op(h, 22, [0xFF])
    return out, {"ctx_sleep": U16(b, 0), "tick_hz": U32(b, 2), "now_secs": U32(b, 6), "ctx_probe": U16(b, 10),
                "uart_max_ms": ms(U16(b, 12))}


def mon(h, sub=0):
    """The gap monitor (op 25): sub 1 on, 2 off, 3 zero. Its maximum counts
    only gaps past the first threshold; with none, its context means nothing."""
    b = op(h, 25, [sub])
    return {"on": bool(b[0]), "max_ms": ms(U16(b, 2)), "n_128us": U32(b, 4), "n_197us": U32(b, 8),
            "n_347us": U32(b, 12), "ticks": U32(b, 16),
            "max_ctx": SCOPES[b[20]] if b[20] < len(SCOPES) else b[20], "max_act": b[21], "seq": U16(b, 22)}


def mon_ring(h, seq):
    """The monitor's gaps of 197 us and over (op 26), the newest 16."""
    slots = {}
    for page in range(8):
        b = op(h, 26, [page])
        for j in range(2):
            e = b[10 * j:10 * j + 10]
            slots[2 * page + j] = {"seq": U16(e, 0), "secs": U32(e, 2), "gap_ms": ms(U16(e, 6)),
                                   "ctx": SCOPES[e[8]] if e[8] < len(SCOPES) else e[8], "act": e[9]}
    return walk_back(slots, seq, 16)


def rxtap(h, sub=0):
    """Gremlin's RX tap (op 15): sub 1 arms it (count zeroed), 2 disarms; the
    count is every byte the link's parser took since arming."""
    b = op(h, 15, [sub])
    return {"armed": bool(b[0]), "bytes": U32(b, 1)}


def walk_back(slots, seq, cap):
    """The newest entries, oldest first: from seq-1 backward (mod 2^16), each
    taken only if its slot carries exactly that sequence number, so an
    unwritten or overwritten slot ends the walk; wrap-safe."""
    out = []
    for k in range(1, cap + 1):
        want = (seq - k) & 0xFFFF
        e = slots[want % cap]
        if e["seq"] != want:
            break
        out.append(e)
    return out[::-1]


def ring(h, seq):
    """The OE ring's entries, newest 32 at most, and the summary they go with:
    re-read if an OE landed during the 16 pages."""
    for _ in range(3):
        slots = {}
        for page in range(16):
            b = op(h, 21, [page])
            for j in range(2):
                e = b[14 * j:14 * j + 14]
                slots[2 * page + j] = {"seq": U16(e, 0), "secs": U32(e, 2), "act": e[6], "kind": e[7] & 3,
                                       "in_drain": bool(e[7] & 0x40), "lock": (e[7] >> 4) & 3,
                                       "span_ms": ms(U16(e, 8)), "usb_max_ms": ms(U16(e, 10)),
                                       "st_max_ms": ms(U16(e, 12))}
        s_now = summary(h)
        if s_now["ring_seq"] == seq:
            return walk_back(slots, seq, 32), s_now
        seq = s_now["ring_seq"]
    sys.exit("the OE ring kept moving during its readout")


def burst(h, sub=0, n=0, lo=40, hi=80, mask_us=0):
    """sub 1 starts PCF reads; sub 3 the depth probe (n masked spans of mask_us)."""
    b = op(h, 23, [sub, n & 0xFF, n >> 8, lo, hi, mask_us & 0xFF, mask_us >> 8])
    return {"left": U16(b, 0), "done": U16(b, 2), "failed": U16(b, 4), "exposure_ms": U32(b, 6),
            "active": bool(b[10]), "skipped": U16(b, 12), "lo": b[14], "hi": b[15]}


def walk_attempts(slots, seq, cap):
    """The deep sleep's ring, oldest first. Since firmware fcb7ae00 (10-29)
    each sleep reserves its number at its teardown, so one a reset cut short
    leaves a gap: from seq-1 back over the last `cap` numbers, a slot is
    taken only if it carries exactly that number and holds an entry (a real
    one always has a reason), and a gap is skipped, not the end (codex, the
    ds-phase re-check). Wrap-safe."""
    out = []
    for k in range(1, cap + 1):
        want = (seq - k) & 0xFFFF
        e = slots[want % cap]
        if e["seq"] == want and e["reason"] != "none":
            out.append(e)
    return out[::-1]


def wakes(h):
    """The deep sleep's last eight wakes, oldest first; re-read if one landed
    during the readout (every reply carries the next sleep's number)."""
    for _ in range(3):
        out = []
        for slot in range(8):
            b = op(h, 24, [slot])
            out.append({"seq": U16(b, 0), "reason": WAKES[b[2]] if b[2] < len(WAKES) else b[2], "flags": b[3],
                        "counted_s": U32(b, 4), "p0": hex(U32(b, 8)), "p1": hex(U32(b, 12)),
                        "p2": hex(U32(b, 16)), "ms": U32(b, 20), "strays": U16(b, 24), "next": U16(b, 26)})
        if len({w["next"] for w in out}) == 1:
            return walk_attempts(out, out[0]["next"], 8)
    sys.exit("the wake ring kept moving during its readout")


def snapshot(h):
    r, s = ring(h, summary(h)["ring_seq"])     # the summary the ring was read against
    k, extra = kinds(h)
    m = mon(h)
    return {"summary": s, "kinds": k, "sleep": extra, "burst": burst(h), "ring": r, "wakes": wakes(h),
            "mon": m, "mon_ring": mon_ring(h, m["seq"]), "rxtap": rxtap(h)}


def show(d):
    s = d["summary"]
    print(f"OE observed {s['oe_obs']} (+{s['oe_drain']} in the drain's re-reads), bytes refused {s['rx_drop']}; "
          f"lock {s['lock']}, UART2 at {s['uart_prio']}; RX tap {d['rxtap']['bytes']} bytes"
          f"{'' if d['rxtap']['armed'] else ' (disarmed)'}")
    print(f"  seen with: a PCF transaction {s['ctx_pcf']}, a flash write {s['ctx_flash']}, a sleep "
          f"{d['sleep']['ctx_sleep']}, the depth probe {d['sleep']['ctx_probe']}, none {s['ctx_none']}; "
          f"receiver-off intervals {s['rx_off']}")
    print(f"  longest handlers: USB {s['usb_max_ms']} ms, system timer {s['st_max_ms']} ms, "
          f"UART2 {d['sleep']['uart_max_ms']} ms")
    m = d["mon"]
    print(f"  gap monitor {'on' if m['on'] else 'off'}: {m['ticks']} ticks, gaps >= 128 us {m['n_128us']}, "
          f">= 197 us {m['n_197us']}, >= 347 us {m['n_347us']}; longest {m['max_ms']} ms"
          + (f" in {m['max_ctx']} (act {m['max_act']:#x})" if m["n_128us"] else ""))
    for e in d["mon_ring"]:
        print(f"    gap #{e['seq']} {e['gap_ms']} ms at board second {e['secs']}, in {e['ctx']} (act {e['act']:#x})")
    for k in d["kinds"]:
        if k["count"]:
            print(f"  PCF {k['kind']:14s} {k['count']:6d} ({k['fails']} failed); longest masked "
                  f"{k['max_span_ms']} ms, whole call {k['max_whole_ms']} ms; spans >= 1.0 ms "
                  f"{k['spans_ge_1ms']}, >= 1.4 ms {k['spans_ge_1_4ms']} of {k['spans']}")
    b = d["burst"]
    print(f"  burst: {'active, ' if b['active'] else ''}{b['done']} done, {b['failed']} failed, {b['left']} left, "
          f"{b['skipped']} skipped passes, {b['exposure_ms']} ms first to last ({b['lo']}-{b['hi']} ms gaps)")
    now = d["sleep"]["now_secs"]
    for e in d["ring"]:
        print(f"  OE #{e['seq']} {now - e['secs']} s ago (board second {e['secs']}): act {e['act']:#x} kind {e['kind']}{' drain' if e['in_drain'] else ''}"
              f" {LOCKS[e['lock']] if e['lock'] < 3 else e['lock']}; last span {e['span_ms']} ms, USB {e['usb_max_ms']}, "
              f"timer {e['st_max_ms']}")
    for w in d["wakes"]:
        print(f"  sleep #{w['seq']}: woke on {w['reason']} after {w['counted_s']} counted s (flags {w['flags']:#x}); "
              f"P0 {w['p0']} P1 {w['p1']} P2 {w['p2']}, strays {w['strays']}, at {w['ms']} ms")


ARMS = {  # name: (lock mode, UART2's priority, a burst, the monitor)
    "tn": (0, 1, False, False), "tb": (0, 1, True, False),
    "un": (2, 1, False, False), "ub": (2, 1, True, False),
    "pn": (2, 0, False, False), "pb": (2, 0, True, False),
    "mn": (2, 0, False, True), "mb": (2, 0, True, True),
}
DEFAULT_ARMS = "tb,ub,ub,tb,tn,un,un,tn,un,pn,pn,un,pb,mb,mb,pb,pn,mn,mn,pn"
READY_S = 60.0      # the load's owner lock, dongle open and 3 s quiet


class Load:
    """mac_raw81_s2.py load SECS in a child: health reads back to back over
    the dongle, 200 at a time. Its first line ("session ...") comes just
    before the first request, so it marks the load's start."""

    def __init__(self, secs):
        self.out = tempfile.mktemp(suffix=".json")
        self.secs = secs
        self.p = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, "mac_raw81_s2.py"), "load",
                                   str(secs), "--json", self.out],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.lines = []

    def wait_ready(self):
        deadline = time.monotonic() + READY_S
        sel = selectors.DefaultSelector()
        sel.register(self.p.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not sel.select(timeout=max(0.0, deadline - time.monotonic())):
                break
            ln = self.p.stdout.readline()
            if not ln:
                break
            self.lines.append(ln.rstrip())
            if ln.startswith("session "):
                return time.time()
        raise SystemExit("the load never started: " + " | ".join(self.lines[-5:]))

    def finish(self):
        try:
            rest, _ = self.p.communicate(timeout=self.secs + 120)
        except subprocess.TimeoutExpired:
            raise SystemExit("the load hung")
        self.lines += rest.splitlines()
        if not os.path.exists(self.out):
            raise SystemExit(f"the load failed (exit {self.p.returncode}): " + " | ".join(self.lines[-5:]))
        with open(self.out) as f:
            e = json.load(f)
        blocks = e.get("load", [])
        tot = lambda f: sum(f(b) for b in blocks)
        link = lambda k: tot(lambda b: b["stall_link_delta"].get(k) or 0)
        return {"exit": self.p.returncode, "fails": e.get("fails", []), "requests": tot(lambda b: b["n"]),
                "ok": tot(lambda b: b["results"].get("ok", 0)), "lost": tot(lambda b: b["results"].get("unknown", 0)),
                "other": tot(lambda b: sum(v for k, v in b["results"].items() if k not in ("ok", "unknown"))),
                "taint": tot(lambda b: b["board_delta"].get("taint", 0)),
                "badsum": tot(lambda b: b["board_delta"].get("badsum", 0)),
                "ge25": link("ge25"), "ge10": link("ge10"), "uart_overrun_link": link("uart_overrun"),
                "giveups": link("giveups"), "replaced": link("replaced"), "queue_full": link("queue_full"),
                "max_rtt_ms": e.get("max_rtt_ms"),
                "losses": [l for b in blocks for l in b["losses"]], "blocks": blocks}

    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(5)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()
        if os.path.exists(self.out):
            os.unlink(self.out)


def settle(h, lock, prio, mon_on):
    """The arm's settings, set and read back; its figures zeroed."""
    burst(h, 2)                                    # nothing left from before
    op(h, 20, [2, lock])
    op(h, 20, [3, prio])
    mon(h, 3)
    mon(h, 1 if mon_on else 2)
    rxtap(h, 1)
    s = summary(h, 1)                              # zero the counts, ring and kinds
    if s["lock"] != LOCKS[lock] or s["uart_prio"] != prio:
        raise SystemExit(f"the board did not take lock {LOCKS[lock]}, UART2 {prio}: it reads {s['lock']}, {s['uart_prio']}")
    return s


def run_arm(name, a, mask_us=0):
    """The load for --secs; in a burst arm, the burst started once the load
    is sending. With mask_us, the burst is the depth probe's masked spans."""
    lock, prio, with_burst, mon_on = ARMS[name]
    ds.with_dev(lambda h: settle(h, lock, prio, mon_on))
    what = (f"{a.n} masked spans of {mask_us} us" if mask_us else f"a burst of {a.n}") if with_burst else "no burst"
    cm.say(f"arm {name}: lock {LOCKS[lock]}, UART2 at {prio}, {what}, monitor {'on' if mon_on else 'off'}, "
           f"{a.secs:.0f} s of load")
    t_arm = time.time()
    load, b0 = Load(a.secs), None
    try:
        t_load = load.wait_ready()
        if with_burst:
            b0 = ds.with_dev(lambda h: burst(h, 3 if mask_us else 1, a.n, a.lo, a.hi, mask_us))
            b0["host_t"] = round(time.time(), 3)
        L = load.finish()
    finally:
        load.close()
    d = ds.with_dev(snapshot)
    unfinished = with_burst and (d["burst"]["active"] or d["burst"]["left"])
    if unfinished:
        ds.with_dev(lambda h: burst(h, 2))
    arm = {"arm": name, "lock": LOCKS[lock], "uart_prio": prio, "monitor": mon_on, "mask_us": mask_us,
           "burst_asked": a.n if with_burst else 0, "burst_unfinished": bool(unfinished),
           "start": round(t_arm, 3), "load_start": round(t_load, 3), "end": round(time.time(), 3),
           "burst_start": b0, "board": d, "load": L}
    s, m = d["summary"], d["mon"]
    cm.say(f"  OE {s['oe_obs']} (+{s['oe_drain']} in the drain), refused {s['rx_drop']}, with PCF {s['ctx_pcf']}, "
           f"none {s['ctx_none']}; "
           # The burst's tally is the last burst's: settling stops one, not zeroes it.
           + (f"burst {d['burst']['done']} of {arm['burst_asked']}{' UNFINISHED' if unfinished else ''}; "
              if with_burst else "no burst; ")
           + f"load {L['ok']} ok, {L['lost']} lost of {L['requests']}, "
           f"ge25 {L['ge25']}, ge10 {L['ge10']}; tap {d['rxtap']['bytes']} B"
           + (f"; gaps >= 128 us {m['n_128us']}, >= 347 us {m['n_347us']}, longest {m['max_ms']} ms" if mon_on else ""))
    return arm


def restore_defaults():
    """Whatever happened: the build's defaults back. Each step on its own, so
    one failing does not skip the rest (nor hide the original error)."""
    for what, fn in (("stop the burst", lambda h: burst(h, 2)), ("lock unlocked", lambda h: op(h, 20, [2, 2])),
                     ("UART2 at 0", lambda h: op(h, 20, [3, 0])), ("monitor off", lambda h: mon(h, 2)),
                     ("tap disarmed", lambda h: rxtap(h, 2))):
        try:
            ds.with_dev(fn)
        except (Exception, SystemExit) as e:
            cm.say(f"cleanup: could not {what}: {e}")


def run_ab(a, masks=None):
    arms = []
    try:
        for name, us in ([("pb", us) for us in masks] if masks else [(n, 0) for n in a.arms.split(",")]):
            arms.append(run_arm(name, a, us))
    finally:
        restore_defaults()
    return arms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["status", "reset", "mode", "prio", "mon", "burst", "ab", "sweep"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--lo", type=int, default=40)
    ap.add_argument("--hi", type=int, default=80)
    ap.add_argument("--arms", default=DEFAULT_ARMS)
    ap.add_argument("--secs", type=float, default=180)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--us", default="50,100,150,200,300,500,1000,1500",
                    help="sweep: the depth probe's masked spans, us")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = None
    if a.cmd == "status":
        res = ds.with_dev(snapshot)
        show(res)
    elif a.cmd == "reset":
        ds.with_dev(lambda h: summary(h, 1))
        print("zeroed")
    elif a.cmd == "mode":
        if a.arg not in LOCKS:
            sys.exit("mode: " + ", ".join(LOCKS))
        s = ds.with_dev(lambda h: summary(h) if op(h, 20, [2, LOCKS.index(a.arg)]) else None)
        print("lock:", s["lock"])
    elif a.cmd == "prio":
        if a.arg not in ("0", "1"):
            sys.exit("prio: 0 or 1")
        s = ds.with_dev(lambda h: summary(h) if op(h, 20, [3, int(a.arg)]) else None)
        print("UART2 at", s["uart_prio"])
    elif a.cmd == "mon":
        subs = {"on": 1, "off": 2, "zero": 3}
        if a.arg not in subs:
            sys.exit("mon: on, off or zero")
        print(ds.with_dev(lambda h: mon(h, subs[a.arg])))
    elif a.cmd == "burst":
        if a.arg == "stop":
            res = ds.with_dev(lambda h: burst(h, 2))
        else:
            n = int(a.arg or 0)
            if not 1 <= n <= 2000 or a.lo < 20 or a.hi < a.lo:
                sys.exit("burst: 1..2000 reads, --lo >= 20, --hi >= --lo")
            res = ds.with_dev(lambda h: burst(h, 1, n, a.lo, a.hi))
        print(res)
    elif a.cmd == "ab":
        if any(c not in ARMS for c in a.arms.split(",")):
            sys.exit("--arms: comma-separated names from " + ", ".join(ARMS))
        res = {"args": vars(a), "at": time.strftime("%Y-%m-%d %H:%M:%S"), "arms": run_ab(a)}
    elif a.cmd == "sweep":
        masks = [int(x) for x in a.us.split(",")]
        if any(not 1 <= m <= 3000 for m in masks):
            sys.exit("--us: 1..3000 each")
        res = {"args": vars(a), "at": time.strftime("%Y-%m-%d %H:%M:%S"), "arms": run_ab(a, masks)}
    if a.json and res is not None:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
