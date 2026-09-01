#!/usr/bin/env python3
"""Read the AK820 Pro's health counters over raw HID.

Wire format (health channel 0x13, firmware health.c / ak820pro.c):
    request : [0x07 SET_VALUE][0x13 HEALTH_CHANNEL][0x01 HC_GET]
    reply   : [0x07][0x13][0x01][version][28-byte snapshot]
Snapshot, little-endian:
    u32 blit_timeouts, u32 tx_sent, u32 tx_timeouts, u32 tx_drops,
    u32 rx_malformed, u32 loop_gap_max_ms, u16 scan_rate,
    u8 wdt_consecutive_resets, u8 flags (bit0 wdt-fired-last-boot,
    bit1 wdt-degraded)

Needs the dip switch in WIRED mode -- raw-HID replies route through the
active host driver, exactly like ak820ctl. The counters accumulate in every
mode; only reading them out needs the cable path.

Usage:  ak820health.py [--json]
Exit 0 always when the read works; interpreting the numbers is the caller's
job (scripts/soak.py does thresholds).
"""
import argparse, json, struct, sys
import hid

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61
SET_VALUE, HEALTH_CHANNEL, HC_GET = 0x07, 0x13, 0x01

FIELDS = ["blit_timeouts", "tx_sent", "tx_timeouts", "tx_drops",
          "rx_malformed", "loop_gap_max_ms", "scan_rate",
          "wdt_consecutive_resets", "flags"]


def open_device():
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
            return hid.Device(path=d["path"])
    raise SystemExit("raw HID interface not found (wired mode? VIA holding it?)")


def read_health(h=None, timeout_ms=500):
    own = h is None
    if own:
        h = open_device()
    try:
        h.write(bytes([0x00, SET_VALUE, HEALTH_CHANNEL, HC_GET] + [0x00] * 29))
        rep = h.read(32, timeout_ms)
        if not rep or len(rep) < 32 or rep[0] != SET_VALUE or rep[1] != HEALTH_CHANNEL:
            raise SystemExit("no/garbled health reply (BT mode routes replies "
                             "over the air -- dip switch to cable)")
        vals = struct.unpack_from("<6IHBB", bytes(rep), 4)
        d = dict(zip(FIELDS, vals))
        d["version"] = rep[3]
        d["wdt_fired_last_boot"] = bool(d["flags"] & 1)
        d["wdt_degraded"] = bool(d["flags"] & 2)
        return d
    finally:
        if own:
            h.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    d = read_health()
    if a.json:
        print(json.dumps(d))
    else:
        for k in ("blit_timeouts", "tx_sent", "tx_timeouts", "tx_drops",
                  "rx_malformed", "loop_gap_max_ms", "scan_rate",
                  "wdt_consecutive_resets", "wdt_fired_last_boot", "wdt_degraded"):
            print(f"{k:24} {d[k]}")


if __name__ == "__main__":
    try:
        main()
    except hid.HIDException as e:
        print(f"ak820health: {e}", file=sys.stderr)
        raise SystemExit(1)
