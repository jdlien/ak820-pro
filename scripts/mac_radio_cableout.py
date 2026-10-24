#!/usr/bin/env python3
"""The daemon's radio, cable out and back, on the Mac
(plans/RAWHID-24G-DAEMON-PLAN.md; Gremlin's test a-d):

    venv/bin/python scripts/mac_radio_cableout.py [--out-s 90] [--json OUT]

a) the cable in: the status file reads transport=usb, radio=off;
b) the cable's data cut (uhubctl, hub 3-1.3.4 port 2): within ~two media ticks
   radio=qualified, transport=radio, radio_pushes counting; held --out-s;
d) the data back: radio -> off ("the board is on USB") first, transport=usb
   on the next media tick; then the band read back over USB (HC_DEVHOOK op
   18: both text lines and the playback readout) against the status file's
   last text, and the board's raw81 counters (op 17) read twice a few
   seconds apart: they must not move once the radio has stood down.

Needs the daemon running with --radio, the slider on 2.4G, the Mac's dongle,
relay 2 on (the board charging; uhubctl cuts the data only). The data goes
back on in a `finally`, whatever happened.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deep_sleep as ds  # noqa: E402
import mac_raw81_s2 as ms  # noqa: E402  (patches win_raw81_s2's transfers for the Mac)

cm = ds.cm
w = ms.w
STATUS = os.path.expanduser("~/Library/Application Support/ak820pro/ak820-agent.status")
HUB = ["-l", "3-1.3.4", "-p", "2", "-e"]   # docs/test-bench.md: the relay cable's port
KEYS = ("transport", "radio", "radio_qualified", "radio_sessions", "radio_pushes", "radio_failures",
        "radio_incomplete", "radio_silent", "radio_last_push", "radio_last_error", "media_last_text", "board")


def status():
    try:
        with open(STATUS) as f:
            kv = dict(ln.rstrip("\n").split("=", 1) for ln in f if "=" in ln)
    except OSError:
        return {}
    return {k: kv.get(k) for k in KEYS} | {"updated": kv.get("updated")}


def uhub(action):
    r = subprocess.run(["perl", "-e", "alarm 15; exec @ARGV", "uhubctl", *HUB, "-a", action],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"uhubctl {action} failed ({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
    return time.time()


def band():
    def rd(h):
        out = {}
        for sub in (0, 1):
            b = w.devhook(h, 18, sub)
            n = b[4]
            out[f"line{sub}"] = {"text": bytes(b[7:7 + n]).decode("ascii", "replace"), "icon": b[5],
                                 "present": bool(b[6])}
        b = w.devhook(h, 18, 2)
        out["playback"] = {"active": bool(b[4]), "ticking": bool(b[5]),
                           "pos": int.from_bytes(bytes(b[6:8]), "little"),
                           "dur": int.from_bytes(bytes(b[8:10]), "little")}
        return out
    return rd(ms.usb_open())


def wait_for(pred, secs, log, what):
    t0 = time.time()
    last = None
    while time.time() - t0 < secs:
        s = status()
        if s != last:
            log.append({"t": round(time.time(), 2), **s})
            last = s
        if pred(s):
            return time.time() - t0, s
        time.sleep(0.5)
    raise SystemExit(f"{what}: not within {secs} s; last {last}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-s", type=float, default=90)
    ap.add_argument("--json")
    a = ap.parse_args()
    rep, log, checks = {"at": time.strftime("%Y-%m-%d %H:%M:%S")}, [], []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail != "" else ""), flush=True)

    s = status()
    rep["before"] = s
    check("a) cable in: transport=usb, radio=off", s.get("transport") == "usb" and s.get("radio") == "off", s)
    rep["band_before"] = band()
    rep["counters_before"] = w.counters(ms.usb_open())
    cut = None
    try:
        cut = uhub("off")
        print(f"data off at {time.strftime('%H:%M:%S')}", flush=True)
        dt, s = wait_for(lambda s: s.get("radio") == "qualified" and s.get("transport") == "radio", 30, log,
                         "b) radio qualified")
        check(f"b) radio=qualified, transport=radio after {dt:.1f} s", True, s)
        p0 = int(s.get("radio_pushes") or 0)
        time.sleep(a.out_s)
        s = status()
        rep["held"] = s
        check(f"b) held {a.out_s:.0f} s: still transport=radio, pushes {p0} -> {s.get('radio_pushes')}",
              s.get("transport") == "radio" and int(s.get("radio_pushes") or 0) > p0, s)
    finally:
        back = uhub("on")
        print(f"data on at {time.strftime('%H:%M:%S')}", flush=True)
    dt, s = wait_for(lambda s: s.get("radio") == "off", 30, log, "d) radio stands down")
    check(f"d) radio -> off after {dt:.1f} s", True, s)
    dt, s = wait_for(lambda s: s.get("transport") == "usb", 30, log, "d) transport back to usb")
    check(f"d) transport=usb after {dt:.1f} s", True, s)
    time.sleep(4)
    rep["band_after"] = b = band()
    text = (status().get("media_last_text") or "")
    # A paused track still has its text (with the pause icon); nothing
    # reported at all is a CLEAR, and the band then reads present=0.
    lines = [b[k]["text"].strip() for k in ("line0", "line1") if b[k]["text"].strip()]
    shown = b["line0"]["present"] and all(ln in text for ln in lines) if text.strip() else not b["line0"]["present"]
    check("d) the band holds the daemon's last text", shown, {"band": b, "media_last_text": text})
    c1 = w.counters(ms.usb_open())
    time.sleep(8)
    c2 = w.counters(ms.usb_open())
    moved = {k: c2[k] - c1[k] for k in c1 if isinstance(c1[k], int) and c2.get(k) != c1[k]
             and k not in ("state", "session_live", "session", "last_seq")}
    check("d) no radio traffic after the stand-down (op 17 counters still for 8 s)", not moved, moved)
    for k in ("stale", "busy", "taint", "drops", "resp_expired"):
        check(f"board {k} +0 across the test", c2.get(k) == rep["counters_before"].get(k),
              (rep["counters_before"].get(k), c2.get(k)))
    rep.update({"cut": cut, "back": back, "status_log": log, "counters_after": c2, "checks": checks})
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump(rep, open(a.json, "w"), indent=1)
    bad = [c for c in checks if not c["ok"]]
    print(f"{len(bad)} FAILED" if bad else "all checks pass")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
