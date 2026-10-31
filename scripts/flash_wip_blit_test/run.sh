#!/usr/bin/env bash
# The real graphics/lcd_bus.c (by path, unedited) against the SPI NOR and panel
# models here: a glyph blit while a host-issued erase runs
# (plans/AUDIT-2026-10-31.md, F-014). An optional argument, 0x00, models a
# MISO line that idles low. CC picks the compiler (default cc); SAN the
# sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -O1 -g $san -Wall -Wextra -Wno-unused-parameter -Wno-unused-function \
    -I"$here/stubs" -I"$here" -I"$kb" -o "$o/test" "$here/test.c" "$here/model.c" "$kb/graphics/lcd_bus.c"
"$o/test" "${1:-0xFF}"
