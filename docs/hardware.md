# Hardware: power, flashing, reliability, and diagnostics

The board itself: the slider, the bootloader, building and flashing, the
watchdog and health counters, and the diagnostic recipes that have actually
cracked problems here.

## ⚠️ The mode slider is a POWER-SOURCE SWITCH

Positions are `bt / 2.4G / cable` — **there is no "off" position** (older
notes said bt/off/cable; wrong). In the wireless positions the MCU runs from
the BATTERY even with USB attached. Measured and named via the RSTST readout
(2026-09-01): most flips are an **LVD brownout reset** (rstst=0x05, LVD+SW,
no POR) — the rail sags during switchover.

| Flip | Reboots? |
|---|---|
| cable → BT | **no** (rides through — analog contact-timing luck, not design) |
| BT → cable | yes, every time |
| 2.4G ↔ anything | yes, both directions |

Consequences:

- **Every RAM state dies on a rebooting flip**: health counters, WDT
  consecutive-reset count, the in-RAM trim. You cannot capture a BT
  session's health counters by flipping to wired and reading. (Backlog: an
  on-LCD health readout.)
- **Cold power-off** = slider to `cable` + unplug ~10 s. The old "board is
  battery-backed, pulling the cable doesn't cold-boot it" is true only in
  the wireless positions.

## ⚠️ The bootloader looks EXACTLY like a dead board

No RGB, dark LCD, no typing. Check before assuming a hang:

```sh
ioreg -p IOUSB -w0 -l | grep -q '"idProduct" = 28992' && echo BOOTLOADER
```

| | bootloader | a real hang |
|---|---|---|
| USB id | `0x7140` | `0x8009` |
| `ak820ctl info` | interface absent | I/O timeout |
| fix | re-flash | power cycle |

USB product IDs in `ioreg` (decimal): 28992 = `0x7140` bootloader, 32777 =
`0x8009` QMK. `system_profiler SPUSBDataType` returns empty under the agent
sandbox — use `ioreg`.

Entering the bootloader: `Fn`+`Esc`, or `ESC` while plugging in. The pin
short is no longer needed; if it ever is again (rollback to stock): it is a
2-pin female header in the spacebar channel
(`ajazz-ak820-pro/img/bootloader-pins.jpg`); use SIM-eject tools, not
tweezers; the ISP pin is sampled only at power-on reset (cold-boot first);
bootloader mode is latched — remove the short once `0x7140` appears or the
post-flash reboot lands back in it.

## Building

```sh
build.sh daily          # console off — what the board lives on
build.sh instrumented   # console + LOOPGAP_INSTRUMENT + WDT_TEST_HOOKS
```

Writes a provenance-named binary to `ak820pro-builds/out/`
(`via-<flavor>-<hash>[-dirty]-<ts>.bin`) and enforces structural checks
(SP `0x20000400`, reset vector, USB descriptor `0C45:8009`), the ChibiOS
submodule pin, and via.json/enum sync (`scripts/check_via_sync.py`). It
REFUSES to build if `lib/chibios-contrib` is off the pinned commit or dirty.

**The ChibiOS patches are COMMITS on the submodule branch `ak820pro-patches`**
(jdlien/ChibiOS-Contrib fork; recovery bundle in `ak820pro-builds/`). Seven
patches — see `keyboards/a_jazz/ak820pro/PATCHES.md` (authoritative). A
`git checkout` in the submodule no longer destroys them, but the tree must
stay on that branch.

Do not compare builds byte-for-byte (not reproducible) and never compare
density against stock (~90% nonzero vs QMK's ~27% — a false alarm that
already happened once).

## Flashing

**Use `./flash.sh`** — it dumps the VIA keymap first (flashing erases the
emulated EEPROM) and restores it after; it refuses to flash if the backup
fails, and prints the binary's mtime so you can confirm it is YOUR build.
Flash the per-build artifact from `ak820pro-builds/out/`, never the shared
`$QMK_HOME/a_jazz_ak820pro_via.bin` path.

- Manual fallback (no keymap preservation):
  `./SonixFlasherC/sonixflasher --vidpid 0c45/7140 --file <bin>` — a good
  flash prints `Flash Verification Checksum: OK!` then `Rebooting.` and the
  board comes back as `0x8009` on its own.
- Expect one benign retry (`Code Option Table ... Received: 0xFFFF` →
  succeeds on attempt 2).
