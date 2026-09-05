# AK820 Pro build environment.  Usage:  source env.sh
#
# Everything lives inside this repo: the dependency clones (pinned by
# deps.lock, created by setup.sh), the toolchain, and the venv. Nothing here
# depends on where the repo itself is checked out.
AK820_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]:-$0}" )" && pwd )"
export AK820_ROOT
export QMK_HOME="$AK820_ROOT/qmk_firmware-ak820pro"

# The venv's directory name is platform-specific, so everything downstream asks
# for $AK820_VENV rather than hardcoding "venv".
#
# ⚠️ On Windows that name MUST contain "mingw64". qmk_cli/script_qmk.py gates
# the whole CLI on `'mingw64' in sys.executable and 'MINGW64' in MSYSTEM`, so a
# venv at .../venv/bin/python.exe is rejected with "It seems you are not using
# the MINGW64 terminal" even though it IS MSYS2's own mingw64 python. Renaming
# the directory is the entire fix; nothing else about the venv differs.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) AK820_VENV="$AK820_ROOT/venv-mingw64" ;;
  *)                    AK820_VENV="$AK820_ROOT/venv" ;;
esac
export AK820_VENV

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # MSYS2 plays the part Homebrew plays on macOS: make, gcc (for sonixflasher
    # and ak820ctl), pkg-config and hidapi all come from /mingw64. There is no
    # brew to ask, and the arm toolchain is the same pinned xpack release --
    # the win32-x64 zip rather than the darwin tarball, same directory name.
    #
    # ⚠️ The arm toolchain goes LAST, not first as it does on macOS. The
    # win32-x64 xpack build ships its own copies of libgcc_s_seh-1.dll,
    # libstdc++-6.dll, libwinpthread-1.dll and libzstd.dll in the same bin/ as
    # the compilers. Ahead of /mingw64/bin those shadow MSYS2's, and the NATIVE
    # gcc's cc1.exe then dies loading them -- exiting non-zero while printing
    # absolutely nothing, so `make` reports a bare "Error 1". That silently
    # breaks the sonixflasher and ak820ctl builds while the firmware build,
    # which wants those DLLs, keeps working. Order is the whole fix: the
    # arm-none-eabi-* names are unique so nothing shadows them from the back,
    # and Windows loads a program's DLLs from its own directory first, so the
    # cross-compiler still finds the copies it needs.
    export PATH="$AK820_VENV/bin:/mingw64/bin:$PATH:$AK820_ROOT/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin"
    ;;
  *)
    # Homebrew's prefix differs by architecture (/opt/homebrew on Apple Silicon,
    # /usr/local on Intel); ask brew rather than guessing.
    _ak820_brew="$(command -v brew >/dev/null 2>&1 && brew --prefix 2>/dev/null || echo /opt/homebrew)"
    export PATH="$AK820_ROOT/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin:$AK820_VENV/bin:$_ak820_brew/bin:$PATH"
    unset _ak820_brew
    ;;
esac

# Prefer ./build.sh over a bare `qmk compile`: it enforces the submodule pin,
# checks the binary structurally, and writes a provenance-named artifact
# instead of the shared output path that whoever compiles last owns.
#   ./build.sh daily
#   ./flash.sh ak820pro-builds/out/<artifact>
#   ./time-util-ak820pro/ak820ctl clock       # LCD clock + flash provisioning
