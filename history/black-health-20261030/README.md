# Black's health, read on Buzz (10-30 12:34)

Black is gremlin's board (the black case; white is JD's, on Buzz's bench).
JD brought it to Buzz and put it on the relay cable. Its health was read once
over USB, with the daemon paused and relay 2 off: `ak820 health --json`, in
`health-1234.json`. Data was on 12:34:38-12:34:39.

- **Build:** `8ec0c8b9b4` dev, token `0xb5f2fdab`. A session on Gizmo
  flashed it at 23:34 10-28.
- **The last boot was a software reset:** `boot_rstst` 0x01, `SWRSTF`
  alone. A cold power-on reads 0x11, a slider brownout 0x05
  (`docs/sn32f299.md`). There is no watchdog record, and
  `consecutive_resets` is 0.
- **When:** `uptime_ms` is 14,539,787 (4 h 2 min). Uptime does not count in
  deep sleep, so the boot was at 08:32 10-30 or earlier.
- **What can cause it in this build:**
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