- **A flash also erases the kb-eeconfig block**: BT slot, LCD brightness and
  the persisted RTC period reset to defaults; the clock re-converges for
  ~10-15 min (designed — see [clock.md](clock.md)).
- Rollback to stock: `StockFWBinaries/AJAZZ_AK820PRO_PID_8009_V1.13_...bin`
  — **never v1.14** (it changes the PID to 8099 and AJAZZ's own drivers stop
  seeing the board). Requires the pin short; `Fn`+`Esc` disappears with QMK.
  The shipped v1.10 is gone permanently. **There is no way to dump firmware
  off the board.**
- `SonixFlasherC` MUST be built `make USE_LIBUSB=1` (`nm sonixflasher |
  grep -c libusb` > 0). On Tahoe the bootloader enumerates with **no HID
  node**, so a plain-hidapi build fails with "Could not open the device" —
  it is not a permissions problem; sudo/Input Monitoring don't help. The
  clone must stay on fpb's `fix_for_macos_tahoe` branch, and the branch
  alone is not sufficient — the flag is.

## Building and flashing on Windows (MSYS2)

Verified 2026-09-04 on Windows 11 Pro 26200: `setup.sh`, `build.sh` and the
structural checks all pass, and two clean builds of the same commit came out
byte-identical (`e504bf9d…`, 262,144 bytes).

**Run everything from the "MSYS2 MinGW 64-bit" shell** — not Git Bash, not
PowerShell, not the plain MSYS or UCRT64 shells. `setup.sh` refuses anything
else, because `qmk_cli` does. `setup.sh` installs the MSYS2 packages itself
(`make`, `gcc`, `pkg-config`, `hidapi`, `zsh` for build.sh's shebang, `vim`
for `xxd`, `diffutils` for `cmp`, and the `python-*` packages that carry
compiled extensions), then behaves exactly as it does on macOS.

Four Windows-only traps, all of which look like something else:

- ⚠️ **CRLF makes the build impossible, and says only "working tree is
  dirty".** Git-for-Windows is usually configured `core.autocrlf=true` and
  checks the clones out with CRLF. MSYS2 ships its **own** git with its own
  `HOME` (`/home/$USER`, not `C:/Users/$USER`), never sees that setting, and
  so reports every file as modified — 2,092 of them in `lib/chibios-contrib`
  alone. `build.sh` refuses a dirty submodule, so it can never succeed.
  `setup.sh`'s `normalize_eol` pins each clone to LF and renormalizes one that
  was checked out wrong, but only when line endings are the *sole* difference.
  `.gitattributes` pins this repo's own `*.sh` and `deps.lock`; a CRLF
  `deps.lock` reads a blank line as `"\r"` and makes setup.sh try to clone `""`.
- ⚠️ **The venv must be named `venv-mingw64`.** `qmk_cli/script_qmk.py` gates
  the whole CLI on `'mingw64' in sys.executable`, so a venv called `venv` is
  rejected with "It seems you are not using the MINGW64 terminal" even when it
  *is* MSYS2's own mingw64 python. `env.sh` exports `$AK820_VENV`; nothing
  should hardcode `venv` any more.
- ⚠️ **The arm toolchain goes LAST on `PATH`, not first.** The win32-x64 xpack
  build ships its own `libgcc_s_seh-1.dll`, `libstdc++-6.dll`,
  `libwinpthread-1.dll` and `libzstd.dll` alongside the compilers. Ahead of
  `/mingw64/bin` they shadow MSYS2's, and the **native** gcc's `cc1.exe` then
  fails to load — exiting non-zero while printing *nothing*, so `make` reports
  a bare `Error 1`. It breaks sonixflasher and ak820ctl while the firmware
  build, which wants those DLLs, keeps working. The `arm-none-eabi-*` names are
  unique, and Windows loads a program's DLLs from its own directory first, so
  putting the toolchain last costs nothing.
- ⚠️ **Do NOT build sonixflasher with `USE_LIBUSB=1` here.** That is the macOS
  Tahoe workaround. The Makefile's Windows branch links hidapi + setupapi, and
  the Sonix bootloader enumerates as an ordinary HID device — so there is **no
  Zadig/WinUSB driver swap** needed to flash, which is the step that makes a
  first flash on Windows look impossible.

`flash.sh` is cross-platform: it asks hidapi whether `0x7140` (bootloader) or
`0x8009` (QMK) is present rather than `ioreg`, and branches BSD/GNU `stat`
(GNU's `-f` means `--file-system`, so it *succeeds* with the wrong output
instead of failing through — do not probe it by trying one first).

