"""P1b's exit gates on the board (plans/CONFIG-MENU-P1-DESIGN.md, "P1b", its
tests; codex's code review, item 4): each outside writer through its real path
mid-edit, observed in order, not only counted; a Save with the lights off and
Lights saved; the panel shown from Screen Off and from level 0.

    venv-win/Scripts/python.exe scripts/menu_p1b_gates.py [--out FILE] < /dev/null

Drives the menu by op 27 (a dev build), VIA by its own packets, the LCD by
HC_DEVHOOK ops 4-6; reads the edit by op 27 sub 14. Puts back every setting it
touches. Persistence across a reboot needs the board power-cycled, so it's
JD's step, not this script's. Never enumerates HID on Windows."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from menu_s0_session import mutate, open_device, read_state, wait, xfer  # noqa: E402

GET, SET, SAVE, RGB_CH = 0x08, 0x07, 0x09, 3
BRIGHTNESS, EFFECT = 1, 2
SET_KB_VALUE, DEVICE_INDICATION = 0x03, 0x05
TOP, LIGHT, SCREEN_ED, BRIGHT, LIGHTS = 17, 40, 41, 43, 47
ROW_SCREEN, L_BRIGHT, L_LIGHTS = 1, 2, 6
fails, log = [], []


def check(ok, what):
    log.append({"check": what, "ok": bool(ok)})
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        fails.append(what)


def via(h, payload):
    """One VIA round trip, its reply matched on the command, channel and value
    id sent (every open handle sees every report on Windows)."""
    n = min(3, len(payload))
    h.write(bytes([0] + payload + [0] * (32 - len(payload))))
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and tuple(r[:n]) == tuple(payload[:n]):
            return bytes(r)
    raise RuntimeError(f"VIA {payload[:n]}: no reply")


def via_brightness(h):
    return via(h, [GET, RGB_CH, BRIGHTNESS])[3]


def via_effect(h):   # 0 while the lights are off
    return via(h, [GET, RGB_CH, EFFECT])[3]


def devop(h, op, arg=0):
    """HC_DEVHOOK op 4 (the LCD level, RAM), 5 (its power), 6 (read): the
    reply's [level, max, on, effective, saved+1]."""
    h.write(bytes([0, 0x07, 0x13, 0x76, op, arg]) + bytes(26))
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        r = h.read(32, 250)
        if r and r[1] == 0x13 and r[2] == 0x76 and r[3] == op:
            return {"level": r[4], "max": r[5], "on": r[6], "effective": r[7], "saved1": r[8]}
    raise RuntimeError(f"devhook op {op}: no reply")


def edit(h):
    r = xfer(h, 14)
    return {"open": r[6], "field": r[7], "value": r[8], "saved": r[9], "ext": r[10] | (r[11] << 8)}


