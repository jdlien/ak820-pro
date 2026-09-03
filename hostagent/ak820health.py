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

Needs the USB cable. The slider position does NOT matter: raw-HID replies
return over USB in every mode (board commit 4b86d95014) -- older notes that
demanded "wired mode" describe pre-fix firmware. The counters accumulate in
every mode; with no host attached the LCD debug page (Fn+D) is the readout.

Pages 2-4 (--stalls, --rows, --isr) are documented in firmware health.h.

Usage:  ak820health.py [--json] [--stalls] [--rows] [--isr]
Exit 0 always when the read works; interpreting the numbers is the caller's
job (scripts/soak.py does thresholds).
"""
import argparse, json, struct, sys
import venv_bootstrap  # noqa: F401 -- re-execs under the repo venv if hid is missing
import hid

VID, PID = 0x0C45, 0x8009
USAGE_PAGE, USAGE = 0xFF60, 0x61
SET_VALUE, HEALTH_CHANNEL, HC_GET = 0x07, 0x13, 0x01
HC_GET2, HC_RESET, HC_GET3, HC_GET4 = 0x04, 0x05, 0x06, 0x07   # stall / reset / per-row / ISR pages

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

# Page 3: per-row sampling. Added when the driver still published ONE row per
# matrix_scan() call (fixed 2026-09-03: every row every ISR cycle). row_samples
# are u16 and wrap every ~5 min at ~215/s; page 4 carries a u32 total.
FIELDS3 = ["row_samples", "row_gap_max_ms", "raw_edges", "consumes",
           "cooked_changes", "row_gap_max_row", "matrix_rows"]

# Page 4 (proto v5): the row ISR's own cost. Its period is (duration + ~53 us)
# because the PWM counter is re-armed at the ISR's END, so duration -- not the
# timer -- sets the row rate and caps the main loop. Ticks at st_freq per second.
FIELDS4 = ["isr_entries", "isr_ticks_sum", "isr_ticks_min", "isr_ticks_max",
           "st_freq", "uptime_ms", "row_samples_total", "_reserved4"]


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


def read_rows(h=None, timeout_ms=500):
    """Page 3: per-row sampling -- fairness, worst per-row gap, raw edges."""
    own = h is None
    if own:
        h = open_device()
    try:
        rep = _txn(h, HC_GET3, timeout_ms)
        if rep[3] < 4:
            raise SystemExit(f"firmware health proto v{rep[3]}; page 3 needs v4")
        v = struct.unpack_from("<7H3I2B", bytes(rep), 4)
        return {"row_samples": list(v[0:6]), "row_gap_max_ms": v[6],
                "raw_edges": v[7], "consumes": v[8], "cooked_changes": v[9],
                "row_gap_max_row": v[10], "matrix_rows": v[11]}
    finally:
        if own:
            h.close()


def read_isr(h=None, timeout_ms=500):
    """Page 4: row-ISR entries and duration (ticks), plus a firmware timebase."""
    own = h is None
    if own:
        h = open_device()
    try:
        rep = _txn(h, HC_GET4, timeout_ms)
        if rep[3] < 5:
            raise SystemExit(f"firmware health proto v{rep[3]}; page 4 needs v5")
        v = struct.unpack_from("<2I2H4I", bytes(rep), 4)
        d = dict(zip(FIELDS4, v))
        d.pop("_reserved4", None)
        return d
    finally:
        if own:
            h.close()


def isr_rates(a, b, wall_s, rows=6):
    """Derive rates from two page-4 reads. dt comes from the board's own ms
    timebase; its ratio to the wall clock is reported too, because docs/leds.md
    records that timebase running slow under ISR load and this makes it a
    number rather than a memory."""
    f = b["st_freq"] or 187500
    m32 = 0xFFFFFFFF
    dt = ((b["uptime_ms"] - a["uptime_ms"]) & m32) / 1000.0
    de = (b["isr_entries"] - a["isr_entries"]) & m32
    dtk = (b["isr_ticks_sum"] - a["isr_ticks_sum"]) & m32
    drs = (b["row_samples_total"] - a["row_samples_total"]) & m32
    us = 1e6 / f
    return {
        "isr_dt_s": round(dt, 3),
        "isr_per_s": round(de / dt, 1) if dt else None,
        "isr_mean_us": round(dtk / de * us, 1) if de else None,
        "isr_min_us": round(b["isr_ticks_min"] * us, 1) if b["isr_ticks_min"] != 0xFFFF else None,
        "isr_max_us": round(b["isr_ticks_max"] * us, 1),
        "isr_cpu_pct": round(dtk / f / dt * 100, 1) if dt else None,
        "row_samples_per_row_per_s": round(drs / dt / rows, 1) if dt else None,
        "timebase_vs_wall": round(dt / wall_s, 4) if wall_s else None,
    }


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
    ap.add_argument("--rows", action="store_true",
                    help="per-row sampling: is every key looked at often enough?")
    ap.add_argument("--stalls", action="store_true",
                    help="also show the phase-1 stall counters")
    ap.add_argument("--isr", action="store_true",
                    help="row-ISR cost: two page-4 reads 2 s apart -> entries/s, "
                         "mean/min/max us, CPU share")
    a = ap.parse_args()
    if a.reset:
        reset_counters()
        print("counters reset (watchdog counters kept -- they are boot facts)")
        return
    d = read_health()
    if a.stalls:
        d.update(read_stalls())
    if a.rows:
        d.update(read_rows())
    if a.isr:
        import time
        A = read_isr(); tA = time.monotonic()      # open/close per read: the
        time.sleep(2.0)                             # agents need the interface too
        B = read_isr(); tB = time.monotonic()
        d.update(B)
        d.update(isr_rates(A, B, tB - tA, d.get("matrix_rows", 6)))
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

        # NOT nested under --stalls: `--rows` alone must print the row page.
        # It used to be, so `ak820health.py --rows` silently read the page and
        # showed nothing -- which is the exact invocation you reach for when you
        # think you just dropped a keystroke.
        if a.rows:
            n = d["matrix_rows"]
            print()
            print(f"{'row_samples':24} {d['row_samples'][:n]}")
            print(f"{'row_gap_max_ms':24} {d['row_gap_max_ms']}  (row {d['row_gap_max_row']})")
            for k in ("raw_edges", "consumes", "cooked_changes"):
                print(f"{k:24} {d[k]}")
            s_ = d["row_samples"][:n]
            # row_samples is a uint16_t in the firmware and the page is full at
            # 28 bytes, so it cannot be widened without restructuring. At the
            # post-fix ~217 samples/s/row it WRAPS EVERY ~5 MINUTES, so the
            # absolute counts only mean something right after --reset.
            #
            # The rows track each other to within ~1 count, so they wrap within
            # a moment of each other -- but a read landing in that moment sees
            # e.g. 65535 and 0 and would report a catastrophic imbalance on a
            # perfectly healthy board. Undo the straddle before comparing.
            if s_ and max(s_) - min(s_) > 32768:
                s_ = [v + 65536 if v < 32768 else v for v in s_]
            if s_:
                even = max(s_) <= min(s_) * 1.25
                print(f"\n  spread {min(s_)}-{max(s_)} "
                      f"({'EVEN' if even else 'UNEVEN -- some keys looked at less often'})"
                      f"  [uint16, wraps every ~5 min -- --reset first for absolute counts]")
            # The whole point of the page. Sampling must be fast against a
            # 25-80 ms keypress; the one-row publish bug read 156-169 ms here.
            g = d["row_gap_max_ms"]
            if g >= 25:
                print(f"  ** worst gap {g} ms on row {d['row_gap_max_row']} -- "
                      "a keypress can END inside that window and never be seen **")
            elif g >= 10:
                print(f"  worst gap {g} ms -- elevated; healthy is single-digit")
            else:
                print(f"  worst gap {g} ms -- healthy "
                      "(a 25-80 ms press gets sampled several times)")
            if d.get("key_presses"):
                print(f"  raw_edges {d['raw_edges']} vs key_presses {d['key_presses']} "
                      f"(expect ~2x: a press and a release are two raw edges)")
        if a.isr:
            print()
            for k in ("isr_per_s", "isr_mean_us", "isr_min_us", "isr_max_us",
                      "isr_cpu_pct", "row_samples_per_row_per_s", "timebase_vs_wall"):
                print(f"{k:24} {d[k]}")
            # The timer configuration (4.8 MHz / 256 ticks) predicts 18,750
            # ISR/s and ~1042 samples/s/row; the board measures ~3,870 and
            # ~215. Not a clock bug: rgb_callback re-arms the PWM counter at
            # its END, so its period is (ISR duration + ~53 us) and the ISR's
            # own cost sets the row rate. isr_cpu_pct is the share of the M0
            # spent inside it -- the ceiling on both scanning and the main loop.
            print("\n  period = ISR duration + ~53 us (counter re-armed at ISR end), "
                  "so isr_mean_us sets the row rate;\n  isr_cpu_pct is the M0 share "
                  "inside the row ISR -- the ceiling on scanning and the main loop")


if __name__ == "__main__":
    try:
        main()
    except hid.HIDException as e:
        print(f"ak820health: {e}", file=sys.stderr)
        raise SystemExit(1)
