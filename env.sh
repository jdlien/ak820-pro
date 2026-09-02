# AK820 Pro build environment.  Usage:  source env.sh
#
# Everything lives inside this repo: the dependency clones (pinned by
# deps.lock, created by setup.sh), the toolchain, and the venv. Nothing here
# depends on where the repo itself is checked out.
AK820_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]:-$0}" )" && pwd )"
export AK820_ROOT
export QMK_HOME="$AK820_ROOT/qmk_firmware-ak820pro"

# Homebrew's prefix differs by architecture (/opt/homebrew on Apple Silicon,
# /usr/local on Intel); ask brew rather than guessing.
_ak820_brew="$(command -v brew >/dev/null 2>&1 && brew --prefix 2>/dev/null || echo /opt/homebrew)"
export PATH="$AK820_ROOT/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin:$AK820_ROOT/venv/bin:$_ak820_brew/bin:$PATH"
unset _ak820_brew

# Prefer ./build.sh over a bare `qmk compile`: it enforces the submodule pin,
# checks the binary structurally, and writes a provenance-named artifact
# instead of the shared output path that whoever compiles last owns.
#   ./build.sh daily
#   ./flash.sh ak820pro-builds/out/<artifact>
#   ./time-util-ak820pro/ak820ctl clock       # LCD clock + flash provisioning