def settle(h, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = read_state(h)
        if s["owner"] == "menu" and s["pixels_done"]:
            return s
        if s["owner"] == "dash" and s["session"] == "none" and s["phase"] == "done":
            return s
        time.sleep(0.1)
    return read_state(h)


def act(h, sub, args=b""):
    st, seq = mutate(h, sub, args)
    if st != 0:
        raise RuntimeError(f"op 27 sub {sub}: refused ({st})")
    state, _ = wait(h, seq)
    if state != "done":
        raise RuntimeError(f"op 27 sub {sub}: {state}")
    time.sleep(0.15)   # past the 90 ms fast window: each turn a single step
    return settle(h)


def turn(h, n):
    return act(h, 1, bytes([n & 0xFF]))


def click(h):
    return act(h, 2)


def hold(h):
    return act(h, 3)


def open_menu(h):
    if read_state(h)["session"] != "none":
        close_menu(h)
    s = act(h, 11)
    if s["screen"] != TOP:
        raise RuntimeError(f"the menu opened on screen {s['screen']}")
    return s


def close_menu(h):
    if read_state(h)["session"] != "none":
        act(h, 11)
    time.sleep(1.5)   # the restore


def to_brightness(h):
    open_menu(h)
    click(h)            # Lighting, on Effect
    turn(h, 1)          # Brightness
    s = click(h)
    if s["screen"] != BRIGHT:
        raise RuntimeError(f"not Brightness: screen {s['screen']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="menu_p1b_gates.json")
    a = ap.parse_args()
    h = open_device()
    v0 = e0 = None
    try:
        close_menu(h)
        v0, e0 = via_brightness(h), via_effect(h)
        lcd0 = devop(h, 6)
        print(f"start: brightness {v0}, effect {e0}, LCD {lcd0}")
        check(e0 != 0, "the lights are on to start")
        # A slow detent is the next shown percentage (JD, 10-25: "micro-adjustments
        # by one value/percent"; menu.c's pct_of/val_of_pct), up unless at the top.
        step = 1 if (v0 * 100 + 127) // 255 < 100 else -1
        moved = ((((v0 * 100 + 127) // 255) + step) * 255 + 50) // 100

        # 1. A VIA read mid-preview answers the restored value.
        to_brightness(h)
        ed = edit(h)
        check(ed["open"] == 1 and ed["value"] == v0 and ed["saved"] == v0, f"Brightness opens on {v0}: {ed}")
        turn(h, 1 if step > 0 else -1)
        check(edit(h)["value"] == moved, "the preview moved")
        x0 = edit(h)["ext"]
        got = via_brightness(h)
        check(got == v0, f"a VIA get mid-preview answers the restored {v0}: {got}")
        ed = edit(h)
        check(ed["open"] == 0 and ed["ext"] == x0 + 1, f"the get cancelled the edit: {ed}")
        s = settle(h)
        check(s["screen"] == LIGHT, f"back on Lighting: screen {s['screen']}")

        # 2. A VIA set mid-preview still applies, after the cancel.
        s = click(h)   # Brightness again (the cursor stayed on it)
        turn(h, 1 if step > 0 else -1)
        target = v0 - 10 if v0 >= 10 else v0 + 10
        via(h, [SET, RGB_CH, BRIGHTNESS, target])
        ed = edit(h)
        check(ed["open"] == 0 and ed["ext"] == x0 + 2, f"the set cancelled the edit: {ed}")
        check(via_brightness(h) == target, f"the set applied: {target}")
        via(h, [SET, RGB_CH, BRIGHTNESS, v0])   # RAM only, as it was
        settle(h)

        # 3. The device indication mid-edit: cancels, and still toggles.
        click(h)
        turn(h, 1 if step > 0 else -1)
        via(h, [SET_KB_VALUE, DEVICE_INDICATION, 0])
        ed = edit(h)
        check(ed["open"] == 0 and ed["ext"] == x0 + 3, f"the indication cancelled the edit: {ed}")
        check(via_effect(h) == 0, "the indication toggled the lights off")
        via(h, [SET_KB_VALUE, DEVICE_INDICATION, 0])
        check(via_effect(h) == e0 and via_brightness(h) == v0, "a second toggles them back, the brightness restored")
        settle(h)

        # 4. A forced VIA save mid-preview stores the restored config.
        click(h)
        turn(h, 1 if step > 0 else -1)
        via(h, [SAVE, RGB_CH])
        ed = edit(h)
        check(ed["open"] == 0 and ed["ext"] == x0 + 4, f"the save cancelled the edit: {ed}")
        check(via_brightness(h) == v0, f"what it saved is the restored {v0}")
        settle(h)
        close_menu(h)

        # 5. Dev ops 4 and 5 cancel a Screen edit, then apply.
        open_menu(h)
        turn(h, ROW_SCREEN)
        s = click(h)
        check(s["screen"] == SCREEN_ED, f"the Screen editor: screen {s['screen']}")
        ed = edit(h)
        lv = ed["value"]
        turn(h, 1 if lv < lcd0["max"] else -1)   # the max from op 6 (100 since P2b)
        x1 = edit(h)["ext"]
        st = devop(h, 4, lv)
        ed = edit(h)
        check(ed["open"] == 0 and ed["ext"] == x1 + 1 and st["level"] == lv, f"op 4 cancelled, then set {lv}: {ed}, {st}")
        settle(h)
        click(h)   # the Screen again
        turn(h, 1 if lv < lcd0["max"] else -1)   # the max from op 6 (100 since P2b)
        st = devop(h, 5, 1)
        ed = edit(h)
        check(ed["open"] == 0 and ed["ext"] == x1 + 2 and st["level"] == lv, f"op 5 cancelled: {ed}, {st}")
        settle(h)
        close_menu(h)

        # 6. Lights saved Off; a Save with the lights off; Lights saved On. Mid-edit
        # the edit is read by sub 14 only: a VIA read is a writer here, and
        # would cancel it (gate 1). VIA reads come after each save.
        open_menu(h)
        click(h)
        turn(h, L_LIGHTS - 1)
        s = click(h)
        ed = edit(h)
        check(s["screen"] == LIGHTS and s["cursor"] == 2 and ed["open"] == 1 and ed["value"] == 1,
              f"Lights opens on On: {s['screen']}, {s['cursor']}, {ed}")
        turn(h, -1)   # Off, previewed
        check(edit(h)["value"] == 0, "Off previewed")
        s = click(h)  # saved
        check(edit(h)["open"] == 0 and s["screen"] == LIGHT and via_effect(h) == 0, "Off saved: the lights off")
        turn(h, -(L_LIGHTS - L_BRIGHT))   # Brightness
        click(h)
        turn(h, 1 if step > 0 else -1)
        check(edit(h)["value"] == moved, "a preview with the lights off")
        click(h)      # saved with the lights off
        check(via_brightness(h) == moved and via_effect(h) == 0, "a Save with the lights off: saved, and still off")
        click(h)      # Brightness back
        turn(h, -1 if step > 0 else 1)
        click(h)
        # Back one detent: the start's percentage, at its own value (86 is 34%,
        # whose value is 87); the restore at the end puts v0 back exactly.
        back = (((v0 * 100 + 127) // 255) * 255 + 50) // 100
        check(via_brightness(h) == back, f"Brightness saved back to {back} (the start {v0}'s percentage)")
        turn(h, L_LIGHTS - L_BRIGHT)
        s = click(h)
        check(s["screen"] == LIGHTS and s["cursor"] == 1, f"Lights opens on Off: {s['cursor']}")
        turn(h, 1)    # On
        click(h)
        check(via_effect(h) == e0, "Lights saved On, the effect as before")
        close_menu(h)

        # 7. The panel shows from level 0 and from Screen Off.
        devop(h, 4, 0)
        check(devop(h, 6)["effective"] == 0, "level 0: the panel dark")
        open_menu(h)
        check(devop(h, 6)["effective"] >= 1, "the menu shows it from level 0")
        close_menu(h)
        devop(h, 4, lcd0["level"])
        devop(h, 5, 0)
        check(devop(h, 6)["effective"] == 0, "Screen Off: the panel dark")
        open_menu(h)
        check(devop(h, 6)["effective"] >= 1, "the menu shows it from Screen Off")
        close_menu(h)
        devop(h, 5, 1)
        end = devop(h, 6)
        check(end["level"] == lcd0["level"] and end["on"] == lcd0["on"], f"the LCD as it was: {end}")
        # The brightness as the menu last saved it: the start's percentage's own
        # value (`back`); the finally below puts v0 itself back, with the lights on
        # (QMK ignores a brightness set while they are off).
        check(via_brightness(h) == back and via_effect(h) == e0, f"the lights as they were (brightness {back})")
    finally:
        try:
            close_menu(h)
            # Whatever happened above, the lights as they were (a gate that
            # failed partway could leave a saved Off or a brightness behind).
            if v0 is not None and (via_brightness(h) != v0 or via_effect(h) != e0):
                via(h, [SET, RGB_CH, EFFECT, e0])
                via(h, [SET, RGB_CH, BRIGHTNESS, v0])
                via(h, [SAVE, RGB_CH])
                print(f"put back: effect {e0}, brightness {v0}")
        finally:
            h.close()
    json.dump({"fails": fails, "log": log}, open(a.out, "w"), indent=1)
    print("PASS" if not fails else f"FAILED: {len(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
