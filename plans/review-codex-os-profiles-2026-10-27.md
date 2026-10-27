# Codex: the Win/Mac switch loads each side's last profile (2026-10-27)

JD (10-27): "can we make it so that the current profile is remembered for
windows and Mac layers so when a user flicks the switch, it changes to the
last profile used with that layer?"; "I think always on makes sense here";
"implement the profile association with win/Mac switch."
qmk_firmware-ak820pro `0ada282c..bf29a081` (branch `gremlin/os-profiles`):
the profile block's active byte a slot a side (bits 0-3 Windows', 4-7 the
Mac's, 0xF none; magic 0xA3), `prof_switch()` from `dip_switch_update_kb()`
index 0 with a three-tick rest, HC_PROFILES 7's [9] the side, dev sub 0x42.
Outer repo: `hostagent/ak820profiles.py`'s conversion, the host tests.
The prompt: `plans/review-prompt-os-profiles.txt`; the raw reply:
`plans/review-codex-os-profiles-raw.md`.

## The reply, verbatim

No flash-safety blocker found in `0ada282c..bf29a081` or the listed host changes.

- [profiles.c:179](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:179): pair/pending handling is consistent across set, delete, format, restore commit, HC 0/6 and tick.
- [profiles.c:475](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:475): boot only initializes the side; countdown handles bounce and waits for recovery/restores. Loads cancel edits/previews. Rename retains its explicit slot.
- [ak820profiles.py:123](/C:/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:123): both conversion directions and normalization agree with the board’s commit semantics.
- [sleep.c:178](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:178): the switch isn’t a wake source; sleeping flips take effect after wake and recovery.

Tests/build weren’t rerun: process execution was denied. The reported 136 B heap gap clears the floor by 8 B.

## Dispositions

- **No blocker; nothing to fix.** Flashed on the keyboard on gremlin
  (`via-dev-bf29a081-20261027-084924`, token `0xef38bc14`, heap gap 136 B;
  the daily `via-daily-bf29a081-20261027-085112` builds clean, heap gap
  2248 B).
- **The sleep note:** as designed. A flip while the board sleeps is seen
  at the wake, and its load waits out the recovery (`profiles_test.c`'s
  `test_switch`, the recovery case).
