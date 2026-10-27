#!/usr/bin/env bash
# Build the firmware's flash_tidy.c (the early cleanup, 10-27), verbatim,
# against the stubs here and the board's own power.h; run test.c. CC picks
# the compiler (default cc; on Windows mingw64's gcc, first on PATH).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="${FLASH_TIDY_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro}"
cc="${CC:-cc}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$kb/flash_tidy.c" "$kb/flash_tidy.h" "$kb/power.h" "$build/"
"$cc" -std=c11 -O1 -Wall -Wextra -Werror -I"$build" -o "$build/test" "$here/test.c" "$build/flash_tidy.c"
"$build/test"