### The host agents on Windows (Scheduled Tasks)

Ported and verified 2026-09-05. Installed with PowerShell, not the MSYS2 shell:

```powershell
powershell -ExecutionPolicy Bypass -File hostagent\install-agents-windows.ps1
                                                    [-Status] [-Uninstall]
```

Two per-user Scheduled Tasks under `\ak820pro\`, logging to
`%LOCALAPPDATA%\ak820pro\`. Three things about them are requirements rather
than preferences:

- They run as the **interactive user**, never SYSTEM and never "whether the
  user is logged on or not". SMTC media sessions belong to a user session, so a
  SYSTEM task sees no media at all.
- They launch under `pythonw.exe`, so no console flashes at every logon — which
  also means `stdout` goes nowhere and a crash would be invisible. Both agents
  therefore log to a file (`--log` for now-playing; the timekeeper knows its
  own path). A missing `import os` made now-playing exit 1 on launch with an
  empty log, and only `-Status`' `result 0x1` showed it at all.
- The settings explicitly set `-DontStopIfGoingOnBatteries`: the default stops
  the task on battery, which would silently kill clock sync on a laptop.
- ⚠️ **Every `subprocess` spawn needs `CREATE_NO_WINDOW`.** `ak820ctl` is a
  console program and the agent runs under `pythonw.exe`, which has none — so
  Windows allocates a fresh console per spawn and **a terminal window flashes
  up and takes focus**. `run_ctl()` fires 2-3 times per sync (`clock`, then
  `clock --read`), i.e. a blink every few minutes. A focus steal mid-keystroke
  can eat the keypress, so without this flag the agent for a *keyboard* drops
  keys at the OS level — a failure that looks exactly like the firmware faults
  the rest of this document is about, and is not one. The flag suppresses the
  console only; piped stdout/stderr still come back normally. `venv_bootstrap`
  carries it too, for the same reason (it probes `python.exe`).

**Why there are two venvs.** The now-playing agent reads SMTC through `winsdk`,
which has no mingw wheel and wants MSVC to build, so it cannot live in
`venv-mingw64`. Native CPython has a prebuilt wheel. Hence `venv-win`, created
by setup.sh step 2b from whatever native python it can find (`$AK820_WIN_PYTHON`,
then `py -3`, then pyenv-win / python.org). `venv_bootstrap.py` now picks the
venv that actually *provides* the module asked for, rather than the first that
exists — otherwise every agent re-exec landed in venv-mingw64, which can never
have winsdk.

**⚠️ ak820ctl must be linked statically on Windows.** A default mingw build
depends on `/mingw64/bin/libhidapi-0.dll` and dies with STATUS_DLL_NOT_FOUND
(exit `-1073741515`, no message) anywhere MSYS2 is not on `PATH` — which is
exactly how a Scheduled Task runs it. setup.sh passes `CFLAGS=-static` and a
static `HID_LIBS` as make command-line overrides, so the pinned clone is
untouched.

**⚠️ ak820ctl keys its calibration cache off `getenv("HOME")`**
(`ak820ctl.c:225`), falling back to `"."`. Windows sets no `HOME`, and MSYS2
sets a POSIX one a native binary cannot resolve — so ak820ctl would scatter
`.ak820ctl-cap` into whatever the working directory was while the timekeeper
read `%USERPROFILE%`. The two would never meet and the learned SOF bias would
silently never arrive. `run_ctl()` exports one agreed `HOME` for both.

### What the now-playing agent can see

Windows has a real OS-level media API — `GlobalSystemMediaTransportControlsSessionManager`
("SMTC", Win10 1809+), the same source the volume-key flyout reads. Apps
register a session and it is read uniformly, so there is **no per-app code**,
unlike the mac agent's AppleScript for Spotify and Music. Browsers register
sessions, so YouTube and web players work too.

`--probe` lists every session and is the answer to "why doesn't X show up?":

```
venv-win\Scripts\python.exe hostagent\nowplaying-windows.py --probe
```

Measured 2026-09-05:

| App | Session | Metadata | Timeline |
|---|---|---|---|
| foobar2000 2.24.6 (stock components) | yes | title + artist | **no** — 0s/0s |
| Apple Music (Store) | yes | yes | yes |

foobar2000 registering at all corrects the older advice that it needs a
plug-in; v2 gained this. But it publishes no timeline properties, so the
playback progress readout stays blank for foobar while text and icon work.
Checked while the session was actually `PLAYING`, not merely paused — it is a
real gap in foobar's SMTC integration, not a stale-session artifact. Recovering
a position for foobar specifically means going outside SMTC (its `foo_beefweb`
HTTP API exposes one), which buys back the timer at the cost of the first
piece of per-app code in this agent.
An app that registers nothing is invisible here and no change to the agent can
fix that — it is an app-side plug-in question.

**The icon can look inverted, and it is not the agent.** `KC_MEDIA_PLAY_PAUSE`
calls `display_toggle_play_icon()` (display.c:1684) so the glyph flips
instantly on the keypress instead of waiting for the host's next poll. With no
agent running nothing ever corrects that guess, so one media-key press leaves
it backwards until something re-asserts the truth. The agent does that within
one poll (3 s), and unconditionally every 30 s.

**The board is only as good as this PC's clock.** `ak820ctl clock` lands the
board within a few ms of the *host*; Windows' own w32time defaults to a
32768 s (~9 h) poll and was measured 20 ms off NTP here. Check with
`w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly`, and
measure the board itself with `hostagent/clock-phase.py`, which reports the
phase error directly (+15.9 ms, spread 1.5 ms, on the day this was written).
A large correction is **slewed, not jumped** — a 1.8 s error spends a while
visibly converging, which reads as "the clock is half a second slow".

## Watchdog + health (2026-09-01 hardening)

**Watchdog** (`watchdog.c`): SN_WDT off the ILRC, ~12 s timeout —
deliberately LONG, because this board has had *recoverable* 8 s stalls, and
a watchdog inside that envelope converts a crawl into a reset loop.
Hardware-confirmed: a wedge recovers in ~12.3 s. Boot accounting lives in a
linker-reserved `.ram7` region (top 16 B of SRAM) that survives everything
short of power loss; **3 consecutive WDT resets latch degraded mode** (WDT
stays off — the board still types, it just loses auto-recovery; a cold
power-off clears it). `bootloader_jump()` is overridden to `wdgStop` first,
so the bootloader can sit indefinitely. RSTST is captured at boot for the
breadcrumb, then **all sticky flags are cleared** so each boot names ITS
cause, not a union of history. A WDT reset shows `WDT reset xN` on the LCD
alert slot for 60 s.

**Health channel** (`health.c`, raw HID channel `0x13`): `HC_GET` 28-byte
counter snapshot (blit timeouts, loop-gap max, tx drops, rx malformed, …),
`HC_CONN` (link state/slot/battery/flags + boot RSTST + stored/live RTC
period). Instrumented builds add test hooks: `HC_STALL 0x7E` (wedge),
`HC_INJECT 0x7D` (fake RX frames), `HC_TXTRACE 0x7C`, `HC_DRIVE 0x7B`
(incl. RX mute). Host tools: `hostagent/ak820health.py`, `scripts/soak.py`,
`scripts/bt_faults.py` (18 assertions), `scripts/consolelog.sh`.

**Raw-HID host gotchas that cost real time:**

- **Writes must be 33 bytes** (report id + full 32-byte payload) — macOS
  silently drops shorter writes. This once made a wedge test appear to
  "recover in 0.3 s" (it never wedged).
- **VIA-protocol firmware echoes EVERY packet.** A "write-only" push on a
  shared handle queues an unread echo that desynchronises the next reply —
  drain before reading.

The full verification record is `history/hardening/HARDWARE-CHECKLIST.md` (all
items green, 2026-09-01); run-when-needed items live in
`plans/BACKLOG.md`.

## The hang, historically (fixed; recipes kept)

The "board dead until power cycle" class. Two distinct mechanisms were found;
both fixes are in and the watchdog now caps the blast radius of any sibling.

1. **Internal-flash program/erase racing the flash→LCD DMA blit** — ANY
   writer (eeconfig, VIA keymap writes, wear-levelling), not just RGB.
   Real fix: `backing_store_pre_write_hook()` (weak hook in
   `wear_leveling_efl.c`, called from `backing_store_unlock()`) — the
   board's override drains any in-flight blit first, and since both writes
   and blits start on the main loop, waiting is sufficient, not merely a
   narrowing. VIA key assignment was the reliable reproduction — retest with
   VIA, not RGB hammering. Supporting layers: `efl_ramtext` patch masks
   interrupts across the per-line program window (NOT sector erase — that
   would starve UART2); `RGB_MATRIX_EEPROM_WRITE_DELAY 750` + settle gate.
   `CORTEX_ENABLE_WFI_IDLE FALSE` was tried first and did NOT fix it (kept
   anyway, free).
2. **`blit_done` stuck false after a missed SPI0 completion IRQ** — the
   "hang" that was actually a CRAWL: every later wait burned its full ~1 s
   bound several times per housekeeping pass. A parked CPU cannot print
   `matrix scan frequency: 178`; the 8 s console gap FOLLOWED BY MORE OUTPUT
   was the tell. Fix: `lcd_blit_wait()` tears the bus down on timeout,
   bounded ~250 ms, prints `[lcd] blit timeout #N` — zero under load means
   the cause is gone; a climbing count means recovery is covering for it.

