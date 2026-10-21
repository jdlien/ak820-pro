# Firmware branches deleted 2026-10-21, and what they held

The firmware fork's short-lived branches were deleted on 10-21, locally and on
`jdlien`. Each one with commits not in `ak820pro-jdlien` is kept here as
`git format-patch` output, one directory per branch, named after the branch and its
tip. Each patch's first line, `From <sha>`, is the commit's original id, so
a plan that cites a commit can still be found here (`grep -rl <sha> .`). To get a
branch back: `git checkout -b <name> <base>`, then `git am <dir>/*.patch`.

**Archived (never for merge):**

| Branch | Tip | Base | Commits | What it was |
|---|---|---|---|---|
| `mac/sleep-pad` | `462cb9244b` | `b2a07e0d37` | 7 | `sleep.c` moved by 4-228 bytes, the deep-sleep regression's placement hunt ([`DEEP-SLEEP-REGRESSION-2026-10-20.md`](../../plans/DEEP-SLEEP-REGRESSION-2026-10-20.md)) |
| `mac/sleep-wfi-diag` | `466aa04636` | `b2a07e0d37` | 1 | the WFI sequence chosen at run time (op 14 sub 7), same plan |
| `mac/sleep-flash-probe` | `83371a49f2` | `b2a07e0d37` | 2 | the flash probe (op 14 sub 8), on top of the WFI diagnostic, same plan |
| `mac/sleep-vt-diag` | `0d765b362d` | `b2a07e0d37` | 1 | raw81's virtual timer never armed (local only), same plan |
| `mac/sleep-fix-xcheck-pad` | `221ffb103a` | `8b06e4dcc4` | 1 | the fix with its flash side moved 4 bytes: a cross-check built but never run |
| `mac/sleep-fix-xcheck-wfi28` | `5a9f7b406d` | `8b06e4dcc4` | 1 | the fix with the WFI moved to 2 mod 8: the other unrun cross-check |
| `bulb-slash-preview` | `d66c27993a` | `7df85fb89b` | 4 | the slash's shades on the panel (local only; [`POWER-MODE-ICONS-PLAN.md`](../../plans/POWER-MODE-ICONS-PLAN.md)) |
| `mac/lockchan-playback` | `9a06d8d22c` | `8b06e4dcc4` | 6 | the lock-LED handler and play times; every commit landed in `ak820pro-jdlien` rebased, under new ids, so this is for the old ids the plans cite ([`LOCK-LED-CHANNEL-PLAN.md`](../../plans/LOCK-LED-CHANNEL-PLAN.md)) |

**Deleted with nothing to keep** (each tip is an ancestor of
`ak820pro-jdlien`, so every commit the plans cite on them is still there):
`mac/lockchan-pm` (`dd8391c28d`), `mac/lockchan-pm-rtc` (`7ae8575c1a`),
`mac/overrun-caps` (`e7f6890e06`), `mac/sleep-wake-sram` (`8b06e4dcc4`),
`mac/uart-latency` (`b2a07e0d37`), `power-modes-revision` (`5df4e0e3b7`),
`power-mode-icons` (`26fcafaeca`, local only).

**Gremlin's branches, deleted the same afternoon** (locally and on
`jdlien`, after `gremlin/lockchan-clock` was merged as `36afff30e8`). Every
commit's change is in `ak820pro-jdlien` but `vt-switch`'s (by `git cherry`);
the other three are kept for the old ids the plans cite:

| Branch | Tip | Base | Commits | What it was |
|---|---|---|---|---|
| `gremlin/lockchan-media` | `1261ab2fa8` | `8b06e4dcc4` | 2 | the lock-LED handler and codex's review of it; landed rebased under new ids |
| `gremlin/rtc-clock-fixes` | `5a0ac6033e` | `8b06e4dcc4` | 3 | the RTC's PCF write and host corrections, rounds 1-3; landed rebased |
| `gremlin/rtc-clock-fixes-5df4` | `76af5c1242` | `5df4e0e3b7` | 3 | the same three on the power modes revised; landed rebased |
| `gremlin/vt-switch` | `981631b925` | `b2a07e0d37` | 1 | op 17 sub 6, raw81's long-clock timer stopped and re-armed at run time for the deep-sleep A/B (never merged) |

Deleted with nothing to keep (ancestors of `ak820pro-jdlien`):
`gremlin/lockchan-clock` (`01abfe0ecf`), `gremlin/raw81` (`0ae4cf8c80`),
`gremlin/rx-tap` (`4ee5629015`).

**Not touched:** the branches checked out in
other sessions' worktrees (`phase1b-flash2`, `power-mode-bulb-base`), and
the fork's older branches from before this repo.
