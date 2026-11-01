#!/usr/bin/env bash
# ak820keymap.py's restore with macros too big for the firmware's buffer
# (codex's verify of the 10-31 audit's Batch 3): the keymap restored, the
# macros skipped, exit 3. PY picks the interpreter (default: the repo's venv).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
py="${PY:-$here/../../venv/bin/python}"
[ -x "$py" ] || py=python3
"$py" "$here/test.py" < /dev/null
