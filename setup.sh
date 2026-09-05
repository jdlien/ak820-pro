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
# Scope: macOS (tested on Tahoe 26.x, Apple Silicon and Intel) and Windows
# (tested on 11 Pro 26200, via the MSYS2 MinGW 64-bit shell). The host agents
# are still macOS-only -- they are LaunchAgents -- but the toolchain, venv,
# pinned clones, flasher and ak820ctl are set up on both.
#
# ⚠️ On Windows, run this from the MSYS2 MinGW 64-bit shell, not Git Bash or
# PowerShell. qmk_cli refuses to run anywhere else, and Git Bash has no make.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOCK="$ROOT/deps.lock"
TC_VER="13.3.1-1.1"
TC_DIR="$ROOT/xpack-arm-none-eabi-gcc-$TC_VER"
FAIL=0

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) PLATFORM=windows ;;
  Darwin)               PLATFORM=macos   ;;
  *)                    PLATFORM=other   ;;
esac

# ⚠️ The venv's NAME is load-bearing on Windows. qmk_cli/script_qmk.py gates the
# entire CLI on `'mingw64' in sys.executable`, so a venv called plain "venv" is
# rejected with "It seems you are not using the MINGW64 terminal" even when it
# is MSYS2's own mingw64 python. env.sh derives the same name; nothing else
# about the venv differs between platforms.
if [ "$PLATFORM" = windows ]; then VENV="$ROOT/venv-mingw64"; else VENV="$ROOT/venv"; fi

log()  { printf '\n=== %s ===\n' "$*"; }
ok()   { printf '  ok: %s\n' "$*"; }
warn() { printf '  WARNING: %s\n' "$*"; }
die()  { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }

[ -f "$LOCK" ] || die "deps.lock not found -- run this from inside the repo."

# --- 0. host prerequisites --------------------------------------------------
log "0/6 prerequisites"
command -v git >/dev/null || die "git not found"

if [ "$PLATFORM" = windows ]; then
  TC_ARCH="win32-x64"; TC_EXT="zip"
  case "${MSYSTEM:-}" in
    MINGW64) : ;;
    *) die "MSYSTEM is '${MSYSTEM:-unset}', not MINGW64.
       Open the 'MSYS2 MinGW 64-bit' shell (not MSYS, not UCRT64, not Git Bash)
       and re-run. qmk_cli hard-fails outside it." ;;
  esac
  # MSYS2 plays Homebrew's part. hidapi is linked by BOTH ak820ctl and the
  # python `hid` package; pkg-config is how ak820ctl's Makefile finds it.
  #
  # The python-* packages are here rather than in pip because they carry
  # compiled extensions with no mingw wheels: rpds-py needs a Rust toolchain
  # and pillow needs zlib headers, so `pip install qmk` fails outright without
  # them. python-hid is the same ctypes pyhidapi the host scripts import.
  PACS="make git diffutils unzip zsh procps-ng vim
        mingw-w64-x86_64-gcc mingw-w64-x86_64-pkg-config mingw-w64-x86_64-hidapi
        mingw-w64-x86_64-python mingw-w64-x86_64-python-pip
        mingw-w64-x86_64-python-hid mingw-w64-x86_64-python-rpds-py
        mingw-w64-x86_64-python-jsonschema mingw-w64-x86_64-python-milc
        mingw-w64-x86_64-python-pillow"
  # shellcheck disable=SC2086
  missing="$(pacman -T $PACS 2>/dev/null || true)"
  if [ -n "$missing" ]; then
    echo "  installing MSYS2 packages: $(echo "$missing" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    pacman -S --needed --noconfirm --disable-download-timeout $PACS >/dev/null \
      || die "pacman install failed"
  fi
  # vim is only here for xxd, which build.sh's structural checks use.
  command -v xxd >/dev/null || die "xxd missing even after installing vim"