**Open item (2026-09-01):** one genuine watchdog reset (`WDT reset x1`,
health `wdt_fired_last_boot`) on the daily build, minutes after the first
use of the new `Fn`+`C` clock-format key. Never reproduced across ~90 min
of console-attached use with the profiled instrumented build (all four
modes, mode cycling, heavy typing, host-injected band-owner flips); health
showed nothing before or after. If it recurs, the `[stall]` line's site
attribution (below) is the first thing to read.

**Diagnostic recipe for any future hang:**

- `ak820ctl info` (raw-HID round-trip) is the liveness probe. USB
  enumeration and `ak820ctl list` answer from OS-cached descriptors and
  prove nothing.
- Timestamped console log, running BEFORE theorising:
  ```sh
  qmk console 2>&1 | while IFS= read -r l; do printf "%s %s\n" "$(date +%H:%M:%S)" "$l"; done >> log
  ```
  A gap followed by more output is a stall; a gap with nothing after it is a
  death. That one distinction redirected the whole 2026-08-30 investigation.

## ⚠️ Keyboard feels slow / drops keystrokes? RULE THE FIRMWARE IN OR OUT FIRST

**Press `Fn`+`D` and read two rows.** Since 2026-09-03 the board can answer this
itself, with no host and no cable:

- **`rowgap`** — worst gap between successive looks at one key row. Single digits
  is healthy. A press lasts 25–80 ms, so anything approaching 25 ms means a press
  can begin and end unseen. This read **156–169 ms** before the matrix publish
  fix, which is what silent keystroke loss looks like on this board.
