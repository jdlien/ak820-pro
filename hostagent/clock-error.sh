#!/bin/bash
# Measure the AK820 Pro's clock phase error in milliseconds.
#
# The wire protocol carries WHOLE SECONDS in both directions, so the sub-second
# offset is recovered by polling the device fast and catching the instant its
# seconds value increments. That edge is the device's second boundary; comparing
# it to the host's gives the phase error, with no sub-second field on the wire.
#
# Needs the USB cable. Works in any dip-switch position: raw-HID replies are
# routed over USB regardless of the active host driver.
set -u
CTL="${CTL:-/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl}"
SAMPLES="${1:-5}"

for n in $(seq 1 "$SAMPLES"); do
  prev=""
  start=$(python3 -c 'import time;print(time.time())')
  while :; do
    line=$("$CTL" clock --read 2>/dev/null | awk '/^device/{print $3}')
    now=$(python3 -c 'import time;print(time.time())')
    [ -z "$line" ] && { echo "no reply (cable? bootloader?)"; exit 1; }
    if [ -n "$prev" ] && [ "$line" != "$prev" ]; then
      # device just ticked; host fraction at this instant IS the phase error
      python3 -c "
import sys
t=float('$now')
frac=t-int(t)
ms=frac*1000
print(f'sample $n: device ticked at host .{ms:06.1f} ms  ->  error {ms if ms<500 else ms-1000:+.1f} ms')"
      break
    fi
    prev="$line"
    over=$(python3 -c "print(1 if float('$now')-float('$start')>3 else 0)")
    [ "$over" = "1" ] && { echo "sample $n: no tick seen in 3 s"; break; }
  done
done
