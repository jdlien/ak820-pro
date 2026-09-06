# AK820 Pro → QMK ("Jackrabbit") — working notes

[`README.md`](README.md) is the front door: what this is, how to set up, build,
flash and install the host agents. This file is the stuff you need when you are
*changing* something.

Personal-first: built for JD's unit, published for other AK820 Pro owners,
deliberately NOT generalized for upstream. `ak820pro-builds/UPSTREAM-CONTRIBUTIONS.md`
sorts genuine bugs from personal preference.

## Layout

The repo tracks its own files (`README.md`, `docs/`, `hostagent/`, `scripts/`,
`assets-src/`, `plans/`, `history/`, `setup.sh`, `build.sh`, `flash.sh`,
`env.sh`, `deps.lock`). The four dependency clones are gitignored, created by
`setup.sh`, and pinned by [`deps.lock`](deps.lock) — **change a pin there, not
in a clone.** `qmk_firmware-ak820pro/` is the exception you may commit into: it
carries the board work on `ak820pro-jdlien`, and its `lib/chibios-contrib`
submodule sits on our `ak820pro-patches` branch.

## The topic docs — read the one for the area you're touching

| Doc | Covers |
|---|---|
| [docs/wireless.md](docs/wireless.md) | CH582F module, BT/2.4G, pairing UX, the `A6`/`5B` quirks, slot memory |
| [docs/display.md](docs/display.md) | LCD panel variant, band layout, glyph queue/DMA pump, backlight, overlays, host text slot |
| [docs/fonts-assets.md](docs/fonts-assets.md) | Font atlases, Cozette, clock crop, the flash memory map, provisioning and its traps |
| [docs/clock.md](docs/clock.md) | The two RTCs, divider trim, persisted period, the timekeeper agent |
| [docs/leds.md](docs/leds.md) | **Interrupt priorities**, RGB field rate, indicator LEDs, the rainbow, effects |
| [docs/hardware.md](docs/hardware.md) | Slider power quirk, bootloader, build/flash, watchdog+health, hang history, diagnostics |

Live work: [`plans/`](plans/) (`BACKLOG.md`, `CLOCK-FORMAT-PLAN.md`).

**In progress: `ak820-agent/`** — a Rust rewrite of the two Windows host agents
as one daemon. **Phases 0–2 complete and audited; 3a met (the scheduler and
learners replayed against the Python log); 4a live — the daemon owns
now-playing on this machine, the Python timekeeper still owns the clock;
the clock takeover (3b/4b) is wired behind `ak820 install --clock` and waits
for the owner; the 3a/4a audit's 18 findings fixed and phase 5 (health) met** (2026-09-06).
305 unit tests, the 2,309-case folding fixture, a 4-test replay of the
timekeeper's log and a 2-test health capture. Read
[`plans/AK820-AGENT-PLAN.md`](plans/AK820-AGENT-PLAN.md)
first; it carries the phase gates and the findings that are load-bearing.
Its two companions are part of the plan, not background:
[`AK820-AGENT-CLOCK-PARITY.md`](plans/AK820-AGENT-CLOCK-PARITY.md) (the Python
scheduler and bias learner) and
[`AK820-AGENT-CLOCK-TRANSACTION.md`](plans/AK820-AGENT-CLOCK-TRANSACTION.md)
(`ak820ctl`'s transaction, where the precision actually lives —
**the clock oracle is Python PLUS the pinned C utility**).
[`review-codex-ak820d-2026-09-05.md`](plans/review-codex-ak820d-2026-09-05.md)
is the review that reshaped all three.

Four things from that work that bite outside it:

- ⚠️ **Windows delivers HID input reports to EVERY open handle** (measured
  2026-09-05). A process that wrote nothing received another process's text
  echo, and a clock GET after a text write returned the text echo. Ordering
  cannot correlate a reply to a request — **validate every read against the
  command it answers**. `ak820ctl`'s `xfer()` does not, and fails safe only by
  accident via the protocol-version field.
