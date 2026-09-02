# AK820 Pro — the "Jackrabbit" firmware

QMK for the **AJAZZ AK820 Pro**, with VIA remapping and a genuinely useful
0.85″ LCD: a clock synced to your Mac to within a few milliseconds, the track
you are playing, battery and connection status, and a layer/lock band.

This is a personal build, published for other AK820 Pro owners. It is a
hardened fork of [fpb](https://github.com/fpb)'s QMK port — not a generalized
upstream contribution, and deliberately so.

**What you get over stock:** working media keys over Bluetooth, pairing that
responds the first time you press it, no backlight flicker, no dropped
keystrokes while typing fast on BT, a ~12 s watchdog that recovers a wedged
board instead of needing a replug, and an LCD that shows something worth
looking at.

---

## ⚠️ Read this before your first flash

**1. There is no backup path. Download the stock image first.**

Get `AJAZZ_AK820PRO_PID_8009_V1.13_SN32F290.bin` from
[fpb/ajazz-ak820-pro](https://github.com/fpb/ajazz-ak820-pro) (`StockFWBinaries/`)
**before you flash anything.** The stock firmware cannot be read off the board.
Once it is gone, that download is your only way back.

    shasum -a 256 AJAZZ_AK820PRO_PID_8009_V1.13_SN32F290.bin
    cd0b01e30cb727d658a540922d1fb153bcfaa3da2ac97902ba547af9e97012ab

Do **not** use the v1.14 image: it changes the USB PID to `0x8099` and AJAZZ's
own software stops recognizing the board.

**2. The bootloader looks exactly like a dead keyboard.** On entry you get a
`BOOTLOADER / 0C45:7140` splash for ~1.5 s, then the backlight drops and the
board sits dark — no lights, no typing. That is normal. Check for the USB id
before assuming you have bricked it:

    ioreg -p IOUSB -w0 -l | grep -c '"idProduct" = 28992'   # 0x7140 = bootloader

Recovery is **re-running the flash**, not a power cycle.

**3. Getting into the bootloader.** From this firmware: `Fn`+`Esc`. From
**stock**, the first time only, you must short the 2-pin header under the
spacebar — put the mode slider in `cable`, cold-boot with the pins shorted
(it is sampled only at power-on). fpb's repo has the photo and the procedure.

**4. Flashing erases the emulated EEPROM** — VIA keymap, RGB settings, LCD
brightness, BT slot, and the persisted RTC trim. `flash.sh` backs up and
restores the VIA keymap for you; the rest re-converges on its own.

---

## Just give me the firmware

If you do not want a toolchain, take the prebuilt binaries from
[Releases](https://github.com/jdlien/ak820-pro/releases): a `.bin` for each
panel variant, the LCD asset image, and `via.json`.

```sh
# 1. bootloader: Fn+Esc  (or the pin short, from stock)
./SonixFlasherC/sonixflasher --vidpid 0c45/7140 --file ak820pro-via.bin

# 2. the LCD assets: fonts, icons, splash  (power-cycle afterwards)
./time-util-ak820pro/ak820ctl flash write 0x0CE0000 flash_assets.bin
```

**If the LCD comes up upside down or colour-inverted**, you have the other
panel revision — use the `-fpb` binary instead. At least two hardware
revisions ship under this name; nothing is wrong with your board.

---

## Build it yourself

Requires macOS (tested on Tahoe 26.x, Apple Silicon and Intel) and Homebrew.

```sh
git clone https://github.com/jdlien/ak820-pro && cd ak820-pro
./setup.sh                    # toolchain, venv, pinned deps, host tools
./build.sh daily              # or: instrumented (console + test hooks)
./flash.sh ak820pro-builds/out/<the artifact it prints>
```

`setup.sh` is idempotent — re-run it any time, and re-run it after changing a
pin. It clones four dependencies at the exact commits in
[`deps.lock`](deps.lock) and refuses to continue if any of them lands
somewhere else. `build.sh` enforces the ChibiOS submodule pin, checks the
resulting binary structurally (stack pointer, reset vector, USB descriptor),
verifies the VIA keycode enum still matches `via.json`, and writes a
provenance-named artifact. `flash.sh` preserves your VIA keymap across the
erase and refuses to flash if that backup fails.

For the other panel revision:

    ./build.sh fpb

**One trap worth repeating:** `SonixFlasherC` must be built with
`USE_LIBUSB=1`, which `setup.sh` does. A plain build compiles, runs, and
prints the same version banner — then fails to flash on Tahoe.

## The host agents (clock + now playing)

```sh
hostagent/install-agents.sh            # --status / --uninstall
```

Two LaunchAgents. **timekeeper** syncs the board clock every 5 minutes, on
wake, and whenever the board re-enumerates, and measures your Mac's USB SOF
bias so the sync lands within a few milliseconds. **nowplaying** pushes the
current Spotify/Music track to the LCD.

Give the clock ~15 minutes before judging it: it slews rather than jumping, so
corrections are gradual by design, and the SOF bias needs that long to be
measured. Watch `~/Library/Logs/ak820pro-timekeeper.log`.

## Using VIA

The board is not in VIA's database, so load the definition by hand:
[usevia.app](https://usevia.app) → Settings → Show Design tab → Load Draft
Definition → `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/via.json`.
The USB cable must be connected; the slider position does not matter.

Layers are `WINBASE=0, WINFN=1, MACBASE=2, MACFN=3` — the mac/win dip switch
picks the base, so a per-key remap usually needs doing on both 0 and 2.

## Where things are

| Path | What |
|---|---|
| [`docs/`](docs/) | The six topic docs — wireless, display, fonts/assets, clock, LEDs, hardware. Read the one for what you are touching. |
| [`hostagent/`](hostagent/) | Clock sync, now-playing, keymap backup, health counters |
| [`assets-src/`](assets-src/) | Font atlas and splash generators |
| [`scripts/`](scripts/) | Soak harness, BT fault injection, console log, VIA sync check |
| [`plans/`](plans/) | Live: known defects, and designed-but-unbuilt features |
| [`history/`](history/) | Completed projects, kept for their reasoning |
| `qmk_firmware-ak820pro/` | The firmware (cloned by `setup.sh`, gitignored here) |

The firmware source is the [`ak820pro-jdlien`](https://github.com/jdlien/qmk_firmware/tree/ak820pro-jdlien)
branch of a QMK fork; the board lives in `keyboards/a_jazz/ak820pro/`. Its
ChibiOS patches are commits on
[`jdlien/ChibiOS-Contrib`](https://github.com/jdlien/ChibiOS-Contrib/tree/ak820pro-patches),
never hand-applied diffs.

## Credit

fpb did the original port, the CH582F protocol reverse-engineering, the
hardware documentation, and the macOS Tahoe flasher fix. This fork is board
hardening, LCD work, clock sync, and host tooling on top of that.
[`ak820pro-builds/UPSTREAM-CONTRIBUTIONS.md`](ak820pro-builds/UPSTREAM-CONTRIBUTIONS.md)
sorts what belongs upstream from what is personal preference.

QMK is GPLv2. No warranty: this is one person's keyboard firmware, published
in case it is useful to someone with the same keyboard.
