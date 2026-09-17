#!/usr/bin/env bash
# check-helper-upstream.sh -- has the plugin's MediaRemote helper moved past the
# copy vendored here? Read-only; exits 1 when it has, so it can gate a release.
#
#   scripts/check-helper-upstream.sh [PLUGIN_REPO]   (default ~/code/streamdeck-now-playing)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${1:-$HOME/code/streamdeck-now-playing}"
PIN="$ROOT/ak820-agent/helper/UPSTREAM"
path=$(awk '$1=="path"{print $2}' "$PIN")
commit=$(awk '$1=="commit"{print $2}' "$PIN")
sha=$(awk '$1=="sha256"{print $2}' "$PIN")
now=$(shasum -a 256 "$REPO/$path" | awk '{print $1}')
if [ "$now" = "$sha" ]; then
  echo "helper unchanged upstream since ${commit:0:7}"
  exit 0
fi
echo "helper CHANGED upstream since the vendored ${commit:0:7}:"
git -C "$REPO" log --oneline "$commit"..HEAD -- "$path" || true
echo "re-vendor: copy it, re-apply the one local change (UPSTREAM 'local'), update the pin."
exit 1
