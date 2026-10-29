"""S1: the slowest passes of each transition, one at a time (HC_ACCT). scripts/menu_s1_acct_transitions.py < /dev/null"""
import sys
import time

sys.path.insert(0, "scripts")
sys.path.insert(0, "hostagent")
from menu_s0_session import mutate, open_device, read_state, wait  # noqa: E402
from menu_s0_accept import dash_done, op1, to_dash, until  # noqa: E402
from ak820health import read_acct  # noqa: E402


def worst(h, label):
    a = read_acct(h)
    ring = sorted(a["ring"], key=lambda e: -e["pass_ms"])[:3]
    print(f"{label:12} slow {a['slow_passes']:4}  worst:",
          "; ".join(f"{e['pass_ms']} ms " + str({k: v for k, v in e['scopes_ms'].items() if v}) for e in ring))
    read_acct(h, "reset")


def menu_open(h):
    st, seq = mutate(h, 4)
    wait(h, seq)
    until(h, lambda s: s["pixels_done"], timeout=5)


h = open_device()
try:
    to_dash(h)
    time.sleep(1)
    read_acct(h, "on")
    read_acct(h, "reset")
    time.sleep(3); worst(h, "dashboard")
    for i in range(3):
        menu_open(h); time.sleep(1); worst(h, "menu open")
        st, seq = mutate(h, 4); wait(h, seq); until(h, dash_done); time.sleep(1); worst(h, "menu close")
        op1(h); time.sleep(2); worst(h, "fn+d in")
        op1(h); until(h, dash_done); time.sleep(1); worst(h, "fn+d out")
        menu_open(h)
        st, seq = mutate(h, 0, bytes([3, 0])); wait(h, seq); until(h, lambda s: s["pixels_done"], timeout=5)
        time.sleep(1); worst(h, "to F2")
        st, seq = mutate(h, 4); wait(h, seq); until(h, dash_done); time.sleep(1); worst(h, "close F2")
finally:
    h.close()
