# Watchdog breadcrumbs — 2026-09-22

Implemented in the QMK working tree and the Rust host agent following the
[real-use reset](../history/incident-2026-09-22-wdt/README.md). This change
collects evidence for the next failure; it does not claim to fix its cause.

## Implementation

- `watchdog_record.c/.h` owns the existing 16-byte `.ram7` allocation:
  versioned magic, saturating reset count, complemented operation/parent path,
  and last housekeeping-entry uptime. The path is updated with one aligned
  store; no timer reads or I/O per scope. Boot capture is immutable until the
  next boot and is not part of `health_reset()`.
- Nested scopes restore the saved path using GCC cleanup, including early
  returns. Two deepest marked scopes are retained. Only main-loop code writes
  the record; interrupt state, program counter, and full stack are not captured.
- The EFL backend adds weak begin/end hooks around the actual program/erase
  calls; board overrides distinguish those operations from the earlier DMA
  drain. Other boards retain no-op hooks.
- Health v6 adds page 5, command `0x08`; old page layouts remain unchanged.
  The Rust CLI decodes it on macOS and Windows. `--crash` requires support;
  ordinary health reads still work against v5.
- The agent logs a new recovered record and its preceding health sample,
  with immediate sampling after an observed recovery in addition to the usual
  five-minute cadence. The on-disk log outlives subsequent keyboard power loss.

## Validation completed

- Actual recorder C code compiled and run on the host: cold/old/corrupt RAM,
  warm reset preservation, nested scopes and early return, boot-time guard,
  immutable captured report, wire byte layout, reset-count saturation and
  brownout rejection.
- Rust suite: 348 unit tests and 13 integration tests passed. Added coverage
  for protocol version/layout rejection, unknown IDs, unavailable evidence,
  JSON output, old firmware behavior and one-time recovery logging with the
  preceding sample.
- macOS release binaries built; Windows MSVC target passes `cargo check`.
- Daily and instrumented firmware builds pass the wrapper's structural
  binary/VIA checks. `.ram7` is exactly 16 bytes at `0x20007ff0`, NOLOAD;
  `__ram0_end__` and the DFU boundary are unchanged. Disassembly confirms one
  aligned `str` publishes the operation path.
- Updated release CLI successfully read the currently installed v5 board:
  no unsupported page requested, no firmware/settings changes.

Builds used `status.showUntrackedFiles=no` only for the wrapper's Git status
checks after verifying both submodules' sole untracked file was `.DS_Store`;
neither submodule has tracked edits or an altered gitlink. Firmware source is
an uncommitted development tree, not a release pinned in `deps.lock`.

## Built artifacts

- `ak820pro-builds/out/via-daily-b89777e0f9-dirty-20260922-134320.bin`
- `ak820pro-builds/out/via-instrumented-b89777e0f9-dirty-20260922-134520.bin`
- `ak820-agent/target/release/ak820` and `ak820-agent`

## Hardware validation — 2026-09-22

Instrumented firmware flashed and checksum-verified. The intentional single
`HC_STALL` mode-1 hang recovered and reported **test_stall within raw_hid**,
reset count **1**, last-pass uptime **32,708 ms**, boot reset flags **0x03**
(SW + WDT). Multiple reads returned the same frozen record; `HC_RESET`
cleared ordinary counters without changing any byte of page 5.

The signed updated agent was installed with clock ownership at **13:59:44**.
It observed the keyboard becoming unresponsive at **13:59:59** and recovered
at **14:00:07**, immediately logged the retained record exactly once, included
the preceding sample from **13:59:47**, and saved the record in its status file.
These timestamps bracket host observations, not the full hardware timeout.

Before flashing, current settings were backed up. Readback before the second
flash matched every keymap byte, encoder assignment and lighting setting.
The daily artifact was then flashed and checksum-verified. Its final readback
matched all 720 original keymap bytes, encoder assignments and RGB settings.
Health reports v6, reset count 0 and an unavailable previous-boot record after
the normal software reboot. The read-only `HC_TXTRACE` command returned
`UNHANDLED`, confirming the test-hook conditional is absent from daily firmware.
The updated signed agent was restarted at **14:02:20**, owns the clock, and
reports the board present with no clock failures.

At 29.9 s uptime the daily build measured scan rate 326 Hz, row sampling
215.9 Hz per row, worst row gap 10 ms, worst main-loop gap 15 ms, no LCD blit
timeouts and no >=25 ms stalls. Pre-update sampling was approximately 216 Hz
per row with a 10 ms worst row gap. This is an initial functional check, not a
long-duration soak or proof that the original intermittent fault is fixed.

The initial flash attempt exposed a separate macOS detection bug: the Sonix
bootloader was present in IOUSB but absent from hidapi enumeration. `flash.sh`
now uses the structured IOUSB registry on macOS, matching VID/PID on the same
node, and retains hidapi on other platforms. Three piped-plist tests cover
nested bootloader presence, mismatched devices and the normal firmware ID.

Evidence: `history/incident-2026-09-22-wdt/validation/`, including the firmware
flash logs, saved raw reports, restored settings, and agent recovery log.
Physical cold-power removal after capturing a record was not separately tested;
the host tests cover power/brownout rejection. Normal reboot/reflash readback
checks that old evidence is not mislabeled as a new watchdog crash.

The earlier real-use reset cannot acquire breadcrumbs retroactively. Its
accumulated LCD timeouts remain a lead, not a demonstrated cause.
