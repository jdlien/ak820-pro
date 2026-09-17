"""Grade the interleaved burst A/B (rule from ak820-pro-c6, 2026-09-17).

usage: python burst_grade.py RAWFILE

Per binary: reads, failed (non-zero exit, 'no reply', or no offset line), rtt
median / p95 / max (from --raw's full-precision rtt_ms), offset jitter = median
|offset[i] - offset[i-1]| over that binary's OWN consecutive successful reads, offset
mean. p95 is sorted[int(0.95 n)], as the clock comparator computes it.
e07fdfa (NEW) passes only if: failed new <= old; |median rtt new - old| <= 0.3 ms;
rtt p95 new <= old + 0.5 ms; jitter new <= 1.2 x old + 0.1 ms.
"""
import re
import statistics
import sys

HEAD = re.compile(r"^=== round (\d+) (NEW|OLD) at (\S+ \S+) exit (-?\d+)")
OFFSET = re.compile(r"offset board-host ([+-]?\d+(?:\.\d+)?) ms\s+rtt ([\d.]+) ms")
RTT = re.compile(r"^rtt_ms ([\d.]+)")
DISCARD = re.compile(r"discarded (\d+) report")


def rank(xs, q):
    xs = sorted(xs)
    return xs[min(int(q * len(xs)), len(xs) - 1)]


def parse(path):
    reads, cur = [], None
    for line in open(path, encoding="utf-8-sig", errors="replace"):
        line = line.rstrip("\r\n")
        m = HEAD.match(line)
        if m:
            cur = dict(round=int(m.group(1)), bin=m.group(2), at=m.group(3), exit=int(m.group(4)),
                       offset=None, rtt=None, rtt_line=None, discarded=0, noreply=False, lines=[])
            reads.append(cur)
            continue
        if cur is None or line[:4].isdigit():   # Note() lines carry a timestamp
            continue
        cur["lines"].append(line)
        if (o := OFFSET.search(line)):
            cur["offset"], cur["rtt_line"] = float(o.group(1)), float(o.group(2))
        if (r := RTT.match(line)):
            cur["rtt"] = float(r.group(1))
        if (d := DISCARD.search(line)):
            cur["discarded"] += int(d.group(1))
        if "no reply" in line:
            cur["noreply"] = True
    return reads


def stats(reads, name):
    mine = [r for r in reads if r["bin"] == name]
    ok = [r for r in mine if r["exit"] == 0 and not r["noreply"] and r["offset"] is not None]
    rtt = [r["rtt"] if r["rtt"] is not None else r["rtt_line"] for r in ok]
    offs = [r["offset"] for r in ok]
    jit = [abs(b - a) for a, b in zip(offs, offs[1:])]
    return dict(n=len(mine), failed=len(mine) - len(ok), discarded=sum(r["discarded"] for r in mine),
                rtt_med=statistics.median(rtt), rtt_p95=rank(rtt, 0.95), rtt_max=max(rtt),
                jitter=statistics.median(jit), off_mean=statistics.fmean(offs),
                off_first=offs[0], off_last=offs[-1],
                failures=[(r["round"], r["exit"], r["lines"][-1] if r["lines"] else "") for r in mine if r not in ok])


def main():
    reads = parse(sys.argv[1])
    new, old = stats(reads, "NEW"), stats(reads, "OLD")
    for name, s in (("e07fdfa (NEW)", new), ("d8ead97 (OLD)", old)):
        print(f"{name}: n {s['n']}, failed {s['failed']}, discarded reports {s['discarded']}, "
              f"rtt median {s['rtt_med']:.3f} / p95 {s['rtt_p95']:.3f} / max {s['rtt_max']:.3f} ms, "
              f"jitter {s['jitter']:.2f} ms, offset mean {s['off_mean']:+.2f} ms "
              f"(first {s['off_first']:+.1f}, last {s['off_last']:+.1f})")
        for f in s["failures"]:
            print(f"   failed read: round {f[0]} exit {f[1]}: {f[2]}")
    c1 = new["failed"] <= old["failed"]
    c2 = abs(new["rtt_med"] - old["rtt_med"]) <= 0.3
    c3 = new["rtt_p95"] <= old["rtt_p95"] + 0.5
    c4 = new["jitter"] <= 1.2 * old["jitter"] + 0.1
    yn = lambda b: "yes" if b else "NO"
    print()
    print(f"1. failed reads: new {new['failed']} <= old {old['failed']}: {yn(c1)}")
    print(f"2. median rtt: |{new['rtt_med']:.3f} - {old['rtt_med']:.3f}| = {abs(new['rtt_med'] - old['rtt_med']):.3f} <= 0.3: {yn(c2)}")
    print(f"3. rtt p95: new {new['rtt_p95']:.3f} <= old {old['rtt_p95']:.3f} + 0.5 = {old['rtt_p95'] + 0.5:.3f}: {yn(c3)}")
    print(f"4. offset jitter: new {new['jitter']:.2f} <= 1.2 x old {old['jitter']:.2f} + 0.1 = {1.2 * old['jitter'] + 0.1:.2f}: {yn(c4)}")
    print(f"BURST A/B VERDICT: {'PASS' if c1 and c2 and c3 and c4 else 'FAIL'}")


if __name__ == "__main__":
    main()
