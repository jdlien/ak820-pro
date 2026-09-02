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
AK820_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-$AK820_ROOT/venv/bin/python}"
PUSH="$(dirname "$0")/ak820text.py"
INTERVAL="${INTERVAL:-3}"     # seconds; 1s is wasteful and can make Spotify sluggish
# Seconds between unconditional re-pushes. Two jobs, and the SHORTER one sets it:
#
#   1. Keep the band alive. The firmware blanks it after DISPLAY_TEXT_TIMEOUT_MS
#      (3 min) so a dead agent or a sleeping machine cannot leave a stale track
#      on screen. Any value well under 3 min does this.
#   2. Correct the firmware's OPTIMISTIC play/pause guess, which is why this is
#      10 and not 60. process_record_kb flips the icon the instant the media key
#      is pressed, then trusts the host to confirm it. When the keypress lands
#      somewhere this script cannot see -- a browser tab, which AppleScript does
#      not expose -- the host state never changes, so the on-change push never
#      fires and the guess stands uncorrected until the next keepalive. At 60 s
#      that is a minute of a backwards icon.
#
# Frequent identical pushes are cheap: display_set_text_line() compares before
# marking the band dirty, so a repeat costs a HID write and no repaint.
KEEPALIVE="${KEEPALIVE:-30}"
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
position_of() {   # $1 = app -> whole seconds
  osascript -e "tell application \"$1\" to player position" 2>/dev/null \
    | awk '{printf "%d", $1 + 0}'
}
duration_of() {   # $1 = app -> whole seconds
  # ⚠️ UNITS DIFFER BY APP: Music reports duration in SECONDS, Spotify in
  # MILLISECONDS. Getting this wrong shows a 3-minute track as 3 seconds (or
  # 50 minutes), which looks like a firmware bug and is not one.
  local d
  d="$(osascript -e "tell application \"$1\" to duration of current track" 2>/dev/null)"
  [ -z "$d" ] && return
  if [ "$1" = "Spotify" ]; then awk -v d="$d" 'BEGIN{printf "%d", d/1000}'
  else                          awk -v d="$d" 'BEGIN{printf "%d", d}'
  fi
}

# One-time Automation probe. Every getter above sends osascript stderr to
# /dev/null, so a TCC denial (errAEEventNotPermitted, -1743) is indistinguishable
# from "nothing is playing" -- the agent runs forever, pushes nothing, and logs
# nothing. Probe once, loudly, then carry on: KeepAlive would just restart us.
probe_automation() {
  local app err
  for app in Spotify Music; do
    err="$(osascript -e "application \"$app\" is running" 2>&1 >/dev/null)"
    case "$err" in
      *-1743*|*"not allowed"*|*"Not authorized"*|*"not authorised"*)
        echo "$(date '+%H:%M:%S') AUTOMATION DENIED for $app: $err"
        echo "  Grant it under System Settings > Privacy & Security > Automation."
        echo "  A LaunchAgent often cannot raise the prompt itself: run"
        echo "  hostagent/nowplaying-macos.sh once from a terminal to trigger it."
        return 1 ;;
    esac
  done
  echo "$(date '+%H:%M:%S') automation ok; polling every ${INTERVAL}s"
}
probe_automation || true

last=""
while true; do
  icon="none"; text=""; who=""; pos=""; dur=""
  for app in Spotify Music; do
    [ "$(running "$app")" = "true" ] || continue
    st="$(state_of "$app")"
    case "$st" in
      playing) icon="play";  text="$(track_of "$app")"; who="$(artist_of "$app")"
               pos="$(position_of "$app")"; dur="$(duration_of "$app")"; break ;;
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
  # Opt-in push log: PUSHLOG=~/some.log to record every push and whether it was
  # a real change or a keepalive. Kept because it is the only way to tell a
  # firmware repaint bug from legitimate churn -- correlate a flash you can see
  # on the panel against what was actually sent. Off by default: a write per
  # push, for a question that is usually not being asked.

  # Playback readout, pushed EVERY poll while playing and separately from the
  # text lines -- re-sending the text would mark the band dirty for nothing.
  # The firmware ticks the timer between pushes, so this only corrects drift
  # and catches seeks; it hands the band back to the clock the moment playback
  # is not "playing".
  if [ "$icon" = "play" ] && [ -n "$dur" ]; then
    "$PY" "$PUSH" --playback 1 "${pos:-0}" "$dur"
    pb_shown=1
  elif [ "${pb_shown:-0}" = "1" ]; then
    "$PY" "$PUSH" --playback 0 0 0
    pb_shown=0
  fi

  cur="$icon|$text|$who"
  if [ "$cur" != "$last" ] || { [ -n "$last" ] && [ $(( $(date +%s) - keepalive_at )) -ge "$KEEPALIVE" ]; }; then
    if [ -n "${PUSHLOG:-}" ]; then
      if [ "$cur" != "$last" ]; then why="CHANGED"; else why="keepalive"; fi
      printf '%s %-9s %s\n' "$(date '+%H:%M:%S')" "$why" "$cur" >> "$PUSHLOG"
    fi
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
      # BOTH lines in ONE invocation. The firmware repaints the band from its
      # ~10 Hz tick, so two separate processes can straddle a tick boundary and
      # produce two full-band clear-and-redraw cycles -- a visible double flash
      # on every track change. One open puts the packets ~1 ms apart.
      if [ -n "$who" ]; then
        "$PY" "$PUSH" "$who" --line1 "$text" --icon "$icon"
      else
        # No artist: title on line 0 rather than a blank first line, and line 1
        # explicitly cleared so a previous artist cannot linger.
        "$PY" "$PUSH" "$text" --line1 "" --icon "$icon"
      fi
    fi
  fi
  sleep "$INTERVAL"
done
