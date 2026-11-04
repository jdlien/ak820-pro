#!/usr/bin/env python3
"""The awake soak's reads summarized: soak_summary.py soak-LABEL.jsonl.
Each read's key fields on one line, then the first-to-last growth."""
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
def g(d, *ks, default=None):
    for k in ks:
        if isinstance(d, dict) and k in d: d = d[k]
        else: return default
    return d
print(f"{'read':>4} {'time':8} {'keys':>5} {'gap':>4} {'loss':>4} {'spur':>4} {'judged':>10} {'rej':>3} {'ev':>3} {'omit':>4} {'inv':>3} {'i2c':>4} {'fail':>4} {'runs':>4} {'rst':>3} {'blits':>6}")
for d in rows:
    c = d.get("clock", {})
    v = d.get("vitals") or {}
    print(f"{d.get('read',0):>4} {str(d.get('t',''))[-8:]:8} {d.get('key_presses',0):>5} {d.get('row_gap_max_ms', d.get('row_gap_max',0)):>4} {d.get('epoch_losses',0):>4} {d.get('spurious',0):>4} "
          f"{d.get('usb_checked',0):>10} {d.get('usb_rejects',0):>3} {d.get('usb_events',0):>3} {d.get('late_omit',0):>4} {d.get('invalid_services',0):>3} "
          f"{c.get('i2c_max_cycles','?'):>4} {c.get('i2c_fail','?'):>4} {c.get('runs_ok','?'):>4} {c.get('restarts','?'):>3} {v.get('blits_issued','?'):>6}")
if len(rows) >= 2:
    a, b = rows[0], rows[-1]
    print(f"\nfirst to last: reads {a.get('read')} to {b.get('read')}; losses {a.get('epoch_losses')} -> {b.get('epoch_losses')}; spurious {a.get('spurious')} -> {b.get('spurious')}; "
          f"frame intervals judged {b.get('usb_checked')} (rejects {b.get('usb_rejects')}, events {b.get('usb_events')}); "
          f"clock runs {g(a,'clock','runs_ok')} -> {g(b,'clock','runs_ok')}, restarts {g(b,'clock','restarts')}, i2c fails {g(b,'clock','i2c_fail')}")
    v = b.get("vitals") or {}
    print(f"vitals at the last read: uptime {v.get('uptime_ms',0)/3600000:.2f} h, token {v.get('build_token')}, msp_free {v.get('msp_free')}, psp_free {v.get('psp_free')}, blits {v.get('blits_issued')}, blit faults {sum(v.get(k,0) for k in ('blit_never_started','blit_stalled','blit_irq_lost','blit_unknown'))}")
