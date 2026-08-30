#!/bin/bash
# Poll macOS media state and push it to the AK820 Pro LCD.
#
# Uses AppleScript against Spotify/Music rather than the private MediaRemote
# framework: MediaRemote would also catch browser media (YouTube), but Apple has
# progressively restricted it and third-party wrappers break between OS
# versions. AppleScript is app-specific but stable.
#
# On Windows the equivalent is GlobalSystemMediaTransportControlsSessionManager,
# which is a public API AND covers browsers -- see CLAUDE.md.
set -u
PY="${PY:-/Users/jdlien/code/ak820-pro/venv/bin/python}"
PUSH="$(dirname "$0")/ak820text.py"
INTERVAL="${INTERVAL:-3}"     # seconds; 1s is wasteful and can make Spotify sluggish

running() { osascript -e "application \"$1\" is running" 2>/dev/null; }

state_of() {   # $1 = app -> "playing|paused|stopped"
  osascript -e "tell application \"$1\" to player state as string" 2>/dev/null
}
track_of() {
  osascript -e "tell application \"$1\" to name of current track" 2>/dev/null
}

last=""
while true; do
  icon="none"; text=""
  for app in Spotify Music; do
    [ "$(running "$app")" = "true" ] || continue
    st="$(state_of "$app")"
    case "$st" in
      playing) icon="play";  text="$(track_of "$app")"; break ;;
      paused)  icon="pause"; text="$(track_of "$app")"; break ;;
    esac
  done

  # Only push on change: every write is a raw-HID round trip and a panel redraw.
  cur="$icon|$text"
  if [ "$cur" != "$last" ]; then
    last="$cur"
    if [ -z "$text" ] && [ "$icon" = "none" ]; then
      "$PY" "$PUSH" --clear
    else
      "$PY" "$PUSH" "$text" --icon "$icon"
    fi
  fi
  sleep "$INTERVAL"
done