- **`stall>25`** — main-loop stalls ≥ 25 ms, flash excluded. **Must be 0.**
  (Dismissing the debug page used to add ~30 ms and show here; fixed in
  `821431e3e4`, measured 0 across several dismissals.)
- **`worst`** — how big the largest gap was and what caused it: `flash` is a
  wear-levelling consolidation (understood, bounded), `blit` is the LCD, `i2c`
  the RTC bus. Anything unrecognised is worth reporting.

Hold `Fn`+`D` for ~800 ms to zero them, or `ak820health.py --reset` over the
cable. **If those rows are clean, the firmware is not losing your keystrokes** —
and that is a real answer, not a dead end. Go to the host:

2026-08-30: severe keystroke loss wired AND BT, diagnosed as a firmware
regression — it was **host-side process accumulation** (two `qmk console`
instances in a tight exclusive-access retry loop; 2,736 log lines of it).
The suspected firmware change A/B'd perfectly clean afterwards.

```sh
pgrep -fl "qmk console|ak820ctl|clock-phase"   # leftover pollers?
launchctl list | grep ak820                    # agents running?
```

Kill everything, then retest. Process lessons, both self-inflicted: never
flash three changes in one build (nothing to bisect), and never fix the
environment AND revert the firmware in one step (destroys the evidence).
**Reproduce first, bisect second.** For a suspected miss over BT, the
passive tripwire is `loop_gap_max` in the health counters (the `[stall]`
line on the instrumented build also carries `hk=` — the worst 10 Hz block —
and `site=name:ms`, the worst sub-task of that block: `LOOP_SITE()` in
`ak820pro.c`/`display.c`. ⚠️ **Sites live inside the 10 Hz block only.**
Wrapping the four per-pass calls too cost ~2 ms per pass on this MCU —
scan rate fell from ~270 Hz to ~175 Hz with the console attached and
keystrokes were felt to drop. An instrument that costs 2 ms a pass is the
fault it is looking for); instrumented
builds attribute stalls via `[stall]` prints.

## `scan_rate` is NOT a full-matrix rate — the one-row latch and its beat (FIXED)

*Historical as of 2026-09-03 — the mechanism below is fixed; see the end of
this section. Kept because it is the keystroke-loss mechanism this project
spent the longest failing to find, and because the reasoning that missed it
is worth not repeating.*

