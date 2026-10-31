#!/usr/bin/env bash
# A power cut at every durable write of a Win/Mac flip, then the reboot, and
# a backup restored on the switch's other side (plans/AUDIT-2026-10-31.md,
# F-012; plans/review-codex-audit-batch3-2026-10-31.md, P1 and P2). The real
# menu/profiles.c. CC picks the compiler (default cc); SAN the sanitizer
# flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=c11 -g -O1 -Wall -Wextra $san -DMENU_HOST_TEST -I"$kb/menu" -o "$o/test" "$here/test.c" "$kb/menu/profiles.c"
"$o/test"
