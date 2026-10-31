#!/usr/bin/env bash
# The knob's modified-consumer sequencer (plans/AUDIT-2026-10-31.md, F-004):
# the real consumer_mod.c, quantum/action_util.c and tmk_core/protocol/report.c,
# with register_code, unregister_code, register_mods, unregister_mods and
# extract_mod_bits cut verbatim out of quantum/action.c and quantum/quantum.c,
# and quantum/keycode_config.c with MAGIC_ENABLE (the board's GUI lock).
# Runs test.c without and with NKRO. CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none); CONSUMER_MOD_C another copy of the
# source (say, an older one); -v as the first argument narrates.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
kb="$q/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
gen="$(mktemp -d)"
trap 'rm -rf "$gen"' EXIT

# The two timing constants and the detent delay, from the board's config.h.
gap=$(awk '/^#define MODIFIED_CONSUMER_GAP_MS/{print $3}' "$kb/config.h")
hold=$(awk '/^#define MODIFIED_CONSUMER_HOLD_MS/{print $3}' "$kb/config.h")
kdelay=$(awk '/^#define ENCODER_MAP_KEY_DELAY/{print $3}' "$kb/config.h")
[[ -n "$gap" && -n "$hold" && -n "$kdelay" ]] || { echo "FAIL: a timing constant is missing from config.h" >&2; exit 1; }

cut_fn() {  # $1 file, $2 exact first line of the function
    awk -v first="$2" 'index($0, first) == 1 {on = 1} on {print} on && /^}/ {exit}' "$1"
}
{
    echo '#include "host.h"'
    echo '#include "keycode.h"'
    echo '#include "command.h"'
    echo '#include "action_util.h"'
    echo '#include "action.h"'
    echo '#include "report.h"'
    echo 'void register_mouse(uint8_t mouse_keycode, bool pressed);'
    echo 'void wait_ms(uint32_t ms);'
    cut_fn "$q/quantum/action.c" '__attribute__((weak)) void register_code(uint8_t code) {'
    cut_fn "$q/quantum/action.c" '__attribute__((weak)) void unregister_code(uint8_t code) {'
    cut_fn "$q/quantum/action.c" '__attribute__((weak)) void register_mods(uint8_t mods) {'
    cut_fn "$q/quantum/action.c" '__attribute__((weak)) void unregister_mods(uint8_t mods) {'
} > "$gen/action_extract.c"
{
    echo '#include "keycodes.h"'
    echo '#include "quantum_keycodes.h"'
    echo '#include "modifiers.h"'
    echo '#include "keycode.h"'
    cut_fn "$q/quantum/quantum.c" 'uint8_t extract_mod_bits(uint16_t code) {'
} > "$gen/quantum_extract.c"
[[ $(grep -c '^}' "$gen/action_extract.c") -eq 4 && $(grep -c '^}' "$gen/quantum_extract.c") -eq 1 ]] ||
    { echo "FAIL: the cut functions were not all found" >&2; exit 1; }

inc="-I$here/stubs -I$kb -I$q/quantum -I$q/quantum/logging -I$q/quantum/keymap_extras
     -I$q/quantum/sequencer -I$q/tmk_core/protocol -I$q/platforms"
defs="-DEXTRAKEY_ENABLE -DMAGIC_ENABLE -DMODIFIED_CONSUMER_GAP_MS=$gap -DMODIFIED_CONSUMER_HOLD_MS=$hold -DENCODER_MAP_KEY_DELAY=$kdelay"
fails=0
for nkro in "" "-DNKRO_ENABLE"; do
    # shellcheck disable=SC2086
    "$cc" -std=gnu11 -g -O1 -Wall -Wno-unused-function $san $defs $nkro $inc \
        "$here/test.c" "${CONSUMER_MOD_C:-$kb/consumer_mod.c}" "$q/quantum/action_util.c" "$q/tmk_core/protocol/report.c" \
        "$q/quantum/bitwise.c" "$q/quantum/keycode_config.c" "$gen/action_extract.c" "$gen/quantum_extract.c" -o "$gen/test"
    echo "== ${nkro:-6KRO}"
    "$gen/test" "$@" | grep -E 'FAIL|failure' || fails=1
done
exit $fails
