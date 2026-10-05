#!/usr/bin/env bash
# One before/after reading for the verification protocol
# (plans/BATTERY-GAUGE-REFINE-PLAN.md): the health counters with the protocol-8
# pages (stalls, transport, flash writers, per-task accounting), the vitals and
# watchdog record, and the battery state, stamped and labelled.
#
#   scripts/board_snapshot.sh <dir> <label>
#
# Writes <dir>/<YYYYmmdd-HHMMSS>-<label>-{health,vitals}.json and -battery.txt.
# Three raw-HID reads; fails loudly if any does.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dir="$1"; label="$2"
mkdir -p "$dir"
stamp=$(date +%Y%m%d-%H%M%S)
py="$here/venv/bin/python3"
"$py" "$here/hostagent/ak820health.py" --stalls --json > "$dir/$stamp-$label-health.json"
"$here/ak820-agent/target/release/ak820" health --crash --json > "$dir/$stamp-$label-vitals.json"
"$py" "$here/hostagent/ak820battery.py" > "$dir/$stamp-$label-battery.txt"
echo "$dir/$stamp-$label-{health,vitals}.json, -battery.txt"
