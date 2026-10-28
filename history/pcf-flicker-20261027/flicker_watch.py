"""Watch the keyboard on gremlin for what could flicker the LEDs, so a flicker
JD sees can be matched to its time (the board's clock is synced to this PC).
Each second: the flash writes, the passes >= 25 ms (and how many were outside
a flash write), the cleanups, and the row ISR's rate over the second (a dip is
the LEDs scanning slower: the CPU-fed SPI0 fills, docs/leds.md). Logs only
changes and dips, with the wall-clock time. Reads only; never enumerates HID."""
import statistics
import sys
import time
from datetime import datetime

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
from menu_s0_session import open_device  # noqa: E402
import ak820health as H  # noqa: E402

OUT = sys.argv[1]
HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
DIP = 0.98   # a second's row rate under 98% of the recent median


def log(msg):
    line = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]}  {msg}"
    print(line, flush=True)
    with open(OUT, "a") as f:
        f.write(line + "\n")


def tidies(h):
    b = H._txn_page(h, H.HC_FLASHW, 4)[4:]
    return b[6] | b[7] << 8, b[0] | b[1] << 8


h = open_device()
try:
    s0 = H.read_stalls(h)
    i0, t_i0 = H.read_isr(h), time.monotonic()
    td0, used0 = tidies(h)
    log(f"start: flash_writes {s0['flash_writes']}, ge25 {s0['count_ge_25ms']} "
        f"(nonflash {s0['count_ge_25ms_nonflash']}), cleanups {td0}, log used {used0}")
    rates = []
    end = time.monotonic() + HOURS * 3600
    n = 0
    while time.monotonic() < end:
        time.sleep(1.0)
        n += 1
        s = H.read_stalls(h)
        i1, t_i1 = H.read_isr(h), time.monotonic()
        r = H.isr_rates(i0, i1, t_i1 - t_i0)["isr_per_s"]
        i0, t_i0 = i1, t_i1
        if r is not None:
            med = statistics.median(rates) if len(rates) >= 10 else None
            if med and r < DIP * med:
                log(f"row rate dip: {r:.0f}/s against {med:.0f} ({100 * r / med:.1f}%)")
            rates = (rates + [r])[-120:]
        dw = s["flash_writes"] - s0["flash_writes"]
        d25 = s["count_ge_25ms"] - s0["count_ge_25ms"]
        dnf = s["count_ge_25ms_nonflash"] - s0["count_ge_25ms_nonflash"]
        if dw or d25 or dnf or s["count_ge_25ms"] < s0["count_ge_25ms"]:
            td, used = tidies(h)
            log(f"flash writes +{dw}, passes >= 25 ms +{d25} (outside a write +{dnf}), "
                f"cleanups {td} (+{td - td0}), log used {used}, flash gap max {s['flash_gap_max_ms']} ms")
            td0 = td
        s0 = s
        if n % 600 == 0 and rates:
            log(f"(alive: row rate median {statistics.median(rates):.0f}/s)")
finally:
    h.close()
    log("stopped")
