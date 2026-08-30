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

# --- singleton guard -------------------------------------------------------
# The raw HID interface is EXCLUSIVE: a second poller cannot open it and every
# push fails with "exclusive access and device already open". This has bitten
# twice, and the second time it masqueraded as a FIRMWARE fault -- a stale
# manual run left over from a debugging session was stealing the interface, and
# the keyboard looked broken until the process list was checked.
#
# mkdir is atomic on every filesystem we care about, so it is the lock. A stale
# directory (killed -9, reboot) is detected by probing the recorded pid rather
# than by age, which has no false positives.
LOCK="${TMPDIR:-/tmp}/ak820pro-nowplaying.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  old=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "$(date '+%H:%M:%S') another poller is live as pid $old -- exiting"
    exit 0
  fi
  echo "$(date '+%H:%M:%S') clearing stale lock (pid ${old:-unknown} is gone)"
  rm -rf "$LOCK"; mkdir "$LOCK" || exit 1
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT INT TERM
# ---------------------------------------------------------------------------

set -u
PY="${PY:-/Users/jdlien/code/ak820-pro/venv/bin/python}"
PUSH="$(dirname "$0")/ak820text.py"
INTERVAL="${INTERVAL:-3}"     # seconds; 1s is wasteful and can make Spotify sluggish
KEEPALIVE="${KEEPALIVE:-60}"  # seconds; must stay well under the firmware's 3 min expiry
keepalive_at=0

running() { osascript -e "application \"$1\" is running" 2>/dev/null; }

state_of() {   # $1 = app -> "playing|paused|stopped"
  osascript -e "tell application \"$1\" to player state as string" 2>/dev/null
}
track_of() {
  osascript -e "tell application \"$1\" to name of current track" 2>/dev/null
}
artist_of() {
  osascript -e "tell application \"$1\" to artist of current track" 2>/dev/null
}

last=""
while true; do
  icon="none"; text=""; who=""
  for app in Spotify Music; do
    [ "$(running "$app")" = "true" ] || continue
    st="$(state_of "$app")"
    case "$st" in
      playing) icon="play";  text="$(track_of "$app")"; who="$(artist_of "$app")"; break ;;
      paused)  icon="pause"; text="$(track_of "$app")"; who="$(artist_of "$app")"; break ;;
    esac
  done

  # Push on change, plus a periodic KEEPALIVE.
  #
  # The firmware expires the text band after DISPLAY_TEXT_TIMEOUT_MS (3 min) so a
  # dead agent, a sleeping machine or an unplugged board leaves a blank slot
  # rather than a stale track. Pushing only on change therefore blanked the panel
  # part-way through any track longer than 3 minutes, and it came back at the next
  # track. Re-push well inside that window so the slot stays alive without losing
  # the staleness guarantee.
  cur="$icon|$text|$who"
  if [ "$cur" != "$last" ] || { [ -n "$last" ] && [ $(( $(date +%s) - keepalive_at )) -ge "$KEEPALIVE" ]; }; then
    keepalive_at=$(date +%s)
    last="$cur"
    if [ -z "$text" ] && [ "$icon" = "none" ]; then
      "$PY" "$PUSH" --clear
    else
      # Line 0 sits beside the transport icon and loses ~2 characters to it;
      # line 1 runs the full width. ARTIST goes on line 0 because it is the less
      # valuable of the two and can afford the loss -- the title gets the full
      # width on line 1.
      #
      # Two packets: a second line does not fit in one report (32 bytes leaves
      # ~26 for ASCII after framing). A torn update is harmless -- the lines are
      # independently meaningful and the poll interval is 3 s.
      if [ -n "$who" ]; then
        "$PY" "$PUSH" "$who"  --icon "$icon" --line 0
        "$PY" "$PUSH" "$text" --icon "$icon" --line 1
      else
        # No artist: put the title on line 0 rather than leaving a blank first
        # line, and clear line 1 so a previous artist cannot linger.
        "$PY" "$PUSH" "$text" --icon "$icon" --line 0
        "$PY" "$PUSH" ""      --icon "$icon" --line 1
      fi
    fi
  fi
  sleep "$INTERVAL"
done
