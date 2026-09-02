#!/usr/bin/env bash
# setup.sh -- bring a fresh clone to the point where ./build.sh works.
#
#   git clone https://github.com/jdlien/ak820-pro && cd ak820-pro
#   ./setup.sh
#   ./build.sh daily
#   ./flash.sh ak820pro-builds/out/<the printed artifact>
#
# Idempotent: safe to re-run, and re-running is how you move to a new pin after
# editing deps.lock. Everything it creates is gitignored and disposable except
# the dependency clones' own git history.
#
# Scope: macOS (tested on Tahoe 26.x, Apple Silicon and Intel). The firmware
# builds anywhere QMK does, but the flasher trap (USE_LIBUSB=1), the host agents
# and the toolchain download below are all macOS-specific.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOCK="$ROOT/deps.lock"
TC_VER="13.3.1-1.1"
TC_DIR="$ROOT/xpack-arm-none-eabi-gcc-$TC_VER"
VENV="$ROOT/venv"
FAIL=0

log()  { printf '\n=== %s ===\n' "$*"; }
ok()   { printf '  ok: %s\n' "$*"; }
warn() { printf '  WARNING: %s\n' "$*"; }
die()  { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }

[ -f "$LOCK" ] || die "deps.lock not found -- run this from inside the repo."

# --- 0. host prerequisites --------------------------------------------------
log "0/6 prerequisites"
[ "$(uname -s)" = "Darwin" ] || warn "this script targets macOS; continuing anyway"
case "$(uname -m)" in
  arm64)  TC_ARCH="darwin-arm64" ;;
  x86_64) TC_ARCH="darwin-x64"   ;;
  *) die "unsupported architecture $(uname -m)" ;;
esac
command -v git >/dev/null || die "git not found"
command -v python3 >/dev/null || die "python3 not found"
if ! command -v brew >/dev/null 2>&1; then
  die "Homebrew not found. Install from https://brew.sh then re-run."
fi
# hidapi is linked by BOTH ak820ctl and the python `hid` package; pkg-config is
# how ak820ctl's Makefile finds it.
for pkg in hidapi pkg-config; do
  brew list "$pkg" >/dev/null 2>&1 || { echo "  installing $pkg"; brew install "$pkg" || die "brew install $pkg"; }
done
ok "hidapi $(pkg-config --modversion hidapi 2>/dev/null || echo '?'), $(git --version)"

# --- 1. arm-none-eabi toolchain --------------------------------------------
log "1/6 arm-none-eabi toolchain (xpack $TC_ARCH, no sudo)"
if [ -x "$TC_DIR/bin/arm-none-eabi-gcc" ]; then
  ok "already present"
else
  URL="https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/download/v$TC_VER/xpack-arm-none-eabi-gcc-$TC_VER-$TC_ARCH.tar.gz"
  curl -fL --retry 3 --progress-bar -o "$ROOT/.tc.tar.gz" "$URL" || die "toolchain download"
  tar xzf "$ROOT/.tc.tar.gz" -C "$ROOT" || die "toolchain extract"
  rm -f "$ROOT/.tc.tar.gz"
fi
export PATH="$TC_DIR/bin:$PATH"
ok "$("$TC_DIR/bin/arm-none-eabi-gcc" --version | head -1)"

# --- 2. python venv ---------------------------------------------------------
# `qmk` drives the build; `hid` is what the host agents and flash.sh's keymap
# backup import. Both live here so the system python is never touched.
log "2/6 python venv (qmk cli + hid)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV" || die "venv create"
"$VENV/bin/pip" -q install --upgrade pip >/dev/null 2>&1
for mod in qmk hid; do
  case "$mod" in
    qmk) have=$([ -x "$VENV/bin/qmk" ] && echo yes || echo no) ;;
    hid) have=$("$VENV/bin/python" -c "import hid" 2>/dev/null && echo yes || echo no) ;;
  esac
  if [ "$have" = yes ]; then ok "$mod already installed"
  else echo "  installing $mod"; "$VENV/bin/pip" -q install "$mod" || die "pip install $mod"; fi
done
export PATH="$VENV/bin:$PATH"
ok "qmk $("$VENV/bin/qmk" --version 2>/dev/null || echo '?')"

