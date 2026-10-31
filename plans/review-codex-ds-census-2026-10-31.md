# Codex: the wake's finer phases and the interrupt census (2026-10-31)

The review of `gremlin/ds-phase` `6ce20ccef98` (on `fcb7ae00b44`), codex
(Astra, xhigh, read-only), with the prompt in
[`review-prompt-ds-census.txt`](review-prompt-ds-census.txt). The change
came from Buzz's session's proposal after the unanchored reviews
([`review-codex-ds-wake-unanchored-2026-10-31.md`](review-codex-ds-wake-unanchored-2026-10-31.md),
[`review-fable-ds-wake-unanchored-2026-10-31.md`](review-fable-ds-wake-unanchored-2026-10-31.md)):
phase 30 split around CT16B3's reset, and USB's state and an interrupt count
kept with phase 31.

`6ce20ccef98` went onto black at gremlin at 03:03 10-31 while codex read
(JD: flash first, fix after). No P1; three P2s, fixed in `935e6e1bd2a`
(on black from 03:12). Codex's verify
([`review-codex-ds-census-verify-raw.md`](review-codex-ds-census-verify-raw.md)):
1 and 2 fixed, 3 partly, as the hook read IPSR before its mask; moved
under it in `05ef0f5bbc9`, on black from 03:19 (token `0x4de76a30`, dev
heap gap 128 B, the floor), and checked again
([`review-codex-ds-census-verify2-raw.md`](review-codex-ds-census-verify2-raw.md)).

## Dispositions

1. **P2, the boot guard opened before the kept census was settled.** Fixed:
   `ds_keep_boot()` sets `ds_kept_checked` last, after the census's
   disposition and a `__DMB()`. The hook counts only once it is set, so
   the boot's own interrupts cannot touch what a reset left. The ELF shows
   the `dmb` and then the store as the function's last two.
2. **P2, a previous wake's census took the failed sleep's number.** Fixed:
   `ds_last_begin()` clears a census that is not frozen at each teardown,
   under the lock. A reset between the teardown and the unmask now reads
   none for the census, where it read the wake before's labelled as this
   sleep's.
3. **P2, nested handlers could erase each other's bit in `seen`, and
   `last`.** Fixed: the hook's update is masked (`cpsid`/`cpsie`, about 20
   cycles, only while it counts). No handler is entered with PRIMASK set,
   so the unconditional unmask restores what was there. The comment says
   `last` is the latest entry, not necessarily a hung handler. The verify
   found the IPSR read still before the mask, so a handler preempted
   between them overwrote the nested one's `last`; it is under the mask
   since `05ef0f5bbc9` (the ELF: `cpsid`, then `mrs`). The longest masked
   path is 26 instructions, with no call or loop.

The review's other notes, kept as reading guidance: the hook runs at the
20 kHz tick too, so its idle cost (a call and two byte tests) is paid there
most; HardFault, the unhandled vector and the bootloader's branch do not
reach it; `INSTS` sampled in the prologue can differ from what the LLD
reads a moment later; SysTick counts in `n_all` and `last` (15), never in
`seen`; `CLOSED` means the close was reached, with the scope's cleanup and
the return after it.

## The review, verbatim

See [`review-codex-ds-census-raw.md`](review-codex-ds-census-raw.md).
