#!/usr/bin/env python3
"""Run ak820health.py's own decoding over captured raw-HID replies.

The phase-5 gate for ak820-agent is "decoding fixtures match ak820health.py".
Sequential live reads cannot match field for field -- tx_sent moves between
them -- so the oracle is run over the SAME bytes the Rust decoder gets: the
32-byte replies that `ak820 health --raw` prints. This feeds them to
ak820health.py through a fake device object, so every line of output below
is the Python's, untouched, and can be pinned as a Rust test expectation.

    venv-win\\Scripts\\python.exe scripts\\health_oracle.py --page1 <32 hex> \\
        [--page2 <32 hex>] [--page3 <32 hex>] [--page4 <32 hex> --page4b <32 hex> --wall SECS]

Prints, in order: the text ak820health.py prints for the flags implied by the
pages given (--stalls for page2, --rows for page3, --isr for page4 + page4b),
a line "----", then json.dumps(d) for the same. --isr's wall-clock seconds
are supplied rather than measured, so the run is deterministic.

Needs no keyboard and enumerates nothing: open_device is replaced.
"""
import argparse
import io
import json
import os
import sys
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
import ak820health  # noqa: E402  (imports hid; run under venv-win)


class FakeDevice:
    """Answers each HC_* command with the captured reply for it; page 4 can
    have two answers, served in order, for --isr's two reads.

    The queues are SHARED with the caller's dict, not copied: read_isr()
    opens its own device per call, so a per-instance copy would hand the
    first page-4 capture to both reads and the rates would come out as a
    zero-length interval."""

    def __init__(self, pages):
        self.pages = pages
        self.last = None

    def write(self, data):
        self.last = data[3]          # [0x00, SET_VALUE, HEALTH_CHANNEL, cmd, ...]

    def read(self, n, timeout_ms=0):
        replies = self.pages.get(self.last)
        if not replies:
            return b""
        return replies.pop(0) if len(replies) > 1 else replies[0]

    def close(self):
        pass


def parse_hex(s):
    b = bytes(int(x, 16) for x in s.split())
    if len(b) != 32:
        raise SystemExit(f"expected 32 bytes, got {len(b)}")
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page1", required=True)
    ap.add_argument("--page2")
    ap.add_argument("--page3")
    ap.add_argument("--page4")
    ap.add_argument("--page4b")
    ap.add_argument("--wall", type=float, default=2.0)
    a = ap.parse_args()

    argv = ["ak820health.py"]
    if a.page2:
        argv.append("--stalls")
    if a.page3:
        argv.append("--rows")
    if a.page4:
        if not a.page4b:
            raise SystemExit("--isr needs two page-4 replies: --page4 and --page4b")
        argv.append("--isr")

    def make_pages():
        pages = {ak820health.HC_GET: [parse_hex(a.page1)]}
        if a.page2:
            pages[ak820health.HC_GET2] = [parse_hex(a.page2)]
        if a.page3:
            pages[ak820health.HC_GET3] = [parse_hex(a.page3)]
        if a.page4:
            pages[ak820health.HC_GET4] = [parse_hex(a.page4), parse_hex(a.page4b)]
        return pages

    pages = make_pages()
    ak820health.open_device = lambda *args, **kwargs: FakeDevice(pages)

    # --isr sleeps 2 s and measures the wall clock; make both deterministic.
    import time
    clock = [0.0]

    def monotonic():
        return clock[0]

    def sleep(s):
        clock[0] += a.wall

    time.monotonic = monotonic
    time.sleep = sleep

    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        sys.argv = argv
        ak820health.main()
    sys.stdout.write(text.getvalue())
    print("----")

    js = io.StringIO()
    with contextlib.redirect_stdout(js):
        sys.argv = argv + ["--json"]
        # the page-4 queue was consumed above; a fresh one for the second run
        pages2 = make_pages()
        ak820health.open_device = lambda *args, **kwargs: FakeDevice(pages2)
        clock[0] = 0.0
        ak820health.main()
    sys.stdout.write(js.getvalue())


if __name__ == "__main__":
    main()
