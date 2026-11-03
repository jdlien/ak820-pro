#!/usr/bin/env python3
"""White's key counts for the presser's gates, as one JSON line: health page 2
(key_presses: after debounce, what reached the host's report) and page 3
(raw_edges: the matrix's transitions seen at consume time, before debounce;
consumes, cooked_changes, the worst row gap). The house open_device, no
enumeration. The host agents must be paused (the daemon) and the data line on."""
import json
import sys

sys.path.insert(0, "hostagent")
import ak820health as hp  # noqa: E402

h = hp.open_device()
try:
    d = hp.read_stalls(h)
    d.update(hp.read_rows(h))
finally:
    h.close()
d.pop("row_samples", None)
print(json.dumps(d))
