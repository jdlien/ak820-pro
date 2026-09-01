#!/usr/bin/env python3
"""Soak/stress harness for the AK820 Pro firmware (hardening plan phase 1.3).

Hammers the known trigger paths CONCURRENTLY from the firmware's point of
view while every host-side transaction stays strictly serialised through one
device open -- multiple outstanding reply-bearing requests on one raw-HID
interface consume each other's replies and manufacture false liveness
failures. Concurrency lives in the firmware-side cadence overlap, not in
parallel host requests.

Stressors (each on its own cadence, one loop, one handle):
  - text pushes (write-only): both LCD lines, varying lengths -> flash->LCD
    DMA blits via the glyph pump
  - VIA dynamic-keymap writes: internal-flash writes racing those blits --
    the historically reliable hang reproduction. Toggles ONE unused matrix
    position (last row/col) between KC_NO and KC_TRNS; original restored.
  - VIA rgb_matrix brightness nudges: dirties eeconfig; the final 15 s stop
    nudging (cooldown) so the debounced flush fires WHILE text still blits.
  - liveness ping (VIA get_protocol_version): the raw-HID round trip is the
    one probe that distinguishes alive from wedged.
  - health polls (channel 0x13): the counters are the pass/fail evidence.

Pass criteria (rates, not "any increase" -- boot/BT baselines are nonzero by
design): HARD FAIL on liveness loss, blit_timeout increase, tx_drop
increase, or a WDT reset during the run. tx_timeouts are reported but not
judged here -- wired soak generates no BT traffic; judge those against the
0.042/frame baseline from a BT session.

Wired mode only (replies). Stop the nowplaying agent first:
  launchctl unload ~/Library/LaunchAgents/com.jdlien.ak820pro.nowplaying.plist
Usage: soak.py [--seconds 120]
"""
import argparse, random, string, struct, sys, time

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "hostagent"))
import hid  # noqa: E402
from ak820health import read_health, open_device  # noqa: E402

SET_VALUE, TEXT_CHANNEL = 0x07, 0x12
TEXT_SET_LINE = 0x03
VIA_GET_PROTOCOL = 0x01
VIA_GET_KEYCODE, VIA_SET_KEYCODE = 0x04, 0x05
VIA_CUSTOM_SET, VIA_CUSTOM_GET = 0x07, 0x08
RGB_CHANNEL, RGB_BRIGHTNESS = 3, 1
LAYER, ROW, COL = 1, 5, 14          # WINFN, last matrix position (unused key)
KC_NO, KC_TRNS = 0x0000, 0x0001


def report(payload):
    return bytes([0x00] + payload + [0x00] * (31 - len(payload)))


