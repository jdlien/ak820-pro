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

**Not touched:** Gremlin's `gremlin/*` branches (Gremlin's call;
`gremlin/lockchan-clock` is the next flash), the branches checked out in
other sessions' worktrees (`phase1b-flash2`, `power-mode-bulb-base`), and
the fork's older branches from before this repo.
