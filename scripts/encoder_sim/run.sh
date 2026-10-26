#!/usr/bin/env bash
# The knob's decoder (drivers/encoder/encoder_quadrature.c, verbatim) on stubs/:
# with the board's rest rule every case holds; without it, the half-detent
# offset shows JD's symptom (10-25). CC= to pick the compiler.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="${ENCODER_SIM_SRC:-$here/../../qmk_firmware-ak820pro/drivers/encoder/encoder_quadrature.c}"
cc="${CC:-cc}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
fail=0
for rule in -DENCODER_REST_PINS_EQUAL ""; do
    # ENCODER_TESTS: QMK's own switch, so each boot() zeroes the count as a real boot does
    "$cc" -std=c11 -Wall -Wextra -Wno-unused-parameter -DENCODER_TESTS $rule -I"$here/stubs" -o "$build/enc" "$here/encoder_test.c" "$src"
    "$build/enc" || fail=1
done
exit $fail
