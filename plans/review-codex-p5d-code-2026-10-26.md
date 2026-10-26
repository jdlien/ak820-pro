# Codex: P5d, eight settings profiles and the list's Save new (2026-10-26)

JD (10-26): "I think maybe just a 'Save New' makes more sense than finite
grayed out unused slots"; "Four is barely enough, 8 feels about right. I
think we can go ahead and use eight in the existing storage."

Rounds, verbatim, then dispositions:
1. `plans/review-prompt-p5d-code.txt`: qmk_firmware-ak820pro `57d5e900..830aa68d`
   (branch `gremlin/p5d`; `57d5e900` is P5b, the mainline), and the host
   side at ak820-pro `1f652e4`.
2. `plans/review-prompt-p5d-verify.txt`: `830aa68d..94072f55`.

## Round 1 (830aa68d)

**Yes—fix one P2 menu regression before flashing.**

- **[P2] A shrinking Profiles list leaves its cursor/page out of range.** [menu.c:1958](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1958) invalidates the display after host writes but never adjusts `cursor` or `top`. Reproduction: fill eight slots, select Save new (`cursor=9`, `top=8`), then delete slots through `0x41`. One deletion leaves no selected row; two leave a blank page despite six saved profiles. Clicking does nothing until a turn repairs the position. The same problem survives returning from a host-deleted slot because [pop():1554](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1554) repairs only valid slots. [Delete:1829](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1829) also retains the old parent position when host changes occurred under the slot/confirmation page. Normalize the list position after shrinkage and on these returns; recompute `top`. Add those cases to [test_profiles():3829](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:3829).

No additional static blocker found:

- **EEPROM:** macro reads, writes, playback and reset respect the explicit size, ending at address 805. No maximum-address consumer exposes profiles as macros. Full `eeconfig_init` still erases everything, as before.
- **Transaction:** Begin clears the count; retries do not advance it; failures close and retain the latch; timeout closes; commit requires nine pages. `tx_state++` cannot carry into `TX_CHANGED`.
- **Menu:** slot identity fits the signature, `pslot` remains tied to the open slot, host writes invalidate names, and ordinary ten-row paging works.
- **Migration:** P5b’s unhandled geometry fallback, A1→A2 conversion, zero-filled slots 5–8, eight-slot normalization and converted readback comparison are consistent. Downgrade refuses occupied upper slots.

The five firmware files match `830aa68d`; the host files now match `1f652e4a`. Artifact hashes and the 136 B heap gap check out. Process execution was denied: tests were inspected, not rerun; board timing and runtime stack margin remain unverified here.
## Round 2 (94072f55)

**Yes—the P2 is closed in all three named paths. No new static blocker for gremlin’s flash found.**

- Host writes fit every stacked Profiles frame and request a retarget: [menu.c:1969](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1969).
- Returning from a slot reselects it if valid, then fits regardless of validity: [menu.c:1565](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1565).
- Delete fits after its two-frame pop: [menu.c:1840](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1840).

Other frames are untouched; Profiles always has at least Back and Save new, preventing underflow: [menu.c:628](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:628).

Snapshot ordering is correct: host writes and input mark it stale before fitting; `row_count()` refreshes through `pfs_get()`: [menu.c:589](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:589), [1866](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1866). Retargeting remains outside scans; menu processing precedes the pump: [ak820pro.c:607](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:607).

One coverage gap: the added regressions don’t exercise host deletions under **Delete confirmation**: [menu_s0_test.c:4055](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:4055).

Tests were inspected, not rerun—process execution was denied. The patch adds no static RAM; the reported 136 B heap gap does not establish runtime stack or timing margin.
## Dispositions

**Round 1, [P2] a shrinking Profiles list leaves its cursor or page out of
range: fixed in `94072f55`.** `prof_list_fit()` clamps a Profiles frame's
cursor to its last row and puts `top` on the cursor's page. It runs over
every frame when `menu_tick()` takes a host's write (then a retarget), in
`pop()` after the return to a slot's row whether or not the slot survived,
and after Delete's two-frame pop. Tests: two host deletes with the cursor on
Save new at row 9; two under Profile 8's page, then a hold; and (round 2's
coverage note) two under Delete's confirm, then the click. Mutants for each
of the fit's lines and the host write's call are caught.

**Round 1's other answers** (no change): macro reads, writes and the reset
stop at the explicit size (805); the in-order count can't carry into
TX_CHANGED; the slot fits the signature's four bits; the migration's
fallback, conversion, normalization and downgrade refusal are consistent.

**Round 2: closed;** its coverage gap (host deletes under Delete's confirm)
has its test.

**Mutants** (`p5d_mutants.py`, 70): three survive, each accepted. Two of
them P5b already accepted: the entry invalidation (a page's rows differ
from the screen they replace anyway) and Load's latched clock. The third,
the input's stale mark, is new: Save new marks the snapshot stale itself,
and anything else a click writes shows within the 128 ms tick.
