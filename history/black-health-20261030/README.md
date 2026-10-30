# Black's health, read on Buzz (10-30 12:34)

Black is gremlin's board (the black case; white is JD's, on Buzz's bench).
JD brought it to Buzz and put it on the relay cable. It was read three times
over USB, with the daemon paused and relay 2 off: `ak820 health --json`, in
`health-1234.json`. Data was on 12:34:38-12:34:39, 12:38:21-12:38:23 (the
ring) and 12:39:24-12:39:27 (the battery log).

- **Build:** `8ec0c8b9b4` dev, token `0xb5f2fdab`. A session on Gizmo
  flashed it at 23:34 10-28.
- **The last boot was a software reset:** `boot_rstst` 0x01, `SWRSTF`
  alone. A cold power-on reads 0x11, a slider brownout 0x05
  (`docs/sn32f299.md`). There is no watchdog record, and
  `consecutive_resets` is 0.
- **When: Gizmo's flash, 23:34 10-28. No reset since, so no crash.**
  - Black's RAM battery log (`battlog-1239.csv`, dumped 12:39:26) runs
    unbroken from 23:49 10-28 to 12:34 10-30: 148 entries, one per 15 min.
  - Its awake time (900 s less `slept_s`, summed) is 14,515 s. Black's
    uptime at that last entry was ~14,518 s (14,539.8 at 12:34:38), a
    match within ~3 s, so its first period began at the boot.
  - `external` (USB) shows only in the first period and from 08:49 10-30.
    Black was off Gizmo's USB by 00:04 10-29.
  - Gizmo's flash.sh jump and the bootloader's exit both leave `SWRSTF`
    alone, which accounts for `boot_rstst` 0x01.
- **The wake ring (`ring-1238.json`, op 24 slots 0-8):** 17 sleeps since
  the boot (`wake_seq`). Seq 9-16, the eight kept, are all from today, each
  woken by a key, with 0 strays and an empty stray snapshot.
- **The other resets this build can do, none of them seen here:**
  - the bootloader jump (`watchdog.c` `bootloader_jump()`: Fn+Esc, the
    menu's Bootloader row, a flash);
  - a deep sleep wake whose clock switch or PLL timed out (`sleep.c` lines
    528, 577 and 580 at `8ec0c8b9b4`; ds-phase's slot 9 flags these as
    `clk_ceil` and `pll_ceil`).
- **The counters since that boot:**
  - `tx_sent` 15538, `tx_timeouts` 1620, `tx_drops` 0;
  - `count_ge_25ms` 5 (2 not at a flash write); `loop_gap_max_ms` 74, at a
    flash write;
  - `flash_writes` 958, `key_presses` 6367.
