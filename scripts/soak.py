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
    the historically reliable hang reproduction. Toggles ONE matrix HOLE
    (row 5 col 3 -- no physical key maps there on any layer) between KC_NO
    and KC_TRNS; original restored and VERIFIED at exit.
  - RGB stress: brightness nudges plus an EFFECT SWEEP that discovers the
    enabled modes by set-then-readback and dwells on the two highest
    (the board-local RAINFALL/DRIFT land at the top of the enum). VIA sets
    are *_noeeprom, so every change batch is followed by id_custom_save --
    THAT is what arms the deferred eeconfig flush this soak exists to race
    against the blits. The final 15 s stop changing values (cooldown) so
    the settle-gated flush actually fires while text still blits.
  - liveness ping (VIA get_protocol_version): the raw-HID round trip is the
    one probe that distinguishes alive from wedged.
  - health polls (channel 0x13): the counters are the pass/fail evidence.

Pass criteria are DELTAS against the starting snapshot (a prior WDT test
leaves nonzero boot counters that are not this run's failure): HARD FAIL on
liveness loss, blit_timeout increase, tx_drop increase, or a WDT reset
count/flag increase during the run. tx_timeouts are reported, not judged --
wired soak generates no BT traffic; judge those against the 0.042/frame
baseline in a BT session. On failure the tail of the console log is printed
if consolelog.sh has been writing one.

Wired mode only (replies). Stop the nowplaying agent first:
  launchctl unload ~/Library/LaunchAgents/com.jdlien.ak820pro.nowplaying.plist
Usage: soak.py [--seconds 300]
"""
import argparse, os, random, string, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
import hid  # noqa: E402
from ak820health import (read_health, read_stalls, reset_counters,  # noqa: E402
                         open_device)

SET_VALUE, TEXT_CHANNEL = 0x07, 0x12
TEXT_SET_LINE = 0x03
VIA_GET_PROTOCOL = 0x01
VIA_GET_KEYCODE, VIA_SET_KEYCODE = 0x04, 0x05
VIA_CUSTOM_SET, VIA_CUSTOM_GET, VIA_CUSTOM_SAVE = 0x07, 0x08, 0x09
RGB_CHANNEL = 3
RGB_BRIGHTNESS, RGB_EFFECT, RGB_SPEED, RGB_COLOR = 1, 2, 3, 4
# A matrix HOLE: (5,3) exists in the 6x15 matrix but maps to no physical key
# in the layout (verified against keyboard.json), so dynamic-keymap writes
# there are invisible whatever value they hold mid-soak.
LAYER, ROW, COL = 1, 5, 3
KC_NO, KC_TRNS = 0x0000, 0x0001
CONSOLE_LOG = os.path.expanduser("~/Library/Logs/ak820pro-console.log")


def report(payload):
    # 33 bytes: report id + full 32-byte report -- one short and macOS
    # quietly drops the write.
    return bytes([0x00] + payload + [0x00] * (32 - len(payload)))


class Soak:
    def __init__(self):
        self.h = open_device()
        self.misses = 0

    def close(self):
        self.h.close()

    def xfer(self, payload, expect0, tries=3, timeout_ms=1000):
        """One serialized request/reply transaction."""
        for _ in range(tries):
            self.h.write(report(payload))
            rep = self.h.read(32, timeout_ms)
            if rep and rep[0] == expect0:
                return bytes(rep)
            self.misses += 1
        return None

    def send(self, payload):
        """Nominally write-only (text) -- but VIA ECHOES every packet, and an
        unread echo left queued desynchronises the next transaction's reply.
        So consume the echo: every push is a transaction on a shared handle.
        (ak820text.py gets away without reading because it closes its handle,
        discarding the queue -- a one-open-per-push luxury a soak can't afford.)"""
        self.h.write(report(payload))
        self.h.read(32, 300)

    def ping(self):
        return self.xfer([VIA_GET_PROTOCOL], VIA_GET_PROTOCOL) is not None

    def get_keycode(self):
        r = self.xfer([VIA_GET_KEYCODE, LAYER, ROW, COL], VIA_GET_KEYCODE)
        return None if r is None else (r[4] << 8) | r[5]

    def set_keycode(self, kc):
        return self.xfer([VIA_SET_KEYCODE, LAYER, ROW, COL, kc >> 8, kc & 0xFF],
                         VIA_SET_KEYCODE) is not None

    def rgb_get(self, vid):
        r = self.xfer([VIA_CUSTOM_GET, RGB_CHANNEL, vid], VIA_CUSTOM_GET)
        return None if r is None else r[3]

    def rgb_set(self, vid, *vals):
        return self.xfer([VIA_CUSTOM_SET, RGB_CHANNEL, vid] + [v & 0xFF for v in vals],
                         VIA_CUSTOM_SET) is not None

    def rgb_save(self):
        # id_custom_save is what moves the *_noeeprom changes into the
        # deferred eeconfig flush -- the internal-flash write under test.
        return self.xfer([VIA_CUSTOM_SAVE, RGB_CHANNEL], VIA_CUSTOM_SAVE) is not None

    def text(self, line, s):
        body = s.encode("ascii", "replace")[: (19 if line == 0 else 21)]
        self.send([SET_VALUE, TEXT_CHANNEL, TEXT_SET_LINE, line, 0] + list(body))

    def health(self):
        # Belt and braces: drain any stray queued reply before a framed read.
        while self.h.read(32, 20):
            pass
        return read_health(self.h)

    def stalls(self):
        while self.h.read(32, 20):
            pass
        return read_stalls(self.h)

    def reset_stalls(self):
        while self.h.read(32, 20):
            pass
        reset_counters(self.h)

    def discover_effects(self, limit=60):
        """Set-then-readback probe for enabled effect ids. The firmware
        clamps/ignores disabled indices, so an id that reads back is real."""
        found = []
        for v in range(1, limit):
            if self.rgb_set(RGB_EFFECT, v) and self.rgb_get(RGB_EFFECT) == v:
                found.append(v)
        return found


def console_tail(n=25):
    if os.path.exists(CONSOLE_LOG):
        out = subprocess.run(["tail", f"-{n}", CONSOLE_LOG],
                             capture_output=True, text=True).stdout
        print(f"\n--- console log tail ---\n{out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=300)
    a = ap.parse_args()

    s = Soak()
    fails = []
    rc = 1

    try:
        if not s.ping():
            sys.exit("FAIL: no liveness at start (wired mode? another holder?)")
        base = s.health()
        print(f"baseline: {base}")
        # Phase-1 gate: measure THIS run, not everything since boot.
        s.reset_stalls()
        if base["wdt_degraded"]:
            print("WARNING: watchdog is DEGRADED (>=3 consecutive resets) -- "
                  "power cycle before a real soak")

        orig_kc = s.get_keycode()
        orig_b = s.rgb_get(RGB_BRIGHTNESS)
        orig_fx = s.rgb_get(RGB_EFFECT)
        if orig_kc is None or orig_b is None or orig_fx is None:
            sys.exit("FAIL: could not read initial keymap/RGB state")

        print("discovering enabled effects...", end=" ", flush=True)
        effects = s.discover_effects()
        s.rgb_set(RGB_EFFECT, orig_fx)
        print(f"{effects} (customs are the top two)")
        dwell = effects[-2:] if len(effects) >= 2 else effects
        print(f"stress hole L{LAYER} r{ROW} c{COL} original=0x{orig_kc:04X}, "
              f"brightness={orig_b}, effect={orig_fx}; running {a.seconds}s")

        t0 = time.time()
        next_ = {"ping": 0.0, "text": 0.0, "keymap": 0.0, "rgb": 0.0,
                 "fx": 10.0, "health": 0.0}
        kc_flip, b_dir, writes, fx_i = False, 1, 0, 0
        while (now := time.time()) - t0 < a.seconds:
            el = now - t0
            cooldown = el > a.seconds - 15
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
                s.rgb_set(RGB_BRIGHTNESS, max(1, min(255, orig_b + b_dir)))
                s.rgb_save()   # arm the deferred eeconfig flush -- the race under test
            if now >= next_["fx"] and not cooldown and effects:
                # Cycle every enabled effect; dwell 15 s on the top two
                # (RAINFALL/DRIFT -- the newest per-frame code), 4 s others.
                fx = effects[fx_i % len(effects)]
                fx_i += 1
                s.rgb_set(RGB_EFFECT, fx)
                s.rgb_save()
                next_["fx"] = now + (15.0 if fx in dwell else 4.0)
            if now >= next_["health"]:
                next_["health"] = now + 5.0
                try:
                    h = s.health()
                except SystemExit:
                    # A garbled reply mid-soak is a failed poll, not a reason
                    # to bail past the restore block (which an earlier version
                    # did, stranding the stress values on the board).
                    fails.append(f"health poll failed at {el:.1f}s")
                    break
                if h["blit_timeouts"] > base["blit_timeouts"]:
                    fails.append(f"blit timeout at {el:.1f}s: {h['blit_timeouts']}")
                if (h["wdt_consecutive_resets"] > base["wdt_consecutive_resets"]
                        or (h["wdt_fired_last_boot"] and not base["wdt_fired_last_boot"])):
                    fails.append(f"WDT reset during soak at {el:.1f}s")
            time.sleep(0.01)

        # Restore and VERIFY -- a soak must not leave state altered, and a
        # silently failed restore must not read as a pass.
        restore_fail = []
        if not s.set_keycode(orig_kc) or s.get_keycode() != orig_kc:
            restore_fail.append(f"keymap (want 0x{orig_kc:04X})")
        s.rgb_set(RGB_EFFECT, orig_fx)
        s.rgb_set(RGB_BRIGHTNESS, orig_b)
        s.rgb_save()
        if s.rgb_get(RGB_EFFECT) != orig_fx or s.rgb_get(RGB_BRIGHTNESS) != orig_b:
            restore_fail.append("rgb effect/brightness")
        if restore_fail:
            fails.append("RESTORE FAILED: " + ", ".join(restore_fail) +
                         " -- fix by hand in VIA")
        s.text(0, "soak done")

        end = None
        try:
            end = s.health()
        except SystemExit:
            pass
        print(f"\n{writes} keymap flash writes, {s.misses} reply retries")
        if end:
            print(f"final: {end}")
            if end["tx_drops"] > base["tx_drops"]:
                fails.append(f"tx drops rose {base['tx_drops']} -> {end['tx_drops']}")
            if end["blit_timeouts"] > base["blit_timeouts"]:
                fails.append(f"blit timeouts rose {base['blit_timeouts']} -> {end['blit_timeouts']}")
            gap = end["loop_gap_max_ms"]
            print(f"worst main-loop gap: {gap} ms")

        # ---- stall gate (LOOP-BUDGET-PLAN phase 4) -----------------------
        #
        # The discriminator is count_ge_25ms_NONFLASH, not the raw count. This
        # soak issues hundreds of synchronous keymap and rgb_save writes by
        # design, so it TRIGGERS wear-levelling consolidations itself -- three
        # or four per run. Gating on the raw >=25 ms count would fail on the
        # harness's own stimulus and teach everyone to ignore it.
        #
        # 25 ms is the threshold that matters: contact lasts 25-80 ms, so a
        # shorter stall ends with the key still down and can only delay a
        # press, never drop it.
        try:
            st = s.stalls()
        except SystemExit as e:
            fails.append(f"could not read stall counters: {e}")
            st = None
        if st:
            print(f"stalls: {st}")
            if st["count_ge_25ms_nonflash"]:
                fails.append(
                    f"{st['count_ge_25ms_nonflash']} UNEXPLAINED stall(s) >= 25 ms "
                    f"(worst blit {st['blit_gap_max_ms']} ms, i2c "
                    f"{st['i2c_gap_max_ms']} ms) -- long enough to lose a keystroke")
            # Consolidation is expected here; a REGRESSION in its length is not.
            # Measured 2026-09-02 on 0091d438fa: 33 ms. 60 leaves headroom for a
            # slower erase without tolerating the 50-300 ms originally feared.
            if st["flash_gap_max_ms"] > 60:
                fails.append(f"flash stall {st['flash_gap_max_ms']} ms > 60 ms budget "
                             "-- wear-levelling consolidation has regressed")
            print(f"  ({st['flash_writes']} flash writes -> "
                  f"~{st['flash_writes'] // 127} consolidation(s) expected)")
        if fails:
            print("\nSOAK FAIL:\n  " + "\n  ".join(fails))
            console_tail()
        else:
            print("\nSOAK PASS")
            rc = 0
    finally:
        s.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
