# AK820 Pro → QMK ("Jackrabbit")

Workspace for JD's **AJAZZ AK820 Pro** running a hardened fork of **fpb's QMK
port**, with VIA remapping and a customizable 0.85″ LCD. Personal-first: built
for this unit and published for other AK820 Pro owners, deliberately NOT
generalized for upstream.

This folder is a git repo. Local files (`CLAUDE.md`, `docs/`, `hostagent/`,
`assets-src/`, `hardening-plan/`, `scripts/`, `flash.sh`, `env.sh`) are
tracked on `main`. The nested upstream clones are **not** part of it — do not
commit into them unless asked, except `qmk_firmware-ak820pro/`, which carries
the board work on its own **`ak820pro-jdlien`** branch (its
`lib/chibios-contrib` submodule is pinned to our patched
**`ak820pro-patches`** branch).

The authoritative device background is
[`ak820pro-builds/AK820PRO-HANDOFF.md`](ak820pro-builds/AK820PRO-HANDOFF.md)
— hardware IDs, flash memory map, asset pipeline, and which upstream docs are
stale. It assumes `~/ak820pro`; everything actually lives here — translate
paths.

## The topic docs — read the one for the area you're touching

| Doc | Covers |
|---|---|
| [docs/wireless.md](docs/wireless.md) | CH582F module, BT/2.4G, pairing UX, the `A6`/`5B` quirks, slot memory |
| [docs/display.md](docs/display.md) | LCD panel variant, band layout, glyph queue/DMA pump, backlight, overlays, host text slot |
| [docs/fonts-assets.md](docs/fonts-assets.md) | Font atlases, Cozette, clock crop, asset provisioning and its traps |
| [docs/clock.md](docs/clock.md) | The two RTCs, divider trim, persisted period, the timekeeper resync agent |
| [docs/leds.md](docs/leds.md) | **Interrupt priorities**, RGB field rate, indicator LEDs, the rainbow, effects |
| [docs/hardware.md](docs/hardware.md) | Slider power quirk, bootloader, build/flash, watchdog+health, hang history, diagnostics |

Project history: `hardening-plan/` (2026-09-01 refactor: plan, findings,
per-phase records, `HARDWARE-CHECKLIST.md` — all verified — and `BACKLOG.md`);
`clock-sync-plan/` (2026-09-01 sub-second clock sync, phases 0-3 implemented:
plan + measured results). ChibiOS patch inventory:
`keyboards/a_jazz/ak820pro/PATCHES.md`.

## Current state (2026-09-01)

QMK VIA firmware flashed and verified (`0C45:8009`); assets provisioned. The
hardening project (phases 0-5) is complete and hardware-verified: board code
split into modules (`ak820pro.c` ~570 lines of init/dispatch; watchdog,
health, kb_eeconfig, bt_ui, consumer_mod, param_overlay, indicators,
hid_protocol), a ~12 s hardware watchdog with reset-loop escape and LCD
alert, health counters on raw-HID channel 0x13, the CH582F pending-action
machinery unified with fault injection, nothing blocking the main loop on the
glyph queue, and BT slot / LCD brightness / RTC trim persisted. Long-standing
LED row-flash artifact fixed; stray-glyph display bug fixed. LED field rate
1046 Hz; matrix scan ~390-400 Hz; BT at 0.042 ACK timeouts/frame.
**Sub-second clock sync implemented the same day** (phases 0-3): host syncs
land within ~3 ms, a USB-SOF frequency loop disciplines the ILRC, offsets
slew instead of jumping, and a no-host reboot self-acquires to ~±15 ms —
see [docs/clock.md](docs/clock.md).

## Build & flash

```sh
source env.sh                        # QMK_HOME + PATH
scripts/build.sh daily               # or: instrumented (console + test hooks)
./flash.sh ak820pro-builds/out/<the printed artifact>
```

`build.sh` enforces the submodule pin, structural binary checks, and
via.json/enum sync; it refuses a dirty or off-pin tree. `flash.sh` preserves
the VIA keymap across the flash (the erase would destroy it) and refuses to
flash if the backup fails. Enter the bootloader with `Fn`+`Esc`.
**A flash erases the emulated EEPROM**: VIA keymap (restored by flash.sh),
BT slot, LCD brightness, and the persisted RTC period (the SOF loop
re-converges in ~4 min with the host attached — designed, not a fault).

Toolchain: xpack `arm-none-eabi-gcc` 13.3.1, venv `qmk` CLI, Homebrew
`hidapi`. `SonixFlasherC` must be built `USE_LIBUSB=1` (see
[docs/hardware.md](docs/hardware.md) — a plain build fails on Tahoe while
looking identical).

## Working with VIA

