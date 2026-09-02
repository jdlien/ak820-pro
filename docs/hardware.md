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

The full verification record is `history/hardening-plan/HARDWARE-CHECKLIST.md` (all
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

## ⚠️ Keyboard feels slow / drops keystrokes? CHECK THE HOST FIRST

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
passive tripwire is `loop_gap_max` in the health counters; instrumented
builds attribute stalls via `[stall]` prints.

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
