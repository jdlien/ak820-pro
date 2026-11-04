#!/usr/bin/env python3
"""After an M4-with press, white's side as one JSON line: the key counts
(health pages 2 and 3), the deep sleep's record (op 14 sub 4, read only: the
last wake's reason, flags, counted s, key_gain, timed-out steps), its last
eight wakes (op 24: the night's keep-alive wakes before the press) and the
sleep page (HC_POWER page 1). The house opens, no enumeration; the data line
on and the daemon paused."""
import json
import sys

sys.path.insert(0, "scripts")
sys.path.insert(0, "hostagent")
import deep_sleep as ds      # noqa: E402
import overrun_diag as od    # noqa: E402
import ak820health as hp     # noqa: E402
import ak820battery as ab    # noqa: E402


def read(h):
    c = hp.read_stalls(h)
    c.update(hp.read_rows(h))
    c.pop("row_samples", None)
    return {"counts": c, "record": ds.deep(h, 0), "wakes": od.wakes(h), "page": ab.sleep_page(h)}


print(json.dumps(ds.with_dev(read)))
