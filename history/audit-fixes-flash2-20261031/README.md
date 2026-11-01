# The audit fixes' second checkpoint onto white (10-31 20:19)

The firmware audit of 10-31 ([`../../plans/AUDIT-2026-10-31.md`](../../plans/AUDIT-2026-10-31.md)),
all five of its batches, on the branch `audit-fixes`: the first checkpoint
(`67f13f6aaf`, [`../audit-fixes-flash1-20261031/`](../audit-fixes-flash1-20261031/README.md))
plus

- Batch 3 reworked after codex's review
  (`../../plans/review-codex-audit-batch3-2026-10-31.md`): the owner byte at
  805 (which side of the Win/Mac switch the live settings are) in place of the
  default layer, `HC_PROFILES` sub 8, the wear-leveling line's check a Berger
  code in place of the CRC-8 (`f70c493e0e`, `f40d3b47a1`); VIA's macro buffer
  18 B;
- Batch 4, writing assets: F-001, F-014, F-015, F-018, F-044 (`d998a97d1e`);
- Batch 5, the radio: F-013, F-019, F-022, F-023 (`451490fa60`) and F-024
  (`57d1368f17`).

**Build:** `via-dev-57d1368f17-20261031-161116.bin` (dev, token `0x191986cf`,
heap gap 184 B). The 24 host regression tests pass on it
(`scripts/audit_tests.sh`).

## The flash

`flash-white.sh` (the first checkpoint's, the build and the tokens changed),
its output in `run.log`. White on Buzz's relay cable, on its pack: relay 2
never touched (the drain). White had woken at 20:14:35 (JD at the bench), in
Power saver; the data's turn-on holds off its sleep.

- **Data on 20:19:03-20:19:33**, the daemon paused 20:19:02-20:19:33.
- Before: token `0x1038e774`, level 38.0%, Power saver.
- flash.sh: the keymap (0 of 19 macro bytes used, so the 18 B buffer takes
  it), the lighting, the profiles (three on the Mac side) and the live
  settings backed up, the battery log dumped
  (`~/Documents/ak820pro-battlogs/log-20261031-201905-preflash.csv`, 19
  entries), flashed, the keymap restored and verified, the profiles and the
  live settings restored and read back on the same side (no sub 8).
- After: token `0x191986cf`; no watchdog reset; the level "unknown" in the
  first seconds before a fresh `5C`, as after the first checkpoint.

Case 3 of Warren's wake fixes (a uhubctl reconnect across a deep sleep)
stopped unrun at 16:35 on the first checkpoint
([`../audit-fixes-case3-20261031/`](../audit-fixes-case3-20261031/)): no key
woke the board within its hour.
