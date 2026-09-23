#!/usr/bin/env bash
# symbolize.sh -- turn a fault PC the board reported into a function and line.
#
#   scripts/symbolize.sh <pc> <build-token>
#
# Both come from `ak820 health --crash`: the watchdog record's `pc` and page 6's
# `build_token`. The token is read AFTER the reset, from the same firmware that
# faulted -- a reflash in between is a non-watchdog reset, which discards the
# record -- so it always names the right build.
#
# The token is looked up in the manifests build.sh writes beside each artifact
# (ak820pro-builds/out/*.json). Exactly one must match: an ambiguous or missing
# match refuses rather than symbolizing against the wrong ELF, whose answer
# would look just as plausible.
set -euo pipefail

[ $# -eq 2 ] || { echo "usage: $0 <pc> <build-token>" >&2; exit 2; }
pc="$1"; token="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/ak820pro-builds/out"
source "$ROOT/env.sh" >/dev/null

case "$pc" in
  0xffffffff|0xFFFFFFFF) echo "pc 0xffffffff: the fault's stack frame was unreadable -- itself evidence of stack corruption" >&2; exit 1 ;;
  0|0x0|0x00000000) echo "pc 0: not recoverable for this record kind (an unhandled vector)" >&2; exit 1 ;;
esac
[ "$token" != "0x00000000" ] && [ "$token" != "0" ] || { echo "token 0: an unarchived build (not from build.sh); no ELF to use" >&2; exit 1; }

matches=$(python3 - "$OUT" "$token" <<'PY'
import glob, json, os, sys
out, token = sys.argv[1], int(sys.argv[2], 0)
for m in sorted(glob.glob(os.path.join(out, "*.json"))):
    try:
        d = json.load(open(m))
    except (OSError, ValueError):
        continue
    if int(str(d.get("token", "0")), 0) == token:
        print(os.path.join(out, d["elf"]))
PY
)
n=$(printf '%s' "$matches" | grep -c . || true)
[ "$n" -eq 1 ] || { echo "token $token matches $n archived builds -- refusing to guess" >&2; exit 1; }
[ -f "$matches" ] || { echo "manifest names $matches, which is missing" >&2; exit 1; }

echo "$(basename "$matches"):"
arm-none-eabi-addr2line -f -C -i -p -e "$matches" "$pc"
