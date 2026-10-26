#!/usr/bin/env python3
"""Fail the build when an RGB effect's stable id changes.

A settings profile stores the effect's id from rgb_effects.c's table, not
QMK's mode number, because enabling or disabling an effect at build time
renumbers the modes after it (plans/SETTINGS-PROFILES-PLAN.md, "The effect's
stable id"). So the ids are APPEND-ONLY, like the ak820pro_keycodes enum
that check_via_sync.py guards: an existing effect keeps its id, no id is
reused, and 0 is RGB_MATRIX_NONE's. A new effect takes the next id, and a
line here. Called from build.sh; runnable standalone.
"""
import os
import re
import sys

KB = os.path.join(os.path.dirname(__file__), "..",
                  "qmk_firmware-ak820pro", "keyboards", "a_jazz", "ak820pro")

# The ids as first committed (10-25), append-only. Never edit or remove a line.
REFERENCE = {
    "SOLID_COLOR": 1,
    "ALPHAS_MODS": 2,
    "BREATHING": 3,
    "CYCLE_ALL": 4,
    "CYCLE_LEFT_RIGHT": 5,
    "CYCLE_UP_DOWN": 6,
    "RAINBOW_MOVING_CHEVRON": 7,
    "CYCLE_PINWHEEL": 8,
    "JELLYBEAN_RAINDROPS": 9,
    "TYPING_HEATMAP": 10,
    "CUSTOM_RAINFALL": 11,
    "CUSTOM_DRIFT": 12,
}


def table(path):
    src = open(path, encoding="utf-8").read()
    rows = re.findall(r"\{\s*RGB_MATRIX_([A-Z0-9_]+)\s*,\s*(\d+)\s*,\s*\"", src)
    if not rows:
        sys.exit("check_effect_ids: could not find rgb_effects[]'s {mode, id, name} entries")
    return [(name, int(i)) for name, i in rows]


def main():
    rows = table(os.path.join(KB, "rgb_effects.c"))
    errors, seen = [], {}
    for name, i in rows:
        if i == 0:
            errors.append(f"{name} has id 0, which is RGB_MATRIX_NONE's")
        if i in seen:
            errors.append(f"id {i} is both {seen[i]}'s and {name}'s")
        seen[i] = name
        if name in REFERENCE and REFERENCE[name] != i:
            errors.append(f"{name}'s id moved from {REFERENCE[name]} to {i}")
        if name not in REFERENCE:
            errors.append(f"{name} (id {i}) isn't in the reference: append it to REFERENCE here, "
                          f"with the next id, {max(REFERENCE.values()) + 1}")
    for name, i in REFERENCE.items():
        if name not in dict(rows) and i in seen:
            errors.append(f"{name}'s id {i} is reused by {seen[i]}")
    names = dict(rows)
    for name in REFERENCE:
        if name not in names:
            errors.append(f"{name} was removed from rgb_effects[]: keep its entry, #ifdef'd on its enable")
    if errors:
        sys.exit("check_effect_ids: FAIL -- " + "; ".join(errors) +
                 ". The ids are append-only: a saved profile stores them.")
    print(f"check_effect_ids: OK ({len(rows)} effects)")


if __name__ == "__main__":
    main()
