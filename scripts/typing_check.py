#!/usr/bin/env python3
"""The verification protocol's delivered-input check (plans/BATTERY-GAUGE-REFINE-PLAN.md).

JD types a fixed reference text into a plain-text file on the Mac during a
per-event check (a plug-in, an unplug, a warning firing, a page change, a
forced flash write). This compares what arrived with what was meant, and
reports what the stall counters cannot see on their own: missing keys,
duplicated keys (one extra) and stuck keys (auto-repeat: two or more).

    The reference: "the quick brown fox jumps over the lazy dog" five times,
    one per line (~220 characters).

Usage:
    typing_check.py --reference            print the reference to type
    typing_check.py typed.txt [--json]     compare a typed file against it

Exit 0 when the text matches exactly, 1 when anything differs. Case and line
endings are not normalized: a dropped Shift is a real difference.
"""
import difflib, json, sys

LINE = "the quick brown fox jumps over the lazy dog"
REFERENCE = "\n".join([LINE] * 5) + "\n"


def compare(typed, ref=REFERENCE):
    """Character-level alignment. An insertion that is one character repeated,
    next to that same character, is a DUPLICATED key (one extra) or a STUCK
    key (auto-repeat: two or more extra), not scattered insertions. difflib
    may place the run on either side of the character it repeats."""
    sm = difflib.SequenceMatcher(a=ref, b=typed, autojunk=False)
    missing, extra, dup, stuck, replaced = [], [], [], [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "delete":
            missing.append((i1, ref[i1:i2]))
        elif op == "insert":
            ins = typed[j1:j2]
            prev = typed[j1 - 1] if j1 > 0 else ""
            nxt = typed[j2] if j2 < len(typed) else ""
            if ins and len(set(ins)) == 1 and ins[0] in (prev, nxt):
                (dup if len(ins) == 1 else stuck).append((i1, ins[0], len(ins)))
            else:
                extra.append((i1, ins))
        elif op == "replace":
            replaced.append((i1, ref[i1:i2], typed[j1:j2]))
    return {
        "ref_chars": len(ref), "typed_chars": len(typed),
        "exact": typed == ref,
        "missing": [{"at": a, "chars": c} for a, c in missing],
        "extra": [{"at": a, "chars": c} for a, c in extra],
        "duplicated": [{"at": a, "char": c} for a, c, n in dup],
        "stuck": [{"at": a, "char": c, "repeats": n} for a, c, n in stuck],
        "replaced": [{"at": a, "want": w, "got": g} for a, w, g in replaced],
    }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--reference":
        sys.stdout.write(REFERENCE)
        return 0
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    typed = open(sys.argv[1], encoding="utf-8", newline="").read()
    if not typed.endswith("\n"):
        typed += "\n"   # an editor that drops the final newline is not a lost key
    r = compare(typed)
    if "--json" in sys.argv:
        print(json.dumps(r))
    else:
        print(f"reference {r['ref_chars']} chars, typed {r['typed_chars']}: "
              f"{'EXACT' if r['exact'] else 'DIFFERS'}")
        for k in ("missing", "duplicated", "stuck", "extra", "replaced"):
            for x in r[k]:
                print(f"  {k:8} {x}")
    return 0 if r["exact"] else 1


if __name__ == "__main__":
    sys.exit(main())
