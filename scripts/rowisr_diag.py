#!/usr/bin/env python3
"""The row ISR rewrite's bench diagnostics: HC_DEVHOOK op 28, dev builds from
stage 1 of plans/ROW-ISR-PLAN.md (rgb/rowisr_diag.c in the firmware).

    venv/bin/python scripts/rowisr_diag.py regs [TIMER|all] [PAGE]   the CT16 timers' registers
    venv/bin/python scripts/rowisr_diag.py hold MS                   a row-only interrupt hold-off, 1..10000 ms
    venv/bin/python scripts/rowisr_diag.py status                    the hold's state and counts
    venv/bin/python scripts/rowisr_diag.py led INDEX R G B | off     one LED at one colour, every other dark
    venv/bin/python scripts/rowisr_diag.py skip MS                   the callback skips the key scan for MS ms
    venv/bin/python scripts/rowisr_diag.py record                    the handler's record past page 7 (stage 2)
    venv/bin/python scripts/rowisr_diag.py usb                       the USB frame counter's record and the clocks' state (D3 case 5)
    venv/bin/python scripts/rowisr_diag.py silence MS [DELAY]        a silence of every interrupt, 1..8000 ms (fractions allowed: 7.5), after DELAY ms (200)
    venv/bin/python scripts/rowisr_diag.py report                    the last silence's report: the spin's length, the extension's reading across it
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

`usb` reads the frame-counter detector's record (op 28 sub 6): how many
intervals it judged, how many it rejected (a disagreement of the extension's
span and the frame counter's beyond 3 ms + 0.2%, a bus event inside the
interval, or the frames stopping with no flag; each rejection is one epoch
loss), how many it excluded unjudged (both ends inside a stale's recovery
with no frame yet: no loss of their own), the worst distance it accepted,
the last rejection's two spans, and the clocks' state now.

`silence` arms a silence of every interrupt (op 28 sub 7): after DELAY ms
the board masks every interrupt for MS ms (sent in microseconds, so 7.5 and
8.1 are fine) with a marker on the Win Lock LED's pin C15, then the record
shows the guard's or the frame counter's verdict (`record`, `usb`; health
page 7). The host sees no replies meanwhile. `report` (subs 8 and 9) gives
the last silence as the spin measured it and the extension's copied state
before and 2 ms after it: a loss generation moved across it is one loss,
the guard's if its rejection count moved too, otherwise the frame
counter's (compare `usb`'s counts); an unchanged generation with the
extension's reading far short of the spin's is the alias past the guard,
which the frame counter must catch on USB and nothing catches off it.

Raw HID is exclusive on macOS: stop the daemon's pollers or run between a
bench trial's reads, as the other bench scripts do.
"""
import json
import os
import sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
from ak820health import open_device  # noqa: E402

SET_VALUE, CH, HC, OP = 0x07, 0x13, 0x76, 28
USAGE = "usage: rowisr_diag.py regs [TIMER|all] [PAGE] | hold MS | skip MS | status | record | usb | silence MS [DELAY] | report | readcost | sections | led INDEX R G B | led off  [--json]"


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
            "hw_fault": bool(r[22]), "silence_armed": bool(r[23]), "silence_ms": u16(r, 24),
            "silence_last_ticks": u32(r, 26), "silence_last_ms": round(u32(r, 26) / 187.5, 3), "silences_run": r[30]}


USB_STATES = {0: "uninit", 1: "stop", 2: "ready", 3: "selected", 4: "ACTIVE", 5: "SUSPENDED"}


