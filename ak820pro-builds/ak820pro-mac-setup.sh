#!/usr/bin/env bash
# AK820 Pro — full macOS setup: QMK build env + firmware + host tools.
# Tested target: macOS Tahoe (26.x), Apple Silicon or Intel.
# Idempotent: safe to re-run.
set -u

WORK="$HOME/ak820pro"
BRANCH="ak820pro-flashlcd-unified-dualspi"
KB="a_jazz/ak820pro"
TC_VER="13.3.1-1.1"
REPO="$WORK/qmk_firmware"

case "$(uname -m)" in
  arm64)  TC_ARCH="darwin-arm64" ;;
  x86_64) TC_ARCH="darwin-x64"   ;;
  *) echo "unsupported arch $(uname -m)"; exit 1 ;;
esac
TC_DIR="$WORK/xpack-arm-none-eabi-gcc-$TC_VER"

log() { printf '\n=== %s ===\n' "$*"; }
mkdir -p "$WORK" || exit 1
cd "$WORK" || exit 1

log "0/7 brew deps (hidapi + pkg-config, for the two C tools)"
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install from https://brew.sh then re-run."; exit 1
fi
brew list hidapi      >/dev/null 2>&1 || brew install hidapi
brew list pkg-config  >/dev/null 2>&1 || brew install pkg-config
echo "hidapi: $(pkg-config --modversion hidapi 2>/dev/null || echo '?')"

log "1/7 clone fpb/qmk_firmware @ $BRANCH"
if [ -d "$REPO/.git" ]; then
  echo "already cloned"
else
  git clone --branch "$BRANCH" --single-branch \
      https://github.com/fpb/qmk_firmware.git "$REPO" || { echo CLONE_FAIL; exit 1; }
fi
cd "$REPO" && echo "branch: $(git branch --show-current)"

log "2/7 arm-none-eabi toolchain (xpack $TC_ARCH, no sudo)"
if [ -x "$TC_DIR/bin/arm-none-eabi-gcc" ]; then
  echo "toolchain already present"
else
  TC_URL="https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/download/v$TC_VER/xpack-arm-none-eabi-gcc-$TC_VER-$TC_ARCH.tar.gz"
  curl -fL --retry 3 -o "$WORK/tc.tar.gz" "$TC_URL" \
    && tar xzf "$WORK/tc.tar.gz" -C "$WORK" && rm -f "$WORK/tc.tar.gz" || { echo TOOLCHAIN_FAIL; exit 1; }
fi
export PATH="$TC_DIR/bin:$PATH"
arm-none-eabi-gcc --version | head -1

log "3/7 python venv + qmk cli"
if [ -x "$WORK/venv/bin/qmk" ]; then
  echo "venv already present"
else
  python3 -m venv "$WORK/venv" \
    && "$WORK/venv/bin/pip" -q install --upgrade pip \
    && "$WORK/venv/bin/pip" -q install qmk || { echo VENV_FAIL; exit 1; }
fi
export PATH="$WORK/venv/bin:$PATH"
echo "qmk cli $(qmk --version)"

log "4/7 make git-submodule (fetches chibios, ~230MB)"
cd "$REPO" || exit 1
make git-submodule 2>&1 | tail -5

log "5/7 apply the six ChibiOS patches, in required order"
cd "$REPO/lib/chibios-contrib" || exit 1
for p in hardware_pwm i2c_fallback rtc_lld spi_fifo_pump spi_flash_dma efl_ramtext; do
  d="../../keyboards/$KB/$p.diff"
  if   git apply --reverse --check "$d" 2>/dev/null; then echo "  already applied: $p"
  elif git apply --check "$d" 2>/dev/null; then git apply "$d" && echo "  APPLIED: $p"
  else echo "  FAILED: $p"; exit 1; fi
done

log "6/7 compile the VIA target"
cd "$REPO" || exit 1
qmk config user.qmk_home="$REPO" >/dev/null 2>&1
qmk compile -kb "$KB" -km via 2>&1 | tail -8

log "7/7 host tools"
cd "$WORK" || exit 1
# SonixFlasherC -- fpb's fork; upstream main does NOT work on Tahoe
if [ ! -d SonixFlasherC/.git ]; then
  git clone --branch fix_for_macos_tahoe --single-branch \
      https://github.com/fpb/SonixFlasherC.git SonixFlasherC || exit 1
fi
( cd SonixFlasherC && make sonixflasher >/dev/null 2>&1 \
  && echo "  sonixflasher: $(./sonixflasher --version 2>&1 | head -1)" \
  || echo "  sonixflasher: BUILD FAILED" )
# ak820ctl -- LCD clock + flash provisioning
if [ ! -d time-util-ak820pro/.git ]; then
  git clone https://github.com/fpb/time-util-ak820pro.git || exit 1
fi
( cd time-util-ak820pro && make >/dev/null 2>&1 \
  && echo "  ak820ctl: built" || echo "  ak820ctl: BUILD FAILED" )

log "RESULT"
ls -la "$REPO"/a_jazz_ak820pro_via.bin 2>/dev/null || echo "firmware MISSING"
echo
echo "firmware : $REPO/a_jazz_ak820pro_via.bin"
echo "flasher  : $WORK/SonixFlasherC/sonixflasher"
echo "lcd tool : $WORK/time-util-ak820pro/ak820ctl"
echo
echo "Rebuild later with:"
echo "  export PATH=\"$TC_DIR/bin:$WORK/venv/bin:\$PATH\""
echo "  cd $REPO && qmk compile -kb $KB -km via"