- ⚠️ **Correlation is not enough for the clock, and this is the one that
  surprises.** A foreign `RTC_GET_TIME` reply is a *well-formed*
  `RTC_GET_TIME` reply — right channel, right command, protocol version 2,
  plausible fields — so no header check can tell it from your own. Taking it
  pairs someone else's board sample with your timestamps: a wrong offset with a
  plausible RTT, silently. **Exactly one process may run clock transactions at
  a time**; that, not the framing, is what makes the clock correct.
- ⚠️ **Never enumerate HID.** `hid_enumerate` opens every HID device on the
  machine; that wedged a UPS on this machine
  (`../jdrgb/docs/ups-wedge-incident.md`). `ak820text.py` is fixed; the
  timekeeper and `ak820ctl` are not — see `plans/BACKLOG.md`.
- ⚠️ The raw-HID interface is **shareable**, not exclusive — the old "VIA
  holding it" advice describes contention over *replies*, not over the open.
  And that contention **breaks VIA, not you**: measured 2026-09-05, VIA
  received another process's reply, rejected it, and then stayed
  **persistently off by one** for the rest of the session. The now-playing
  agent does this every ~3 s. **Pause the host agents before using VIA**
  (`hostagent/install-agents-windows.ps1 -Status` to see them), and read
  lighting values back over `[0x08, 3, 1..4]` rather than trusting VIA's UI
  after an error — the board executes the writes, VIA only loses the replies.

Measured results and audit findings from completed work: [`history/`](history/).
ChibiOS patch inventory: `keyboards/a_jazz/ak820pro/PATCHES.md`.

## Current state (2026-09-03)

QMK VIA firmware flashed and verified (`0C45:8009`); assets provisioned. The
hardening project (phases 0-5) is complete and hardware-verified: board code
split into modules (`ak820pro.c` ~570 lines of init/dispatch; watchdog, health,
kb_eeconfig, bt_ui, consumer_mod, param_overlay, indicators, hid_protocol), a
~12 s hardware watchdog with reset-loop escape and LCD alert, health counters
on raw-HID channel 0x13, the CH582F pending-action machinery unified with fault
injection, nothing blocking the main loop on the glyph queue, and BT slot / LCD
brightness / RTC trim persisted. LED row-flash artifact and stray-glyph bug
fixed. BT at 0.042 ACK timeouts/frame (BT-mode typing burst). **2026-09-03:
the matrix publish fix** — the driver scans every row every ISR cycle, and the
worst per-key sampling gap fell from ~169 ms to ~5 ms
([docs/hardware.md](docs/hardware.md)). The row ISR measures 3,876/s with a
188 µs body (160 µs LED-only, 261 µs with the row scan) — **72.8% of the CPU** —
not the 18,750/s the timer implies, because it re-arms its counter at its end;
so the LED field rate is ~215 Hz and the main loop ~335 Hz. Health page 4
(`ak820health.py --isr`) measures it live. **`Fn`+`D` puts the health counters
on the LCD** for untethered use, with hold-to-reset
([docs/display.md](docs/display.md)). Everyday firmware measures **zero stalls
>= 25 ms**, the threshold below which a press cannot be lost — including
dismissing that debug page, which cost ~30 ms until `821431e3e4` staged its
restore (worst blit now 20 ms, the Caps-on paint).
Sub-second clock sync implemented the same day (phases 0-3):
host syncs land within ~3 ms, a USB-SOF loop disciplines the ILRC, offsets slew
instead of jumping — see [docs/clock.md](docs/clock.md). The repo was
restructured the same day into a clone-and-build package: `setup.sh` +
`deps.lock`, and a README that assumes no context.

## Build & flash

```sh
./setup.sh                  # idempotent; re-run after changing deps.lock
./build.sh daily            # or: instrumented (console + test hooks)
./flash.sh ak820pro-builds/out/<the printed artifact>
```

