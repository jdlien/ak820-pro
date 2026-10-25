#!/usr/bin/env bash
# power_log_agent.sh -- run the bench's power recorder (power_log.py) as a
# LaunchAgent, so it outlives the terminal that started it. A recorder started
# from a cmux shell, even detached (PPID 1, its own session), died when cmux
# restarted at 14:11:47 10-24, and the drain lost 4.9 h of rows. launchd also
# restarts it within 10 s if it exits, and starts it again at login.
#
#   scripts/power_log_agent.sh install [csv]   # stops any other recorder first
#   scripts/power_log_agent.sh status
#   scripts/power_log_agent.sh uninstall       # nothing records after this
#
# csv defaults to history/power-bench-2026-10-15/power.csv; the notes go to
# its .log and the pid to its .pid, as with --detach. The switch leaves a gap
# of a second or two, which the INA228's charge register bridges: it clears
# only when the QT Py loses power. The plist is written here whole: re-run
# install to change it, never edit the installed copy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL=com.jdlien.ak820pro.powerlog
DOMAIN="gui/$(id -u)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

last_row() {   # the CSV's last row and its age in seconds
  local row; row=$(tail -1 "$1")
  echo "last row $(( $(date +%s) - $(cut -d, -f2 <<<"$row" | cut -d. -f1) )) s ago: $row"
}

case "${1:-}" in
install)
  csv="${2:-history/power-bench-2026-10-15/power.csv}"
  case "$csv" in /*) ;; *) csv="$ROOT/$csv" ;; esac
  base="${csv%.csv}"
  mkdir -p "$(dirname "$PLIST")"
  cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <!-- The bench's power recorder (docs/test-bench.md, "The power logger").
         Written by scripts/power_log_agent.sh: re-run its install to change
         this, never edit it in place. -->
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT/venv/bin/python</string>
        <string>$ROOT/scripts/power_log.py</string>
        <string>--out</string>
        <string>$csv</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>

    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$base.log</string>
    <key>StandardErrorPath</key>
    <string>$base.log</string>

    <key>ProcessType</key>
    <string>Standard</string>
</dict>
</plist>
EOF
  plutil -lint "$PLIST" >/dev/null
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  # Any other recorder holds the QT Py's port (one QT Py, one recorder).
  for pid in $(pgrep -f 'power_log\.py' || true); do
    echo "stopping recorder pid $pid: $(ps -p "$pid" -o command= || true)"
    kill "$pid" 2>/dev/null || true
  done
  for _ in $(seq 50); do pgrep -f 'power_log\.py' >/dev/null || break; sleep 0.1; done
  if pgrep -f 'power_log\.py' >/dev/null; then echo "a recorder would not stop" >&2; exit 1; fi
  launchctl enable "$DOMAIN/$LABEL"
  for try in 1 2 3 4 5; do   # bootstrap can fail briefly right after a bootout
    launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null && break
    [ "$try" = 5 ] && { echo "launchctl bootstrap failed" >&2; exit 1; }
    sleep 1
  done
  echo "loaded $LABEL, recording to $csv"
  sleep 5
  last_row "$csv"
  tail -3 "$base.log"
  ;;
status)
  if ! launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E $'^\t(state|pid|last exit code|runs) ='; then
    echo "$LABEL is not loaded"
    exit 1
  fi
  csv=$(plutil -extract ProgramArguments.3 raw "$PLIST")
  last_row "$csv"
  ;;
uninstall)
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null && echo "stopped $LABEL" || echo "$LABEL was not loaded"
  rm -f "$PLIST"
  ;;
*)
  sed -n '2,16p' "$0" | cut -c3-
  exit 2
  ;;
esac
