#!/usr/bin/env bash
# Claude Code hook -> AK820 Pro (hostagent/ak820notify.py).
#
#   Stop                         slot-1 GIF (the octopus) + orange breathe,
#                                full screen until a key is pressed
#   PermissionRequest (SYNC)     the question on the board -- arrows move,
#                                Space ticks, Enter answers, Esc hands it back:
#                                  - a tool permission: Allow / Deny
#                                  - AskUserQuestion: a choice, or checkboxes
#                                The answer goes back to Claude Code as the
#                                decision. No answer within TIMEOUT
#                                (~/.config/ak820notify.conf, default 300 s):
#                                say nothing, and Claude asks in the terminal.
#   Notification permission_prompt  the question is now in the terminal: a
#                                "Permission / <tool>" page as a reminder
#   UserPromptSubmit, PostToolUse, PostToolUseFailure, PermissionDenied,
#   SessionEnd                   you are back at the computer: abort a question
#                                still waiting on the board, or close the page --
#                                only for events from the SAME session, and for
#                                tool events only the tool that was waiting
#
# Reads the hook JSON on stdin; needs jq. Never fails. Sends are serialised
# with flock -- two frames interleaved on the LED channel corrupt each other.
# Log: ~/.cache/ak820-claude-hook.log
#
# ~/.claude/settings.json (next to any hooks you already have):
#   "Stop":               [{"hooks": [{"type": "command", "async": true, "command": "<this script>"}]}],
#   "Notification":       [{"matcher": "permission_prompt", "hooks": [ ...async, same... ]}],
#   "PermissionRequest":  [{"matcher": "*", "hooks": [{"type": "command", "command": "<this script>",
#                           "timeout": 330, "statusMessage": "AK820: answer on the keyboard"}]}],
#   "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "PermissionDenied",
#   "SessionEnd":         [{"matcher": "*", "hooks": [ ...async, same... ]}]
#
# While the PermissionRequest hook waits, Claude Code does not show a tool
# permission in the terminal (an AskUserQuestion it does show). Esc on the
# board hands it back at once.
HERE=$(cd "$(dirname "$0")" && pwd)
NOTIFY=("$HERE/../../venv/bin/python" "$HERE/../ak820notify.py")
[ -x "${NOTIFY[0]}" ] || NOTIFY=(python3 "$HERE/../ak820notify.py")
LOG=$HOME/.cache/ak820-claude-hook.log
LOCK=$HOME/.cache/ak820-claude-hook.lock
mkdir -p "$(dirname "$LOG")"

input=$(cat)
ev=$(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null)
proj=$(basename "$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)")
sid=$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null)
nl=$'\n'
# Who owns the open page and the waiting question: only the same session may
# close them. Without this, a second Claude Code session (or a parallel tool
# call in this one) finishing a tool aborted every pending question -- you
# pressed Enter on a board that had already stopped listening.
PAGE_OWNER=$HOME/.cache/ak820notify.page.owner   # session_id
ASK_CTX=$HOME/.cache/ak820notify.ask.ctx         # session_id and tool fingerprint
# Fingerprint of a tool call, to recognise the PostToolUse of the very tool
# whose permission was asked (i.e. it was answered in the terminal).
toolkey() { jq -cS '{t: .tool_name, i: .tool_input}' <<<"$input" 2>/dev/null | sha1sum | cut -c1-16; }

log() { echo "$(date '+%F %T') $*" >>"$LOG"; }

bg() {   # background, serialised
  {
    flock -w 30 9 || exit 0
    log "$ev ${*:1:2}"
    "${NOTIFY[@]}" "$@" >>"$LOG" 2>&1
  } 9>"$LOCK" &
  disown
}

