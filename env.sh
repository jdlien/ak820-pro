# AK820 Pro build env (Gizmo / macOS Tahoe, Apple Silicon).
# Usage:  source env.sh
# Note: everything lives in this repo, NOT ~/ak820pro as the handoff script assumes.
AK820_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]:-$0}" )" && pwd )"
export AK820_ROOT
export QMK_HOME="$AK820_ROOT/qmk_firmware-ak820pro"
export PATH="$AK820_ROOT/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin:$AK820_ROOT/venv/bin:/opt/homebrew/bin:$PATH"

# Rebuild firmware:  qmk compile -kb a_jazz/ak820pro -km via
# Flash (bootloader must be up, 0C45:7140):
#   "$AK820_ROOT/SonixFlasherC/sonixflasher" --vidpid 0c45/7140 \
#       --file "$QMK_HOME/a_jazz_ak820pro_via.bin"
# LCD/clock tool: "$AK820_ROOT/time-util-ak820pro/ak820ctl"
