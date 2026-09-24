#!/usr/bin/env bash
# Claude Code hook -> AK820 Pro notification (hostagent/ak820notify.py).
#
#   Stop                           slot-1 GIF (the octopus) + orange breathe,
#                                  full screen until a key is pressed
#   Notification permission_prompt "Permission / <tool>" + yellow blink, same
#
# Reads the hook JSON on stdin; needs jq. Never fails and never blocks Claude
# Code: the send runs in the background, and with no board it does nothing.
# Sends are serialised with flock -- two frames interleaved on the LED channel
# would corrupt each other. Log: ~/.cache/ak820-claude-hook.log
#
# ~/.claude/settings.json (next to any hooks you already have):
#   "Stop":         [{"hooks": [{"type": "command", "async": true,
#                     "command": "/path/to/ak820-pro/hostagent/claude-code/ak820-claude-hook.sh"}]}],
#   "Notification": [{"matcher": "permission_prompt", "hooks": [ ...same... ]}]
HERE=$(cd "$(dirname "$0")" && pwd)
NOTIFY=("$HERE/../../venv/bin/python" "$HERE/../ak820notify.py")
[ -x "${NOTIFY[0]}" ] || NOTIFY=(python3 "$HERE/../ak820notify.py")
LOG=$HOME/.cache/ak820-claude-hook.log

input=$(cat)
ev=$(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null)
proj=$(basename "$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)")
nl=$'\n'

case "$ev" in
  Stop)
    args=(send "Claude" "finished${proj:+$nl$proj}" --page --gif 1 --color orange --effect breathe --dur until)
    ;;
  Notification)
    [ "$(jq -r '.notification_type // empty' <<<"$input")" = permission_prompt ] || exit 0
    msg=$(jq -r '.message // empty' <<<"$input")
    tool=$(sed -nE 's/.*permission to use (.*)$/\1/p' <<<"$msg")   # "...permission to use Bash"
    args=(send "Permission" "${tool:-$msg}${proj:+$nl$proj}" --page --color yellow --effect blink --dur until)
    ;;
  *) exit 0 ;;
esac

mkdir -p "$(dirname "$LOG")"
{
  flock -w 30 9 || exit 0
  echo "$(date '+%F %T') $ev ${args[1]}"
  "${NOTIFY[@]}" "${args[@]}" 2>&1
} 9>"$HOME/.cache/ak820-claude-hook.lock" >>"$LOG" 2>&1 &
disown
exit 0
