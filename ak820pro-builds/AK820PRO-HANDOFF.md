# AJAZZ AK820 Pro → QMK — handoff to Gizmo (macOS Tahoe)

Goal: flash fpb's QMK port onto JD's AK820 Pro, with **VIA** remapping and a
**customizable LCD**. Setup and flashing happen on the Mac; the Windows box has
already proven the build works.

---

## 0. State of play

| | |
|---|---|
| **GREMLIN** (Windows 11) | Keyboard is **physically plugged in here** right now. WSL build env working at `~/ak820pro`. Verified `.bin`s at `C:\Users\jdlien\code\ak820pro-builds\`. |
| **Gizmo** (macOS Tahoe 26.x) | Target machine. Nothing set up yet. |

**The USB cable must be moved to the Mac before flashing.** The keyboard sits on
a physical Genesys Logic hub on GREMLIN; it is not RDP-redirected and will not
appear on the Mac until it's replugged there.

Everything below has been verified against the actual source and the actual USB
bus — not assumed. Where a project doc is wrong, it's called out.

---

## 1. Hardware and device IDs

| Item | Value |
|---|---|
| MCU | **HFD80CP100** — clone of SONiX SN32F299 (QMK: `SN32F299F`, bootloader `sn32-dfu`) |
| Wireless | WCH **CH582F** (BT + 2.4 GHz), own firmware, untouched by a QMK flash |
| External flash | **PY25Q128HA**, 16 MB SPI |
| LCD | 0.85″ 128×128, **GC9107** |
| RTC | CHMC D8563F (PCF8563 clone), bit-banged I2C |

| State | VID:PID |
|---|---|
| This unit, stock v1.10 | `0C45:800A` |
| Other stock batches | `0C45:8009` (v1.13), `0C45:8099` (v1.14) |
| **Bootloader (ISP)** | **`0C45:7140`** |
| After flashing QMK | `0C45:8009` |

### The PID is a firmware property, not a hardware one

fpb's own commit on the v1.14 dump states it: *"the USB PID really does change:
V1.13 is 0x0C45:0x8009, V1.14 is 0x0C45:0x8099."* So this unit's `800A` simply
reflects stock v1.10. It is **not** evidence of a hardware variant, and fpb's
images are valid for it.

`800A` is also the Leobod K81 Pro's PID — coincidence of a shared vendor SDK.
Confirmed by decoding USB string descriptors out of the stock binaries: both
AJAZZ dumps carry iProduct `AK820` (what this unit reports), the Leobod one
carries `K81 Pro`.

### No rollback to the exact shipped image

**SonixFlasherC is write-only** — there is no `--read`/`--dump`. The shipped
v1.10 cannot be backed up. Recovery means fpb's `AJAZZ_AK820PRO_PID_8009_V1.13`
image (same hardware, different version). Prefer **v1.13 over v1.14** for
rollback: v1.14's PID change to `8099` makes the keyboard undetectable by AJAZZ's
own drivers.

Optional, free, do it while still on stock: grab AJAZZ's Windows driver installer
and keep it. It's the only route to a vendor firmware image.

---

## 2. Which branch, and why

**`ak820pro-flashlcd-unified-dualspi`** of `github.com/fpb/qmk_firmware`.

It is fpb's preferred build *and* the only recommended branch with a VIA keymap.
LCD art and GIF animations live in external SPI flash and are provisioned from
the host — which is what makes the screen customizable without a firmware
rebuild.

Everything works: key matrix, per-key RGB (hardware PWM), LCD, dip switches,
volume knob, BT/2.4G, RTC clock, flash provisioning.

### Two project docs are stale — ignore them

1. **ak820ctl's README** says flash provisioning is `ak820pro-flashlcd-tiles`
   **only**. Wrong for this branch. Verified in `keyboards/a_jazz/ak820pro/ak820pro.c`:
   `FLASH_CHANNEL = 0x11` ("Flash provisioning channel (Stage D)") is present,
   alongside `RTC_CHANNEL = 0x10` for the clock. Both channels are live.
2. **`rules.mk`** claims the RTC "does NOT work on hardware yet". Superseded —
   later rtc commits landed bit-bang I2C fixes, and the main README lists clock
   support as done.

`rules.mk` also points at `graphics/res/mkraw.py`, which does not exist there.
The packers live in the **ak820ctl repo** at `assets/mkraw.py` and `assets/mkanim.py`.

---

## 3. Setup (one script)

Run `ak820pro-mac-setup.sh` (alongside this file). It is idempotent — re-run it
freely. It mirrors the pattern already proven on GREMLIN: xpack toolchain +
venv `qmk` CLI, so Homebrew is only needed for the two C tools.

```sh
chmod +x ak820pro-mac-setup.sh && ./ak820pro-mac-setup.sh
```

What it does:

1. `brew install hidapi pkg-config`
2. Clone `fpb/qmk_firmware` @ `ak820pro-flashlcd-unified-dualspi`
3. xpack `arm-none-eabi-gcc` 13.3.1 into `~/ak820pro` (arch auto-detected, no sudo)
4. Python venv + `qmk` CLI
5. `make git-submodule` (~230 MB)
6. Apply the six ChibiOS patches **in this order** — `spi_flash_dma` must follow
   `spi_fifo_pump` (same LLD file), and `efl_ramtext` is **required for VIA**:
   `hardware_pwm` → `i2c_fallback` → `rtc_lld` → `spi_fifo_pump` → `spi_flash_dma` → `efl_ramtext`
7. `qmk compile -kb a_jazz/ak820pro -km via`
8. Build **fpb's** SonixFlasherC (`fix_for_macos_tahoe`) and ak820ctl

> **Tahoe requires fpb's fork.** Upstream `SonixQMK/SonixFlasherC` has only a
> `main` branch and does not carry the fix.

> The patches are **working-tree edits**. Any `git submodule update` discards
> them — re-run the script's step 5 to reapply.

Result:

```
~/ak820pro/qmk_firmware/a_jazz_ak820pro_via.bin
~/ak820pro/SonixFlasherC/sonixflasher
~/ak820pro/time-util-ak820pro/ak820ctl
```

Rebuild later:

```sh
export PATH="$HOME/ak820pro/xpack-arm-none-eabi-gcc-13.3.1-1.1/bin:$HOME/ak820pro/venv/bin:$PATH"
cd ~/ak820pro/qmk_firmware && qmk compile -kb a_jazz/ak820pro -km via
```

### Verifying a build is sane

A correct build is **~27% nonzero** across the 256 KB image and its vector table
reads `SP=0x20000400`, `Reset=0x00000191`, `HardFault=0x00000193`,
`SVC[11]=PendSV[14]=0x00000193`, USB descriptor `0C45:8009` bcd `0x0100`.
The GREMLIN build matched fpb's prebuilt on every one of those.

**Do not compare density against stock firmware (~90% nonzero).** That ratio is
what exposed fpb's *truncated* v1.14 extraction — applying it to a QMK build
produces a false alarm.

---

## 4. Flashing

### Entering the bootloader — this needs the case open, once

While still on stock firmware, the **only** way in is shorting two pins under the
spacebar while plugging in USB. They sit under two insulation layers plus a
removable foam strip; a window has to be cut through the insulation. Photo:
`img/bootloader-pins.jpg` in `fpb/ajazz-ak820-pro`.

Once QMK is on, this is never needed again — **`ESC` while plugging in**, or
**`Fn`+`ESC`** from a running keyboard.

### Flash

```sh
cd ~/ak820pro
./SonixFlasherC/sonixflasher --vidpid 0c45/7140 --file qmk_firmware/a_jazz_ak820pro_via.bin
```

Confirm `0C45:7140` is present first (`system_profiler SPUSBDataType | grep -i 7140`).
The keyboard reboots into QMK.

### Rollback

Same pin short (the `ESC` shortcut is gone once you leave QMK), then flash
`StockFWBinaries/AJAZZ_AK820PRO_PID_8009_V1.13_SN32F290.bin` from
`fpb/ajazz-ak820-pro` with the same command.

### macOS gotcha

If `ak820ctl` reports the raw HID interface as not found, grant the terminal app
**Input Monitoring** in System Settings → Privacy & Security. macOS gates HID
access to keyboard-class devices.

---

## 5. Customizing the screen

The dashboard draws: 128×128 boot splash, big clock (`HH:MM:SS` or `HH:MM`) plus
date, OS icon (mac/windows), connection icon (USB/BT/2.4G) with a blinking
channel digit, battery, and a GIF animation slot.

Art is RGB565 with colors baked in. Source PNGs and both packers live in
`~/ak820pro/time-util-ak820pro/assets/`. Python 3 stdlib only — no Pillow, no ffmpeg.

Current set is 8 assets: `sonixqmk` (128×128 splash), five 24×24 icons
(apple, windows, cable, bluetooth, 2.4g), and two Iosevka font atlases
(Regular-30 at 15×34, Medium-20 at 10×23, 95 glyphs each). Font atlases mark each
glyph cell with a magenta `(255,0,255)` pixel at its top-left, so the packer
derives grid and advance width itself — no metrics file.

### Set the clock

```sh
./ak820ctl clock                      # host's current local time
./ak820ctl clock 2026-07-01T14:30:00  # specific
```

### Change the art

```sh
cd ~/ak820pro/time-util-ak820pro/assets
# edit the PNGs, keeping each image's dimensions
python3 mkraw.py --flash              # -> flash_assets.bin + flash_assets.h
cd ..
./ak820ctl info                                        # JEDEC id + writable base
./ak820ctl flash write 0x0CE0000 assets/flash_assets.bin
```

Takes effect on next boot. `flash write` erases, streams, then CRC32-verifies on
device.

**The one firmware coupling:** if you add, remove, or reorder assets,
`flash_assets.h` changes and must be copied into the firmware tree, then rebuilt:

```sh
cp assets/flash_assets.h ~/ak820pro/qmk_firmware/keyboards/a_jazz/ak820pro/graphics/res/
```

Changing only *pixels* needs no rebuild.

### GIF animation

```sh
cd ~/ak820pro/time-util-ak820pro/assets
python3 mkanim.py myloop.gif -o myloop.bin   # --fit cover|contain
cd ..
./ak820ctl flash write 0x540000 assets/myloop.bin --unlock
```

Toggle on the keyboard with **Fn+Delete** (`ANIM_TOG`, already bound in the VIA keymap).

**Verified against firmware source** (`graphics/lcd_bus.c`), since the docs
disagree elsewhere:

| Constant | Value |
|---|---|
| `FLASH_ASSET_BASE` | `0x0CE0000` (3.12 MB, erased since manufacture, always writable) |
| `ANIM_BASE` | `0x540000` |
| `ANIM_STRIDE` / `ANIM_HDR` | `0x8000` / `0x100` |
| Max frames | **243** |
| Unlockable stock slots | `0x1AA000`, `0x200000`, `0x38B000`, `0x540000` |

Animation slots need `--unlock`; the stock LCD-asset region is never writable.
Flashing is refused while an animation is playing — toggle it off first.
Playback is a fixed **~100 ms/frame**, so a GIF authored at another rate plays
faster or slower; `mkanim.py` prints both durations.

> fpb's v1.14 note about stock animation slots moving to `0x1AA000`/`0x38B000` is
> a *stock firmware* detail. QMK defines its own `ANIM_BASE = 0x540000`, so
> `0x540000` is correct here.

---

## 6. Keymap

VIA keymap has four layers — `WINBASE`, `WINFN`, `MACBASE`, `MACFN` — on
`LAYOUT_82_ansi`, with `QK_BOOT` on Fn+Esc and `ANIM_TOG` on Fn+Delete. The
encoder is exposed as a remappable VIA knob.

Load `QMKFWBinaries/via.json` from `fpb/ajazz-ak820-pro` into VIA or Vial.
Dynamic keymap is 4 layers.

---

## 7. Repos

| Repo | Purpose |
|---|---|
| `fpb/qmk_firmware` @ `ak820pro-flashlcd-unified-dualspi` | the port |
| `fpb/ajazz-ak820-pro` | reverse-engineering docs, pinouts, stock + prebuilt binaries, `via.json` |
| `fpb/time-util-ak820pro` | `ak820ctl` — clock + LCD provisioning, asset pipeline |
| `fpb/SonixFlasherC` @ `fix_for_macos_tahoe` | flasher (**required** on Tahoe) |

Prebuilt `.bin`s exist in `fpb/ajazz-ak820-pro/QMKFWBinaries/` if you ever want
to skip building — including `ak820pro-flashlcd-unified-dualspi_via.bin`.
