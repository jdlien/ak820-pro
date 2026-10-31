#!/usr/bin/env bash
# usb_wakeup_try(), extracted verbatim from ak820pro.c (from the
# '#define USB_STATUS_REMOTE_WAKEUP' line to the function's closing brace),
# built with the real platforms/timer.c against the stubs here; runs test.c.
# CC picks the compiler (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
qmk="$here/../../qmk_firmware-ak820pro"
src="$qmk/keyboards/a_jazz/ak820pro/ak820pro.c"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=all}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
awk '/^#define USB_STATUS_REMOTE_WAKEUP/{on=1}
     on{print}
     on && /^static void usb_wakeup_try\(void\)/{fn=1}
     fn && /^}/{exit}' "$src" > "$build/x_wakeup.inc"
grep -q '^static void usb_wakeup_try(void)' "$build/x_wakeup.inc" || { echo "FAIL: usb_wakeup_try not found in $src" >&2; exit 1; }
# shellcheck disable=SC2086
"$cc" -std=gnu11 -O1 -g -Wall -Wextra -Wno-include-next-absolute-path $san -I"$here" -I"$build" -I"$qmk/platforms" \
    -o "$build/test" "$here/test.c" "$qmk/platforms/timer.c"
"$build/test"
