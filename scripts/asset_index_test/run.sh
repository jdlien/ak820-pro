#!/usr/bin/env bash
# fa_entry_ok(), flash_assets_init() and flash_asset(), extracted verbatim from
# graphics/lcd_bus.c with FRAME_W and FRAME_H, FLASH_CHIP_SIZE, FLASH_ASSET_BASE
# and the index's constants, and flash_asset_t and the song fonts' ids from
# graphics/lcd_bus.h (plans/AUDIT-2026-10-31.md, F-018, and codex's review);
# the index loaded from the shipped assets-src/current/flash_assets.bin. CC picks the compiler
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
  grep -m1 -E '^#define LCD_FONT_SONG_LARGE ' "$g/lcd_bus.h"
  grep -m1 -E '^#define LCD_FONT_SONG_REGULAR ' "$g/lcd_bus.h"
  grep -m1 -E '^#define LCD_FONT_IS_SONG' "$g/lcd_bus.h"
  sed -n '/^#define FA_MAGIC /,/^static uint8_t  *fa_count/p' "$g/lcd_bus.c"
  awk '/^static bool fa_entry_ok\(const flash_asset_t \*a\) \{/{on=1} on{print} on && /^\}/{exit}' "$g/lcd_bus.c"
  awk '/^bool flash_assets_init\(void\) \{/{on=1} on{print} on && /^\}/{exit}' "$g/lcd_bus.c"
  grep -m1 -E '^uint8_t flash_assets_count\(void\)' "$g/lcd_bus.c"
  awk '/^const flash_asset_t \*flash_asset\(uint16_t id\) \{/{on=1} on{print} on && /^\}/{exit}' "$g/lcd_bus.c"
} > "$o/x_assets.inc"
for f in fa_entry_ok 'flash_asset_t;' 'bool flash_assets_init' 'flash_asset(uint16_t id)' 'fa_count'; do
  grep -qF "$f" "$o/x_assets.inc" || { echo "FAIL: the extraction found no $f" >&2; exit 1; }
done
# shellcheck disable=SC2086
"$cc" -std=gnu11 -O1 -g -Wall -Wextra $san -I"$o" -o "$o/test" "$here/test.c"
"$o/test" "$here/../../assets-src/current/flash_assets.bin"