else
  [ "$PLATFORM" = macos ] || warn "this script targets macOS or MSYS2; continuing anyway"
  TC_EXT="tar.gz"
  case "$(uname -m)" in
    arm64)  TC_ARCH="darwin-arm64" ;;
    x86_64) TC_ARCH="darwin-x64"   ;;
    *) die "unsupported architecture $(uname -m)" ;;
  esac
  command -v python3 >/dev/null || die "python3 not found"
  if ! command -v brew >/dev/null 2>&1; then
    die "Homebrew not found. Install from https://brew.sh then re-run."
  fi
  # hidapi is linked by BOTH ak820ctl and the python `hid` package; pkg-config is
  # how ak820ctl's Makefile finds it.
  for pkg in hidapi pkg-config; do
    brew list "$pkg" >/dev/null 2>&1 || { echo "  installing $pkg"; brew install "$pkg" || die "brew install $pkg"; }
  done
fi
ok "hidapi $(pkg-config --modversion hidapi 2>/dev/null || echo '?'), $(git --version)"

# --- 1. arm-none-eabi toolchain --------------------------------------------
log "1/6 arm-none-eabi toolchain (xpack $TC_ARCH, no sudo)"
if [ -x "$TC_DIR/bin/arm-none-eabi-gcc" ] || [ -x "$TC_DIR/bin/arm-none-eabi-gcc.exe" ]; then
  ok "already present"
else
  # Same pinned xpack release on both platforms -- and the same directory name,
  # so env.sh needs no branch for it. Only the archive format differs.
  URL="https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/download/v$TC_VER/xpack-arm-none-eabi-gcc-$TC_VER-$TC_ARCH.$TC_EXT"
  curl -fL --retry 3 --progress-bar -o "$ROOT/.tc.$TC_EXT" "$URL" || die "toolchain download"
  case "$TC_EXT" in
    zip)    unzip -q "$ROOT/.tc.zip" -d "$ROOT"      || die "toolchain extract" ;;
    tar.gz) tar xzf "$ROOT/.tc.tar.gz" -C "$ROOT"    || die "toolchain extract" ;;
  esac
  rm -f "$ROOT/.tc.$TC_EXT"
fi
# ⚠️ On Windows the arm toolchain goes LAST. Its win32-x64 bin/ ships copies of
# libgcc_s_seh-1.dll, libstdc++-6.dll and libwinpthread-1.dll; ahead of
# /mingw64/bin they shadow MSYS2's, and the native gcc used for sonixflasher and
# ak820ctl in step 5 then fails SILENTLY -- cc1.exe cannot load, gcc exits
# non-zero printing nothing, and make says only "Error 1". env.sh carries the
# same ordering and the same warning.
if [ "$PLATFORM" = windows ]; then
  export PATH="$PATH:$TC_DIR/bin"
else
  export PATH="$TC_DIR/bin:$PATH"
fi
ok "$("$TC_DIR/bin/arm-none-eabi-gcc" --version | head -1)"

# --- 2. python venv ---------------------------------------------------------
# `qmk` drives the build; `hid` is what the host agents and flash.sh's keymap
# backup import. Both live here so the system python is never touched.
log "2/6 python venv (qmk cli + hid)"
if [ "$PLATFORM" = windows ]; then
  # --system-site-packages so the venv can see the pacman-provided compiled
  # extensions (rpds-py, pillow, hid); without it pip tries to build them from
  # source and fails for want of Rust and zlib. Built from /mingw64's python
  # specifically -- qmk_cli checks sys.executable for "mingw64".
  [ -x "$VENV/bin/python.exe" ] || /mingw64/bin/python -m venv --system-site-packages "$VENV" \
    || die "venv create"
  PIP="$VENV/bin/python -m pip"
else
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV" || die "venv create"
  PIP="$VENV/bin/pip"