case "$ev" in
  Stop)
    echo "$sid" > "$PAGE_OWNER"
    bg send "Claude" "finished${proj:+$nl$proj}" --page --gif 1 --color orange --effect breathe --dur until
    ;;

  Notification)
    [ "$(jq -r '.notification_type // empty' <<<"$input")" = permission_prompt ] || exit 0
    # Cancelled on the board a moment ago: you are right there, skip the reminder.
    c=$HOME/.cache/ak820notify.cancelled
    if [ -e "$c" ] && [ $(( $(date +%s) - $(stat -c %Y "$c") )) -lt 15 ]; then rm -f "$c"; exit 0; fi
    msg=$(jq -r '.message // empty' <<<"$input")
    tool=$(sed -nE 's/.*permission to use (.*)$/\1/p' <<<"$msg")   # "...permission to use Bash"
    echo "$sid" > "$PAGE_OWNER"
    bg send "Permission" "${tool:-$msg}${proj:+$nl$proj}" --page --color yellow --effect blink --dur until
    ;;

  UserPromptSubmit|PostToolUse|PostToolUseFailure|PermissionDenied|SessionEnd)
    # A question still waiting on the board but answered here: abort it (it
    # closes its own page and releases the lock).
    # Same session only; for tool events, only the tool that was waiting.
    pidf=$HOME/.cache/ak820notify.ask.pid
    if [ -s "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
      read -r asid akey 2>/dev/null <"$ASK_CTX"
      [ "$sid" = "$asid" ] || exit 0
      case "$ev" in
        PostToolUse|PostToolUseFailure|PermissionDenied) [ "$(toolkey)" = "$akey" ] || exit 0 ;;
      esac
      kill -TERM "$(cat "$pidf")" 2>/dev/null; log "$ev aborts the question"; exit 0
    fi
    [ -e "$HOME/.cache/ak820notify.page" ] || exit 0   # nothing open: no traffic
    [ "$sid" = "$(cat "$PAGE_OWNER" 2>/dev/null)" ] || exit 0   # another session's page
    bg close --if-open
    ;;

  PermissionRequest)
    tool=$(jq -r '.tool_name // empty' <<<"$input")
    if [ "$tool" = AskUserQuestion ]; then
      # One question at a time; several go to the terminal.
      [ "$(jq '.tool_input.questions | length' <<<"$input")" = 1 ] || exit 0
      title=$(jq -r '.tool_input.questions[0].header // "Choose"' <<<"$input")
      opts=$(jq -r '[.tool_input.questions[0].options[].label] | join("|")' <<<"$input")
      args=(ask "$title" --options "$opts" --color cyan --effect breathe)
      [ "$(jq -r '.tool_input.questions[0].multiSelect // false' <<<"$input")" = true ] && args+=(--multi)
    else
      case "$tool" in
        Bash) detail=$(jq -r '.tool_input.command // empty' <<<"$input") ;;
        Edit|Write|Read|NotebookEdit) detail=$(basename "$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")") ;;
        WebFetch) detail=$(jq -r '.tool_input.url // empty' <<<"$input" | sed -E 's#^https?://##') ;;
        *) detail="" ;;
      esac
      detail=${detail//$'\n'/ }
      args=(ask "Permission" "$tool" "${detail:0:12}" --permission --color yellow --effect blink)
    fi
    echo "$sid $(toolkey)" > "$ASK_CTX"
    # Synchronous: Claude Code waits for the decision. The lock is held for
    # the whole wait so nothing else interleaves on the LEDs.
    ans=$( { flock -w 30 9 || exit 0; "${NOTIFY[@]}" "${args[@]}" 2>>"$LOG"; } 9>"$LOCK" )
    log "PermissionRequest $tool -> ${ans:-error}"
    [ "$ans" = cancel ] && touch "$HOME/.cache/ak820notify.cancelled"
    case "$ans" in
      allow)
        jq -cn '{hookSpecificOutput:{hookEventName:"PermissionRequest",decision:{behavior:"allow"}}}' ;;
      deny)
        jq -cn '{hookSpecificOutput:{hookEventName:"PermissionRequest",decision:{behavior:"deny",message:"Denied on the keyboard"}}}' ;;
      choice:*)
        i=$(( ${ans#choice:} - 1 ))
        jq -c --argjson i "$i" '{hookSpecificOutput:{hookEventName:"PermissionRequest",decision:{behavior:"allow",
          updatedInput:(.tool_input + {answers:{(.tool_input.questions[0].question):(.tool_input.questions[0].options[$i].label)}})}}}' <<<"$input" ;;
      multi:*)
        jq -c --arg sel "${ans#multi:}" '($sel | split(",") | map(select(. != "") | tonumber - 1)) as $ix
          | {hookSpecificOutput:{hookEventName:"PermissionRequest",decision:{behavior:"allow",
             updatedInput:(.tool_input + {answers:{(.tool_input.questions[0].question):
               ([$ix[] as $i | .tool_input.questions[0].options[$i].label] | join(", "))}})}}}' <<<"$input" ;;
    esac
    ;;
esac
exit 0
