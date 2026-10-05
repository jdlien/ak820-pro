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
Protocol 8 (Phase 1b) adds three paged commands, all shown by --stalls:
HC_LINK (every way the CH582F link can lose a frame), HC_FLASHW (internal-flash
write sessions by writer and kb field; flash_stats.h) and HC_ACCT (the per-task
accounting of slow passes; loop_acct.h). --acct-on / --acct-off / --acct-reset
drive the accounting for the cost A/B (the plan's gate 3).

Usage:  ak820health.py [--json] [--stalls] [--rows] [--isr]
                       [--acct-on | --acct-off | --acct-reset]
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
HC_FLASHW, HC_ACCT, HC_LINK = 0x0C, 0x0D, 0x0E                  # protocol 8: Phase 1b diagnostics

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


# Protocol 8. HC_LINK: every way the CH582F link can lose a frame
# (ch582_link_stats). "<5I3HH"
LINK_FIELDS = ["sent", "timeouts", "queue_full", "giveups", "replaced",
               "uart_overrun", "uart_framing", "uart_parity", "_reserved"]
# HC_FLASHW: write sessions/programs/erases by writer (flash_stats.h).
WRITERS = ["other", "kb", "rgb", "via"]
KB_FIELDS = ["bt", "rtc_period", "lcd_brightness", "clock_mode", "batt_level"]
RTC_PATHS = {0: "-", 1: "sof", 2: "pcf"}
# HC_ACCT: scope order is loop_acct.h's enum acct_scope, unaccounted last.
SCOPES = ["ch582", "battery", "display_hk", "blit_pump", "rtc_task", "rtc_fast",
          "leds", "health", "eeconfig", "second_edge", "anim", "hk_other",
          "unaccounted"]


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


def _txn_page(h, cmd, page, arg=0, timeout_ms=500):
    """A paged protocol-8 command: [cmd, page, arg] -> [cmd, page, 28 bytes].
    The reply must answer THIS command (CLAUDE.md: validate every read)."""
    h.write(bytes([0x00, SET_VALUE, HEALTH_CHANNEL, cmd, page, arg] + [0x00] * 27))
    rep = h.read(32, timeout_ms)
    if not rep or len(rep) < 32 or rep[0] != SET_VALUE or rep[1] != HEALTH_CHANNEL or rep[2] != cmd:
        raise SystemExit(f"no/garbled reply to health command {cmd:#04x} page {page} "
                         "(protocol 8 firmware needed)")
    return bytes(rep)


def read_link(h):
    rep = _txn(h, HC_LINK)
    if rep[2] != HC_LINK or rep[3] < 8:
        raise SystemExit(f"firmware health proto v{rep[3]}; HC_LINK needs v8 -- flash the current build")
    d = dict(zip(LINK_FIELDS, struct.unpack_from("<5I3HH", bytes(rep), 4)))
    d.pop("_reserved")
    return d


def read_flashw(h):
    p0 = _txn_page(h, HC_FLASHW, 0)
    p1 = _txn_page(h, HC_FLASHW, 1)
    p2 = _txn_page(h, HC_FLASHW, 2)
    v0 = struct.unpack_from("<4I4H2H", p0, 4)
    v1 = struct.unpack_from("<4I5H", p1, 4)
    v2 = struct.unpack_from("<HBBH4II", p2, 4)
    return {
        "sessions": dict(zip(WRITERS, v0[0:4])),
        "erases": dict(zip(WRITERS, v0[4:8])),
        "programs": dict(zip(WRITERS, v1[0:4])),
        "kb_field_sessions": dict(zip(KB_FIELDS, v1[4:9])),
        "kb_mixed": v0[8], "kb_unknown": v0[9],
        "rtc_last_proposed": v2[0], "rtc_last_proposed_path": RTC_PATHS.get(v2[1], v2[1]),
        "rtc_last_stored_path": RTC_PATHS.get(v2[2], v2[2]), "rtc_last_stored": v2[3],
        "rtc_proposals": {"sof": v2[4], "pcf": v2[5]},
        "rtc_stores": {"sof": v2[6], "pcf": v2[7]},
        "last_erase_uptime_ms": v2[8],
    }


def read_acct(h, op=None):
    """op: None (read), 'on', 'off' or 'reset' (then read)."""
    if op in ("on", "off"):
        p0 = _txn_page(h, HC_ACCT, 0xF0, 1 if op == "on" else 0)
    elif op == "reset":
        p0 = _txn_page(h, HC_ACCT, 0xF1)
    else:
        p0 = _txn_page(h, HC_ACCT, 0)
    enabled, n, ring_len, ring_next = p0[4:8]
    passes, slow, st_hz, uptime, written = struct.unpack_from("<5I", p0, 8)
    slow_t = list(struct.unpack_from("<7I", _txn_page(h, HC_ACCT, 1), 4)) + \
             list(struct.unpack_from("<6I", _txn_page(h, HC_ACCT, 2), 4))
    all_ms = list(struct.unpack_from("<7I", _txn_page(h, HC_ACCT, 3), 4)) + \
             list(struct.unpack_from("<6I", _txn_page(h, HC_ACCT, 4), 4))
    top = list(struct.unpack_from("<13H", _txn_page(h, HC_ACCT, 5), 4))
    ring = []
    for i in range(ring_len):
        r = _txn_page(h, HC_ACCT, 16 + i)
        up = struct.unpack_from("<I", r, 4)[0]
        if up:
            ring.append({"uptime_ms": up, "pass_ms": r[8],
                         "scopes_ms": dict(zip(SCOPES, r[9:9 + n]))})
    ring.sort(key=lambda e: e["uptime_ms"])
    return {
        "enabled": bool(enabled), "passes": passes, "slow_passes": slow,
        "st_freq": st_hz, "uptime_ms": uptime, "ring_written": written,
        "slow_ms": {k: round(t * 1000 / st_hz, 2) for k, t in zip(SCOPES, slow_t)},
        "all_ms": dict(zip(SCOPES, all_ms)),
        "slow_top": dict(zip(SCOPES, top)),
        "ring": ring,
    }


def print_phase1b(d):
    lk = d.get("link")
    if lk:
        print("\ntransport (every way the CH582F link can lose a frame):")
        print(f"  sent {lk['sent']}  timeouts {lk['timeouts']}  queue_full {lk['queue_full']}  "
              f"giveups {lk['giveups']}  replaced {lk['replaced']}  "
              f"| uart overrun {lk['uart_overrun']} framing {lk['uart_framing']} parity {lk['uart_parity']}")
    fw = d.get("flash")
    if fw:
        print("\ninternal-flash writes by writer (sessions / programs / erases):")
        for w in WRITERS:
            print(f"  {w:6} {fw['sessions'][w]:7} {fw['programs'][w]:8} {fw['erases'][w]:6}")
        kf = fw["kb_field_sessions"]
        print("  kb sessions by field: " + "  ".join(f"{k} {v}" for k, v in kf.items()) +
              f"  mixed {fw['kb_mixed']}  unknown {fw['kb_unknown']}")
        print(f"  rtc period: last proposed {fw['rtc_last_proposed']} ({fw['rtc_last_proposed_path']}), "
              f"last stored {fw['rtc_last_stored']} ({fw['rtc_last_stored_path']}); "
              f"proposals sof {fw['rtc_proposals']['sof']} pcf {fw['rtc_proposals']['pcf']}, "
              f"stores sof {fw['rtc_stores']['sof']} pcf {fw['rtc_stores']['pcf']}")
        le = fw["last_erase_uptime_ms"]
        print(f"  last page erase at uptime {le / 1000:.1f} s" if le else "  no page erase since reset")
    ac = d.get("acct")
    if ac:
        print(f"\nper-task accounting ({'ON' if ac['enabled'] else 'OFF'}): {ac['passes']} passes, "
              f"{ac['slow_passes']} slow (>= 10 ms)")
        tot = sum(ac["slow_ms"].values()) or 1
        print(f"  {'scope':12} {'slow ms':>9} {'share':>6} {'largest':>7} {'all ms':>10}")
        for k in SCOPES:
            print(f"  {k:12} {ac['slow_ms'][k]:9.1f} {100 * ac['slow_ms'][k] / tot:5.1f}% "
                  f"{ac['slow_top'][k]:7} {ac['all_ms'][k]:10}")
        if ac["ring"]:
            print(f"  last {len(ac['ring'])} slow passes (uptime s, pass ms: scopes > 0 ms):")
            for e in ac["ring"]:
                parts = ", ".join(f"{k} {v}" for k, v in e["scopes_ms"].items() if v)
                print(f"    {e['uptime_ms'] / 1000:10.1f}  {e['pass_ms']:3} ms: {parts}")


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
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--acct-on", action="store_true", help="turn the per-task accounting on, then show it")
    g.add_argument("--acct-off", action="store_true", help="turn it off (gate 3's A/B), then show it")
    g.add_argument("--acct-reset", action="store_true", help="clear the accounting only, then show it")
    a = ap.parse_args()
    if a.reset:
        reset_counters()
        print("counters reset (watchdog counters kept -- they are boot facts)")
        return
    d = read_health()
    op = "on" if a.acct_on else "off" if a.acct_off else "reset" if a.acct_reset else None
    if op:
        h = open_device()
        try:
            d["acct"] = read_acct(h, op)
        finally:
            h.close()
        a.stalls = True
    if a.stalls:
        d.update(read_stalls())
        if d.get("version", 0) >= 8:
            h = open_device()
            try:
                d["link"] = read_link(h)
                d["flash"] = read_flashw(h)
                if "acct" not in d:
                    d["acct"] = read_acct(h)
            finally:
                h.close()
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
            if d.get("version", 0) >= 8:
                print_phase1b(d)
            else:
                print(f"\n  (protocol v{d.get('version')}: no transport, flash-writer or "
                      "per-task pages before v8)")

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
