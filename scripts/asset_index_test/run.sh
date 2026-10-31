#!/usr/bin/env bash
# fa_entry_ok(), extracted verbatim from graphics/lcd_bus.c with FRAME_W and
# FRAME_H, FLASH_CHIP_SIZE and FLASH_ASSET_BASE, and flash_asset_t from
# graphics/lcd_bus.h (plans/AUDIT-2026-10-31.md, F-018). CC picks the compiler
# (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
g="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
{
  grep -m1 -E '^#define FRAME_W ' "$g/lcd_bus.c"
  grep -m1 -E '^#define FRAME_H ' "$g/lcd_bus.c"
  grep -m1 -E '^#define FLASH_CHIP_SIZE ' "$g/lcd_bus.c"
  grep -m1 -E '^#define FLASH_ASSET_BASE ' "$g/lcd_bus.c"
  awk '/^typedef struct \{/{buf=$0; on=1; next} on{buf=buf"\n"$0} on && /\} flash_asset_t;/{print buf; exit} on && /^\}/{on=0}' "$g/lcd_bus.h"
  awk '/^static bool fa_entry_ok\(const flash_asset_t \*a\) \{/{on=1} on{print} on && /^\}/{exit}' "$g/lcd_bus.c"
} > "$o/x_assets.inc"
grep -q 'fa_entry_ok' "$o/x_assets.inc" && grep -q 'flash_asset_t;' "$o/x_assets.inc" || { echo "FAIL: the extraction found nothing" >&2; exit 1; }
# shellcheck disable=SC2086
"$cc" -std=gnu11 -O1 -g -Wall -Wextra $san -I"$o" -o "$o/test" "$here/test.c"
"$o/test"