**The single most misleading number on this board.** `shared_matrix_scan_keys()`
(`drivers/led/sn32f2xx.c`) samples ONE row and immediately asserts
`matrix_scanned`; `matrix_scan_custom()` then copies the whole ROLLING matrix
and clears the latch. `scan_rate` counts `matrix_scan()` CALLS
(`quantum/keyboard.c:209`), so with 6 rows a given key is only freshly sampled
`scan_rate / 6` times a second.

The matrix scan is physically coupled to the RGB row multiplexing: only the row
the PWM is currently driving can be read. So the row sampled at each consume is
whichever one the PWM happens to be on.

**That produces an ALIASING BEAT.** Measured 2026-09-03:

| | |
|---|---|
| consumes | ~344/s (2.91 ms apart) |
| full row cycle | ~1044 Hz (0.96 ms) |
| rows advanced per consume | ~18.2 → **fractional drift ~0.2 rows** |
| samples per row | **57/s predicted, 57/s measured** |
| **worst gap between samples of ONE row** | **156-169 ms** |

The sampled row creeps: each row is sampled in a short burst, then ignored for
a beat period while the phase walks round the others. Row totals therefore look
perfectly FAIR (spread <4%) while individual gaps are ~9x the mean.

**Consequence: a key can go ~160 ms unsampled on an idle board with the main
loop running perfectly.** That is 2-6x the duration of a keypress. A press and
release inside that window is invisible to the matrix, to debounce, and to every
health counter — `count_ge_25ms` read **0** in all three runs that showed it.
This is a keystroke-loss mechanism that needs no stall at all, and it is
invisible to instrumentation that only watches the main loop.

Read it with `ak820health.py --rows` (`row_gap_max_ms`, `row_samples`).

### FIXED 2026-09-03 — scan every row, every cycle

`shared_matrix_scan_keys()` now scans straight into `shared_matrix` on every
genuine key-row transition instead of once per consume. `matrix_scanned` is
demoted from a scan GATE to a DIRTY FLAG, and the main loop's compare/copy/clear
runs under `chSysLock()` so an ISR write cannot land mid-copy. A `rows_seen` mask
withholds readiness until all six rows have been sampled once after boot.

| | before | after |
|---|---|---|
| worst gap between samples of one row | 156–169 ms | **5–7 ms** |
| samples per row per second | ~57 | **~217** |
| spread across the six rows over 12 s | 825–897 | **2599–2603** |
| `scan_rate` | 326–378 | 301–338 |
| `count_ge_25ms_nonflash` | 0 | 0 |

The spread collapsing from ~70 counts to ~4 is the signature that the aliasing is
gone: rows are sampled in strict rotation now, not phase-selected. `scan_rate`
dips slightly because the ISR does ~4x the scanning work per consume; that is the
intended trade and it is cheap at this magnitude.

**A full night of real use, 2026-09-03 22:25 → 09-04 11:14 (13 h):** 6,845
presses, `count_ge_25ms` **0**, `count_ge_25ms_nonflash` **0**, `row_gap_max_ms`
**10** (the post-flash keymap restore; typing never exceeded 7), worst
non-flash blit 21 ms, 3 flash writes after the restore. Against the 156–169 ms
gaps measured before the fix in 12-second windows, this is the claim that
matters: thirteen hours in which nothing on the board could have dropped a
keystroke.

**Debounce only starts working here.** `sym_defer_pk`'s 5 ms window previously
contained at most one sample of any given key, so it re-validated a stale value
it never re-read — a no-op. At 4.6 ms per-row sampling it can finally observe
stability. Bounce rejection on this board dates from this commit, not from
whenever `DEBOUNCE` was set.

The staging-buffer scheme originally proposed (accumulate a whole matrix in the
ISR, publish the complete snapshot) was dropped: scanning in place needs no
second buffer and no ISR `memcpy`, and the codex/gpt-5.6-sol audit preferred it.
See `plans/review-codex-sol-matrix-2026-09-03.md`.

### Typing does not degrade sampling; only flash does

Measured 2026-09-03, ~57 s of real typing after `--reset`, no LED or keymap
changes (so no wear-levelling writes):

```
loop_gap_max_ms   9        row_gap_max_ms   5  (row 2)
consumes          18453    row_samples      12524 x6, spread 1
raw_edges         587      cooked_changes   583
```

