#!/bin/zsh
# Timestamped qmk console capture -- the diagnostic that cracked the blit-
# timeout crawl. A gap FOLLOWED BY MORE OUTPUT is a stall; a gap with nothing
# after it is a real death. Appends to ~/Library/Logs/ak820pro-console.log.
#
# Needs the INSTRUMENTED build flavor -- the daily build has no console.
set -euo pipefail

# qmk console claims the interface EXCLUSIVELY; a second instance spins in a
# tight retry loop against the macOS HID subsystem and degrades the whole
# host (2026-08-30: 2,736 log lines of "exclusive access and device already
# open"). Refuse to start a second one.
if pgrep -f "qmk console" >/dev/null; then
  echo "ERROR: a qmk console is already running:" >&2
  pgrep -fl "qmk console" >&2
  exit 1
fi

WORK="$(cd "$(dirname "$0")/.." && pwd)"
source "$WORK/env.sh"
LOG="$HOME/Library/Logs/ak820pro-console.log"

echo "logging to $LOG (ctrl-C to stop)"
qmk console 2>&1 | while IFS= read -r l; do
  printf "%s %s\n" "$(date +%H:%M:%S)" "$l"
done >> "$LOG"