class Soak:
    def __init__(self):
        self.h = open_device()
        self.misses = 0

    def xfer(self, payload, expect0, tries=3, timeout_ms=1000):
        """One serialized request/reply transaction."""
        for i in range(tries):
            self.h.write(report(payload))
            rep = self.h.read(32, timeout_ms)
            if rep and rep[0] == expect0:
                return bytes(rep)
            self.misses += 1
        return None

    def send(self, payload):  # write-only (text)
        self.h.write(report(payload))

    def ping(self):
        return self.xfer([VIA_GET_PROTOCOL], VIA_GET_PROTOCOL) is not None

    def get_keycode(self):
        r = self.xfer([VIA_GET_KEYCODE, LAYER, ROW, COL], VIA_GET_KEYCODE)
        return None if r is None else (r[4] << 8) | r[5]

    def set_keycode(self, kc):
        return self.xfer([VIA_SET_KEYCODE, LAYER, ROW, COL, kc >> 8, kc & 0xFF],
                         VIA_SET_KEYCODE) is not None

    def get_brightness(self):
        r = self.xfer([VIA_CUSTOM_GET, RGB_CHANNEL, RGB_BRIGHTNESS], VIA_CUSTOM_GET)
        return None if r is None else r[3]

    def set_brightness(self, v):
        return self.xfer([VIA_CUSTOM_SET, RGB_CHANNEL, RGB_BRIGHTNESS, v & 0xFF],
                         VIA_CUSTOM_SET) is not None

    def text(self, line, s):
        body = s.encode("ascii", "replace")[: (19 if line == 0 else 21)]
        self.send([SET_VALUE, TEXT_CHANNEL, TEXT_SET_LINE, line, 0] + list(body))

    def health(self):
        return read_health(self.h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=120)
    a = ap.parse_args()

    s = Soak()
    fails = []

    if not s.ping():
        sys.exit("FAIL: no liveness at start (wired mode? another holder?)")
    base = s.health()
    print(f"baseline: {base}")
    if base["wdt_degraded"]:
        print("WARNING: watchdog is in DEGRADED mode (>=3 consecutive resets)")

    orig_kc = s.get_keycode()
    orig_b = s.get_brightness()
    if orig_kc is None or orig_b is None:
        sys.exit("FAIL: could not read initial keymap/brightness state")
    print(f"stress position L{LAYER} r{ROW} c{COL} original=0x{orig_kc:04X}, "
          f"brightness={orig_b}; running {a.seconds}s")

    t0 = time.time()
    next_ = {"ping": 0.0, "text": 0.0, "keymap": 0.0, "rgb": 0.0, "health": 0.0}
    kc_flip, b_dir, writes = False, 1, 0
    try:
        while (now := time.time()) - t0 < a.seconds:
            el = now - t0
            cooldown = el > a.seconds - 15  # let the eeconfig flush fire under text load
            if now >= next_["ping"]:
                next_["ping"] = now + 0.1
                if not s.ping():
                    fails.append(f"liveness lost at {el:.1f}s")
                    break
            if now >= next_["text"]:
                next_["text"] = now + 0.2
                n = random.randint(3, 21)
                s.text(random.randint(0, 1),
                       "".join(random.choices(string.ascii_letters + " ", k=n)))
            if now >= next_["keymap"] and not cooldown:
                next_["keymap"] = now + 1.0
                kc_flip = not kc_flip
                if s.set_keycode(KC_TRNS if kc_flip else KC_NO):
                    writes += 1
                else:
                    fails.append(f"keymap write lost at {el:.1f}s")
                    break
            if now >= next_["rgb"] and not cooldown:
                next_["rgb"] = now + 2.0
                b_dir = -b_dir
                s.set_brightness(max(1, min(255, orig_b + b_dir)))
            if now >= next_["health"]:
                next_["health"] = now + 5.0
                h = s.health()
                if h["blit_timeouts"] > base["blit_timeouts"]:
                    fails.append(f"blit timeout at {el:.1f}s: {h['blit_timeouts']}")
                if h["wdt_consecutive_resets"] > 0 or h["wdt_fired_last_boot"]:
                    fails.append(f"WDT reset during soak at {el:.1f}s")
            time.sleep(0.01)
    finally:
        # Restore even on failure -- a soak must not leave the keymap altered.
        try:
            s.set_keycode(orig_kc)
            s.set_brightness(orig_b)
            s.text(0, "soak done")
        except Exception as e:
            print(f"RESTORE FAILED -- fix by hand in VIA: {e}", file=sys.stderr)

    end = s.health() if not fails or "liveness" not in fails[-1] else None
    print(f"\n{writes} keymap flash writes, {s.misses} reply retries")
    if end:
        print(f"final: {end}")
        if end["tx_drops"] > base["tx_drops"]:
            fails.append(f"tx drops rose {base['tx_drops']} -> {end['tx_drops']}")
        if end["blit_timeouts"] > base["blit_timeouts"]:
            fails.append(f"blit timeouts rose {base['blit_timeouts']} -> {end['blit_timeouts']}")
        gap = end["loop_gap_max_ms"]
        print(f"worst main-loop gap: {gap} ms" +
              (" (over 60 ms -- investigate)" if gap > 60 else ""))
    if fails:
        print("\nSOAK FAIL:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("\nSOAK PASS")


if __name__ == "__main__":
    main()
