#!/usr/bin/env python3
"""The configuration menu's S1: the polled sends' failure paths, on the
`devfault` build (HC_POLLFAULT, [0x07, 0x13, 0x75, n, mode, skip]). Codex's
acceptance for revisions 14 and 15 (plans/review-codex-s1-step4/6-*.md).

    venv-win/Scripts/python.exe scripts/menu_s1_fault.py [--out F] < /dev/null

Cases, each in mode 0 (the send gives up halfway) and mode 1 (after every
byte):
  fill    a selection change paints two rows: skip 0-4 lands on one of the
          first fill's five window sends, skip 5 on its payload
  dma     a pattern change paints the title's glyphs first: skip 0-4 lands
          on one of the first glyph's DMA-arm window sends
  retry   a lost completion (HC_BLITFAULT 1) whose retry's window gives up
          (skip 5: the original arm's five window sends go through)
  mono    S1's mono text (lcd_blit_mono through the stream, F3 in lit/half
          rows): a selection change's first piece, skip 0-4 on its window,
          skip 5 on its payload
After each: the owner took the loss (op 27's losses +1) and repainted
(pixels_done), a later DMA and a later fill both work (on F3: a later style
change and a later selection change), no blit timeout where none belongs,
and invariant_fail holds only 0x20 (PO_FAIL_SPI0_POLL, sticky, expected).
Never enumerates HID on Windows."""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402
from menu_s0_accept import to_dash, until  # noqa: E402

SET_VALUE, CH = 0x07, 0x13
MONO_FIRST = 16   # op 27 sub 0's F3 patterns: 16 lit/half ... 19 inverted/full
HC_BLITFAULT, HC_POLLFAULT = 0x77, 0x75
AK820 = os.path.join(os.path.dirname(__file__), "..", "ak820-agent", "target", "release", "ak820.exe")
EXPECTED_FAIL = 0x20


def hc(h, cmd, args):
    h.write(bytes([0, SET_VALUE, CH, cmd]) + bytes(args) + bytes(29 - len(args)))
    end = time.perf_counter() + 3.0
    while time.perf_counter() < end:
        r = h.read(32, 250)
        if r and len(r) == 32 and r[1] == CH and r[2] == cmd:
            if r[0] != SET_VALUE:
                raise RuntimeError(f"HC {cmd:#x} unhandled: not a devfault build?")
            return bytes(r)
    raise RuntimeError(f"HC {cmd:#x}: no reply")


def health():
    out = subprocess.run([AK820, "health", "--json"], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=30)
    j = json.loads(out.stdout)
    return {"timeouts": j.get("blit_timeouts"), "retry_ok": j.get("vitals", {}).get("blit_retry_successes")}


def settle(h, timeout=5.0):
    ok, s = until(h, lambda s: s["pixels_done"], timeout=timeout)
    return ok, s


def mut(h, sub, args=b""):
    st, seq = mutate(h, sub, args)
    if st != 0:
        raise RuntimeError(f"op 27 sub {sub} refused: {st}")
    state, s = wait(h, seq)
    if state != "done":
        raise RuntimeError(f"op 27 sub {sub}: {state}")


def one(h, kind, mode, skip, pattern):
    s0 = read_state(h)
    h0 = health()
    if kind == "retry":
        hc(h, HC_POLLFAULT, [1, mode, skip])
        hc(h, HC_BLITFAULT, [1])
    else:
        hc(h, HC_POLLFAULT, [1, mode, skip])
    # The trigger: rows by a selection change, glyphs by a pattern change.
    if kind in ("fill", "mono"):
        mut(h, 1, bytes([1]))
    else:
        mut(h, 0, bytes([pattern[0], 0]))
        pattern[0] ^= 1
    # The fault taken, the loss handled, the target repainted.
    t0 = time.perf_counter()
    lost = False
    while time.perf_counter() - t0 < 4.0:
        s = read_state(h)
        if s["losses"] != s0["losses"]:
            lost = True
            break
        time.sleep(0.02)
    ok, s1 = settle(h, timeout=5.0)
    left = hc(h, HC_POLLFAULT, [0, 0, 0])[3]   # writes 0 too: nothing may stay armed
    h1 = health()
    # Afterwards: a DMA (title glyphs, a flash read on SPI1) and a fill (rows)
    # work; on F3, a style change (the title and every row) and a selection.
    if kind == "mono":
        mut(h, 0, bytes([MONO_FIRST + 2 + (pattern[0] & 1), 0]))   # inverted, half or full
        pattern[0] ^= 1
        ok_dma, _ = settle(h)
        mut(h, 0, bytes([MONO_FIRST, 0]))                           # back to lit, half rows
        settle(h)
    else:
        mut(h, 0, bytes([pattern[0], 0]))
        pattern[0] ^= 1
        ok_dma, _ = settle(h)
    mut(h, 1, bytes([1]))
    ok_fill, s2 = settle(h)
    h2 = health()
    dt = (h1["timeouts"] or 0) - (h0["timeouts"] or 0)
    ev = {"kind": kind, "mode": mode, "skip": skip, "lost": lost, "repainted": ok,
          "losses": [s0["losses"], s1["losses"]], "left_armed": left,
          "blit_timeouts": dt, "after_dma": ok_dma, "after_fill": ok_fill,
          "timeouts_after": (h2["timeouts"] or 0) - (h1["timeouts"] or 0),
          "invariant_fail": s2["invariant_fail"], "owner": s2["owner"]}
    good = lost and ok and ok_dma and ok_fill and s2["owner"] == "menu" and \
        (s2["invariant_fail"] & ~EXPECTED_FAIL) == 0 and ev["timeouts_after"] == 0
    if kind == "retry":
        good = good and dt >= 1   # the lost completion's timeout, then the retry gave up
    else:
        good = good and dt == 0
    return good, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_s1_fault.json")
    a = ap.parse_args()
    h = open_device()
    results = []
    pattern = [1]
    try:
        to_dash(h)
        mut(h, 4)                     # open the fixture
        ok, _ = settle(h)
        if not ok:
            raise RuntimeError("the fixture didn't settle")
        cases = [("fill", m, k) for m in (0, 1) for k in range(6)] + \
                [("dma", m, k) for m in (0, 1) for k in range(5)] + \
                [("retry", m, 5) for m in (0, 1)] + \
                [("mono", m, k) for m in (0, 1) for k in range(6)]   # retry: the original arm's five window sends pass; the retry's first fails
        for kind, mode, skip in cases:
            # The fixture closes after 24 s idle: a selection change keeps it.
            if read_state(h)["session"] != "open":
                mut(h, 4)
                settle(h)
            screen = read_state(h)["screen"]
            if kind == "mono" and screen != 3:
                mut(h, 0, bytes([MONO_FIRST, 0]))   # F3, lit text, half rows
                settle(h)
            elif kind != "mono" and screen != 1:
                mut(h, 0, bytes([3, 0]))            # F3 -> F2 -> F1
                mut(h, 0, bytes([3, 0]))
                settle(h)
            good, ev = one(h, kind, mode, skip, pattern)
            ev["pass"] = good
            results.append(ev)
            print(("PASS " if good else "FAIL ") + json.dumps(ev), flush=True)
        mut(h, 4)                     # close
        to_dash(h)
    finally:
        h.close()
        with open(a.out, "w") as f:
            json.dump(results, f, indent=1)
    n_fail = sum(1 for r in results if not r["pass"])
    print(f"{len(results) - n_fail} of {len(results)} passed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