fi
$PIP -q install --upgrade pip >/dev/null 2>&1
for mod in qmk hid; do
  case "$mod" in
    qmk) have=$({ [ -x "$VENV/bin/qmk" ] || [ -x "$VENV/bin/qmk.exe" ]; } && echo yes || echo no) ;;
    hid) have=$("$VENV/bin/python" -c "import hid" 2>/dev/null && echo yes || echo no) ;;
  esac
  if [ "$have" = yes ]; then ok "$mod already installed"
  else echo "  installing $mod"; $PIP -q install "$mod" || die "pip install $mod"; fi
done
export PATH="$VENV/bin:$PATH"
ok "qmk $("$VENV/bin/qmk" --version 2>/dev/null || echo '?')"

# --- 2b. Windows only: a SECOND venv, on native python, for the host agents --
# The now-playing agent reads SMTC (Windows' media-session API) through winsdk,
# and winsdk has no mingw wheel -- building it wants MSVC and cmake, so it
# cannot live in venv-mingw64. Native CPython has a prebuilt wheel. Hence two
# venvs: venv-mingw64 builds firmware, venv-win runs the agents.
#
# Not fatal if native python is missing: the firmware build does not need it.
if [ "$PLATFORM" = windows ]; then
  log "2b/6 host-agent venv (native python + winsdk)"
  WINVENV="$ROOT/venv-win"
  find_win_python() {
    if [ -n "${AK820_WIN_PYTHON:-}" ] && [ -x "$AK820_WIN_PYTHON" ]; then
      echo "$AK820_WIN_PYTHON"; return 0
    fi
    # The py.exe launcher is the standard python.org entry point.
    if command -v py >/dev/null 2>&1; then
      p="$(py -3 -c 'import sys; print(sys.executable)' 2>/dev/null | tr -d '\r')"
      [ -n "$p" ] && { cygpath -u "$p" 2>/dev/null || echo "$p"; return 0; }
    fi
    # pyenv-win and the per-user python.org layout, newest last. $LOCALAPPDATA
    # and $USERPROFILE arrive as BACKSLASH paths, which bash treats as escapes
    # and never globs -- convert before using them.
    local_appdata="$(cygpath -u "${LOCALAPPDATA:-}" 2>/dev/null || echo "")"
    userprofile="$(cygpath -u "${USERPROFILE:-$HOME}" 2>/dev/null || echo "$HOME")"
    for p in "$userprofile"/.pyenv/pyenv-win/versions/*/python.exe \
             ${local_appdata:+"$local_appdata"/Programs/Python/Python3*/python.exe}; do
      [ -x "$p" ] && found="$p"
    done
    [ -n "${found:-}" ] && { echo "$found"; return 0; }
    return 1
  }
  if WINPY="$(find_win_python)"; then
    [ -x "$WINVENV/Scripts/python.exe" ] || "$WINPY" -m venv "$WINVENV" \
      || die "venv-win create with $WINPY"
    "$WINVENV/Scripts/python.exe" -m pip -q install --upgrade pip >/dev/null 2>&1
    for mod in winsdk hid; do
      if "$WINVENV/Scripts/python.exe" -c "import $mod" >/dev/null 2>&1; then
        ok "$mod already installed"
      else
        echo "  installing $mod"
        "$WINVENV/Scripts/python.exe" -m pip -q install "$mod" \
          || { warn "pip install $mod failed"; FAIL=1; }
      fi
    done
    # ⚠️ The `hid` package is a ctypes wrapper and needs hidapi.dll at RUNTIME.
    # Python 3.8+ dropped PATH and the exe's directory from ctypes' DLL search,
    # so shipping the DLL is not enough -- the .pth re-adds the directory at
    # interpreter start, which is what makes a bare `import hid` work for every
    # script without any of them having to care. MSYS2's own libhidapi is a
    # mingw build; use libusb's official MSVC one to stay on the right CRT.
    if ! "$WINVENV/Scripts/python.exe" -c "import hid" >/dev/null 2>&1; then
      HIDZIP="$ROOT/.hidapi-win.zip"
      curl -fsSL --retry 3 -o "$HIDZIP" \
        "https://github.com/libusb/hidapi/releases/latest/download/hidapi-win.zip" \
        && unzip -qo "$HIDZIP" -d "$ROOT/.hidapi-win" \
        && cp "$ROOT/.hidapi-win/x64/hidapi.dll" "$WINVENV/Scripts/hidapi.dll"
      rm -rf "$HIDZIP" "$ROOT/.hidapi-win"
      printf '%s\n' \
        'import os, sys; d = os.path.join(sys.prefix, "Scripts"); os.path.isdir(d) and os.add_dll_directory(d)' \
        > "$WINVENV/Lib/site-packages/ak820_hidapi_dll.pth"
    fi
    if "$WINVENV/Scripts/python.exe" -c "import winsdk, hid" >/dev/null 2>&1; then
      ok "venv-win ready ($("$WINVENV/Scripts/python.exe" --version 2>&1))"
    else
      warn "venv-win incomplete -- the host agents will not run"; FAIL=1
    fi
  else
    warn "no native Windows python found; skipping venv-win.
       The host agents (clock sync, now-playing) need it -- winsdk has no mingw
       wheel. Install python.org 3.10+ and re-run, or set AK820_WIN_PYTHON to
       a python.exe. The firmware build does not need this."
  fi
