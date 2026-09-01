# Findings — input-validation audit (phase 2.3)

Audited 2026-09-01 at `a4382c747c`+`d770b64937` era tree. Scope: every parser
of host- or module-controlled bytes in `keyboards/a_jazz/ak820pro/`. Raw HID
is reachable by any local process with HID access (and relayed in BT mode),
so "the host script is trusted" is not a full answer — severities are weighed
for a keyboard, not a bank. QMK delivers raw-HID buffers at a fixed 32 bytes
(`RAW_EPSIZE`), which several checks below rely on; that assumption is safe
within QMK but is noted where it is load-bearing.

## Findings, ranked

### 1. Medium — `rtc_apply_bytes()` writes unvalidated fields into the battery-backed PCF8563

`ak820pro.c:553` (rtc_apply_bytes) → `rtc/rtc.c:493` (rtc_set_time) →
`rtc.c:158` (pcf_write). No range validation anywhere on the path: month 0
or 13, day 32, hour 25, seconds 200 all pass straight to `dec2bcd()` and
into the chip.

- **Scenario:** a malformed `[07 10 01 yy 13 32 ..]` packet (buggy host
  script, or any local process) writes nonsense BCD into a battery-backed
  part. `dec2bcd(seconds >= 80)` additionally sets bit 7 of the seconds
  register, which is the PCF8563 **VL (voltage-low) flag** — persistent
  side effects beyond a wrong time.
- **Consequence:** clock displays garbage until the next 6-hourly host
  clocksync self-heals it (needs the cable). Weekday is masked (`& 0x07`);
  nothing crashes — the damage is wrong persistent state, not memory safety.
- **Fix:** validate in `rtc_apply_bytes` before touching hardware —
  `month 1..12, day 1..31, weekday 0..6, hours 0..23, min/sec 0..59` —
  reject with `data[0] = RTC_UNHANDLED`. Also propagate the existing bool:
  the caller ignores `rtc_apply_bytes()`'s return, so an I2C failure still
  replies "handled" (both dispatch variants).
- **Disposition: fix-now** (10 lines, no behavior change for valid input).

### 2. Low-medium — nothing counts malformed CH582F traffic (`health_note_rx_malformed` is never called)

`bluetooth/ch582f_ajazz.c` parse loop (~line 650): the rolling window is
self-resynchronising by construction, but a byte pattern `[5A|5B|5C] d ck`
with a WRONG checksum — the signature of a corrupted frame, exactly what the
historical priority inversion produced — is silently skipped. The health
counter hook added in phase 1 (`health.h`) has no producer yet.

- **Scenario:** UART corruption returns (a future priority regression, EMI,
  a module firmware quirk). Frames are lost silently; the only symptom is
  behavioral (stuck digit, missed LED state) with no counter to correlate.
- **Fix:** in the parse loop, when `b2` is a known type byte and `b0 !=
  (uint8_t)(b2+b1)` **and** the byte does not begin a new match, call
  `health_note_rx_malformed()`. Expect a small false-positive rate from
  payload bytes that happen to look like type bytes — the counter is a
  trend instrument, not an exact frame count; document that at the call
  site.
- **Disposition: fix-now** (with the false-positive caveat in the comment).

### 3. Low — a forged/corrupted `5B` frame can flip connection state through a weak checksum

`ch582f_ajazz.c` 5B handling: the only integrity on a state-changing frame
is the 1-byte additive checksum. A corrupted burst that happens to read
`5B 32 8D` asserts "connected" (clearing retries, setting
`is_module_connected`); `5B 31 8C` fakes "advertising", etc.

- **Consequence:** transient wrong UI state and, worst case, a suppressed
  retry; the next genuine 5B frame corrects it. The 5A path already carries
  a plausibility guard and a promotion dwell; 5B codes are a whitelist
  (unknown codes fall to the 0x23-idle default and are ignored).
- **Fix considered and NOT recommended:** requiring two consecutive
  identical 5B frames would break the protocol — `5B 32` is sent ONCE
  (CLAUDE.md: the missed-`5B 32` bug class exists precisely because there
  is no repetition to lean on).
- **Disposition: accept-and-document.** Finding 2's counter gives it
  observability.

### 4. Low — `FC_UNLOCK` is a one-byte, unauthenticated gate to the stock animation slots

