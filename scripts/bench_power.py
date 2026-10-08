#!/usr/bin/env python3
"""Cut and restore the keyboard's USB power from the host (docs/test-bench.md).

The keyboard's port on the Acasis hub is left switched ON (the hub remembers
it across power cycles), and the hub's brick is on the HomeKit outlet
"Christmas Tree". Cutting the outlet cuts the keyboard's USB power, and so its
charging. Every request is confirmed from the USB side: the keyboard leaving
or rejoining the bus in the IORegistry. That opens no device, so it is safe
under the never-enumerate-HID rule.

  bench_power.py status
  bench_power.py off [--log CSV] [--note TEXT]
  bench_power.py on  [--log CSV] [--note TEXT]

`off` and `on` exit 0 only once the bus confirms the change. The shortcut
returning means HomeKit accepted the request, not that the outlet switched,
so an unconfirmed request is retried once and then reported as a failure.
With --log, one row per action is appended: the request time, the confirmed
time (epoch seconds, to 0.25 s), and the result.

⚠️ The slider must be on BT or 2.4G: on cable a cut is a cold power-off and
the battery log in RAM is lost. ⚠️ The outlet powers the WHOLE hub.
"""
import argparse
import csv
import os
import subprocess
import sys
import time

SHORTCUT = {"off": "Turn off Christmas Tree", "on": "Turn on Christmas Tree"}
POLL_S = 0.25
CONFIRM_S = {"off": 8.0, "on": 20.0}   # measured 10-08: gone within 1 s; all chips back in 5 s


def present():
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-w0"], capture_output=True, text=True).stdout
    return "AK820 PRO@" in out


def stamp(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) + f".{int(t % 1 * 100):02d}"


def request(action):
    """One shortcut run. It can hang: on 10-08 a "Turn on" sat for 60 s and
    switched nothing, and the retry returned in 2 s and worked."""
    t = time.time()
    try:
        r = subprocess.run(["shortcuts", "run", SHORTCUT[action]], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return t, -1, "shortcut hung for 30 s"
    return t, r.returncode, (r.stderr or r.stdout).strip()


def wait_for(want_present, limit):
    end = time.time() + limit
    while time.time() < end:
        if present() == want_present:
            return time.time()
        time.sleep(POLL_S)
    return None


def switch(action):
    want = action == "on"
    if present() == want:
        return None, None, "already " + ("present" if want else "absent") + ": nothing confirms the request"
    for attempt in (1, 2):
        t_req, rc, err = request(action)
        if rc != 0:
            note = f"shortcut exit {rc}: {err[:120]}"
            if attempt == 2:
                return t_req, None, note
            continue
        t_ok = wait_for(want, CONFIRM_S[action])
        if t_ok is not None:
            return t_req, t_ok, "confirmed" + (" (on the retry)" if attempt == 2 else "")
    return t_req, None, f"not confirmed in {CONFIRM_S[action]:.0f} s, twice"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "off", "on"])
    ap.add_argument("--log")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    if a.action == "status":
        print("present" if present() else "absent")
        return
    t_req, t_ok, result = switch(a.action)
    line = (f"{a.action}: requested {stamp(t_req) if t_req else '-'}, "
            f"bus {stamp(t_ok) if t_ok else '-'}: {result}")
    print(line)
    if a.log:
        new = not os.path.exists(a.log)
        with open(a.log, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["action", "requested", "confirmed", "requested_epoch", "confirmed_epoch", "result", "note"])
            w.writerow([a.action, stamp(t_req) if t_req else "", stamp(t_ok) if t_ok else "",
                        f"{t_req:.2f}" if t_req else "", f"{t_ok:.2f}" if t_ok else "", result, a.note])
    sys.exit(0 if t_ok else 1)


if __name__ == "__main__":
    main()