fi

# --- 3. pinned dependency clones -------------------------------------------
# Each clone's HEAD is checked against deps.lock. A mismatch is fatal: an
# unnoticed wrong pin produces a binary that looks right and is not, which is
# precisely the failure class build.sh's structural checks exist to catch.
log "3/6 dependency clones (pinned by deps.lock)"

# ⚠️ Windows line endings, the trap that stops the build before it starts.
#
# Git-for-Windows is commonly configured with core.autocrlf=true, so it checks
# these clones out with CRLF. MSYS2 ships its OWN git with its own HOME
# (/home/$USER, not C:/Users/$USER), so it never sees that setting, has autocrlf
# unset, and therefore reports every checked-out file as modified -- 2,092 of
# them in lib/chibios-contrib alone. build.sh refuses to build against a dirty
# submodule, so on a fresh Windows clone it can never succeed, and the error it
# prints ("working tree is dirty") points nowhere near the cause.
#
# Pin each clone to LF regardless of the user's global config, and renormalize
# a tree that was already checked out wrong -- but ONLY when line endings are
# the sole difference, so real local work is never discarded.
normalize_eol() {
  dir="$1"
  [ "$PLATFORM" = windows ] || return 0
  git -C "$dir" config core.autocrlf false
  git -C "$dir" config core.eol lf
  if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ] \
     && git -C "$dir" diff --ignore-cr-at-eol --quiet 2>/dev/null; then
    git -C "$dir" rm --cached -r -q . >/dev/null 2>&1 || true
    git -C "$dir" reset --hard -q || return 0
    ok "$(basename "$dir"): renormalized CRLF -> LF"
  fi
}

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
  normalize_eol "$dir"
  ok "$name at $sha"
}
while read -r name url branch sha; do
  case "${name:-}" in ''|'#'*) continue ;; esac
  fetch_dep "$name" "$url" "$branch" "$sha"
# `tr -d '\r'`: if deps.lock was checked out CRLF (see .gitattributes), a blank
# line reads as "\r" rather than "", slips past the skip above, and setup.sh
# dies with `fatal: The empty string is not a valid path` while "cloning ".
done < <(tr -d '\r' < "$LOCK")

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
# Same CRLF trap as the clones above, and this is where it actually bites:
# build.sh checks lib/chibios-contrib specifically.
for sub in lib/chibios lib/chibios-contrib lib/printf lib/lufa; do
  [ -d "$QMK_REPO/$sub/.git" ] || [ -f "$QMK_REPO/$sub/.git" ] && normalize_eol "$QMK_REPO/$sub"