`ak820pro.c` (FC_UNLOCK) → `lcd_bus.c:311/314/323`. With unlock on,
`in_anim_slot()` accepts each slot base + `0x100 + 132*0x8000` ≈ 4.1 MB —
the four "slots" overlap each other and blanket roughly `0x1AA000..0x960100`,
far more than any real animation. Below `0x1AA000` stays unwritable
regardless, and the chip-bounds check in `flash_writable` is correct.

- **Scenario:** any HID-capable process sends `[07 11 08 01]` then erases
  the stock animation frames (which this board's zeroed header never plays
  anyway). No path to the QMK asset region below `FLASH_ASSET_BASE` other
  than the anim slots; no path to internal MCU flash at all from this
  channel.
- **Disposition: accept-and-document** — the unlock exists precisely so
  `ak820ctl --unlock` can reprovision those slots; an attacker with local
  HID access could equally erase the *asset* region above the floor, which
  is always writable by design. Recovery for both is a re-provision. Not
  worth an auth scheme on a keyboard. (Optional tightening if revisited:
  size `in_anim_slot` to the real `ANIM_STRIDE * 244` ceiling instead of
  132*32K per slot.)

### 5. Info — `FC_CRC32` reads any flash address (including below the write floor)

By design: it is how the animation header was probed (CLAUDE.md). Read-only
information disclosure of stock flash content to any HID-capable process.
Benign on this device; noted so nobody mistakes it for an oversight.

## Verified clean

- **`flash_command` write/erase path:** `FC_ERASE` and the page-program path
  both route through `flash_writable()` (floor at `FLASH_ASSET_BASE`,
  chip-size bounds, len-0 reject) — a malformed packet cannot touch internal
  flash (different peripheral entirely) or stock regions below the floor
  without the explicit unlock. `FC_WRITE_BEGIN` requires page alignment and
  writability; the per-page re-check in `flash_page_program` catches a
  stream that runs past a writable window (defense in depth).
- **`FC_WRITE_DATA` arithmetic:** `n > length - 4` is safe under integer
  promotion (a short `length` cannot underflow into acceptance); `fw_pg`
  flushes exactly at 256 so `fw_fill` cannot exceed the buffer with n ≤ 28;
  the FS_BUSY rewind (`fw_fill -= i+1`) is consistent with the host
  re-sending the identical packet.
- **`FC_CRC32/FC_CRC_NEXT`:** 24-bit len cannot overflow `crc_left`;
  `FC_CRC_NEXT` with no running CRC rejects (`crc_left == 0`); reads past
  chip end are benign (SPI returns idle bytes).
- **`text_command` and display setters:** line index validated
  (`line >= TEXT_LINES` rejects), per-line length clamps
  (`DISPLAY_TEXT_MAX_L0/L1`), icon id clamped to `DISPLAY_ICON_STOP`,
  non-ASCII mapped to `?` at the single choke point
  (`display_set_text_line`), `TEXT_PLAYBACK` length-checked and its values
  benign at render (worst case an odd-looking timer).
- **`health_command` (0x13):** `HC_GET` length-checked; the 4+28 reply
  exactly fits the 32-byte report. `HC_STALL` is compiled only under
  `WDT_TEST_HOOKS` (instrumented flavor via `build.sh` EXTRAFLAGS) — in a
  daily build the case does not exist and the packet answers UNHANDLED.
  (In an *instrumented* build any HID process can wedge the board by
  design; that flavor is a test build — documented here.)
- **Dispatch guards:** `is_flash_cmd` (len ≥ 4), `is_text_cmd` (len ≥ 3),
  `is_health_cmd` (len ≥ 3), RTC set (len ≥ 10) — all check length before
  indexing; both VIA and non-VIA variants dispatch identically.
- **CH582F parser structure:** 64-byte per-pass cap bounds latency; the
  window match requires a whitelisted type byte AND checksum; `5C` battery
  is range-checked (`d <= 100`); `5A` has the plausibility mask + link gate
  + promotion dwell; unknown `5B` codes are ignored. Arbitrary byte soup
  cannot index arrays or livelock the loop.
- **`via_custom_value_command_kb`:** unknown channels/commands fall through
  to UNHANDLED; VIA core ids are handled upstream by VIA itself.

## Summary of dispositions

| # | Finding | Disposition |
|---|---|---|
| 1 | RTC field validation + honest reply | **fix-now** |
| 2 | Wire up `health_note_rx_malformed` | **fix-now** |
| 3 | 5B trusts weak checksum | accept-and-document (done here) |
| 4 | FC_UNLOCK unauthenticated / oversized slots | accept-and-document (done here) |
| 5 | CRC reads below floor | info only |
