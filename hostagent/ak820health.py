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
HC_GET2, HC_RESET = 0x04, 0x05      # stall page + counter reset (proto v2)

FIELDS = ["blit_timeouts", "tx_sent", "tx_timeouts", "tx_drops",
          "rx_malformed", "loop_gap_max_ms", "scan_rate",
          "wdt_consecutive_resets", "flags"]

# Page 2 (LOOP-BUDGET-PLAN phase 1). A SECOND page exists because HC_GET's
# payload was already exactly full at 28 bytes.
FIELDS2 = ["count_ge_10ms", "count_ge_25ms", "passes", "flash_writes",
           "flash_gap_max_ms", "blit_gap_max_ms", "i2c_gap_max_ms",
           "count_ge_25ms_nonflash", "key_presses",
           "loop_gap_max_mark", "_reserved"]

MARKS = {0: "none", 1: "flash", 2: "blit", 3: "i2c"}


def open_device(tries=12, delay=0.25):
    """The raw-HID interface is EXCLUSIVE, and the host agents open it briefly
    every few seconds (timekeeper shells out to ak820ctl; nowplaying opens per
    push). A single attempt therefore fails often enough to make a passive
    measurement impractical -- retry across the gaps instead of demanding the
    agents be stopped, which would itself change what is being measured."""
    import time
    last = None
    for _ in range(tries):
        for d in hid.enumerate(VID, PID):
            if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
                try:
                    return hid.Device(path=d["path"])
                except Exception as e:            # held by an agent or VIA
                    last = e
                    break
        else:
            raise SystemExit("raw HID interface not found (board unplugged?)")
        time.sleep(delay)
    raise SystemExit(f"raw HID busy after {tries} tries: {last}\n"
                     "  something is holding it exclusively -- check "
                     "`hostagent/install-agents.sh --status` and `pgrep -fl qmk`")


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


def _txn(h, cmd, timeout_ms=500):
    h.write(bytes([0x00, SET_VALUE, HEALTH_CHANNEL, cmd] + [0x00] * 29))
    rep = h.read(32, timeout_ms)
    if not rep or len(rep) < 32 or rep[0] != SET_VALUE or rep[1] != HEALTH_CHANNEL:
        raise SystemExit("no/garbled health reply (BT mode routes replies "
                         "over the air -- dip switch to cable)")
    return rep


def read_stalls(h=None, timeout_ms=500):
    """Page 2: the stall-measurement counters."""
    own = h is None
    if own:
        h = open_device()
    try:
        rep = _txn(h, HC_GET2, timeout_ms)
        # v3 repacked page 2 (u16 maxima + the nonflash discriminator). Same
        # command, different layout, so a version check is the only thing
        # standing between a stale board and silently misparsed numbers.
        if rep[3] < 3:
            raise SystemExit(f"firmware health proto v{rep[3]}; page 2 needs v3 "
                             "-- flash the current build")
        vals = struct.unpack_from("<4I5HBB", bytes(rep), 4)
        d = dict(zip(FIELDS2, vals))
        d["loop_gap_max_mark"] = MARKS.get(d["loop_gap_max_mark"], d["loop_gap_max_mark"])
        d.pop("_reserved", None)
        return d
    finally:
        if own:
            h.close()


def reset_counters(h=None, timeout_ms=500):
    """Clear the resettable counters. Watchdog counters are boot facts and
    survive deliberately -- a reset must not erase evidence that the board
    reset itself."""
    own = h is None
    if own:
        h = open_device()
    try:
        _txn(h, HC_RESET, timeout_ms)
    finally:
        if own:
            h.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="clear the resettable counters, then exit")
    ap.add_argument("--stalls", action="store_true",
                    help="also show the phase-1 stall counters")
    a = ap.parse_args()
    if a.reset:
        reset_counters()
        print("counters reset (watchdog counters kept -- they are boot facts)")
        return
    d = read_health()
    if a.stalls:
        d.update(read_stalls())
    if a.json:
        print(json.dumps(d))
    else:
        for k in ("blit_timeouts", "tx_sent", "tx_timeouts", "tx_drops",
                  "rx_malformed", "loop_gap_max_ms", "scan_rate",
                  "wdt_consecutive_resets", "wdt_fired_last_boot", "wdt_degraded"):
            print(f"{k:24} {d[k]}")
        if a.stalls:
            print()
            for k in ("passes", "count_ge_10ms", "count_ge_25ms",
                      "count_ge_25ms_nonflash", "loop_gap_max_mark",
                      "flash_writes", "flash_gap_max_ms", "blit_gap_max_ms",
                      "i2c_gap_max_ms", "key_presses"):
                print(f"{k:24} {d[k]}")
            # >=25 ms is the only class that can LOSE a press: contact lasts
            # 25-80 ms, so anything shorter ends with the key still down.
            if d["count_ge_25ms_nonflash"]:
                print(f"\n  ** {d['count_ge_25ms_nonflash']} UNEXPLAINED stall(s) "
                      ">= 25 ms -- long enough to lose a keystroke **")
            elif d["count_ge_25ms"]:
                print(f"\n  {d['count_ge_25ms']} stall(s) >= 25 ms, all attributed to "
                      "flash (wear-levelling consolidation -- understood, bounded)")
            else:
                print("\n  no stall >= 25 ms since reset "
                      "(shorter stalls delay a press, they cannot drop it)")


if __name__ == "__main__":
    try:
        main()
    except hid.HIDException as e:
        print(f"ak820health: {e}", file=sys.stderr)
        raise SystemExit(1)