Load `keyboards/a_jazz/ak820pro/via.json` (board not in VIA's database):
usevia.app in Chrome/Edge → Settings → Show Design tab → Load Draft
Definition. **The USB cable must be connected; the slider position does not
matter** — raw-HID replies return over USB in any mode (board commit
4b86d95014, 2026-08-29; verified with round-trips in the BT position
2026-09-01). Older notes demanding "wired mode" describe the pre-fix
firmware.

- Layers: `WINBASE=0, WINFN=1, MACBASE=2, MACFN=3` — the mac/win dip switch
  picks the base, so per-key remaps usually need doing on both 0 and 2.
- **VIA's stored keymap overrides the firmware default** — a keycode newly
  bound in keymap.c will not appear if EEPROM already has that key assigned.
- **The `ak820pro_keycodes` enum is index-matched to via.json's
  `customKeycodes[]`. APPEND ONLY** — inserting shifts every later keycode
  and corrupts existing VIA keymaps (`check_via_sync.py` guards this).
- Keymap backup: `python3 hostagent/ak820keymap.py dump|restore|show` — raw
  dynamic-keymap buffer + encoders (a separate VIA command; skipping them
  would silently drop the knob mapping).

## Stock Fn shortcuts (quick reference)

`Fn`+`Q/W/E` BT slots (tap = select, hold 2 s = pair) · `Fn`+`R` 2.4G ·
`Fn`+`←/→` hue · `Fn`+`↑/↓` brightness · `Fn`+`6/7` saturation · `Fn`+`X`
RGB on/off · `Fn`+`\` next effect · `Fn`+`-/=` speed (or 2nd colour on
Alphas/Mods) · `Fn`+`PgUp/PgDn` LCD brightness · `Fn`+`Home` LCD toggle ·
`Fn`+`Esc` bootloader · `Fn`+`Delete` ANIM_TOG. BT keys are inert in wired
mode. `Fn`+`P` (pair) is unbound by default.

## Critical warnings (details in the docs)

- ⚠️ **The mode slider is a power-source switch** — most flips brown-out the
  MCU and lose all RAM state; there is no "off" position. Cold power-off =
  `cable` + unplug ~10 s. → [hardware.md](docs/hardware.md)
- ⚠️ **The bootloader looks exactly like a dead board.** Check for USB id
  `0x7140` before assuming a hang. → [hardware.md](docs/hardware.md)
- ⚠️ **`ak820ctl flash write` erases first** — verify `ak820ctl info`
  answers before provisioning, and power-cycle after (a CRC match does NOT
  mean the board renders the new assets). → [fonts-assets.md](docs/fonts-assets.md)
- ⚠️ **Asset ids are assigned by sorted filename** — renaming/adding files
  forces a coordinated rebuild + re-provision. Two filenames are deliberate
  lies; do not "fix" them. → [fonts-assets.md](docs/fonts-assets.md)
- ⚠️ **If Bluetooth regresses, check the interrupt priority table first**,
  not the ISR rate. → [leds.md](docs/leds.md)
- ⚠️ **Keyboard feels slow / drops keystrokes? Check the HOST first**
  (leftover pollers with exclusive HID access). → [hardware.md](docs/hardware.md)
- ⚠️ **Multiple sessions**: coordinate via SendMessage, claim files, flash
  only provenance-named artifacts. → [hardware.md](docs/hardware.md)

## Where things live

**Firmware** — `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/` (branch
`ak820pro-jdlien`; git history is the change inventory). Notables:
`graphics/lcd_bus.c` holds the authoritative flash memory map;
`graphics/res/flash_assets.h` is generated by `mkraw.py` and is the one
firmware↔asset coupling; `PATCHES.md` documents the seven ChibiOS patches.
A few local commits live in QMK core outside `keyboards/`:
`drivers/led/sn32f2xx.c` (ISR hook, periodticks fix, flash-window mux
blanking, flush lock), `quantum/rgb_matrix/rgb_matrix.c` (flush-allowed
hook), `platforms/chibios/.../wear_leveling_efl.c` (pre-write hook) — all
weak-hooked/no-op for other boards.

**Host tools** — `hostagent/` (`ak820text.py`, `nowplaying-macos.sh`,
`ak820keymap.py`, `ak820health.py`, clocksync + nowplaying LaunchAgents);
`scripts/` (build, soak, bt_faults, consolelog, check_via_sync);
`time-util-ak820pro/` (`ak820ctl`, `assets/mkraw.py`, `mkanim.py`);
`SonixFlasherC/` (flasher, libusb build).

**Reference** — `ajazz-ak820-pro/` (datasheets, `CH582F_PROTOCOL.md`,
pinouts, stock + fpb prebuilt binaries, `via.json`);
`ak820pro-builds/` (handoff doc, build artifacts in `out/`, chibios patch
bundle); `assets-src/` (font/splash sources and shipped-atlas copies).

**Upstream clones** (do not commit; verify branches):
`qmk_firmware-ak820pro` (fpb, our branch), `ajazz-ak820-pro` (fpb/main),
`time-util-ak820pro` (fpb/main), `SonixFlasherC` (**fpb,
`fix_for_macos_tahoe`** — back on SonixQMK/main would be a regression). If a
clone looks mass-modified, check `git diff --ignore-cr-at-eol --stat` before
believing it (CRLF from the original Windows transfer).