done

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
# ⚠️ On macOS, USE_LIBUSB=1 is not optional: a plain build compiles, runs, prints
# the same banner, and fails to flash on Tahoe. See docs/hardware.md.
#
# On Windows it is the opposite -- do NOT set it. The Tahoe bug is macOS-only,
# the Makefile's Windows branch links hidapi + setupapi, and the Sonix
# bootloader enumerates as a plain HID device there. That means no libusb and,
# more to the point, no Zadig/WinUSB driver swap to get into the bootloader.
if [ "$PLATFORM" = windows ]; then SF_FLAGS=""; else SF_FLAGS="USE_LIBUSB=1"; fi

# Keep the build log and show its tail on failure. Swallowing it into
# /dev/null turned every compile error into the same four content-free words.
BUILDLOG="$(mktemp "${TMPDIR:-/tmp}/ak820setup.XXXXXX")"
# shellcheck disable=SC2086
if make -C "$ROOT/SonixFlasherC" $SF_FLAGS sonixflasher >"$BUILDLOG" 2>&1; then
  ok "sonixflasher: $("$ROOT/SonixFlasherC/sonixflasher" --version 2>&1 | head -1)"
else
  warn "sonixflasher build FAILED -- flash.sh will not work"
  sed 's/^/      /' "$BUILDLOG" | tail -12
  FAIL=1
fi
# On Windows, link ak820ctl STATICALLY. A default mingw build depends on
# /mingw64/bin/libhidapi-0.dll and dies with STATUS_DLL_NOT_FOUND (exit
# -1073741515, no message) the moment it runs anywhere MSYS2 is not on PATH --
# which is exactly how a Scheduled Task runs it, so the timekeeper agent would
# fail silently in service. Command-line variables override the Makefile's :=
# assignments, so this needs no change to the pinned clone.
CTL_MAKE_ARGS=""
if [ "$PLATFORM" = windows ]; then
  CTL_MAKE_ARGS="CFLAGS=-O2 -Wall -static"
fi
# shellcheck disable=SC2086
if [ "$PLATFORM" = windows ]; then
  make -C "$ROOT/time-util-ak820pro" \
       CFLAGS="-O2 -Wall -static" \
       HID_LIBS="$(pkg-config --libs --static hidapi) -lsetupapi -lole32 -loleaut32" \
       >"$BUILDLOG" 2>&1
  ctl_rc=$?
else
  make -C "$ROOT/time-util-ak820pro" >"$BUILDLOG" 2>&1
  ctl_rc=$?
fi
if [ "$ctl_rc" = 0 ]; then
  ok "ak820ctl: built$([ "$PLATFORM" = windows ] && echo ' (static)')"
else
  warn "ak820ctl build FAILED -- clock sync and asset provisioning will not work"
  sed 's/^/      /' "$BUILDLOG" | tail -12
  FAIL=1
fi
rm -f "$BUILDLOG"

# --- 6. report --------------------------------------------------------------
log "6/6 result"
if [ "$FAIL" = 0 ]; then
  cat <<EOF
  Ready. Next:

    ./build.sh daily          # or: instrumented (console + test hooks)
    ./flash.sh ak820pro-builds/out/<the printed artifact>

  Read README.md before the first flash -- there is no backup path back to
  stock once it is gone.
EOF
  if [ "$PLATFORM" = windows ]; then
    cat <<'EOF'

  Windows notes:
    - Run build.sh / flash.sh from THIS shell (MSYS2 MinGW 64-bit) only.
    - Host agents (clock sync + now-playing) install as Scheduled Tasks, and
      that installer is PowerShell, not this shell:

        powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1
                                                            [-Status] [-Uninstall]

      Which apps the now-playing agent can see is a property of Windows, not of
      the agent -- ask it:
        venv-win\Scripts\python.exe hostagent\nowplaying-windows.py --probe
EOF
  else
    cat <<'EOF'

  Host agents (clock sync + now-playing on the LCD):

    hostagent/install-agents.sh
EOF
  fi
else
  echo "  Finished WITH FAILURES (above). The firmware may still build."
  exit 1
fi
