#!/usr/bin/env python3
"""Cut and restore the keyboard's USB power from the host (docs/test-bench.md).

⚠️ RETIRED (by 11-03): the Acasis hub's brick is off the "Christmas Tree"
outlet, which powers the household's tree again, so `off` and `on` refuse and
switch nothing. The keyboard's 5 V is relay 2. `status` still reads the bus.
The rest of this docstring describes how it worked.

The keyboard's port on the Acasis hub is left switched ON (the hub remembers
it across power cycles), and the hub's brick is on the "Christmas Tree"
outlet, which Home Assistant switches (`switch.christmas_tree`; until
2026-10-13 it was in Apple Home, driven by Shortcuts). Cutting the outlet
cuts the keyboard's USB power, and so its charging. Retired for the keyboard:
the USB relay does this now (docs/test-bench.md). Every request is confirmed from the USB side: the keyboard leaving
or rejoining the bus in the IORegistry. That opens no device, so it is safe
under the never-enumerate-HID rule.

  bench_power.py status
  bench_power.py off [--log CSV] [--note TEXT]
  bench_power.py on  [--log CSV] [--note TEXT]

`off` and `on` exit 0 only once the bus confirms the change. Home Assistant
accepting the call means the request went out, not that the outlet switched,
so an unconfirmed request is retried once and then reported as a failure.
The token comes from the Keychain item `home-assistant`, or $HA_TOKEN.
With --log, one row per action is appended: the request time, the confirmed
time (epoch seconds, to 0.25 s), and the result.

⚠️ The slider must be on BT or 2.4G: on cable a cut is a cold power-off and
the battery log in RAM is lost. ⚠️ The outlet powers the WHOLE hub.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.request

HA_URL = os.environ.get("HA_URL", "https://ha.jdlien.ca")
OUTLET = "switch.christmas_tree"
POLL_S = 0.25
CONFIRM_S = {"off": 8.0, "on": 20.0}   # measured 10-08: gone within 1 s; all chips back in 5 s


def present():
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-w0"], capture_output=True, text=True).stdout
    return "AK820 PRO@" in out


def stamp(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) + f".{int(t % 1 * 100):02d}"


def token():
    t = os.environ.get("HA_TOKEN") or subprocess.run(
        ["security", "find-generic-password", "-s", "home-assistant", "-w"],
        capture_output=True, text=True, timeout=10).stdout.strip()
    if not t:
        sys.exit("no Home Assistant token: the Keychain item home-assistant, or $HA_TOKEN")
    return t


def request(action):
    """One call to Home Assistant. (The Shortcuts it replaced could hang: on
    10-08 a "Turn on" sat for 60 s and switched nothing.)"""
    t = time.time()
    req = urllib.request.Request(
        f"{HA_URL}/api/services/switch/turn_{action}", method="POST",
        data=json.dumps({"entity_id": OUTLET}).encode(),
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except OSError as e:   # URLError, HTTPError and timeouts
        return t, -1, str(e)
    return t, 0, ""


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
            note = f"Home Assistant: {err[:120]}"
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
    sys.exit("refusing: the \"Christmas Tree\" outlet no longer powers the bench (retired by "
             "11-03). It powers the household's tree again, and the keyboard's 5 V is relay 2 "
             "(docs/test-bench.md, \"The USB relay\"). Nothing was switched.")
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
