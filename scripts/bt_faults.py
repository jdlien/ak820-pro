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
        # 33 bytes on the wire: report id + the full 32-byte report. One byte
        # short and macOS quietly drops the write (learned the hard way).
        self.h.write(bytes([0x00] + payload + [0x00] * (32 - len(payload))))
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

    # ---- pending-action machinery, via the A6 TX trace ----------------------
    # (Codex phase-3 review #2: rx-only tests could not see supersession,
    # retry cadence, or the bounce's ordered selects. HC_TXTRACE + HC_DRIVE
    # make those observable. The periodic A6 53 battery poll shares the
    # trace, so assertions filter it out.)
    BT1, BT2, BT3, PAIR = 0x31, 0x32, 0x33, 0x51

    def a6(self=t):
        """(count, params) -- battery polls are excluded firmware-side, so the
        count is an EXACT observable and immune to trace-ring saturation."""
        r = self.xfer([SET_VALUE, HEALTH, 0x7C])
        cnt = r[3] | (r[4] << 8)
        n = r[5]
        return cnt, list(r[6:6 + n])

    def drive(op, arg=0):
        t.xfer([SET_VALUE, HEALTH, 0x7B, op, arg])
        time.sleep(0.05)

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}: {name}")
        if not cond:
            t.failures.append(name)

    # Determinism: the LIVE module answers A6 commands even in wired mode and
    # its interleaved 5B frames would race these assertions -- mute real RX so
    # the parser sees only injected bytes. The injected ACK sets module_alive,
    # or the cold-boot select retry (500 ms, uncapped) would pollute counts.
    drive(4, 1)
    t.inject([0x61, 0x0D, 0x0A])

    print("8. select goes out; 5B 33 stops the retry (never re-select an attempting module)")
    drive(1, BT2)
    c0, tr = a6()
    check("A6 32 sent on select", tr[-1:] == [BT2])
    t.inject(frame(0x5B, 0x33))
    c1, _ = a6()
    time.sleep(2.0)   # past the 1.5 s retry cadence
    c2, _ = a6()
    check("no retry after 5B 33", c2 == c1)

    print("9. select retry: 5B 23 refires immediately, clock refires at 1.5 s")
    drive(1, BT3)
    c0, _ = a6()
    t.inject(frame(0x5B, 0x23))
    c1, tr = a6()
    check("5B 23 event refire", c1 == c0 + 1 and tr[-1] == BT3)
    time.sleep(1.7)
    c2, tr = a6()
    check("timed retry fired", c2 == c1 + 1 and tr[-1] == BT3)

    print("10. pair retries until 5B 31 confirms")
    drive(2)
    c0, tr = a6()
    check("A6 51 sent", tr[-1] == PAIR)
    time.sleep(1.0)   # ~2 retries at 400 ms
    c1, tr = a6()
    check("pair retrying", c1 >= c0 + 2 and tr[-2:] == [PAIR, PAIR])
    t.inject(frame(0x5B, 0x31))   # confirmed -> PAIRING state, retry stops
    c2, _ = a6()
    time.sleep(1.0)
    c3, _ = a6()
    check("retry stops on 5B 31", c3 == c2)

    print("11. cancel-pairing bounce: a DIFFERENT slot first, then the target")
    # state is PAIRING from test 10; selecting BT2 must bounce via BT1
    drive(1, BT2)
    time.sleep(1.0)   # bounce fires the real select after 700 ms
    _, tr = a6()
    check("bounce order [other, target]", tr[-2:] == [BT1, BT2])

    drive(3)     # cancel: leave the driver idle
    drive(4, 0)  # un-mute real module traffic

    t.h.close()
    if t.failures:
        print(f"\nFAULT TESTS FAILED: {t.failures}")
        sys.exit(1)
    print("\nALL FAULT TESTS PASS (toggle the mode slider to restore real link state)")


if __name__ == "__main__":
    main()
