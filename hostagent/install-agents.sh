#!/usr/bin/env bash
# install-agents.sh -- install the AK820 Pro host agents as LaunchAgents.
#
#   hostagent/install-agents.sh              install + start
#   hostagent/install-agents.sh --uninstall  stop + remove
#   hostagent/install-agents.sh --status     what is running
#
# Installs TWO agents:
#   timekeeper  -- syncs the board clock every 5 min, on re-enumeration (a
#                  slider flip or replug reboots the board) and on wake, and
#                  measures this Mac's USB SOF bias.
#   nowplaying  -- pushes the current track to the LCD text slot.
#
# ⚠️ It deliberately does NOT install the old `clocksync` agent. The timekeeper
# replaces it, and the raw-HID interface is EXCLUSIVE: two pollers means one of
# them fails every call. That has twice been mistaken for a firmware fault.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/hostagent"
DEST="$HOME/Library/LaunchAgents"
AGENTS=(timekeeper nowplaying)
DOMAIN="gui/$(id -u)"

render() {   # template -> installed plist, with this checkout's paths
  sed -e "s|@AK820_ROOT@|$ROOT|g" -e "s|@HOME@|$HOME|g" "$1" > "$2"
}

# `bootout` returns before teardown finishes, and bootstrapping into a service
# that is still SIGTERMed fails with the unhelpful "Bootstrap failed: 5:
# Input/output error". Wait for it to actually go.
wait_gone() {
  for _ in $(seq 1 40); do
    launchctl print "$DOMAIN/$1" >/dev/null 2>&1 || return 0
    sleep 0.5
  done
  return 1
}

case "${1:---install}" in
--status)
  for a in "${AGENTS[@]}"; do
    label="com.jdlien.ak820pro.$a"
    if line=$(launchctl list | grep -F "$label"); then echo "  running: $line"
    else echo "  not loaded: $label"; fi
  done
  echo
  echo "  logs: ~/Library/Logs/ak820pro-{timekeeper,nowplaying}.log"
  exit 0 ;;
--uninstall)
  for a in "${AGENTS[@]}"; do
    label="com.jdlien.ak820pro.$a"
    launchctl bootout "$DOMAIN/$label" 2>/dev/null && echo "  stopped $label"
    rm -f "$DEST/$label.plist"
  done
  echo "  removed. Logs and ~/.ak820ctl-bias.json are left in place."
  exit 0 ;;
--install|"") ;;
*) echo "usage: $0 [--install|--uninstall|--status]" >&2; exit 2 ;;
esac

# --- preconditions ----------------------------------------------------------
# Both agents shell out to these. Checking here turns a silent do-nothing agent
# into an error at install time.
fail=0
[ -x "$ROOT/venv/bin/python3" ] || { echo "missing: venv -- run ./setup.sh first" >&2; fail=1; }
[ -x "$ROOT/time-util-ak820pro/ak820ctl" ] || { echo "missing: ak820ctl -- run ./setup.sh first" >&2; fail=1; }
"$ROOT/venv/bin/python3" -c "import hid" 2>/dev/null || { echo "missing: python hid module -- run ./setup.sh" >&2; fail=1; }
[ "$fail" = 0 ] || exit 1

mkdir -p "$DEST" "$HOME/Library/Logs"

# One-time migration: the timekeeper used to log to a file named after the agent
# it replaced, which reads as evidence the OLD agent is running.
OLD="$HOME/Library/Logs/ak820pro-clocksync.log"
NEW="$HOME/Library/Logs/ak820pro-timekeeper.log"
if [ -f "$OLD" ]; then
  cat "$OLD" >> "$NEW" && rm -f "$OLD" && echo "  merged the old clocksync log into ak820pro-timekeeper.log"
fi

for a in "${AGENTS[@]}"; do
  label="com.jdlien.ak820pro.$a"
  render "$SRC/$label.plist.in" "$DEST/$label.plist" || { echo "render failed: $a" >&2; exit 1; }
  chmod 644 "$DEST/$label.plist"
  plutil -lint "$DEST/$label.plist" >/dev/null || { echo "generated plist is invalid: $a" >&2; exit 1; }
  launchctl bootout "$DOMAIN/$label" 2>/dev/null
  wait_gone "$label" || echo "  warning: $label was slow to unload"
  if launchctl bootstrap "$DOMAIN" "$DEST/$label.plist" 2>/dev/null; then
    echo "  started $label"
  else
    echo "  FAILED to start $label" >&2; exit 1
  fi
done

echo
echo "  Installed. Check them with:  $0 --status"
echo "  The clock takes a few minutes to converge, and ~15 min before it has"
echo "  measured this Mac's SOF bias -- watch ~/Library/Logs/ak820pro-timekeeper.log."
echo
echo "  ⚠️ Never edit an installed plist with PlistBuddy: it silently strips the"
echo "  XML comments. Edit the .plist.in template and re-run this script."
