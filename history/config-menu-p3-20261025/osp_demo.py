"""Ready the keyboard on gremlin for JD's flip: the Mac's side remembers
Cyan-Magenta (slot 1), Windows' keeps RGB Cycle (slot 2), JD's live
settings put back as they were. The Mac's side by HC_PROFILES' dev sub 0x42,
the Load through the menu (op 27), as a press would; then Windows' side
again. Never enumerates HID."""
import sys
import time

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
import ak820profiles as ap  # noqa: E402
import menu_p1a_board as g  # noqa: E402
from menu_s0_session import open_device  # noqa: E402
from menu_s0_accept import to_dash  # noqa: E402

SCR = g.SCR
TOP, PROFILES, PSLOT = 1, 50, 51


def flip(h, mac):
    r = ap.xfer(h, 0x42, [1 if mac else 0])
    assert r[5] == 0, r[5]
    time.sleep(0.8)


h = open_device()
try:
    gm = ap.geometry(h)
    assert gm.side == "windows", gm.side
    live0 = ap.read_live(h)
    b = ap.read_block(h, gm)
    s2 = b[2 + 27:2 + 54]
    same = live0[2:14] == s2[2:14]
    print("JD's live settings", "equal slot 2's" if same else "differ from slot 2's (a `*`)", flush=True)
    print(f"pair before {b[1]:#04x}", flush=True)
    flip(h, True)
    print("on the Mac's side: live effect", ap.read_live(h)[3], flush=True)
    to_dash(h)
    g.step(h, 11, b"", "open", SCR(TOP), 0)
    g.turn(h, g.R_PROF, "to Profiles", SCR(TOP), g.R_PROF)
    g.click(h, "Profiles", SCR(PROFILES), 2)
    g.turn(h, -1, "to Cyan-Magenta", SCR(PROFILES), 1)
    g.click(h, "its page", SCR(PSLOT), 0x01)
    g.click(h, "Load", SCR(PROFILES), 1)
    g.hold(h, "the top level", SCR(TOP), g.R_PROF)
    g.step(h, 11, b"", "close", owner="dash")
    time.sleep(1.5)
    to_dash(h)
    print("on the Mac's side after Load: live effect", ap.read_live(h)[3], flush=True)
    flip(h, False)
    print("back on Windows' side: live effect", ap.read_live(h)[3], flush=True)
    ap.apply_live(h, live0)   # JD's live settings exactly, the pair untouched
    time.sleep(6)
    b = ap.read_block(h, ap.geometry(h))
    print(f"pair after {b[1]:#04x} (want 0x01: Windows slot 2, the Mac slot 1)", flush=True)
    print("live back:", ap.read_live(h)[1:26] == live0[1:26], flush=True)
    print("fails:", g.fails, flush=True)
finally:
    h.close()
