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
restores the VIA keymap for you. BT slot, LCD brightness and the RTC trim
re-converge on their own (the clock takes a few minutes with a host attached).

⚠️ **RGB is the exception: nothing restores it.** Every flash reverts the LEDs
to `rgb_matrix.default` in `keyboards/a_jazz/ak820pro/keyboard.json` and leaves
them there. If your lighting differs from that default, note it before you
flash — or set the default to match, which is what keeps it from silently
reverting on every single flash.

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

macOS (tested on Tahoe 26.x, Apple Silicon and Intel) with Homebrew, or
Windows (tested on 11 Pro 26200) from the **MSYS2 MinGW 64-bit** shell.

```sh
git clone https://github.com/jdlien/ak820-pro && cd ak820-pro
./setup.sh                    # toolchain, venv, pinned deps, host tools
./build.sh daily              # or: instrumented (console + test hooks)
./flash.sh ak820pro-builds/out/<the artifact it prints>
```

**On Windows:** install MSYS2 (`winget install MSYS2.MSYS2`), open the *MSYS2
MinGW 64-bit* shell — not Git Bash, not PowerShell — and run the same three
commands; `setup.sh` installs the MSYS2 packages it needs. Flashing needs **no
Zadig/WinUSB driver**: the Sonix bootloader is a plain HID device there, and
the `USE_LIBUSB=1` flag below is a macOS-only workaround. The clock and
now-playing agents are macOS LaunchAgents and are not installed on Windows.
The four Windows-specific traps — CRLF, the venv's name, `PATH` order, and
that libusb flag — are written up in
[docs/hardware.md](docs/hardware.md#building-and-flashing-on-windows-msys2).

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

## The host agents (clock sync + now playing)

Two small background agents, on both macOS and Windows:

- **timekeeper** — keeps the LCD clock right. Syncs every 5 minutes, on wake,
  and whenever the board re-enumerates (a slider flip or replug reboots it),
  measuring the USB SOF bias so a sync lands within a few milliseconds.
- **nowplaying** — pushes the currently playing track to the LCD: artist on the
  top line, title below, a play/pause icon, and a progress timer where the
  player reports one (see the Windows notes — foobar2000 does not).

Run `./setup.sh` first — both agents live in the repo's venv.

> **One holder at a time.** The board's raw-HID interface is *exclusive*. If a
> usevia.app tab is open it owns the interface and the agents cannot push; the
> logs will say so. Close the tab (or stop the agents) before using VIA. This
> has twice been mistaken for a firmware fault.

### macOS

```sh
hostagent/install-agents.sh              # install and start
hostagent/install-agents.sh --status     # what is running
hostagent/install-agents.sh --uninstall  # stop and remove
```

Installs two LaunchAgents (`com.jdlien.ak820pro.timekeeper` / `.nowplaying`),
which then start at every login. Logs:

```
~/Library/Logs/ak820pro-timekeeper.log
~/Library/Logs/ak820pro-nowplaying.log
```

⚠️ **First run needs an Automation grant.** nowplaying reads Spotify and Music
over AppleScript, and macOS blocks that until you approve it — but a LaunchAgent
usually cannot raise the prompt itself, so it just runs forever pushing nothing.
If the log says `AUTOMATION DENIED`, run it once from a terminal to trigger the
prompt, then approve under **System Settings → Privacy & Security → Automation**:

```sh
hostagent/nowplaying-macos.sh
```

### Windows

The installer is **PowerShell**, not the MSYS2 shell you built the firmware in:

```powershell
powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1
powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1 -Status
powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1 -Uninstall
```

No admin rights needed. It registers two per-user Scheduled Tasks under
`\ak820pro\`, starts them immediately so you need not log out, and re-runs them
at every logon. Logs:

```
%LOCALAPPDATA%\ak820pro\ak820pro-timekeeper.log
%LOCALAPPDATA%\ak820pro\ak820pro-nowplaying.log
```

nowplaying reads **SMTC**, Windows' own media-session API — the one behind the
volume-key flyout — so it needs no per-app support at all. Spotify, Apple Music,
foobar2000 and **any browser** (YouTube and web players included) all appear
through one interface. To see exactly what Windows is exposing:

```powershell
venv-win\Scripts\python.exe hostagent\nowplaying-windows.py --probe
```

An app missing from that list registers no SMTC session, which no change to the
agent can fix. Two measured quirks: **foobar2000** reports title and artist but
no timeline, so it gets no progress timer; **Apple Music** reports everything.

### Checking it worked

Both platforms: `--status` / `-Status` should show each agent running, and the
timekeeper log should show a sync within a minute or so, like

```
sync (enumerated): clock set (sub-second): before -4.3 ms, after -4.0 ms, ...
```

Give the clock ~15 minutes before judging it: it slews rather than jumping, so
a large correction converges gradually by design — a board that was 1.8 s out
spends a while visibly catching up — and the SOF bias needs that long to be
measured. To measure the board directly rather than eyeball it against a wall
clock:

```sh
hostagent/clock-phase.py                                  # macOS
venv-win\Scripts\python.exe hostagent\clock-phase.py      # Windows
```

It reports the phase error in milliseconds — a few tens of ms or better is
healthy, and that figure includes your computer's own clock error, not just the
board's (measured +16 ms against a PC itself 20 ms behind NTP).

Remember the board can only be as accurate as the computer driving it. macOS
keeps tight time by default; **Windows' w32time polls every ~9 hours** out of
the box, so if the board looks off, check the PC first:

```powershell
w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
w32tm /resync
```

## Using VIA

VIA is how you remap keys, edit layers and set the RGB lighting, live, with no
rebuild and no flashing. This board is not in VIA's public database, so you have
to hand it the definition once.

**Before you start**

- Use **Chrome or Edge**. VIA talks to the board over WebHID, which Firefox and
  Safari do not implement.
- **Plug the USB cable in.** The slider position does not matter — raw-HID
  replies come back over USB in every mode.
- If you installed the host agents, **stop them first**. The board's raw-HID
  interface is exclusive, so the clock/now-playing agents and VIA cannot both
  hold it; symptoms are VIA failing to connect, or the agents logging push
  failures. See [the host agents](#the-host-agents-clock-sync--now-playing) for
  the `--uninstall` / `-Uninstall` commands, or just stop the tasks temporarily.

**Where the definition file is**

```
qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/via.json
```

That path only exists after `./setup.sh` has cloned the firmware (the clone is
gitignored). If you have not set up a toolchain, download `via.json` from
[Releases](https://github.com/jdlien/ak820-pro/releases) instead — it is the
same file.

**Loading it**

1. Go to [usevia.app](https://usevia.app) and click **Authorize device**, then
   pick the AK820 PRO in the browser's device prompt.

2. VIA will report that it does not recognise the board:

   > VIA could not find a V3 definition for AK820 PRO.

   That is expected — it means the definition is not loaded yet, not that
   anything is wrong with the keyboard.

3. Click the **gear icon** (top right) to open Settings, and turn on
   **Show Design tab**.

4. Click the **paintbrush icon** to open the Design tab, click
   **Load Draft Definition**, and select the `via.json` above.

5. Re-select the keyboard. VIA now recognises it, and the Configure tab works
   normally — keymap, layers and lighting.

The draft definition is stored in that browser, so this is a one-time setup per
browser profile — but it is *only* in the browser, so a new machine, a new
profile, or cleared site data means loading it again.

**Once you are in**

Layers are `WINBASE=0, WINFN=1, MACBASE=2, MACFN=3`. The mac/win dip switch
picks which base layer is active, so a per-key remap usually needs doing on
**both 0 and 2** to take effect in both positions.

⚠️ **VIA's stored keymap overrides the firmware default.** Whatever you set here
lives in the board's EEPROM and wins over what was compiled in. Two consequences
worth knowing:

- A flash erases it. `flash.sh` backs the keymap up and restores it around the
  flash, but **RGB settings are not restored** — see the flashing notes above.
- Back it up yourself after a remap you care about:

  ```sh
  hostagent/ak820keymap.py dump                              # macOS
  venv-win\Scripts\python.exe hostagent\ak820keymap.py dump  # Windows
  ```

  This saves the raw keymap buffer *and* the encoder mapping (a separate VIA
  command that is easy to lose). `restore` puts it back.

To make your VIA layout the firmware's built-in default — what the board falls
back to if the EEPROM is ever wiped without a restore — regenerate `keymap.c`
from a dump rather than editing it by hand:

```sh
# macOS
./venv/bin/python scripts/keymap_to_c.py ~/Documents/ak820pro-keymap.json --write
# Windows (venv-mingw64, not venv-win: this one needs qmk's hjson)
venv-mingw64/bin/python scripts/keymap_to_c.py ~/Documents/ak820pro-keymap.json --write
```

It emits symbolic keycodes only, and refuses to write a keymap with no
`QK_BOOT` on any layer — regenerating your way out of the bootloader shortcut
would leave no way in short of shorting pads. Rebuild and flash afterwards for
it to take effect.

## Where things are

| Path | What |
|---|---|
| [`docs/`](docs/) | The six topic docs — wireless, display, fonts/assets, clock, LEDs, hardware. Read the one for what you are touching. |
| [`hostagent/`](hostagent/) | Clock sync, now-playing, keymap backup, health counters |
| [`assets-src/`](assets-src/) | Font atlas and splash generators |
| [`scripts/`](scripts/) | Soak harness, BT fault injection, console log, VIA sync check |
| [`plans/`](plans/) | Live: known defects, and designed-but-unbuilt features |
| [`history/`](history/) | Measured results and audit findings worth keeping |
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