Works on macOS and on Windows from the **MSYS2 MinGW 64-bit shell** (only that
shell — `qmk_cli` refuses the others). Windows has four traps that all present
as something else, and every one of them costs an hour if you meet it cold:
CRLF checkouts make `build.sh` see a permanently dirty submodule; the venv must
be named `venv-mingw64` (use `$AK820_VENV`, never a literal `venv`); the xpack
arm toolchain must come **last** on `PATH` or its bundled DLLs make the native
gcc fail silently; and `USE_LIBUSB=1` is macOS-only — on Windows the bootloader
is plain HID, so no Zadig. All four are written up in
[docs/hardware.md](docs/hardware.md#building-and-flashing-on-windows-msys2).

Windows host agents are Scheduled Tasks under `\ak820pro\`. **As of
2026-09-06 now-playing is the Rust daemon** (`ak820 install` / `status` /
`uninstall`, task `AK820Pro-agent`, log and status file in
`%LOCALAPPDATA%\ak820pro\`), and **the clock is still the Python timekeeper**,
installed from **PowerShell**:
`hostagent/install-agents-windows.ps1 [-Status] [-Uninstall]`. That installer
also re-registers the Python now-playing task; it then exits at once because
the daemon holds its mutex, which is the intended outcome. The Python agents
need `venv-win` (native python) — `venv-mingw64` can never hold `winsdk`, so
`venv_bootstrap.py` picks the venv that *provides* the module, not the first
that exists. Two traps that fail silently: **ak820ctl must be linked static**
on Windows (a Scheduled Task has no MSYS2 on `PATH`), and it keys its
calibration cache off `getenv("HOME")`, which Windows does not set — the
timekeeper exports one agreed `HOME` so both see the same file.

`build.sh` enforces the submodule pin, structural binary checks and via.json /
enum sync; it refuses a dirty or off-pin tree. `flash.sh` preserves the VIA
keymap **and the RGB lighting** across the flash; it refuses to flash if the
keymap backup fails, and only warns if the lighting backup does. Bootloader is
`Fn`+`Esc`. **A flash erases the emulated EEPROM**: VIA keymap and RGB
effect/colour (both restored by flash.sh), BT slot, LCD brightness, persisted
RTC period (re-converges in ~4 min with the host attached — designed, not a
fault). The default keymap is the owner's VIA layout, regenerated with
`scripts/keymap_to_c.py`, never hand-edited.

⚠️ **The RGB restore is new as of 2026-09-06** —
`hostagent/ak820lighting.py` (`show` / `dump` / `restore`), backup at
`~/Documents/ak820pro-lighting.json`, over VIA's own lighting channel
`[0x08, 3, 1..4]`. Before it, every flash silently reverted the LEDs to
`keyboard.json`'s `rgb_matrix.default` — unnoticed through all nine flashes of
2026-09-03. Keeping that default near the owner's setup is still worth doing as
a backstop, because `--no-backup` and a missing backup file both fall back to
it. On Windows `ak820 lighting` reads the same values without enumerating HID.

## Working with VIA

Load `keyboards/a_jazz/ak820pro/via.json` at usevia.app → Settings → Show
Design tab → Load Draft Definition. The USB cable must be connected; **the
slider position does not matter** — raw-HID replies return over USB in any mode
(board commit 4b86d95014). Older notes demanding "wired mode" describe pre-fix
firmware.

- Layers: `WINBASE=0, WINFN=1, MACBASE=2, MACFN=3` — the mac/win dip switch
  picks the base, so per-key remaps usually need doing on both 0 and 2.
- **VIA's stored keymap overrides the firmware default** — a keycode newly bound
  in keymap.c will not appear if EEPROM already has that key assigned.
- **The `ak820pro_keycodes` enum is index-matched to via.json's
  `customKeycodes[]`. APPEND ONLY** — inserting shifts every later keycode and
  corrupts existing VIA keymaps (`scripts/check_via_sync.py` guards this).
- Keymap backup: `venv/bin/python hostagent/ak820keymap.py dump|restore|show`
  — raw dynamic-keymap buffer *and* encoders (a separate VIA command; skipping
  them silently drops the knob mapping).

## Stock Fn shortcuts (quick reference)

`Fn`+`Q/W/E` BT slots (tap = select, hold 2 s = pair) · `Fn`+`R` 2.4G ·
`Fn`+`←/→` hue · `Fn`+`↑/↓` brightness · `Fn`+`6/7` saturation · `Fn`+`X`
RGB on/off · `Fn`+`\` next effect · `Fn`+`-/=` speed (or 2nd colour on
Alphas/Mods) · `Fn`+`PgUp/PgDn` LCD brightness · `Fn`+`Home` LCD toggle ·
`Fn`+`Esc` bootloader · `Fn`+`Delete` ANIM_TOG · `Fn`+`C` clock format
(24h / 12h+AM-PM / off / date, persisted) · `Fn`+`D` debug page (tap
toggles, HOLD ~800 ms resets the health counters). BT keys are inert in
wired mode. `Fn`+`P` (pair) is unbound by default.

## Critical warnings (details in the docs)

- ⚠️ **The mode slider is a power-source switch** — most flips brown-out the MCU
  and lose all RAM state; there is no "off" position. Cold power-off =
  `cable` + unplug ~10 s. → [hardware.md](docs/hardware.md)
- ⚠️ **The bootloader looks exactly like a dead board.** Check for USB id
  `0x7140` before assuming a hang. → [hardware.md](docs/hardware.md)
- ⚠️ **`ak820ctl flash write` erases first** — verify `ak820ctl info` answers
  before provisioning, and power-cycle after (a CRC match does NOT mean the
  board renders the new assets). → [fonts-assets.md](docs/fonts-assets.md)
- ⚠️ **Asset ids are assigned by sorted filename** — renaming/adding files
  forces a coordinated rebuild + re-provision. Two filenames are deliberate
  lies; do not "fix" them. → [fonts-assets.md](docs/fonts-assets.md)
- ⚠️ **If Bluetooth regresses, check the interrupt priority table first**, not
  the ISR rate. → [leds.md](docs/leds.md)
- ⚠️ **Keyboard feels slow / drops keystrokes?** Read `Fn`+`D` first: `rowgap`
  (single digits = healthy) and `stall>25` (must be 0) say whether the firmware
  is even involved. If both are clean, **check the HOST** — a leftover poller
  starves everything else. (Contention, not exclusivity: the interface is
  shareable; replies are what collide. Measured 2026-09-05.)
  `hostagent/install-agents.sh --status`. → [hardware.md](docs/hardware.md)
- ⚠️ **Drawing to the LCD can eat keystrokes.** `lcd_draw_flash_text()` is
  synchronous, one LCD operation per glyph (~1.6 ms each); a full-screen
  `lcd_clear_rect()` blocks ~43 ms. Bulk drawing goes through the glyph queue,
  and big clears go in bands. Both rules were learned the hard way on
  2026-09-03. → [display.md](docs/display.md)
- ⚠️ **Never edit an installed LaunchAgent plist with PlistBuddy** — it silently
  strips the XML comments. Edit `hostagent/*.plist.in` and re-run the installer.
- ⚠️ **Multiple sessions**: coordinate via SendMessage, claim files, flash only
  provenance-named artifacts. → [hardware.md](docs/hardware.md)

## Where things live

**Firmware** — `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/` (branch
`ak820pro-jdlien`; git history is the change inventory).
`graphics/lcd_bus.h` holds the authoritative flash memory map;
`graphics/res/flash_assets.h` is generated by `mkraw.py` and is the one
firmware↔asset coupling; `PATCHES.md` documents the seven ChibiOS patches.
Four core files outside `keyboards/` carry local commits —
`drivers/led/sn32f2xx.c` + `.h` (ISR hook, periodticks fix, flash-window mux
blanking, flush lock), `quantum/rgb_matrix/rgb_matrix.c` (flush-allowed hook),
`platforms/chibios/.../wear_leveling_efl.c` (pre-write hook) — all
weak-hooked/no-op for other boards.

**Windows daemon (in progress)** — `ak820-agent/`, Rust, one direct dependency
(`windows` pinned `=0.62.2`; the blocking async spelling is `.join()`, not
`.get()`). Two binaries because a PE has one subsystem: `ak820-agent.exe` is
windows-subsystem so it can never flash a console, `ak820.exe` is a console CLI.
Built test-first; `cargo test` from that directory (305 tests + 9 integration).
`cargo build --release` gives static-CRT binaries (`.cargo/config.toml`); a
`v*` tag builds the Releases zip in CI (`.github/workflows/release.yml`).

The daemon side: `ak820 install [--in-place]` / `uninstall` / `status`, and
`ak820 --version` for which build and which protocols. The CLI is the evidence
for phases 0–2 — **every other command reads the board and never writes it**;
run these before touching the transport, they need no arguments and take under
a second each:

```sh
cd ak820-agent && cargo build            # then target/debug/ak820.exe
ak820 list            # 33 HID interfaces present, 5 of them this board's
ak820 list --caps     # the five collections; exactly one passes
ak820 info            # must equal `ak820ctl info` byte for byte
ak820 selftest        # budget guard, idle cancel, and recovery
ak820 watch [secs]    # narrate presence + what the drain discards
ak820 probe           # what SMTC sees; touches no keyboard at all
ak820 lighting        # RGB values read back off the board
ak820 health          # the firmware's counters, as ak820health.py prints them (--stalls --rows --isr --json --raw)
ak820 clock [--raw]   # the RTC, printed as `ak820ctl clock --read` prints it
```

`watch` is the one to reach for when something looks like contention: its drain
lines name whose traffic is landing on our handle. There is deliberately **no
CLI clock set**: one owner of the clock, or the lead learner is wrong. ⚠️ And
**`ak820 clock` refuses while the Python timekeeper task is running** — our
GET reply lands in its `ak820ctl`'s read and becomes one of *its* measurement
samples (the phase-2 audit's P1). `--anyway` accepts one possibly spoiled
sync; the other commands only print a note, because their replies fail the
C's version check rather than feed its learner.

⚠️ **The clock fixtures come from the C, not from reading the C.**
`scripts/clock_oracle.c` is the pinned `ak820ctl.c` clock code verbatim; its
tables feed `clock/cache.rs` and `clock/transaction.rs`, and its `decode` mode
renders a reply captured with `ak820 clock --raw` the way `ak820ctl clock
--read` would, which is the phase-2 gate. Build it with mingw64's gcc **first**
on `PATH` — otherwise gcc fails silently, the same xpack-DLL trap as `build.sh`.

⚠️ **Two generated files, one command regenerates both:**
`python scripts/gen_ascii_fold.py` writes `ak820-agent/src/text/fold_table.rs`
and `ak820-agent/tests/ascii_fold_parity.rs`. Never hand-edit either. The
generator checks the table against `ak820text.py`'s own `to_ascii` across all
1,112,064 scalar values and refuses to write if they disagree -- so a Python
carrying a different Unicode version fails loudly instead of drifting.

**Host tools** — `hostagent/` (`ak820text.py`, `nowplaying-macos.sh`,
`ak820keymap.py`, `ak820health.py`, `ak820-timekeeper.py`, the LaunchAgent
templates and `install-agents.sh`); `scripts/` (soak, bt_faults, consolelog,
check_via_sync); `time-util-ak820pro/` (`ak820ctl`, `assets/mkraw.py`,
`mkanim.py`); `SonixFlasherC/` (flasher, libusb build).

**Reference** — `ak820pro-builds/` (build artifacts in `out/`, the chibios patch
bundle, `UPSTREAM-CONTRIBUTIONS.md`); `assets-src/` (font/splash sources and
shipped-atlas copies). Hardware datasheets, `CH582F_PROTOCOL.md`, pinouts and
the stock firmware images live in [fpb/ajazz-ak820-pro](https://github.com/fpb/ajazz-ak820-pro)
— a citation, not a component; `setup.sh` deliberately does not clone it.

If a dependency clone looks mass-modified, check
`git diff --ignore-cr-at-eol --stat` before believing it (CRLF from the
original Windows transfer).