# --- 3. pinned dependency clones -------------------------------------------
# Each clone's HEAD is checked against deps.lock. A mismatch is fatal: an
# unnoticed wrong pin produces a binary that looks right and is not, which is
# precisely the failure class build.sh's structural checks exist to catch.
log "3/6 dependency clones (pinned by deps.lock)"
fetch_dep() {
  local name="$1" url="$2" branch="$3" sha="$4" dir="$ROOT/$1"
  if [ -d "$dir/.git" ]; then
    if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]; then
      warn "$name has uncommitted changes -- leaving it alone (expected HEAD $sha)"
      return 0
    fi
    [ "$(git -C "$dir" rev-parse HEAD)" = "$sha" ] && { ok "$name at $sha"; return 0; }
    echo "  $name: moving to pinned $sha"
    git -C "$dir" fetch --quiet origin "$branch" 2>/dev/null
    git -C "$dir" fetch --quiet origin "$sha"    2>/dev/null
  else
    echo "  cloning $name"
    git clone --quiet --branch "$branch" --single-branch --depth 1 "$url" "$dir" \
      || die "clone $name"
    # The pin is usually the branch tip, so the shallow clone already has it.
    # If the branch has moved on, ask for the exact commit, then give up on
    # being shallow rather than give up on being correct.
    if [ "$(git -C "$dir" rev-parse HEAD)" != "$sha" ]; then
      git -C "$dir" fetch --quiet --depth 1 origin "$sha" 2>/dev/null \
        || git -C "$dir" fetch --quiet --unshallow origin 2>/dev/null
    fi
  fi
  git -C "$dir" checkout --quiet --detach "$sha" 2>/dev/null \
    || die "$name: cannot check out pinned $sha (is deps.lock right?)"
  [ "$(git -C "$dir" rev-parse HEAD)" = "$sha" ] || die "$name: HEAD != $sha after checkout"
  ok "$name at $sha"
}
while read -r name url branch sha; do
  case "${name:-}" in ''|'#'*) continue ;; esac
  fetch_dep "$name" "$url" "$branch" "$sha"
done < "$LOCK"

QMK_REPO="$ROOT/qmk_firmware-ak820pro"
[ -d "$QMK_REPO/.git" ] || die "deps.lock did not provide qmk_firmware-ak820pro"

# --- 4. firmware submodules -------------------------------------------------
# Driven with git rather than `make git-submodule`, which shells out to the qmk
# CLI and so cannot run before step 2 -- a bootstrap ordering trap the old
# setup script fell into.
#
# Only what the SN32 ARM build needs. lufa is NOT just AVR: the ChibiOS USB
# stack includes LUFA's descriptor headers through tmk_core/protocol/chibios/
# lufa_utils, so omitting it fails at ak820pro.c with a missing
# HIDClassCommon.h. vusb, pico-sdk, lvgl and googletest genuinely are unused
# here; initializing them costs hundreds of MB for nothing.
#
# NOT shallow: lib/chibios-contrib must land on the pinned commit that carries
# the seven ChibiOS patches, and a depth-1 fetch of a branch tip may not contain
# it. See keyboards/a_jazz/ak820pro/PATCHES.md.
log "4/6 firmware submodules (chibios, chibios-contrib, printf, lufa)"
git -C "$QMK_REPO" submodule sync --quiet lib/chibios lib/chibios-contrib lib/printf lib/lufa 2>/dev/null
git -C "$QMK_REPO" submodule update --init lib/chibios lib/chibios-contrib lib/printf lib/lufa \
  || die "submodule init"
gitlink=$(git -C "$QMK_REPO" ls-tree HEAD lib/chibios-contrib | awk '{print $3}')
subhead=$(git -C "$QMK_REPO/lib/chibios-contrib" rev-parse HEAD 2>/dev/null || echo none)
[ "$gitlink" = "$subhead" ] || die "lib/chibios-contrib at $subhead, gitlink wants $gitlink"
# Leave it on the named branch rather than the detached HEAD `submodule update`
# produces: docs/hardware.md tells you the tree must stay on ak820pro-patches,
# and a detached HEAD makes a later `git checkout` there look like a change.
git -C "$QMK_REPO/lib/chibios-contrib" branch -f ak820pro-patches "$subhead" 2>/dev/null
git -C "$QMK_REPO/lib/chibios-contrib" checkout --quiet ak820pro-patches 2>/dev/null
ok "chibios-contrib at $subhead (matches gitlink)"

# --- 5. host tools ----------------------------------------------------------
log "5/6 host tools"
# ⚠️ USE_LIBUSB=1 is not optional: a plain build compiles, runs, prints the same
# banner, and fails to flash on Tahoe. See docs/hardware.md.
if make -C "$ROOT/SonixFlasherC" USE_LIBUSB=1 sonixflasher >/dev/null 2>&1; then
  ok "sonixflasher: $("$ROOT/SonixFlasherC/sonixflasher" --version 2>&1 | head -1)"
else
  warn "sonixflasher build FAILED -- flash.sh will not work"; FAIL=1
fi
if make -C "$ROOT/time-util-ak820pro" >/dev/null 2>&1; then
  ok "ak820ctl: built"
else
  warn "ak820ctl build FAILED -- clock sync and asset provisioning will not work"; FAIL=1
fi

# --- 6. report --------------------------------------------------------------
log "6/6 result"
if [ "$FAIL" = 0 ]; then
  cat <<EOF
  Ready. Next:

    ./build.sh daily          # or: instrumented (console + test hooks)
    ./flash.sh ak820pro-builds/out/<the printed artifact>

  Host agents (clock sync + now-playing on the LCD):

    hostagent/install-agents.sh

  Read README.md before the first flash -- there is no backup path back to
  stock once it is gone.
EOF
else
  echo "  Finished WITH FAILURES (above). The firmware may still build."
  exit 1
fi