**5 ms under load is the same as 5 ms idle.** Scanning latency is set by the ISR
and is indifferent to what the main loop is doing, which is the point of moving
the publish into the ISR. The 15 ms high-water mark seen earlier was
flash-attributable: it appeared alongside `flash_writes 18` /
`flash_gap_max_ms 34`, and vanished in a window with no flash write in it.

So the only remaining path that can starve sampling is a flash-programming
window, where `rgb_callback` deliberately parks the mux (see the FLASH_PGM
branch in `sn32f2xx.c`). Bounded, understood, and it happens when adjusting LEDs
or the keymap rather than mid-sentence.

Two useful side results:

- **The ~217 samples/s/row figure is confirmed by an independent clock.**
  `consumes / scan_rate` gives 57 s; `row_samples / 217` gives 57.7 s. Two
  unrelated counters agreeing on elapsed time means the per-row rate is real,
  and that the ISR samples ~4.07 rows per main-loop consume (6 x 12524 / 18453).
- **The switches are clean.** 587 raw edges produced 583 cooked changes -- per-key
  debounce rejected 4 transitions in ~294 keypresses. There is no chatter on this
  board, which retires the "dodgy switches" hypothesis on evidence rather than on
  the argument that bounce is a solved problem.

### RESOLVED 2026-09-03 — the row ISR's own cost sets the row rate

The timer configuration says 4.8 MHz / 256 ticks = 18,750 ISR/s, the key row
advancing every third ISR → **1,041.7 samples/s per row**. Measured is ~215/s,
and the reason is not a clock bug: **`rgb_callback` re-arms the PWM counter at
its END** (`pwm_lld_change_counter(pwmp, UINT16_MAX)`), so its period is (ISR
body + ~53 µs of counter time + entry/exit) BY DESIGN, and the body — not the
timer — sets the rate. Health page 4 (firmware `d457105af7`, weak
`sn32f2xx_isr_enter_hook()`/`exit_hook()` around the callback body, read with
`ak820health.py --isr`) measures it directly. 20 s idle after `--reset`, host
agents stopped:

| | measured |
|---|---|
| ISR entries | **3,876/s** |
| ISR body, mean | 187.9 µs |
| ISR body, min (LED-only slot) | 160.0 µs |
| ISR body, max (slot carrying the row scan) | 261.3 µs |
| CPU share inside the body | **72.8%** |
| samples per row per second | 215.3 |
| `row_gap_max_ms` | 6 |
| `scan_rate` | 335–339 |
| ms timebase vs wall clock | 1.0001–1.0004 |

Consequences:

- **LED multiplexing alone is 62% of the CPU** (160 µs × 3,876/s): 15
  `pwmDisableChannel` + 15 `pwmEnableChannel` calls through the ChibiOS API at
  roughly 5 µs each, plus 18 row-pin writes. The row scan adds ~85–100 µs to one
  ISR in three (select/unselect go through `palSetLineMode`, slow on SN32):
  ~11% of the CPU.
- **1046 Hz was never achievable with this ISR body.** Even a zero-cost scan
  gives 160 + ~70 = 230 µs → ~4,350/s → ~242 Hz. Raising
  `SN32F2XX_RGB_PWM_FREQ` buys nothing; the only lever is a cheaper body
  (direct register writes instead of the API), which is a driver rewrite.
- **The publish fix lowered the field rate by about 8%.** The row scan used to
  run ~344 times/s (once per consume), now ~1,292. Solving the same arithmetic
  for the old scan rate gives ~4,220 ISR/s → ~235 Hz before vs 215 Hz after.
  Above flicker fusion either way and the owner reports none — but there was
  no before-measurement, so this is derived, not measured.
- **The main loop's ~335/s is what 27% of a 48 MHz M0 buys.** Main-loop cost
  still trades 1:1 against `scan_rate`; the ceiling is the ISR.
- **Observer effect: none measurable.** The uninstrumented build read 3,874
  ISR/s from `row_samples`; the instrumented one reads 3,876.
- **The ms timebase is not slow.** The "~1.2% slow" note in `docs/leds.md`
  predates the free-running CT16B5 system timer; `timebase_vs_wall` reads
  1.0001. Retracted there.

Debounce stays marginal at 4.6 ms sampling against a 5 ms window — about one
re-sample per window. Bounce has not been observed (4 rejections in ~294
presses, above), so leave `DEBOUNCE 5` alone.

## Scan rate IS the main-loop rate

Measured 2026-09-02: over 20.4 s, 7549 main-loop passes (371/s) against a
reported `scan_rate` of 372 Hz — **ratio 0.997**.

