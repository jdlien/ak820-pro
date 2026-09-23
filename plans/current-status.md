# Current status — AK820 Pro watchdog diagnostics

Updated 2026-09-22 after implementing, hardware-testing, flashing, and pushing
the retained watchdog breadcrumb feature.

## Current installed state

- The keyboard is running the daily firmware built from
  `via-daily-b89777e0f9-dirty-20260922-134320.bin`.
- Health protocol is v6. The keyboard reports reset count 0 after the final
  daily flash, no LCD blit timeouts, no stalls >=25 ms, and an unavailable
  previous-boot record, as expected after a normal reboot.
- The keymap, encoder assignments, and RGB settings were backed up before
  flashing and read back identically afterward: 720 keymap bytes, four layers,
  one encoder, effect 2, hue 181, saturation 219, value 105, speed 227.
- The signed Rust agent is installed and running as
  `com.jdlien.ak820pro.agent`, owning the clock. The Python timekeeper and old
  now-playing LaunchAgents remain disabled.
- The agent status and log live at:
  `~/Library/Application Support/ak820pro/ak820-agent.status` and
  `~/Library/Logs/ak820pro/ak820-agent.log`.

## What changed

The firmware now uses the existing 16-byte reset-retained `.ram7` region to
keep a versioned, corruption-checked operation breadcrumb. It records the
current main-loop operation, its parent, and the uptime at the last completed
housekeeping pass. Scope exits restore the parent, including early returns.
The record is captured at boot after a watchdog reset and then frozen for that
boot. It is not a full log, stack trace, program counter, or proof of cause.

Covered operations include raw HID, wireless handling, key events, LCD waits
and transfers, external flash, RTC I2C, internal flash drain/program/erase,
and housekeeping subtasks. Power loss, brownout, ordinary reset, or corrupt
retained RAM makes the record unavailable instead of reporting stale evidence.
The ordinary health-counter reset does not clear it.

Health command `HC_GET5 = 0x08` exposes the record. The updated Rust CLI reads
it with:

```sh
ak820-agent/target/release/ak820 health --crash --json
```

The agent reads it after recovery and at its normal health interval, logs each
new watchdog recovery once, includes the preceding health sample, and writes
the record into the status file. Existing v5 firmware remains readable; v6 is
required for `--crash` evidence.

## Hardware validation

The instrumented build was flashed, settings restored, and one controlled
`HC_STALL` mode-1 hang was triggered. It recovered through the hardware
watchdog in about 12 seconds and reported:

```text
test_stall within raw_hid
reset count: 1
last pass uptime: 32708 ms
reset flags: 0x03
```

The updated agent observed the temporary disconnect, logged the retained record
once with the preceding health sample, and saved it in the status file.
Reading the record repeatedly returned the same frozen bytes. Resetting normal
health counters left the record unchanged. The daily build was then flashed,
its checksum verified, settings restored, and the test hook was confirmed
absent (`HC_TXTRACE` returned `UNHANDLED`).

Initial daily measurements after the final flash: scan rate 326 Hz, row
sampling 215.9 Hz per row, worst row gap 10 ms, worst main-loop gap 15 ms,
zero LCD blit timeouts, and zero stalls >=25 ms. This is a functional check,
not a long soak and does not establish that the original intermittent crash is
fixed.

## How to investigate the next real crash

Do not power-cycle after a watchdog reset. Let the keyboard recover, leave it
connected, and let the agent observe the reconnect. Then inspect:

```sh
rg "firmware watchdog reset" \
  ~/Library/Logs/ak820pro/ak820-agent.log
ak820-agent/target/release/ak820 health --crash --json
ak820-agent/target/release/ak820 status
```

The log line should identify the interrupted operation and include the
preceding health snapshot. If the keyboard loses power, the retained SRAM
record is gone, but anything already written to the host log remains.

## Source, commits, and validation artifacts

- Main repository commit `773246a`, pushed to `origin/main`.
- Firmware repository commit `8d1eb4dd21`, pushed to `jdlien/ak820pro-jdlien`.
- Firmware metadata ignore commit `a2c3b1a4e1`, pushed to
  `jdlien/ak820pro-jdlien`.
- Implementation and hardware details: [`WATCHDOG-BREADCRUMBS.md`](WATCHDOG-BREADCRUMBS.md).
- Incident and raw validation captures:
  [`history/incident-2026-09-22-wdt/README.md`](../history/incident-2026-09-22-wdt/README.md).
- Host tests: 348 Rust tests passed; Windows MSVC `cargo check` passed; the
  retained-record C simulation passed with AddressSanitizer and UBSan; daily
  and instrumented firmware builds passed structural checks.

## Repository notes

`qmk_firmware-ak820pro` is a separate firmware repository ignored by the main
repo, with direct nested submodules `lib/chibios` and
`lib/chibios-contrib`. Their commits and gitlinks were not changed by this
work. `.DS_Store` is ignored in the main repository, the firmware repository,
and locally in the two nested submodule checkouts; all existing `.DS_Store`
files under this workspace were removed. The unrelated root `.taskmaster/`
directory remains untracked and was deliberately left alone.

## Open question

The original spontaneous `WDT reset x1` remains unexplained. Its preceding
health sample had accumulated LCD blit timeouts and non-flash stalls, but those
counters were historical and did not prove causation. The next real reset is
the first one that should identify where main-loop progress stopped.
