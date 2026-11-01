#!/usr/bin/env bash
# The firmware's flash write path, the animation ceiling and header reader
# (graphics/lcd_bus.c) and the raw-HID flash channel (hid_protocol.c),
# extracted verbatim at build time, against a timed 16 MB chip model, and
# ak820ctl.c itself on a fake hidapi (plans/AUDIT-2026-10-31.md, F-001, F-015,
# F-044, and codex's review of them; first written as the audit's verify-046). CC picks the compiler
# (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
l="$kb/graphics/lcd_bus.c"
h="$kb/hid_protocol.c"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
g="$(mktemp -d)"
trap 'rm -rf "$g"' EXIT
{
  grep -m1 '^#define FLASH_CMD_READ' "$l"
  sed -n '/^#define ANIM_BASE /,/^#define ANIM_MAX /p' "$l"
  sed -n '/^#define FLASH_CMD_WREN/,/^uint32_t flash_crc32(uint32_t addr, uint32_t len) {/p' "$l" | sed '$d'
  grep -m1 '^static uint8_t  anim_count' "$l"
  sed -n '/^static bool anim_read_header(void) {/,/^}/p' "$l"
} > "$g/lcd.inc"
sed -n '/^\/\/ Nothing here ever blocks on the chip/,/^static inline bool is_flash_cmd/p' "$h" | sed '$d' > "$g/hid.inc"
grep -q 'bool flash_writable' "$g/lcd.inc" && grep -q 'static void flash_command' "$g/hid.inc" ||
    { echo "FAIL: the extraction found nothing" >&2; exit 1; }
ctl="$here/../../time-util-ak820pro/ak820ctl.c"
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -I"$here/fake_hidapi" -Dmain=ak820ctl_main -c -o "$g/ak820ctl.o" "$ctl"
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -Wno-unused-function -I"$g" -I"$here/fake_hidapi" -o "$g/test" "$here/test.c" "$g/ak820ctl.o"
TEST_TMP="$g" "$g/test" || { echo "--- ak820ctl's output:"; tail -40 "$g/ak820ctl.log"; exit 1; }
