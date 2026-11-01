#!/usr/bin/env bash
# The raw-HID receive and reply loop under backpressure (codex's review of the
# 10-31 audit's Batch 4, P1 on F-001): tmk_core's send_raw_hid() and
# raw_hid_task(), extracted verbatim from usb_main.c, with the board's
# RAW_HID_TASK_MAX_REPORTS from config.h, and once without it as the control
# (the model must show the uncapped drain starving the watchdog). CC picks the
# compiler (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fw="$here/../../qmk_firmware-ak820pro"
u="$fw/tmk_core/protocol/chibios/usb_main.c"
cfg="$fw/keyboards/a_jazz/ak820pro/config.h"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
g="$(mktemp -d)"
trap 'rm -rf "$g"' EXIT
sed -n '/^void send_raw_hid(uint8_t \*data, uint8_t length) {/,/^void raw_hid_task(void) {/p' "$u" | sed '$d' |
    sed 's/^void send_raw_hid/static void send_raw_hid/' > "$g/raw.inc"
sed -n '/^void raw_hid_task(void) {/,/^}/p' "$u" >> "$g/raw.inc"
grep -q 'send_report(USB_ENDPOINT_IN_RAW' "$g/raw.inc" && grep -q 'raw_hid_receive(buffer' "$g/raw.inc" ||
    { echo "FAIL: the extraction found nothing" >&2; exit 1; }
cap="$(awk '/^#define RAW_HID_TASK_MAX_REPORTS/ {print $3}' "$cfg")"
[ -n "$cap" ] || { echo "FAIL: config.h sets no RAW_HID_TASK_MAX_REPORTS" >&2; exit 1; }
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -I"$g" -DRAW_HID_TASK_MAX_REPORTS="$cap" -o "$g/capped" "$here/test.c"
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -I"$g" -o "$g/control" "$here/test.c"
"$g/capped"
"$g/control"
