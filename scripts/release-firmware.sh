#!/usr/bin/env bash
# Upload this checkout's firmware artifacts to the GitHub Release for a tag.
#
#   scripts/release-firmware.sh v0.1.0
#
# CI (.github/workflows/release.yml) creates the Release from the tag with the
# agent zip. The firmware is built HERE, with the pinned MSYS2 toolchain that
# is not worth reproducing on a runner, and this script puts it on the same
# Release:
#
#   ak820pro-via.bin          the daily build, for the common panel revision
#   ak820pro-via-fpb.bin      the fpb build, for the other one (when built)
#   flash_assets.bin          the LCD asset image (assets-src/current/)
#   via.json                  the VIA definition matching the firmware
#   FIRMWARE.txt              provenance: commit, branch, which artifacts
#   firmware-sha256sums.txt
#
# Provenance rules, every one a refusal rather than a warning:
#   - the firmware clone's HEAD must equal deps.lock's pin, so someone building
#     from the tag gets the same source;
#   - the clone must be clean -- build.sh stamps a dirty tree "-dirty", and a
#     -dirty artifact is never shipped;
#   - the artifact must be a clean build of that HEAD in ak820pro-builds/out/
#     (the newest such: clean builds of one commit hash identically here, which
#     is what makes "newest" safe);
#   - this checkout must be at the tag, or FIRMWARE.txt would lie.
# A missing fpb build is a warning: that panel revision gets nothing this time.
#
# Runs from Git Bash or the MSYS2 shell; needs gh (GitHub CLI) logged in.
set -euo pipefail

die() { echo "release-firmware: $*" >&2; exit 1; }
warn() { echo "release-firmware: WARNING $*" >&2; }

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TAG=${1:-}
[[ -n $TAG ]] || die "usage: $0 <tag>   (e.g. v0.1.0)"
FW=$ROOT/qmk_firmware-ak820pro
OUT=$ROOT/ak820pro-builds/out
command -v gh >/dev/null || die "gh (GitHub CLI) is not on PATH"
[[ -d $FW/.git ]] || die "no firmware clone at $FW -- ./setup.sh first"

# --- provenance -------------------------------------------------------------
head=$(git -C "$FW" rev-parse HEAD)
short=${head:0:8}
pin=$(awk '$1 == "qmk_firmware-ak820pro" { print $4 }' "$ROOT/deps.lock")
[[ $head == "$pin" ]] || die "firmware HEAD $short is not deps.lock's pin ${pin:0:8}; move the pin (and re-verify on hardware) before releasing"
if [[ -n $(git -C "$FW" status --porcelain --untracked-files=no) ]]; then
    git -C "$FW" status --short --untracked-files=no >&2
    die "the firmware clone is dirty; commit or stash before releasing (a -dirty artifact is never shipped)"
fi
at=$(git -C "$ROOT" describe --tags --exact-match 2>/dev/null || true)
[[ $at == "$TAG" ]] || die "this checkout is not at $TAG (git describe says '${at:-no tag}'); check the tag out first"

# newest clean build of HEAD for a flavour, or nothing
pick() { ls -t "$OUT"/via-"$1"-"$short"-2*.bin 2>/dev/null | grep -v -- '-dirty-' | head -1 || true; }
daily=$(pick daily)
fpb=$(pick fpb)
[[ -n $daily ]] || die "no clean daily build of $short in $OUT -- ./build.sh daily first"
[[ -n $fpb ]] || warn "no fpb build of $short in $OUT (./build.sh fpb); the other panel revision gets no binary this release"
assets=$ROOT/assets-src/current/flash_assets.bin
via=$FW/keyboards/a_jazz/ak820pro/via.json
[[ -f $assets ]] || die "missing $assets"
[[ -f $via ]] || die "missing $via"

crc32() {
    local py
    for py in python3 python; do
        command -v "$py" >/dev/null || continue
        "$py" -c 'import sys,zlib;print("%08x" % zlib.crc32(open(sys.argv[1],"rb").read()))' "$1" 2>/dev/null && return 0
    done
    echo '?'
}

# --- stage ------------------------------------------------------------------
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp "$daily" "$stage/ak820pro-via.bin"
[[ -n $fpb ]] && cp "$fpb" "$stage/ak820pro-via-fpb.bin"
cp "$assets" "$stage/flash_assets.bin"
cp "$via" "$stage/via.json"
{
    echo "AK820 Pro firmware artifacts for $TAG"
    echo
    echo "firmware   $head"
    echo "           $(git -C "$FW" log -1 --format='%ci  %s' HEAD)"
    echo "branch     $(git -C "$FW" branch --show-current)  (github.com/jdlien/qmk_firmware)"
    echo "chibios    $(git -C "$FW" rev-parse HEAD:lib/chibios-contrib 2>/dev/null || echo '?')  (lib/chibios-contrib gitlink)"
    echo
    echo "ak820pro-via.bin       <- $(basename "$daily")"
    if [[ -n $fpb ]]; then
        echo "ak820pro-via-fpb.bin   <- $(basename "$fpb")"
    else
        echo "ak820pro-via-fpb.bin   not built for this release"
    fi
    echo "flash_assets.bin       <- assets-src/current/flash_assets.bin  (crc32 $(crc32 "$assets"))"
    echo "via.json               <- keyboards/a_jazz/ak820pro/via.json"
    echo
    echo "Flash: Fn+Esc for the bootloader (0C45:7140), then"
    echo "  sonixflasher --vidpid 0c45/7140 --file ak820pro-via.bin"
    echo "Assets (erases first -- check 'ak820ctl info' answers), then power-cycle:"
    echo "  ak820ctl flash write 0x0CE0000 flash_assets.bin"
    echo "Read README.md, 'Read this before your first flash', before either."
} > "$stage/FIRMWARE.txt"
( cd "$stage" && sha256sum ak820pro-via.bin ${fpb:+ak820pro-via-fpb.bin} flash_assets.bin via.json > firmware-sha256sums.txt )
cat "$stage/FIRMWARE.txt"
echo
cat "$stage/firmware-sha256sums.txt"
echo

# --- upload -----------------------------------------------------------------
# CI creates the Release at the end of its job; wait for it rather than race it.
for _ in $(seq 1 90); do
    gh release view "$TAG" >/dev/null 2>&1 && break
    sleep 10
done
gh release view "$TAG" >/dev/null 2>&1 || die "no Release for $TAG after 15 min -- did the tag push, and did .github/workflows/release.yml run?"
gh release upload "$TAG" "$stage"/* --clobber
echo
echo "release $TAG now carries:"
gh release view "$TAG" --json assets --jq '.assets[] | "  \(.name)\t\(.size) bytes"'
gh release view "$TAG" --json url --jq .url