The matrix is scanned in the ROW ISR (`shared_matrix_scan_keys`,
`drivers/led/sn32f2xx.c`), which latches into `shared_matrix` and holds it until
`matrix_scan_custom()` consumes it behind the `matrix_scanned` gate. The ISR
produces faster than the loop consumes, so **the loop is the limit**.

Two consequences:

- **Any per-pass work costs scan rate 1:1.** This is the real basis for keeping
  instrumentation inside the 10 Hz block. (The "~2 ms per pass for timer reads"
  figure that originally justified that rule does not survive arithmetic —
  `timer_read32` is ~5-10 us — and was measured with the console attached,
  never isolated. The rule is right; its stated reason was not.)
- **`scan_rate` is a free, always-on regression metric** for main-loop cost.
  `scripts/soak.py` gates on the idle baseline being >= 320 Hz.

⚠️ **The noise floor is ~6%; do not chase drift inside it.** Measured
2026-09-02 at rest, LCD on: **356-378 Hz**, and two blocks taken five minutes
apart under IDENTICAL conditions differed by 5 Hz. Under soak load it drops to
~270.

A controlled A/B settled what the host agents cost: agents stopped 371-378
(mean ~374), agents running with music playing 366-375 (mean ~371), agents
stopped again 367-370 (mean ~369). **The agents cost ~3 Hz** — the earlier
guess that host-driven LCD traffic explained a ~16 Hz gap was WRONG, and the
A/B disproved it.

Historical figures of 390-400 (CLAUDE.md) and 375 (BACKLOG.md) record no
conditions, and the gap to today's readings is one to two sampling intervals
wide. **No regression is demonstrable**, and a flash bisect against these
numbers would be measuring noise. If a real regression is ever suspected, the
only valid method is an A/B of two builds back-to-back in ONE session with
many samples each — never a comparison against a recorded historical figure. `display_set_power(false)`
does NOT stop drawing — it only forces the backlight duty to 0 — so "LCD off" is
not a way to isolate display cost either.

## Input quirks (USB-level)

**Modified consumer keycodes race the endpoints** (`LSA(KC_VOLU)` on the
knob): keyboard and consumer reports go out on DIFFERENT USB endpoints with
no ordering guarantee, so the host can see the usage before the modifiers —
three different outcomes from one gesture is the tell. Fix:
`process_modified_consumer()` (`consumer_mod.c`) — register mods, flush,
wait 8 ms, then the usage; release unwinds in reverse. Fast-spin support:
hold the mods across a burst (150 ms, REAL mods not weak),
`ENCODER_MAP_KEY_DELAY 1` (10 made `wait_ms` block the loop and DROP
detents), `MAX_QUEUED_ENCODER_EVENTS 32` (default 4 is a ring with usable
depth 3; overflow drops, not delays). Encoder ceiling ~90-100 detents/s at
the ~390 Hz scan — accepted; do not buy headroom with the field rate. `LSA`
is on the Mac layers only (Alt+Shift is Windows' input-language hotkey).

**Caps Lock didn't capitalise (2026-08-28, resolved by reflash, cause
unknown):** macOS showed the caps indicator but letters stayed lowercase.
The NKRO-split theory was never confirmed. If it recurs: both shifts + `S`
dumps nkro/protocol/led state to console; `N` toggles NKRO; `H` lists magic
keys. Related fact that is NOT a bug: macOS tracks Caps per keyboard — the
laptop's and the AK820's Caps are independent.

## ⚠️ Two sessions cannot share this tree blindly

Live multi-session coordination works via `ListAgents`/`SendMessage` — use
it, and claim files before editing. Shared resources that conflict:

| Resource | Conflict |
|---|---|
| `$QMK_HOME/a_jazz_ak820pro_via.bin` | last compile wins, silently — flash provenance-named artifacts instead |
| `qmk console` | exclusive; a second instance spins in a retry loop |
| raw HID (`0xFF60`/`0x61`) | ak820ctl, VIA, the media poller and health scripts all want it |
| `flash_assets.bin` + `.h` | must change together or the panel renders garbage |
| `lib/chibios-contrib` | must stay on `ak820pro-patches` (build.sh enforces) |

The historical incident: one session's rebuild silently replaced another's
binary eleven seconds before a flash; the flash "succeeded" with the wrong
build. `stat` the binary before flashing — or better, only flash
`ak820pro-builds/out/` artifacts, which made the shared-path hazard moot.
