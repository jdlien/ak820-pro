#!/usr/bin/env python3
"""CH582F fault-injection tests (hardening phase 3.2).

Replays the wire captures from hardening-plan/findings-ch582-states.md
against the REAL parser via the HC_INJECT hook, and asserts the resulting
state via HC_CONN. Needs the INSTRUMENTED build (WDT_TEST_HOOKS), wired
mode, and a quiet interface (no VIA, poller unloaded).

⚠️ These tests MUTATE the driver's live connection state (that's the point).
Run with the mode slider in USB/cable position where the CH582F link is
unused; the BT icon/digit may flicker during the run. Finish with a slider
toggle or reboot if you want the state pristine afterwards.

States (ch582f_ajazz.h): 0 IDLE, 1 LINKING, 2 PAIRING, 3 CONNECTED,
4 REJECTED.
"""
import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hostagent"))
from ak820health import open_device, read_health  # noqa: E402

SET_VALUE, HEALTH = 0x07, 0x13
HC_CONN, HC_INJECT = 0x02, 0x7D
IDLE, LINKING, PAIRING, CONNECTED, REJECTED = range(5)
NAMES = ["IDLE", "LINKING", "PAIRING", "CONNECTED", "REJECTED"]


def frame(t, d):
    return [t, d, (t + d) & 0xFF]


class T:
    def __init__(self):
        self.h = open_device()
        self.failures = []

    def xfer(self, payload):
        self.h.write(bytes([0x00] + payload + [0x00] * (31 - len(payload))))
        rep = self.h.read(32, 1000)
        if not rep or rep[0] != SET_VALUE:
            raise SystemExit("no reply (instrumented build? wired mode?)")
        return bytes(rep)

    def inject(self, byts):
        assert len(byts) <= 27
        self.xfer([SET_VALUE, HEALTH, HC_INJECT, len(byts)] + list(byts))
        time.sleep(0.05)  # let a couple of ch582_task passes consume them

    def conn(self):
        r = self.xfer([SET_VALUE, HEALTH, HC_CONN])
        return {"state": r[3], "slot": r[4], "battery": r[5], "flags": r[6]}

    def expect(self, name, want_state):
        got = self.conn()["state"]
        ok = got == want_state
        print(f"  {'PASS' if ok else 'FAIL'}: {name} -> {NAMES[got]}"
              + ("" if ok else f" (wanted {NAMES[want_state]})"))
        if not ok:
            self.failures.append(name)


def main():
    t = T()
    base = read_health(t.h)

    print("1. connect attempt then link-up (the normal path)")
    t.inject(frame(0x5B, 0x33))
    t.expect("5B 33 -> LINKING", LINKING)
    t.inject(frame(0x5B, 0x32))
    t.expect("5B 32 -> CONNECTED", CONNECTED)

    print("2. advertising (pair confirmation)")
    t.inject(frame(0x5B, 0x31))
    t.expect("5B 31 -> PAIRING", PAIRING)

    print("3. attempt abandoned persists (the unreachable-slot capture)")
    t.inject(frame(0x5B, 0x33) + frame(0x5B, 0x33) + frame(0x5B, 0x36) +
             frame(0x5B, 0x23))
    t.expect("33,33,36,23 -> REJECTED (23 ignored)", REJECTED)

    print("4. missed 5B 32: the 5A promotion (3 s dwell)")
    t.inject(frame(0x5B, 0x34))
    t.expect("5B 34 -> LINKING", LINKING)
    t.inject(frame(0x5A, 0x02))   # plausible LED frame, but inside the dwell
    t.expect("early 5A does NOT promote", LINKING)
    time.sleep(3.2)
    t.inject(frame(0x5A, 0x02))
    t.expect("5A after 3 s dwell promotes", CONNECTED)

    print("5. implausible 5A never promotes")
    t.inject(frame(0x5B, 0x34))
    time.sleep(3.2)
    t.inject(frame(0x5A, 0xF2))   # high bits set: forged-frame signature
    t.expect("implausible 5A ignored", LINKING)

    print("6. byte soup: parser survives, malformed counter moves, state sane")
    t.inject(frame(0x5B, 0x32))   # ground state CONNECTED
    soup = [0x5B, 0x99, 0x00, 0x12, 0x5A, 0x5C, 0xFF, 0x00, 0x61, 0x0D,
            0x5B, 0x5B, 0x33, 0x8E + 0x5B & 0xFF]
    t.inject(soup)
    st = t.conn()["state"]
    print(f"  state after soup: {NAMES[st]} (must be a valid state, no wedge)")
    end = read_health(t.h)
    dm = end["rx_malformed"] - base["rx_malformed"]
    print(f"  rx_malformed moved by {dm} ({'PASS' if dm > 0 else 'FAIL: expected >0'})")
    if dm <= 0:
        t.failures.append("malformed counter")

    print("7. battery frame never touches connection state")
    t.inject(frame(0x5B, 0x32))
    t.inject(frame(0x5C, 55))
    c = t.conn()
    ok = c["state"] == CONNECTED and c["battery"] == 55
    print(f"  {'PASS' if ok else 'FAIL'}: battery=55, state CONNECTED")
    if not ok:
        t.failures.append("battery isolation")

    t.h.close()
    if t.failures:
        print(f"\nFAULT TESTS FAILED: {t.failures}")
        sys.exit(1)
    print("\nALL FAULT TESTS PASS (toggle the mode slider to restore real link state)")


if __name__ == "__main__":
    main()
