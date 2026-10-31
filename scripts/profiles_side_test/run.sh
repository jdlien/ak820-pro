#!/usr/bin/env bash
# The real menu/profiles.c with scripts/profiles_test.c's fakes: the Win/Mac
# switch moved while the board is off (plans/AUDIT-2026-10-31.md, F-030), and
# scripts/profiles_test.c's own checks before it. CC picks the compiler
# (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
{
  "$cc" -std=c11 -g -O1 -Wall -Wextra $san -DMENU_HOST_TEST -I"$kb/menu" -o "$o/pt" "$here/../profiles_test.c" "$kb/menu/profiles.c"
  "$cc" -std=c11 -g -O1 -Wall -Wextra -Wno-unused-function $san -DMENU_HOST_TEST -I"$kb/menu" -o "$o/test" "$here/test.c" "$kb/menu/profiles.c"
}
"$o/pt" | tail -1
"$o/pt" | grep -q "all checks passed"
"$o/test"
