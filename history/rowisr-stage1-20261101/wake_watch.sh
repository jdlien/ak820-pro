#!/bin/bash
# After the detector flash (11-02 16:42): wait on the power logger for white
# to deep-sleep on its own (Power saver, the current under 6 mA for three
# samples), then for JD's key to wake it (over 12 mA for two), then run
# wake_read.sh at once with its own label, so the spurious count across one
# wake stands alone after silence_check.sh's counter reset. Hands-free: the
# logger samples once a second (power.csv, field 6 = mA; asleep about 3.3).
set -u
cd "$(dirname "$0")/../.." || exit 1
CSV=history/power-bench-2026-10-15/power.csv
D=history/rowisr-stage1-20261101
LABEL=${1:-wake-detector-read}
state=awake; n=0
tail -n 0 -F "$CSV" 2>/dev/null | while IFS=, read -r t ep qt vb vs ma rest; do
    case $state in
        awake)
            if awk "BEGIN{exit !($ma < 6)}"; then n=$((n + 1)); else n=0; fi
            if [ "$n" -ge 3 ]; then echo "asleep at ${t#* }: $ma mA"; state=asleep; n=0; fi ;;
        asleep)
            if awk "BEGIN{exit !($ma > 12)}"; then n=$((n + 1)); else n=0; fi
            if [ "$n" -ge 2 ]; then echo "awake at ${t#* }: $ma mA; wake_read.sh starts"; break; fi ;;
    esac
done
"$D/wake_read.sh" "$LABEL" > "$D/$LABEL.log" 2>&1
grep -E '^\[' "$D/$LABEL.log" | cut -c1-400
echo "wake_read.sh done: $D/$LABEL.log"
