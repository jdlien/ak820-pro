#!/usr/bin/env python3
"""Redraw times in each menu face on JD's board (8b0f47e245), measured by the
board (op 27 sub 10's repaint_ms: a target's creation to its settling, and
the longest main-loop pass). The face set over HC_PROFILES' live apply, the
board's own live settings put back at the end. Same opener as flash.sh's tools."""
import json
import os
import sys
import time

R = "/Users/jdlien/code/ak820-pro"
sys.path.insert(0, os.path.join(R, "scripts"))
sys.path.insert(0, os.path.join(R, "hostagent"))
import ak820profiles as ap  # noqa: E402
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402
from menu_s1_gate import decode_meas  # noqa: E402

FACES = [("10px bold", 0), ("10px", ap.BV_REG), ("8px", ap.BV_SMALL)]
ROWS = {"10px bold": 7, "10px": 7, "8px": 8}
R_FONT, R_DIAG = 9, 11


def with_face(live, bits):
    r = bytearray(live)
    r[12] = (r[12] & ap.BV_VIEW) | bits
    r[26] = ap.crc8(r[1:26])
    return bytes(r)


def settled(h, timeout=4.0):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        s = read_state(h)
        if s["owner"] == "menu" and s["pixels_done"]:
            return s
        if s["owner"] == "dash" and s["session"] == "none":
            return s
        time.sleep(0.05)
    return read_state(h)


def measure(h, what, fn):
    xfer(h, 10, bytes([1]))          # arm: maxima zeroed
    time.sleep(0.05)
    fn()
    s = settled(h)
    time.sleep(0.05)
    m = decode_meas(xfer(h, 10, bytes([0])))
    e = {"what": what, "repaint_ms": m["repaint_ms"], "pass_max_ms": round(m["pass_max_us"] / 1000, 1),
         "over15": m["over15"], "screen": s["screen"], "cursor": s["cursor"]}
    print(json.dumps(e), flush=True)
    return e


def op(h, sub, args=b""):
    st, seq = mutate(h, sub, args)
    if st != 0:
        raise SystemExit(f"op 27 sub {sub} refused ({st})")
    wait(h, seq, poll=0.02)


def main():
    h = open_device()
    out = []
    orig = ap.read_live(h)
    try:
        if read_state(h)["session"] != "none":
            op(h, 11)                    # a menu left open: closed first
            time.sleep(1.5)
        for name, bits in FACES:
            print(f"== {name}", flush=True)
            ap.apply_live(h, with_face(orig, bits))
            time.sleep(1.0)
            rows = ROWS[name]
            res = {"face": name}
            res["open"] = measure(h, f"{name}: open (top level)", lambda: op(h, 11))
            moves = [measure(h, f"{name}: cursor down {i + 1}", lambda: op(h, 1, bytes([1]))) for i in range(3)]
            res["move"] = moves
            res["page"] = measure(h, f"{name}: to page two (Font's row)", lambda: op(h, 1, bytes([R_FONT - 3])))
            res["into"] = measure(h, f"{name}: into the Font page", lambda: op(h, 2))
            res["back"] = measure(h, f"{name}: back (hold)", lambda: op(h, 3))
            res["diag"] = measure(h, f"{name}: into Diagnostics", lambda: (op(h, 1, bytes([R_DIAG - R_FONT])), op(h, 2)))
            res["sysinfo"] = measure(h, f"{name}: into System info", lambda: op(h, 2))
            op(h, 3); settled(h); op(h, 3); settled(h)
            nxt = FACES[(FACES.index((name, bits)) + 1) % 3]
            res["refont"] = measure(h, f"{name} -> {nxt[0]}: the face changed, menu open",
                                    lambda: ap.apply_live(h, with_face(orig, nxt[1])))
            op(h, 11)                    # close
            time.sleep(1.5)
            out.append(res)
    finally:
        try:
            if read_state(h)["session"] != "none":
                op(h, 11)
                time.sleep(1.5)
        finally:
            ap.apply_live(h, orig)       # JD's live settings, as they were
            print("live settings put back", flush=True)
            h.close()
    with open(os.path.join(os.path.dirname(__file__), "font_timing.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