def usb_dict(r):
    o = r[4:]
    return {"usb_checked": u32(o, 0), "usb_rejects": o[4], "usb_events": o[5], "usb_worst_ms": u16(o, 6),
            "usb_last_dt_ms": u16(o, 8), "usb_last_df_ms": u16(o, 10), "loss_gen": u32(o, 12), "usb_gen": u16(o, 16),
            "usb_state": USB_STATES.get(o[18], o[18]), "usb_trusted_now": bool(o[19]), "frmno": u16(o, 20),
            "time_valid": bool(o[22]), "time_excl": o[23], "guard_last_gap_ticks": u16(o, 24),
            "guard_last_gap_ms": round(u16(o, 24) / 187.5, 3), "frames_fresh": bool(o[26]),
            "usb_unjudged": o[27] & 0x7F, "recovery_pending": bool(o[27] & 0x80)}


def report_dict(r, r2=None):
    o = r[4:]
    d = {"us": u32(o, 0), "ticks": u32(o, 4), "measured_ms": round(u32(o, 4) / 187.5, 3), "ext0": u32(o, 8), "ext1": u32(o, 12),
         "gen0": u16(o, 16), "gen1": u16(o, 18), "tc0": u16(o, 20), "tc1": u16(o, 22), "valid0": bool(o[24]), "valid1": bool(o[25]),
         "lost": o[26], "run": o[27]}
    d["ext_delta_ticks"] = (d["ext1"] - d["ext0"]) & 0xFFFFFFFF
    d["ext_delta_ms"] = round(d["ext_delta_ticks"] / 187.5, 3)
    d["gen_delta"] = (d["gen1"] - d["gen0"]) & 0xFFFF
    if r2 is not None:
        p = r2[4:]
        d.update({"stamp0": u16(p, 0), "stamp1": u16(p, 2), "guard_gap0_ticks": u16(p, 4), "guard_gap1_ticks": u16(p, 6),
                  "guard_rejects0": u16(p, 8), "guard_rejects1": u16(p, 10)})
        d["guard_rejected"] = d["guard_rejects1"] != d["guard_rejects0"]   # by the count, not the gap's value (two equal gaps would hide one)
        d["guard_gap1_ms"] = round(d["guard_gap1_ticks"] / 187.5, 3)
    return d


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
    print(f"  silence {'ARMED, ' + str(d['silence_ms']) + ' ms' if d['silence_armed'] else 'none armed'}; "
          f"run {d['silences_run']}, the last measured {d['silence_last_ms']} ms ({d['silence_last_ticks']} CT16B5 ticks)")


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args:
        sys.exit(USAGE)
    cmd = args[0]
    ok = (cmd == "regs" and len(args) <= 3 and all(a == "all" or a.isdigit() for a in args[1:])) or \
         (cmd in ("hold", "skip") and len(args) == 2 and args[1].isdigit()) or (cmd in ("status", "record", "usb", "report", "readcost", "sections") and len(args) == 1) or \
         (cmd == "silence" and 2 <= len(args) <= 3 and all(a.replace(".", "", 1).isdigit() for a in args[1:])) or \
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
        elif cmd == "readcost":   # op 28 sub 10: HCLK cycles a read, the loop included (a RAM word is the loop alone)
            o = xfer(h, 10)[4:]
            d = {"frmno": u16(o, 0), "insts": u16(o, 2), "cfg": u16(o, 4), "ct16b5_tc": u16(o, 6), "ram": u16(o, 8),
                 "trials": o[10], "reads": u16(o, 11) or 256}   # 95ef5cbc5d writes the 256 one byte high ([17]); the count is fixed anyway
            if as_json:
                print(json.dumps(d))
            else:
                print(f"HCLK cycles a read, the loop included, the least of {d['trials']} trials of {d['reads']} reads: "
                      f"USB FRMNO {d['frmno']}, USB INSTS {d['insts']}, USB CFG {d['cfg']}, CT16B5 TC {d['ct16b5_tc']}, a RAM word {d['ram']}; "
                      f"so a USB register read costs about {max(d['frmno'] - d['ram'], 0)} cycles ({max(d['frmno'] - d['ram'], 0) / 48:.2f} us) "
                      f"over a RAM word's, a timer's {max(d['ct16b5_tc'] - d['ram'], 0)}")
        elif cmd == "sections":   # op 28 sub 11: the handler's sections since the last read, HCLK ticks summed; two reads make a window
            names = ["entry snapshot", "step 1 and the frame counter's judgment", "steps 2-5 (mux rows, scan, match registers)",
                     "step 6 (the arm)", "exit snapshot", "exit judgment and the record"]
            xfer(h, 11)   # reset
            time.sleep(10)
            o = xfer(h, 11)[4:]
            n = u32(o, 0)
            sums = [u32(o, 4 + 4 * i) for i in range(6)]
            d = {"services": n, "sections_us": [round(x / n / 48.0, 2) if n else None for x in sums],
                 "total_us": round(sum(sums) / n / 48.0, 2) if n else None, "names": names}
            if as_json:
                print(json.dumps(d))
            elif n == 0:
                print("no full services in 10 s (scan-only, or the handler held off): nothing to divide")
            else:
                print(f"{n} full services in 10 s; the handler's sections, mean us (HCLK ticks / 48):")
                for nm, us in zip(names, d["sections_us"]):
                    print(f"  {us:8.2f}  {nm}")
                print(f"  {d['total_us']:8.2f}  total, stamp 0 to stamp 6: the ISR hooks and the sums' own commit lie outside, page 4 includes them")
        elif cmd == "usb":   # op 28 sub 6
            d = usb_dict(xfer(h, 6))
            if as_json:
                print(json.dumps(d))
            else:
                print(f"frame counter: {d['usb_checked']} intervals judged, {d['usb_rejects']} rejected on the spans, "
                      f"{d['usb_events']} rejected for a bus event or the frames stopping, {d['usb_unjudged']} excluded unjudged in a "
                      f"stale's recovery; the worst accepted distance {d['usb_worst_ms']} ms; "
                      f"the last rejection's spans {d['usb_last_dt_ms']} ms by the extension, {d['usb_last_df_ms']} by the frames")
                print(f"  now: USB {d['usb_state']}, frames {'trusted' if d['usb_trusted_now'] else 'NOT trusted'}, FRMNO {d['frmno']}, "
                      f"bus-event generation {d['usb_gen']}; the extension {'VALID' if d['time_valid'] else 'INVALID'}, "
                      f"loss generation {d['loss_gen']}, exclusions 0x{d['time_excl']:02x}")
        elif cmd == "silence":   # op 28 sub 7
            us = int(round(float(args[1]) * 1000)); delay = int(float(args[2])) if len(args) == 3 else 0
            r = xfer(h, 7, us.to_bytes(4, "little") + bytes([delay & 0xFF, delay >> 8]))
            if as_json:
                print(json.dumps(status_dict(r)))
            else:
                print(f"a silence of every interrupt armed: {us / 1000} ms after {delay or 200} ms")
                print_status(r)
        elif cmd == "report":   # op 28 subs 8 and 9
            d = report_dict(xfer(h, 8), xfer(h, 9))
            if as_json:
                print(json.dumps(d))
            else:
                verdict = ("no loss across it" if not d["gen_delta"] else
                           f"a loss across it, the guard's (its count moved; the gap it rejected: {d['guard_gap1_ms']} ms)" if d["guard_rejected"] else
                           "a loss across it, not the guard's (the frame counter's or an exclusion's: see `usb`)")
                print(f"the last silence: asked {d['us'] / 1000} ms, the spin measured {d['measured_ms']} ms ({d['ticks']} ticks), "
                      f"TC {d['tc0']} -> {d['tc1']}; the extension read {d['ext_delta_ms']} ms across it (its stamps {d['stamp0']} -> {d['stamp1']}), "
                      f"generation {d['gen0']} -> {d['gen1']}: {verdict}; VALID before {d['valid0']} after {d['valid1']}; "
                      f"run {d['run']}, not run for a high pin {d['lost']}")
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
