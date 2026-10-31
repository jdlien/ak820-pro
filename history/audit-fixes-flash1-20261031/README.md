# The audit fixes' first checkpoint onto white (10-31 15:28)

The firmware audit of 10-31 ([`../../plans/AUDIT-2026-10-31.md`](../../plans/AUDIT-2026-10-31.md)),
its fixes so far, on the branch `audit-fixes`: Icon only (`5c8c5f5ea8`, white's
build before) plus

- Batch 1: F-002 (QMK Command off), F-009 (the clock reply from one stamp),
  F-007 and F-028 (the remote wake only for keys to USB), F-003 (an abandoned
  pairing lapses after 10 min), F-004 (the Mac knob keeps held modifiers);
  codex: no P1, two P2s fixed (`../../plans/review-codex-audit-batch1-2026-10-31.md`);
- Batch 2, the clock: F-005 and F-006 (a PCF stopped by a reset released at
  boot, a failed seed retried), F-016, F-025, F-026; codex held it on one P1
  and three P2s, all fixed, and its verify found nothing new
  (`../../plans/review-codex-audit-batch2-2026-10-31.md`);
- Batch 3, settings across a power cut: F-030 (the boot takes the Win/Mac side
  from the persisted default layer), F-011, F-012, F-041, F-010 (a CRC on each
  wear-leveling log line), F-017 (a keycode is one write); codex reviewing
  when this was flashed;
- Warren's `gremlin/wake-fixes` (`70f7c1ea10`: the CT16B3 reset bounded, the
  USB PHY's pair restored as the driver left it, F-032), merged;
- F-020 and F-027 in `sleep.c`.

**Build:** `via-dev-67f13f6aaf-20261031-152817.bin` (dev, token `0x1038e774`,
heap gap 208 B). Fourteen host regression tests pass on it
(`scripts/audit_tests.sh`).

## The flash

`flash-white.sh` (icon-only-20261030's, the token and level changed), its
output in `run.log`. White on Buzz's relay cable, on its pack: relay 2 never
touched (the drain). White had woken at 15:25:50 (JD at the bench); in Power
saver.

- **Data on 15:28:32-15:29:03**, the daemon paused 15:28:31-15:29:03.
- Before: token `0x5b880dd4`, level 36.9% (`battery-before.txt`), Power saver.
- flash.sh: the keymap, the lighting, the profiles and the live settings
  backed up to the default files, the battery log dumped
  (`~/Documents/ak820pro-battlogs/log-20261031-152834-preflash.csv`, 87
  entries), flashed, the keymap restored and verified, the profiles and the
  live settings restored and read back, the clock left to the daemon.
- After: token `0x1038e774`.

Not yet run on it: the wake fixes' case 3 (a uhubctl reconnect across a deep
sleep, both USB bits back, SOFs moving, HID working), which needs a key to
wake the board.
