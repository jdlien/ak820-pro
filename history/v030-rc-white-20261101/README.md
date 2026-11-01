# The v0.3.0 release candidate onto white (11-01 14:40), and its checks

`audit-fixes` at `4c7395a4c6`: the 10-31 audit's five batches, codex's
reviews and three verifies, and the low sweep
([`../../plans/AUDIT-2026-10-31.md`](../../plans/AUDIT-2026-10-31.md);
`plans/BACKLOG.md`'s audit section), on top of the second checkpoint
(`57d1368f17`, [`../audit-fixes-flash2-20261031/`](../audit-fixes-flash2-20261031/README.md)).
It is also the base of the row ISR's stage 1 A/B, which ran on white
straight after these checks (`history/rowisr-stage1-20261101/`).

**Build:** `via-dev-4c7395a4c6-20261031-224044.bin` (dev, token `0x6f758b40`,
heap gap 152 B, sha256 `d6774616…bdbd2e`, checked by the script).

## The flash

`flash-white.sh`, its output in `run.log`. White on Buzz's relay cable, on
its pack, relay 2 never touched (the drain); awake at the bench.

- **Data on 14:39:57-14:40:31**, the daemon paused for it.
- **Before:** token `0x191986cf`, level 35.6%, Power saver.
- **flash.sh:** the keymap restored and read back (720 bytes, 4 layers); the
  live settings applied and flushed, then the profiles written and read
  back. This was the first run on hardware of the restore's new order (the
  block unpublished while the pages go in, the live record applied with
  sub 5 and flushed with sub 6, then the commit with the side in its [7]).
- **After:** token `0x6f758b40`. The profiles read off the board equal the
  backup (`profiles-after.txt`, "same"). The level read "unknown" 2 s after
  the reboot, before the module's first `5C`; at 16:15 it read 35.2%.

## The checks (16:15-16:29)

- **Typing over Bluetooth:** JD's, "about the same as before".
- **The Win/Mac flip:** the switch was on the Mac after the flash and ended
  on Windows (`flip-read.sh`, `profiles-after-flip.txt`). The flip saved the
  Mac side's settings as left, and Windows, with no profile of its own,
  changed nothing, as designed. The brightness (v125 to v177) and the power
  mode (Power saver to Balanced, then back) were JD's own changes before it.
- **Deep sleep and wake:** dark at 16:26:20 (13.9 mA), deep sleep at
  16:26:31 (3.7-3.8 mA, Power saver), JD's key at 16:29:29 woke it (45 mA).
  While the Mac played music, the sleeping board woke for 7-15 s at
  ~14.4 mA every 30-60 s; `57d1368f17` did exactly the same at
  13:49-13:53 that day, so it is the daemon's lock-light frames
  (`plans/BACKLOG.md`), not the candidate.

White went to the row ISR session at 16:29 in its standing state: data off,
the daemon running, Power saver.
