#!/usr/bin/env python3
"""Fail the build when the ak820pro_keycodes enum and via.json's
customKeycodes[] disagree.

The two are INDEX-MATCHED (both map onto QK_KB_0): inserting or removing an
entry in one shifts every later keycode in the other and silently corrupts
existing VIA keymaps -- the failure mode CLAUDE.md warns about twice. A
build-time count comparison converts that into a loud error. Called from
scripts/build.sh; runnable standalone.
"""
import json, re, sys, os

KB = os.path.join(os.path.dirname(__file__), "..",
                  "qmk_firmware-ak820pro", "keyboards", "a_jazz", "ak820pro")


def enum_count(header):
    src = open(header).read()
    m = re.search(r"enum ak820pro_keycodes \{(.*?)AK820PRO_SAFE_RANGE", src, re.S)
    if not m:
        sys.exit("check_via_sync: could not find ak820pro_keycodes enum")
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    names = re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*(?:=\s*\w+)?\s*,", body, re.M)
    return len(names), names


def main():
    n_enum, names = enum_count(os.path.join(KB, "ak820pro.h"))
    via = json.load(open(os.path.join(KB, "via.json")))
    n_via = len(via["customKeycodes"])
    if n_enum != n_via:
        sys.exit(f"check_via_sync: FAIL -- ak820pro_keycodes has {n_enum} entries "
                 f"({', '.join(names)}) but via.json customKeycodes has {n_via}. "
                 "These are index-matched; append-only, and always to both.")
    print(f"check_via_sync: OK ({n_enum} custom keycodes)")


if __name__ == "__main__":
    main()
