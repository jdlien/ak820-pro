# Warren's ds-phase with slot 10 on JD's board (00:02-00:05 10-29)

`gremlin/ds-phase` at `fcb7ae00b4`, built here as dev:
`via-dev-fcb7ae00b4-20261029-000229.bin`, token `0xf2a645a7`, heap gap
152 B. It is `27d1105dc1` (`../ds-phase-check-20261028-2350/`) plus codex's
fixes:
- the kept RAM checked at every boot (`sleep_boot_check()`);
- the sequence number reserved at the teardown;
- the magic `DSL2`;
- **slot 10**: slot 9 as this boot inherited it, frozen in `.bss` until the
  next reset, so the next sleep (minutes later on battery) can't overwrite
  the evidence of a reset before anyone reads it.

`ds-sequence2.sh` (this folder; relay 2 never touched, the daemon paused):

| step | slot 9 | slot 10 |
|---|---|---|
| after the flash | zero (27d1105d's `DSL1` refused) | empty |
| after a 30 s fed armed sleep (the cap, 30 counted, PLL 95) | `DSL2`, seq 0, the cap, flags `0xc0`, 30 s | empty |
| after re-flashing the same `.bin` | the same, `from_boot_before` 1 | **the same sleep, present** |

The wake ring holds seq 0 and names 1 as the next. A reset inside a sleep
now leaves where (the record's phase), and what, when and the strays (slot
10), for as long as the board runs.

USB data on 00:02:36 for this; off again after it.
