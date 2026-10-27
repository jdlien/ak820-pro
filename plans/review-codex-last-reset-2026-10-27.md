# Codex: each side kept as left, JD's defaults, and Reset settings (2026-10-27)

JD (10-27): "let's do this 'don't lose your settings when switching between
mac/windows' feature, the new sensible defaults, and the 'reset to defaults'
option". qmk_firmware-ak820pro `bf29a081..d83d47c4` (branch
`gremlin/os-profiles`), then the fixes `d83d47c4..33d6d4ae`. The prompts:
`plans/review-prompt-last-reset.txt`, `plans/review-prompt-last-reset-fix.txt`;
the raw replies: `plans/review-codex-last-reset-raw.md`,
`plans/review-codex-last-reset-fix-raw.md`.

## The reply, verbatim

I’d hold the flash for these:

- **P2 — previews become remembered settings:** [profiles.c:529](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:529) captures before cancelling previews. Preview another profile, flip away/back: the preview replaces the outgoing side’s actual settings. Cancel before capturing.
- **P2 — swap durability:** [profiles.c:542](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:542) persists the outgoing record before incoming live settings finish their deferred writes. Cut power then reboot on the incoming side: boot skips recovery, losing that side’s previous unsaved settings.
- **P2 — reset bypasses recovery BUSY under the latch:** [profiles.c:625](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:625): `writable()` returns WRITE_FAILED before checking recovery; reset rejects only BUSY. Check recovery independently.
- **P2 — migration refusal comes after erase:** [ak820profiles.py:169](/C:/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:169), [flash.sh:297](/C:/Users/jdlien/code/ak820-pro/flash.sh:297): eight populated 0xA3 slots pass backup, then conversion aborts restoration, including live settings. Preflight conversion before flashing.

No additional findings in defaults, menu/title IDs, or seven-slot bounds. Tests/build weren’t rerun: process execution was denied.

## Dispositions

- **P2, previews kept: FIXED** in `33d6d4ae`: settle_side() cancels the
  previews before it captures the side left. Reproduced first
  (`scripts/profiles_test.c`'s `test_switch_codex`: a preview at screen 99
  over the side's own 31 was kept as 99 on `d83d47c4`).
- **P2, the swap's durability: FIXED** in `33d6d4ae`: the arrived side's
  settings are flushed (env_settings_flush()) before the side left's record
  is written; a cut between the two loses the side left's changes only, and
  the side arrived at shows its own. Reproduced first (the flush's order,
  the record's state at the flush).
- **P2, Reset under the latch in a recovery: FIXED** in `33d6d4ae`:
  prof_reset() checks env_recovering() and an open restore itself.
  Reproduced first.
- **P2, eight profiles across the flash: FIXED** in the outer repo:
  `ak820profiles.py fits` (exit 3 above seven), which `flash.sh` runs before
  it flashes and refuses on (`--no-profiles` past it); a restore whose
  conversion refuses still restores the live settings and exits 4, which
  `flash.sh` takes as the live settings done. Checked on JD's backup (fits),
  eight on 0xA3 (3), seven and a last record on 0xA4 (fits).

## Codex's check of the fixes, verbatim

All four P2s close: [preview cancellation](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:539), [ordered persistence](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:547), [independent BUSY check](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:635), and [preflight](/C:/Users/jdlien/code/ak820-pro/flash.sh:210) with [exit-4 handling](/C:/Users/jdlien/code/ak820-pro/flash.sh:310).

Flush runs once per settled switch in [10 Hz housekeeping](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:651), adding synchronous kb/RGB writes and possible consolidation stalls; latency remains unmeasured. Bypassing the RGB guard is safe here: previews cancelled, recovery excluded, [DMA drained](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:716). [DSB_FLASH](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:253) covers pending kb writes; sleep follows completion.

**New P3:** [ak820profiles.py:451](/C:/Users/jdlien/code/ak820-pro/hostagent/ak820profiles.py:451) claims live settings restored/returns 4 after `--block-only` conversion refusal, although live application was skipped. Return 1 there.

No new flash blocker found. Tests/build weren’t rerun: process execution denied.

### Dispositions

- **All four closed; no blocker:** flashed
  (`via-dev-33d6d4ae-20261027-102752`, token `0xe27cbc8a`, heap gap 136 B).
- **The flush's latency: measured on the board** (GREMLIN-RESULTS §20x, the
  switch check's passes).
- **P3, `--block-only`: FIXED** in the outer repo: nothing restored, exit 1.
