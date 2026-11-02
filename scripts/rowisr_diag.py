#!/usr/bin/env python3
"""The row ISR rewrite's bench diagnostics: HC_DEVHOOK op 28, dev builds from
stage 1 of plans/ROW-ISR-PLAN.md (rgb/rowisr_diag.c in the firmware).

    venv/bin/python scripts/rowisr_diag.py regs [TIMER|all] [PAGE]   the CT16 timers' registers
    venv/bin/python scripts/rowisr_diag.py hold MS                   a row-only interrupt hold-off, 1..10000 ms
    venv/bin/python scripts/rowisr_diag.py status                    the hold's state and counts
    venv/bin/python scripts/rowisr_diag.py led INDEX R G B | off     one LED at one colour, every other dark
    venv/bin/python scripts/rowisr_diag.py skip MS                   the callback skips the key scan for MS ms
    ... --json                                                       the reply as JSON, decoded

`regs` reads a timer's registers as they stand (TIMER 0-5, CT16Bn; PAGE 0 is
the control set: TMRCTRL, TC, PRE, MCTRL, PWMCTRL, RIS and the terminal
match; PAGE 1 the second set, which differs by timer: rowisr_diag.h). `all`
reads CT16B0, B1, B2 and B4, both pages. Reading clears nothing. Stage 0b's
Q4 and Q5 evidence: whether a counter is running (CEN), where it is (TC),
what its matches do (MCTRL's IE/RST/STOP trios) and which outputs are
enabled (PWMCTRL's EN/IOEN).

`hold` disables the row ISR's NVIC line for MS milliseconds with everything
else running, and marks the hold on the Caps Lock LED's pin (D15, high for
the hold) for a probe: the rising edge sits in one critical section with the
NVIC disable, the falling edge with the enable (the plan, stage 2's endpoint
contract). What the board shows meanwhile, by eye, camera or the INA228, is
Q4: a hot row (the counter free-running with the last row selected) or dark
(the counter stopped). The 20 kHz tick times it in 50 us steps; refused
while a hold runs or the tick is stopped.

`led` sets a one-LED pattern that outlives the effect (applied after every
render until `led off`; it needs an effect rendering, so RGB on): with a
slow tagged slot sequence on the witness it settles Q6, which physical LED
each mux pin drives.

`skip` makes the row ISR do its LED work and skip the key scan for MS ms
(keys are dead meanwhile): health page 4's callback metric with and without
it attributes the scan's cost (stage 0b). Timed and refused as `hold` is.

Raw HID is exclusive on macOS: stop the daemon's pollers or run between a
bench trial's reads, as the other bench scripts do.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
from ak820health import open_device  # noqa: E402

SET_VALUE, CH, HC, OP = 0x07, 0x13, 0x76, 28
USAGE = "usage: rowisr_diag.py regs [TIMER|all] [PAGE] | hold MS | skip MS | status | record | led INDEX R G B | led off  [--json]"


def xfer(h, sub, args=b""):
    payload = bytes([0, SET_VALUE, CH, HC, OP, sub]) + bytes(args)
    h.write(payload + bytes(33 - len(payload)))   # report id + 32 bytes
    for _ in range(5):
        r = h.read(32, 1000)
        if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == OP:
            if r[0] != SET_VALUE:
                sys.exit(f"refused: op 28 sub {sub} ({bytes(r[:8]).hex()}); a dev build from stage 1 or later?")
            return bytes(r)
    sys.exit("no reply")


def u16(b, i): return b[i] | (b[i + 1] << 8)
def u32(b, i): return b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)


def trios(mctrl, mctrl2, timer):
    """(match, IE, RST, STOP) per match register the timer has (docs/sn32f299.md,
    section 7): CT16B1 MR0-9 in MCTRL at 3n and MR10-12 in MCTRL2; the others
    MR0-3 at 3n and MR9 at bits 21-23."""
    out = []
    if timer == 1:
        for n in range(10):
            v = (mctrl >> (3 * n)) & 7
            out.append((n, v & 1, (v >> 1) & 1, (v >> 2) & 1))
        for n in range(3):
            v = (mctrl2 >> (3 * n)) & 7
            out.append((10 + n, v & 1, (v >> 1) & 1, (v >> 2) & 1))
    else:
        for n in range(4 if timer in (0, 2, 5) else 2):
            v = (mctrl >> (3 * n)) & 7
            out.append((n, v & 1, (v >> 1) & 1, (v >> 2) & 1))
        v = (mctrl >> 21) & 7
        out.append((9, v & 1, (v >> 1) & 1, (v >> 2) & 1))
    return out


def decode_page0(r):
    t = r[4]
    tmrctrl = u32(r, 6)
    mctrl, pwmctrl, ris, term = u32(r, 14), u32(r, 18), u32(r, 22), u32(r, 26)
    d = {"timer": t, "page": 0, "TMRCTRL": tmrctrl, "CEN": tmrctrl & 1, "CRST": (tmrctrl >> 1) & 1,
         "CM": (tmrctrl >> 4) & 7, "TC": u16(r, 10), "PRE": u16(r, 12), "MCTRL": mctrl, "PWMCTRL": pwmctrl,
         "RIS": ris, "terminal_match": term, "terminal_reg": "MR12" if t == 1 else "MR9"}
    if t == 1:
        d["pwm_modes"] = [(pwmctrl >> (2 * n)) & 3 for n in range(12)]
    else:
        nch = 4 if t in (0, 2, 5) else 2
        d["pwm_en"] = [(pwmctrl >> n) & 1 for n in range(nch)]
        d["pwm_mode"] = [(pwmctrl >> (4 + 2 * n)) & 3 for n in range(nch)]
        d["pwm_ioen"] = [(pwmctrl >> (20 + n)) & 1 for n in range(nch)]
    return d


def decode_page1(r):
    t = r[4]
    w = [u32(r, 6 + 4 * k) for k in range(6)]
    names = (["MCTRL2", "PWMENB", "PWMIOENB", "MR0", "MR1", "MR2"] if t == 1 else
             ["PC", "CNTCTRL", "EM", "MR0", "MR1", "PWMmNIOCTRL" if t in (3, 4) else "MR2"])
    return {"timer": t, "page": 1, **dict(zip(names, w))}


def print_page0(d, mctrl2=None):
    t = d["timer"]
    print(f"CT16B{t}: TMRCTRL 0x{d['TMRCTRL']:08x} (CEN {d['CEN']}, CRST {d['CRST']}, CM {d['CM']})  "
          f"TC {d['TC']}  PRE {d['PRE']}  {d['terminal_reg']} {d['terminal_match']}  RIS 0x{d['RIS']:08x}")
    tr = trios(d["MCTRL"], mctrl2 or 0, t)
    print(f"  MCTRL 0x{d['MCTRL']:08x}: " + "  ".join(
        f"MR{n}:{'I' if ie else '-'}{'R' if rst else '-'}{'S' if stop else '-'}" for n, ie, rst, stop in tr)
          + ("" if t != 1 or mctrl2 is not None else "  (MR10-12 in page 1's MCTRL2)"))
    if t == 1:
        print(f"  PWMCTRL 0x{d['PWMCTRL']:08x}: modes {d['pwm_modes']} (ENB/IOENB in page 1)")
    else:
        print(f"  PWMCTRL 0x{d['PWMCTRL']:08x}: EN {d['pwm_en']} MODE {d['pwm_mode']} IOEN {d['pwm_ioen']}")


def print_page1(d):
    t = d["timer"]
    print(f"CT16B{t} page 1: " + "  ".join(f"{k} 0x{v:08x}" for k, v in d.items() if k not in ("timer", "page")))


def status_dict(r):
    return {"hold_active": bool(r[4]), "hold_ms_left": u16(r, 5), "row_was_on": bool(r[7]), "holds_done": u16(r, 8),
            "holds_backstopped": u16(r, 10), "holds_cancelled": u16(r, 12), "row_irq": r[14],
            "row_irq_enabled": bool(r[15]), "hold_depth": r[16], "last_hold_overlapped": bool(r[17]),
            "prime_timed_out": bool(r[18]), "skip_active": bool(r[19]), "skip_ms_left": u16(r, 20),
            "hw_fault": bool(r[22])}


def print_status(r):
    d = status_dict(r)
    print(f"hold {'ACTIVE, ' + str(d['hold_ms_left']) + ' ms left' if d['hold_active'] else 'idle'}; "
          f"scan skip {'ACTIVE, ' + str(d['skip_ms_left']) + ' ms left' if d['skip_active'] else 'idle'}")
    print(f"  ended by the tick {d['holds_done']}, by the backstop {d['holds_backstopped']}, cancelled by a tick stop {d['holds_cancelled']}; "
          f"the row line was {'on' if d['row_was_on'] else 'off'} when the last hold began"
          + (";  ⚠️ the last hold OVERLAPPED another holder (the clock chip's transaction): not a measurement" if d['last_hold_overlapped'] else ""))
    print(f"  row IRQ {d['row_irq']} is {'enabled' if d['row_irq_enabled'] else 'DISABLED'} now, hold depth {d['hold_depth']}"
          + (";  ⚠️ the boot's prime TIMED OUT: Bootmagic scanned an empty matrix" if d['prime_timed_out'] else "")
          + (";  ⚠️ HW FAULT: a timer's reset never completed at init, nothing runs" if d['hw_fault'] else ""))


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args:
        sys.exit(USAGE)
    cmd = args[0]
    ok = (cmd == "regs" and len(args) <= 3 and all(a == "all" or a.isdigit() for a in args[1:])) or \
         (cmd in ("hold", "skip") and len(args) == 2 and args[1].isdigit()) or (cmd in ("status", "record") and len(args) == 1) or \
         (cmd == "led" and (args[1:] == ["off"] or (len(args) == 5 and all(a.isdigit() for a in args[1:]))))
    if not ok:
        sys.exit(USAGE)   # before the board is opened: a typo must not cost a raw HID open
    h = open_device()
    try:
        if cmd == "regs":
            timers = [0, 1, 2, 4] if len(args) < 2 or args[1] == "all" else [int(args[1])]
            pages = [0, 1] if len(args) < 3 else [int(args[2])]
            if len(args) >= 2 and args[1] == "all":
                pages = [0, 1]
            out = []
            for t in timers:
                p1 = decode_page1(xfer(h, 0, bytes([t, 1]))) if 1 in pages else None
                p0 = decode_page0(xfer(h, 0, bytes([t, 0]))) if 0 in pages else None
                if as_json:
                    out += [d for d in (p0, p1) if d]
                else:
                    if p0: print_page0(p0, p1["MCTRL2"] if (p1 and t == 1) else None)
                    if p1: print_page1(p1)
            if as_json:
                print(json.dumps(out))
        elif cmd in ("hold", "skip"):
            ms = int(args[1])
            r = xfer(h, 1 if cmd == "hold" else 4, bytes([ms & 0xFF, ms >> 8]))
            if as_json:
                print(json.dumps(status_dict(r)))
            else:
                print(f"{'holding the row interrupt off' if cmd == 'hold' else 'skipping the scan'} for {ms} ms:")
                print_status(r)
        elif cmd == "record":   # op 28 sub 5: the handler's record's remainder (stage 2; page 7 has the totals)
            r = xfer(h, 5, b"")[4:]   # past the reply's header (xfer returns the raw report; status_dict indexes from 4)
            d = {"omit_run_max": r[0] | r[1] << 8, "spurious": r[2], "late_omit": r[3], "epoch_losses": r[4],
                 "invalid_services": r[5], "elapsed_min_ticks": r[6] | r[7] << 8, "omit_row": list(r[8:8 + 18]),
                 "serviced_lo16": r[26] | r[27] << 8}
            d["elapsed_min_us"] = round(d["elapsed_min_ticks"] / 48.0, 2)
            if as_json:
                print(json.dumps(d))
            else:
                print(f"longest run of omissions {d['omit_run_max']}, spurious invocations {d['spurious']}, "
                      f"omissions by the arm deadline {d['late_omit']}, epoch losses {d['epoch_losses']}, "
                      f"invalid services {d['invalid_services']}, shortest handler {d['elapsed_min_us']} us, "
                      f"services (low 16 bits) {d['serviced_lo16']}")
                print("omissions per mux row (R, B, G per key row, the pins' order; 255 = saturated):")
                for k in range(6):
                    print(f"  key row {k}: R {d['omit_row'][3 * k]:3d}  B {d['omit_row'][3 * k + 1]:3d}  G {d['omit_row'][3 * k + 2]:3d}")
        elif cmd == "status":
            r = xfer(h, 2)
            print(json.dumps(status_dict(r))) if as_json else print_status(r)
        elif cmd == "led":
            if args[1:] == ["off"]:
                r = xfer(h, 3, bytes([0xFF, 0, 0, 0]))
            else:
                i, rr, g, b = (int(x) for x in args[1:5])
                r = xfer(h, 3, bytes([i, rr, g, b]))
            d = {"led": None if r[4] == 0xFF else r[4], "r": r[5], "g": r[6], "b": r[7]}
            print(json.dumps(d) if as_json else (f"pattern off" if d["led"] is None else
                                               f"LED {d['led']} at ({d['r']}, {d['g']}, {d['b']}), every other dark"))
    finally:
        h.close()


if __name__ == "__main__":
    main()
