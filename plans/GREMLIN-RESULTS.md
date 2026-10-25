# Gremlin results (Windows 11, the second AK820 Pro), from 2026-10-19

The Windows half of [`GREMLIN-HANDOFF-2026-10-19.md`](GREMLIN-HANDOFF-2026-10-19.md):
what this board and this PC measured, in the order it was done. Gremlin's
session writes this file; the Mac's session gets each result as it lands.

## 0. Bringing the board up to `de5450e487` (10-19)

Flashed 16:55, the **dev** build (`via-dev-de5450e4-20261019-165306.bin`,
token `0xa3e3804c`), from `8608c4f6-dirty` (09-05). Fixes in `9880f47` and
`30de86b`.

- **`setup.sh`: clean** from a real MinGW64 shell. Launched from Git Bash,
  MSYS2's bash loses `USERPROFILE`/`LOCALAPPDATA` and warns that `venv-win`
  cannot be made: an artifact of nesting one MSYS runtime in another, not the
  script. Launch MSYS2 from PowerShell or the Start menu.
- **`build.sh daily` and `dev`: clean.**
- **`flash.sh`, three snags, each fixed or documented:**
  1. Under MSYS2 `$HOME` is `C:\msys64\home\<user>`, with no `Documents`: the
     keymap dump crashed. Backups now go to the Windows profile's Documents.
  2. With the daemon running, the keymap backup failed ("unexpected reply 0x07
     to command 0x12": the daemon's `07 12 04` echo on our handle). The
     keymap tool's `xfer` now matches the request's first four bytes.
  3. A board on pre-battery firmware cannot answer the battery-log dump ("no
     reply to 0x0a"): the first flash from there needs `--no-battlog`
     (README).
- **No HID enumeration on Windows.** `ak820text.open_device` lists the board's
  path from the Configuration Manager (opens nothing) and opens only it;
  `ak820health.open_device` delegates there, so `ak820battery.py`,
  `ak820bootloader.py` and the health scripts are safe on Windows. (Before,
  `ak820text` cached the path per process: every one-shot tool still
  enumerated once.)
- **One clock owner:** `flash.sh` leaves the post-flash sync to a live daemon
  that owns the clock. Verified: one `sync (enumerated)`, -25.2 ms before,
  7 s after the board came back.
- **After the flash:** keymap and lighting restored and read back; no pass
  >= 25 ms; power mode reads Balanced.
- **LCD variant: the default** (not `fpb`). JD: the panel looks as the Mac's.
- ⚠️ **An older VIA keymap hides the power modes.** VIA's stored keymap
  overrides `keymap.c`, and JD's (saved before `PWR_MODE` existed) had
  `KC_TRNS` at `Fn`+`B` on both Fn layers, so the modes were unreachable.
  Bound by hand (`0x7E16` at row 4 col 6, layers 1 and 3) and the backup
  re-dumped. Any owner upgrading keeps their old map: worth a README line
  or a one-shot migration.

## The 2.4 GHz dongle: what it is (10-19)

`0C45:FDFD` (Sonix), five interfaces. Read with each collection opened at
access 0 (`HidP_GetCaps`), then a `GENERIC_WRITE` open closed unused:

| collection | usage page / usage | in / out / feature bytes | write-open |
|---|---|---|---|
| `MI_00` | `0x01`/`0x06` boot keyboard (`\KBD`) | 9 / **2** / 0 | **allowed** |
| `MI_01` | `0x01`/`0x02` mouse | 6 / 0 / 0 | allowed |
| `MI_02&Col01` | `0x0C`/`0x01` consumer | 3 / 0 / 0 | allowed |
| `MI_02&Col02` | `0x01`/`0x80` system control | 2 / 0 / 0 | allowed |
| `MI_02&Col03` | `0x01`/`0x06` NKRO keyboard (`\KBD`) | 16 / 0 / 0 | allowed |
| `MI_02&Col04` | `0x01`/`0x0E` | 9 / 0 / 0 | allowed |
| `MI_02&Col05` | `0xFFFF`/`0x01` | 4 / 0 / 0 | allowed |
| **`MI_03`** | **`0xFF60`/`0x61`, QMK raw HID's usage** | 33 / 33 / 0 | allowed |
| `MI_04` | `0xFF59`/`0x61` vendor | 65 / 65 / 0 | allowed |

- **Windows lets a user process open the dongle's boot keyboard for
  writing**, and its only output report is the LED byte (report id 0 plus one
  byte), but the open is all it gets: the writes are refused (section 2).
- **`MI_03` has QMK raw HID's usage on the dongle.** Probably the dongle's own
  port, not a tunnel: fpb's `CH582F_PROTOCOL.md` lists only `5A`/`5B`/`5C`
  from the module to the SN32, so a raw-HID payload has no frame to ride in.
  Listened 10 s on `MI_03` and `MI_04` (opened for read, nothing written): no
  unsolicited report on either. Nothing has been sent to them.

## 1. Deep sleep in 2.4G, on battery (10-19, ~17:00-17:20)

Slider on 2.4G, cable out. Read afterwards over the cable
(`ak820battery.py sleep`): **5 sleeps since the flash, 222 s asleep in all, no
blocker recorded, recovery done every time.**

| # | mode | woke on | notes |
|---|---|---|---|
| 1 | Balanced | key (Esc) | ~7 min idle, board dark; 146 s by the PCF, 130 counted; the key typed |
| 2 | Lights out | key | a burst, every character registered |
| 3 | Lights out | knob | the waking turn changed the volume |
| 4 | Lights out | key | a burst, all registered |
| 5 | Lights out | **charge** | the cable plugged in; 21 s by the PCF, 19 counted |

The dongle link was back for the first key every time. The RTC's ~10-13%
slow second asleep shows here too, and the PCF's count is the one kept.
JD thought the lights flashed at the first Lights-out wake; not seen at the
second, not confirmed. Lights out lights the screen 4 s for a band message
(`MESSAGE_WAKE_MS`), the likely candidate if it recurs.

## 2. Lock lights over 2.4G (10-19)

- **Real lock changes reach the board over 2.4G.** Scroll Lock tapped on and
  off from software (`keybd_event`): the board's 5A trace shows each change
  **three times, ~0-5 ms apart** (`0x05` x3, then `0x01` x3, >254 ms between).
  The dongle repeats every LED report; the receiver ignores repeats (a digit is
  a transition), so they cost nothing but UART time.
- **A user process cannot write the LED report through the dongle's keyboard
  collection.** `MI_00` opens with `GENERIC_WRITE`, but both `WriteFile` and
  `HidD_SetOutputReport` fail with error 1 (`ERROR_INVALID_FUNCTION`): the
  keyboard driver owns the collection's output. Nothing reached the board;
  the user's locks never moved (`scripts/win_ledwrite_probe.py`).
- ⚠️ **Toggling the real locks is out on JD's PC regardless:** an installed
  utility (Logitech's, JD thinks) shows every lock change on screen, so the
  plan's last-resort route would flash it per symbol. Settles codex's
  finding 19 against that route, for this machine at least.
- ✅ **The route that works: `IOCTL_KEYBOARD_SET_INDICATORS` on the
  dongle's keyboard-class interface**, unprivileged. The interface comes from
  the Configuration Manager's `GUID_DEVINTERFACE_KEYBOARD` list
  (`\\?\HID#VID_0C45&PID_FDFD&MI_00#...#{884b96c3-...}`), opened with access
  0 (read is refused, error 5). Setting Scroll reached the board (`0x05` x3,
  then `0x01` x3) and **Windows' lock state never moved** (`GetKeyState`
  before and after), so nothing watching the system's locks sees it. It is
  per device: only the dongle's unit (5) is addressed.
  - `IOCTL_KEYBOARD_QUERY_INDICATORS` answers `0x0000` with Num on: the class
    driver's copy is stale, so a sender must build the flags from
    `GetKeyState`, never from the query, or it turns the user's Num off.
  - **Kana is refused**, NTSTATUS `0xC0110004` (`HIDP_STATUS_USAGE_NOT_FOUND`):
    the dongle's descriptor has no Kana LED. Padding bits cannot be expressed
    in `LedFlags` at all. **So Windows over 2.4G has Num and Scroll: profile
    P0** (Caps never).
  - **Speed** (16 Scroll changes a run, the 5A ring's 52 frames read after):
    issued back to back (each call returns in ~0.1 ms) they merge, 6 of 16
    arrived; **spaced 20, 12, 8, 5 or 3 ms, 16 of 16 every run**, two runs
    each, change to change 5-10 ms on the board at the tighter spacings, so
    **~125 changes/s**, about 4x BLE's 32/s. P0 at that rate is ~200 bit/s, a
    30-character title in ~1.5 s. Each change still arrives 3x (~375 UART
    frames/s at the top rate): afterwards no pass >= 25 ms, no UART overrun,
    framing or parity error.
  - Not yet: frames through the receiver (`ledchannel_test.py frames`'s P0
    on this route), the 20-ms-and-under error rate over thousands of
    changes, and what the user's own Num/Scroll press does mid-frame.
- **The 2.4G link's ACK timeouts so far:** 109 in 5,009 frames (0.022 a
  frame), typing included, against BT's 0.042 on record. Not yet a controlled
  burst.

## 3. P0 frames through the receiver, from Windows over 2.4G (10-19)

`scripts/ledchannel_test.py frames` with its Windows sender (the keyboard-class
IOCTL, P0 only, the user's real locks as the baseline, the warm-up on Num):
six frames a run, 20-37-byte texts, 178 writes for the longest, each checked
byte for byte against what `lockchan.c` committed. Results in
`history/ledchannel-2026-10-19-gremlin*/`.

| write spacing | committed exactly | anchor to commit | UART overruns |
|---|---|---|---|
| 3 ms | 0/6 (gap aborts) | - | +1 |
| 5 ms | 0/6 (gap aborts) | - | +0 |
| 6 ms | 0/6 | - | +0 |
| **7 ms** | **6/6** | 1141-1655 ms | +0 |
| 8 ms (twice) | 6/6, 6/6 | 1217-1768 ms | +1, +2 |
| 10 ms | 6/6 | 1515-2194 ms | +0 |
| 12 ms | 6/6 | 1821-2616 ms | +1 |

- **A cliff between 6 and 7 ms:** closer than that the dongle merges changes,
  a merged change is a lost digit, and the frame dies on the 500 ms gap.
  (Scroll alone alternating survived 3 ms in section 2: one bit flipping
  cannot show a merge as anything but a missing pair.) **A sender should use
  10 ms** for margin: a 30-character title in ~2 s, against P0's 4.4-5.6 s
  over BLE on the Mac and P3's 1.5-2.2 s there.
- No pass >= 25 ms in any run.
- ⚠️ **UART overruns: +0 to +2 a run** (~1 minute each), well above the
  link's ~1-2 an hour. Each change arrives three times, so a frame is ~530
  module frames in ~2 s; the overruns did not cost a frame here (the
  repeats cover a lost copy), but they are the link's known weakness and a
  long run should count them.

## 4. The RX tap (firmware branch `gremlin/rx-tap`, 10-19)

The parser's 3-byte window drops any byte outside a 5A/5B/5C frame or an ACK
without a trace, so whether the dongle's `FF60` interface relays to the board
could not be told from "no reply". The tap: a dev-only 260-byte ring of every
raw module byte while armed, `HC_DEVHOOK` ops 15-16, `scripts/devhook.py rxtap
arm | stop | json` (the read splits frames, ACKs and the rest).

**Two codex reviews of `f2e22aae`**, the same prompt
([`review-prompt-rx-tap.txt`](review-prompt-rx-tap.txt)): the Mac's
([verbatim](review-codex-rx-tap-2026-10-19.md)) and gremlin's
([verbatim](review-codex-rx-tap-2026-10-19-gremlin.md)). **Neither has a
must-fix.** Dispositions:

| finding | both reviews | disposition |
|---|---|---|
| The count's 2^32 rollover skips slots 256-259 (2^32 % 260 = 256) | should-fix | **Fixed in `4ee56290`:** the slot is its own index, wrapping at 260; the count is only a total. It also drops the M0's software modulo per byte. |
| Injected bytes reach the tap in a build with both `WDT_TEST_HOOKS` and `AK820_DEV_HOOKS` | Mac: should-fix; gremlin: note (no standard flavour combines them) | **Fixed in `4ee56290`:** the tap sits in the real, unmuted read's branch only. |
| Zero added overruns cannot be certified statically; the ring holds ~231 ms at the burst rate | note | **Agreed.** Captures stop before reading, and the probes are short and spaced; overruns are counted beside every capture. |

Bounds, header layout, placement (each real byte once, before the parser),
main-loop-only access and the dev-only guards: passed by both.

## 5. ⚡ The dongle relays raw HID to the board: module frame `81` (10-19, 17:45)

Flashed `via-dev-4ee56290` (the RX tap, hands-free through the dev build's
jump). Control first: two Scroll changes through the keyboard-class route
showed in the tap as `5a 05 5f` x3, `5a 01 5b` x3, beside an ACK and a `5c`.

Then, the tap armed, one 32-byte output report on the dongle's `MI_03`
(`FF60`/`61`) each, 2 s of baseline before:

```
sent 01 + 31 zeros        -> board: 81 01 00 .. 00 82            (34 bytes)
sent 07 13 01 + 29 zeros  -> board: 81 07 13 01 00 .. 00 9c      (34 bytes)
```

**A new module-to-SN32 frame: `81`, the 32-byte report verbatim, then a sum
by the same rule as `5A`/`5B`/`5C`** (`(0x81 + Σ payload) & 0xFF`). Both
arrived intact; the parser's 3-byte window drops them, which is why it was
never seen. No reply reached the host (our firmware does not handle `81`).
No overrun, no stall.

So **host-to-board raw HID over 2.4G exists**, with the full 32-byte report.
Unknown: the reverse (a board-to-module frame the dongle returns on `MI_03`'s
input report: look in the stock firmware first), the latency and loss of `81`,
and whether BLE has an equivalent.

## 6. Raw HID over 2.4G, stage 2: two-way, dispatched, passing (10-19, ~22:30)

The board now answers allow-listed raw-HID requests over the dongle (text,
health reads) with the same reply it gives on USB plus a CRC-checked receipt.
On gremlin, from Windows: every text write read back from the board's stored
state, every health read matching USB, every NAK provoked, and 999 of 1000 in
a back-to-back stream (the one loss the UART-overrun taint the board counted),
RTT median 26 ms, no pass >= 25 ms, no keyboard frame lost. Design, five plan
revisions through codex, the implementation review and the numbers:
`plans/RAWHID-24G-PLAN.md`, from "Stage 2: dispatch, as designed".
Follow-up: ~1 in 4 transactions costs a 10 ms pass (latency, not loss).

## 7. Envelope v2, the daemon over the dongle, and the cable-out test (10-19/20)

**Firmware.** Envelope v2 (no request an older board can misread), R4-1 (a
restarted host starts afresh; a response unsent after 250 ms is dropped), the
long clock kept by a virtual timer (codex's must-fix: a stall could hold a
response past the host's quiet), and two dev hooks for its regressions. Three
codex passes, flashed on gremlin 23:33 10-19 (`0ae4cf8c`): `win_raw81_s2.py
all` passes whole, stream 1000/1000 (`history/raw81-v2-gremlin-0ae4cf8c.json`).
`ak820pro-jdlien` fast-forwarded to it, then to the Mac's UART-latency build
on top (`ce70c8da`), which gremlin also passes (00:51 10-20,
`history/raw81-v2-gremlin-ce70c8da.json`; passes >= 10 ms +39 against +11, a
threshold count at slow passes of 10-12 ms, being followed up).

**The daemon** (`ak820-agent`, `--radio`): now-playing over the dongle when the
USB opener says the board is absent. Three codex passes (the implementation
review held it twice on ownership: a stuck transfer's lock, the quiet's start,
and boundary tests), 392 tests. Live on gremlin with the cable in
(`--radio-only`): qualified 3 s after the lock, the readout every tick, the
board counting 11 dispatched in 30 s and nothing lost.

**The cable-out test ran on the Mac** (JD, 10-20: its bench drops USB data
with no hands; `history/uart-latency-20261020/radio-cableout.{json,log}`,
daemon `v0.1.1-628-g5a9bac1` installed `--clock --radio`):
- cable in: `transport=usb`, `radio=off`;
- USB data off (01:06:57): `radio=qualified`, `transport=radio` after 6.6 s
  (the 3 s quiet, then the next tick); held 60 s, the keepalive 32 s later,
  no failure, incomplete, silence or error;
- USB data on (01:08:04): `radio=off` after 3.6 s, `transport=usb` the same
  tick; the band read back over op 18 ("Lucy In Disguise" / "Passing
  Mirrors", paused) matched `media_last_text`; the board's op 17 counters
  still for 8 s after; stale, busy, taint, drops and expiries +0 throughout.

Left for JD: a track change while on the radio, the deep-sleep backoff, and
the same cable-out on gremlin (Windows) by hand.

## 8. P0 frames from Windows over Bluetooth (10-20, ~14:45)

Board on `466aa04636` (dev, token `0x43ac66bd`), BT slot 1, the cable in for
the devhook reads only (in BT mode the board ignores USB LED reports). The
sender is the 2.4G one (section 3) pointed at the **BLE keyboard's
keyboard-class interface**, `HID#{00001812-...}_Dev_VID&010c45_PID&fefe_..._Col01`,
from the Configuration Manager's `GUID_DEVINTERFACE_KEYBOARD` list (no HID
enumeration; `AK820_WIN_KBD` picks it in `ledchannel_test.py`). The daemon
was stopped for the runs. Results in `history/ledchannel-2026-10-20-gremlin-ble-*/`.

- **`IOCTL_KEYBOARD_SET_INDICATORS` reaches the board over BLE**, access 0,
  unprivileged: one Scroll change and back arrived as `0x05` x3 then `0x01`
  x3, 0-5 ms apart, as over the dongle. So the Windows route is the same
  call on both radios, P0 only (Num and Scroll).

| write spacing | committed exactly | anchor to commit |
|---|---|---|
| 40 ms | 6/6 | 5956-8709 ms |
| 32 ms | 6/6 | 4863-7097 ms |
| 24 ms | 6/6 | 3669-5308 ms |
| 16 ms | 6/6 | 2506-3572 ms |
| **10 ms** | **6/6** | **1579-2334 ms** |
| 7 ms | 2/6 (gap and CRC aborts) | 1265-1473 ms |
| 5 ms | 0/6 (range and CRC aborts) | - |
| 3 ms | 0/6 | - |

- **Windows' BLE is ~3x the Mac's**: 10 ms a change holds, where the Mac's
  writes take ~30 ms each. The cliff is between 7 and 10 ms, as the
  dongle's (6-7 ms): closer, changes merge, digits are lost, and the frame
  dies on a gap, a range check or its CRC. **No frame committed wrong.**
- No pass >= 25 ms in any run; UART overruns +3 only in the 3 ms run.
- **A sender should use 16 ms over BLE** (a 20-37-byte P0 frame in 2.5-3.6 s),
  10 ms over the dongle (section 3), until a longer error-rate run says
  closer is safe.

## 9. The user's locks on a sender thread (10-20, R2-2)

`scripts/win_keystate_probe.py`, for the lock-light sender's freshness
contract (`LOCK-LED-CHANNEL-PLAN.md`, R2-2):

- **Software toggles** (Scroll Lock by `SendInput` from the main thread, read
  on a second thread every 5 ms, 3 rounds each): plain `GetKeyState` on a
  thread with no message queue saw the change in **1-8 ms**; with a
  `PeekMessage` before each read, 4 ms; **`GetKeyboardState` never** (1.5 s).
- **JD's real Caps Lock presses on the AK820 over BT** (watch mode, plain
  `GetKeyState`, second thread): all 8 changes seen at his pace (~200 ms
  apart), ending on his final state.
- **JD's real Scroll Lock presses** (Fn+[ on the AK820 over BT, mapped in
  VIA): all 6 changes seen, ~1 s apart.
- So the sender reads the locks with plain `GetKeyState` on its own thread.
  Not yet: Num from a real keyboard (the AK820 has no Num key),
  another keyboard, and the daemon's own context (a Task Scheduler process in
  the session, not a console): the soak checks those.

## 10. The configuration menu's S0 on gremlin's board (10-23)

Firmware `gremlin/config-menu` `4b899118`, after codex's code review and three
verifications ([`review-codex-config-menu-s0-code-2026-10-23.md`](review-codex-config-menu-s0-code-2026-10-23.md)):
the dev build (token `0x45c1f7b6`), and the `devfault` build (token `0xdb007df3`)
for A7. The cases are [`CONFIG-MENU-S0-BOARD-TESTS.md`](CONFIG-MENU-S0-BOARD-TESTS.md);
the raw results are in `history/config-menu-s0-20261023/`.

**Passed, no hands** (`scripts/menu_s0_accept.py`, `scripts/menu_s0_fault.py`):

| Case | Result |
|---|---|
| A1 | unknown sub 10: byte 0 `0xFF`; sub 5: `0x07`, status 0. The short-report guard by reading the source |
| A3 | the probe: gq 3, lq 1 before the handoff, 0 and 0 after; the restore to DONE, gen 1 to 2 |
| A5 | the arm's live record with the fixture open: blockers `0x4002` (USB, menu); closed: `0x0002` |
| A6 | `superseded` on the first try: the loss dropped at the boundary |
| A8 | the startup restore interrupted in its CLEAR: WAITING under Fn+D, then a fresh restore (gen 4 to 6) to DONE |
| A7 | the real lost completion (HC_BLITFAULT), under the dashboard, the fixture, Health and Camera. N=1: one timeout, the retry succeeded, no loss. N=2: two timeouts and a loss; the dashboard repaired to the next generation, the fixture repainted, the debug pages kept. `invariant_fail` 0 throughout. **The animation's case not run:** no host op starts it |

**The workload, as a smoke run only** (two repeats, 10 s of the dashboard, no
track): 100 steps in 7 s, no failures (92 done, 8 holds cancelled by their
own Back), ge25 0, `invariant_fail` 0, the dashboard restored at the end. ge10
rose by 161 in ~20 s while the fixture repainted without pause: S1's paint
budget is where that's measured and bounded.

**A11 in full** (23:48 and 23:54, Apple Music playing, run twice): ten repeats
of the 50 steps in 34 s, then 300 s of the dashboard. **Every board criterion
met, both runs:** 460 done and 40 cancelled (the holds' own Back), ge25 0,
`invariant_fail` 0, the dashboard DONE at the end (gen 42 to 83), the loop's
worst pass 20 ms. **The script still exits 1, on its media gate:** its last
sample found SMTC 12 s and then 18 s stale, against a 10 s bar. That was
Windows' media service, not the board: Apple Music's session answered one
poll in ~25 s, where the daemon's poll is every 3 s (`smtc_polls` +1 between
status writes 25 s apart, `smtc_failures` 0). The now-playing pushes kept
arriving every 30 s, the track never changed, and JD had it playing. **Taken
as a pass, with the gate's miss recorded** (Warren's call as the plan's owner);
a stricter rerun wants a player whose SMTC session answers promptly. Raw:
`a11-session.json`, `a11-session-run1-smtc-stale.json`.

**A12:** after A11, 632 B free on the interrupt stack (648 at the build's
start) and 1,216 on the main. The heap gap is dev 360 B, daily 2,472 and
devfault 264. Passes.

**⚠️ The fixture's painting dims the RGB by ~19%.** JD saw the keyboard's
lights dim while A11 flashed the patterns. `scripts/menu_s0_ledrate.py`
reads health page 4 (the row ISR) in 5 s windows (`ledrate.json`):

| Window | Row ISR/s | ISR share of the CPU | ge10 in 5 s | Main-loop passes/s |
|---|---|---|---|---|
| Dashboard | 3,726 | 73.7% | 0 | 215 |
| The fixture open, still | 3,726 | 73.7% | 0 | 209 |
| The fixture toggling A and B | **3,033** | 60.7% | **+243** | 110 |

The ISR's own time is unchanged (198 to 200 us), so it isn't slower: its start
is held off, ~62 us a row. The fixture's colour fills are `lcd_fill_rect`,
a `spiSend` through SPI0's **FIFO interrupt** (`spi_fifo_pump.diff`), which
sits at priority 3 beside the row ISR. Since the row ISR re-arms its counter
at its end, every delay to its start is a longer dark gap for every row. The
dashboard's glyphs go by flash-to-LCD DMA and cost the ISR nothing. Every
ge10 in A11 came from the fixture's repaints: the dashboard's 300 s added
none. **For S1:** the real menu fills rows too (the cursor, half or full
rows), so its paint path needs a budget measured in row ISR/s as well as
in milliseconds. Options to weigh: fills by DMA, fills spread across passes,
smaller fill areas. The banded clears of the restore and the Fn+D page use
the same path and will dim briefly too, unmeasured.

**A13 and A2, photographed by JD** (10-24, 08:08-08:13,
`scripts/menu_s0_photos.py`, which holds each frame until told to go on;
`photos.json`):
- **A13 passes.** Each photo matches its expected frame cell for cell:
  - fixture-B-stop13: "FIXTURE B", row 0 in B (magenta/cyan), row 1's
    first half repainted (yellow), and rows 2-7 still A's. Row 2 is
    magenta/cyan in both patterns, so it reads as B. Corrected from "rows
    0-2 in B" (codex, 10-24); the reference frame always agreed;
  - fixture-A, and A again after the stop: identical, as they should be;
  - F2: the 4×4 grid in table order.

  The board's state agreed at every frame: the stop held through the shot,
  the fixture stayed open, `invariant_fail` 0. The 1-pixel separator and
  the scrollbar are too thin to resolve in a phone photo, so they rest on
  the host test.
- **A2 passes.** The Camera page at 08:12:49 and at 08:13:23, 3 s and 37 s
  after the injected loss (losses +1, owner DEBUG). Both show the clock
  line's colons, `V`, `%`, `5C` and `@`. There's no photo from before the
  loss, but every conditional field is present in both photos, which is
  stronger.
- **The runner's first try lost frame 2:** the fixture closed on its idle
  timer, because a pattern change (sub 0) isn't input and the keep-alive
  clock restarted at each frame. Fixed with one clock across all the frames;
  the rerun held frame 2 for 56 s.
- **⚠️ A ghost of "100%"** shows faintly in the bottom-right dark grey cells
  (A's row 7, F2's tile 15). It's at the dashboard's status-row battery
  percentage (y 109-123), which gremlin's screen shows all day on USB. It's
  faint and sits under a solid fill, so it's most likely the panel's image
  retention, not a missed paint: a missed paint would show the text at full
  white. Worth knowing for S1, whose menu will sit on that area.
- The photos aren't in the repo: the phone's JPEGs carry location data, and
  the crop that would have stripped it hung gremlin, which needed a hard
  power-off.

**A9 passes** (10-24, 08:20-08:27, JD's hands). Gremlin's keymap has no
animation key: its Fn+Delete is `SCR_TOG` (JD's first press turned the
backlight off), so `ANIM_TOG` (`0x7E11`) went temporarily onto Fn+F12 (layer 1,
r0 c12, was transparent; read back). Fn+F12 under the Fn+D page: nothing
changed; the owner stayed DEBUG, no restore, `invariant_fail` 0. Fn+F12 with
the fixture open (held by keep-alive): nothing changed; MENU and OPEN
throughout, `invariant_fail` 0. **The limit:** gremlin's animation slot is
empty, so a refusal and an empty slot's no-op look alike from outside. The
order in `anim_toggle()` (`display_anim_admissible()` before
`anim_read_header()`) is what makes it a refusal, and the host tests cover
the predicate. **Fn+F12 stays bound** until S0's hands-on cases are done;
gremlin's keymap from before is saved.

**A10, all but one case passes** (10-24, 08:30-08:39, JD's hands; armed by
sub 6 and logged by `scripts/menu_s0_watch.py`, `a10-watch.json`). The knob
is Mute and volume on gremlin, so a leaked press or turn shows as Windows'
pop-up. Every case: no pop-up, no stuck key, the capture bits back to 0,
dropped 0, `invariant_fail` 0.
- **Fn+knob with Fn released first:** opened; the knob's release consumed.
- **The idle close:** 24 s after the last input, timed by the log.
- **Turns:** the cursor stepped both ways and wrapped.
- **A hold:** the Back closed on the hold, still down; its release consumed
  under the dashboard (a hold across a close).
- **A timeout while held:** opened, held 30 s; closed at 24 s with the knob
  down; the release consumed.
- **The knob remapped in VIA, layer 0:** the menu opened and closed each time.
  - one-shot Shift (`0x52A2`): the next letters lowercase;
  - mod-tap Shift/Mute (`0x22A8`): lowercase, no Mute;
  - layer-tap Fn/Mute (`0x41A8`): a plain tap afterwards gave Mute (the
    correct result), so the Fn layer wasn't left on.

  The knob is back to Mute (`0x00A8`).
- **A pending tap-hold on another key** (09:26-09:29; F12 as mod-tap
  Shift/F12, `0x2245`, held while Fn+knob was pressed;
  `a10-watch-taphold.json`). Safe: ten opens and closes, every capture back
  to 0, nothing dropped, `invariant_fail` 0, the letters after lowercase. **⚠️
  But the opener misses inside the tapping term.** Pressed within ~200 ms of
  F12, Fn+knob didn't open the menu. With a pause it always did. The cause:
  the capture runs in `pre_process_record_kb`, before QMK's tapping buffer,
  and judges Fn by `layer_state`. Fn's own press is still held in that buffer
  behind the undecided F12, so the knob reads as Fn-less and is forwarded.
  QMK then replays it after F12 resolves. Nothing sticks; the opener just
  doesn't fire. A finding for C2 (the build plan's "Open" item 5). F12 is
  back to plain F12 (`0x0045`); the opener is disarmed.
- **⚠️ JD: every turn, and the opening, visibly dips the keyboard's LEDs.**
  It's the fill finding above, now a requirement for S1 (the build plan's
  "Open" item 4).

**The LED dimming, fixed in a prototype** (10-24, firmware `gremlin/fill-poll`
`f2b107be`, dev, token `0xc852966f`, heap gap 368 B; codex:
[`review-codex-spi0-poll-2026-10-24.md`](review-codex-spi0-poll-2026-10-24.md),
safe as it was, its three should-fixes done before the flash). Bulk SPI0
sends (fills, RAM blits, the panel-order stream) are polled with the FIFO
interrupt masked, so the row ISR preempts them instead of queueing behind
them. Same script and checks before and after, every repaint completed,
`invariant_fail` 0:

| Window | `4b899118` row ISR/s | `f2b107be` row ISR/s |
|---|---|---|
| Dashboard | 3,725 | 3,726 |
| The fixture toggling A and B | 3,039 / 3,062 (-18%) | **3,678 / 3,678 (-1.3%)** |
| Fn+D in / Camera / out (1 s) | 3,714 / 3,721 / 3,713 | 3,710 / 3,720 / 3,721 |
| Toggles in 5 s | 14 | 12 |
| ge25 | 0 | 0 |

**The cost:** a repaint takes ~15% longer in wall time (12 toggles in 5 s
against 14), and the worst main-loop pass since the flash is **23 ms** (20
before). That's under 25 ms but closer. The fixture paints a whole row or
tile (up to 2,048 bytes) in one pass, so S1 splits big fills across passes
(codex's point 4).

**JD by eye on the keyboard on gremlin (09:37): "looks way better now... No flicker", and the knob "decently responsive". 88 menu state changes, `invariant_fail` 0.**

**A11's workload on `f2b107be`** (09:45, no track playing, so the media gate
failed by design; `soak-f2b107be-*.json`):
- 10×50 steps (460 done, 40 cancelled), then 300 s of the dashboard;
- ge25 0, `invariant_fail` 0, the dashboard DONE at the end;
- stacks 648 and 1,216 B free.

**⚠️ But the worst pass since the flash is now 24 ms,** one under the line.
The per-pass byte bound (the build plan's revision 7, C4's
`MENU_PASS_BYTES`) is S1's first job, not an option.

**A4 passes** (10-24, ~10:00, JD's hands, on `f2b107be`). The setup: the
cable out, the slider on BT, Lights out (Fn+B), and a deep sleep. Then Fn+D
woke it straight onto the Fn+D page, and the cable went back in.
- **The sleep page** (`a4-sleep.json`): 1 sleep, 339 s by the PCF, woke on a
  key; the recovery done, with `pcf acq_done reattach usb_20s slept` valid
  and **nothing timed out**, so the display's wake hold was released, not
  timed out at `RC_HOLD_MAX_MS`.
- **The owner:** DEBUG afterwards, `invariant_fail` 0; the dashboard restored
  by op 1 (gen 2).
- The keyboard on gremlin is still in Lights out; JD will cycle it back.

**S0's board cases are complete:** A1-A13 pass. The limits are recorded with
their cases:
- A7's animation case wasn't run, and A9 can't tell a refusal from an empty
  slot: gremlin's animation slot is empty.
- A11's media gate missed on Apple Music's slow SMTC.
- A10 found the tapping-term miss.

What's left is the merge into `ak820pro-jdlien`, `deps.lock`, and
`warren/config-menu` into main.

## 11. S1's first increment on the keyboard on gremlin (10-24)

Firmware `gremlin/s1` `6a9a16b7` (dev, token `0xe3a9d6ef`, heap gap 368 B),
built from the build plan's revision 12. It's the polled fills plus:
- pieces under `MB_PASS_BYTES` (512 B, one a pass);
- the end-of-op latch, and a failed piece ending its op;
- the entry check (`SPI_READY` included), HC_POLLFAULT, and the
  chibios-contrib FIFO dispatch patch (`gremlin/s1-fifo-ie`).

Codex: safe to flash; its three should-fixes were done first
([`review-codex-s1-step1-2026-10-24.md`](review-codex-s1-step1-2026-10-24.md)).
Host tests pass; two mutants fail 96 and 18 checks.

**The LEDs** (`menu_s0_ledrate.py`, after a health reset outside the span;
`history/config-menu-s1-20261024/ledrate-s1-6a9a16b7.json`): the toggling
windows ran 3,697 row ISR/s against the dashboard's 3,750, **a ratio of
0.986** (C10 needs 0.98). Fn+D's 1 s windows ran 0.996 to 0.998. Every
repaint completed, `invariant_fail` 0, ge25 0.

**The cost:** 7 full A/B repaints in 5 s, against the prototype's 12. One
512 B piece a pass costs ~5 ms in `blit_pump`, because the polled send gets
only the CPU the row ISR leaves (~26%), plus the window's command bytes.

**Where the passes go** (HC_ACCT, `scripts/menu_s1_acct_toggle.py` and
`menu_s1_acct_transitions.py`):
- **A painting pass is 10-13 ms:** ~5 ms of piece, plus ~4-5 ms of QMK's own
  pass, "unaccounted" (a dashboard pass is ~4.4 ms, 225 a second). So every
  painting pass counts as a ge10, by design, and **none reaches 15 ms**:
  the menu's own passes meet C10's target.
- **The ge10 count follows the passes, not the polling:** with toggles 1.5 s
  apart and no polling, 80 ge10 in 8 s; flat-out polling, 511.
- **⚠️ The 19-23 ms passes are the dashboard's restore,** after the menu
  closes or the Fn+D page exits (three runs of each). One pass spends
  15-16 ms in `blit_pump`. The dashboard alone has none, and the Fn+D page's
  entry and Camera peak at 12-17 ms (`second_edge` and `display_hk`, 7 ms
  each). It's the restore's stages (`display.c:1442-1473`): most likely case
  4, `draw_battery(true)`, with six small fills each preceded by its window
  through byte-at-a-time `spiSend`, then the bolt tile and the percentage's
  synchronous glyphs, or else case 2, the connection row and the clock.
  S0's A11 already saw 20 ms there, so it's mainline cost, now ~2 ms more
  with polling. **The next increment splits those stages one component a
  pass**, as the lock stage was in 2026-09 (25-30 ms then), and C10's
  instrumentation times each stage. C10's armed interval counts these
  passes, so S1 can't pass without it.
- **Boot alone** leaves a 23 ms pass (`loop_gap_max` read 20 s after the
  flash). The prototype's "worst pass 24 ms" was read since boot, so it
  mixed boot and restore with the fills.

## 12. S1's second increment and the gate's first run (10-24)

Firmware `gremlin/s1` `0aaefca2` (dev, token `0xad2f32d7`, heap gap 264 B):
C10's instrumentation (op 27 sub 10, `debug_done`, the session token,
DMA ends timed at CS release) and the restore's blank shadows. Codex: safe
to flash; its should-fixes were done first
([`review-codex-s1-step2-2026-10-24.md`](review-codex-s1-step2-2026-10-24.md)).
A1 passes on sub 31.

**The blank shadows work** (`scripts/devhook.py read` after the gate):
"restore: text slot" fell from 16.12 ms to 0.55 ms.

**`scripts/menu_s1_gate.py`'s first run**
(`history/config-menu-s1-20261024/gate-0aaefca2.json`) failed, as a
measurement should when it finds something:
- **The LEDs: far inside C10.** The sustained windows ran 0.997. Every
  transition window was at least 0.994 (the bar is 0.95), and each kind's
  mean at least 0.998 (the bar is 0.98).
- **Completions inside 1,000 ms, two of them close:**

  | Kind | Completion |
  |---|---|
  | Fn+D in | 781-883 ms |
  | Camera | 258-344 ms |
  | Fn+D out | 250-313 ms |
  | open | 821-922 ms |
  | layout | 797-914 ms |
  | close | 219-281 ms |

  The Camera second completed within one poll each time.
- **The timebase check failed in four 500 ms windows,** by 13-18 ms. That was
  the script: `time.monotonic()` on Windows ticks at ~15.6 ms. Fixed to
  `perf_counter()`.
- **Continuous input committed nothing during the burst:** the buckets were
  `[0 x 19, 1]`. The books balanced (200 created, 200 settled or superseded),
  and the final target settled in 157 ms. The cause: every detent's new
  generation restarted every partial slot, and a half row is now four pieces.
  Fixed by the build plan's revision 13 (resume on the slot's own signature).
- **26 passes over 15 ms, the longest 18.8 ms.** HC_ACCT
  (`menu_s1_acct_transitions.py`):
  - **the debug page's composition**, ~9 ms of `second_edge` or
    `display_hk`. Camera composed all nine Health rows behind it, then
    blanked them. Fixed: it composes only its own lines.
  - **the restore's battery outline** (9.6 ms, five fills each with its
    window sent a byte at a time) and **the connection row with the forced
    clock** (8.7 ms). Fixed: one edge a pass, and the row and the clock in two
    passes, each stage holding until done.

## 13. The gate's second run (10-24)

Firmware `gremlin/s1` `b3dcaeca` (dev, token `0xa885e369`, heap gap 264 B):
- revision 13's resume on the slot's own signature, with the untimed resumed
  op and the kept in-flight glyph;
- the debug page composing only the page showing;
- the restore's split stages;
- Health's ISR window rebased.

Codex's review and dispositions:
[`review-codex-s1-step3-2026-10-24.md`](review-codex-s1-step3-2026-10-24.md).
The gate now sends mutations once and times completions by their
evidence (`history/config-menu-s1-20261024/gate-b3dcaeca.json`).

**Everything but the timing passes:**

| Check | Result |
|---|---|
| Sustained ratio | 0.999, 0.999 |
| Fn+D in | mean 0.998, min 0.994, completed in 741-925 ms |
| Camera | mean 0.998, min 0.995, 247-395 ms |
| Fn+D out | mean 0.999, min 0.997, 246-346 ms |
| open | mean 1.000, min 0.997, 813-894 ms |
| layout (to F2) | mean 1.000, min 0.998, 809-896 ms |
| close | mean 0.999, min 0.997, 245-348 ms |
| Camera's second | 0 ms each (within the poll) |
| Continuous | 200 detents, none late; 4-5 slots committed in every 500 ms bucket; 200 created against 200 settled or superseded; the final target in 236 ms |
| The timebase | inside 2% plus the brackets in every window |

**The timing fails: the longest pass 17,050 us, four over 15,000.** The
display probe's worst stage is now 6.15 ms (the debug compose, down from
9.12), the connection row 5.71 (from 8.69); the battery outline is gone from
the top. HC_ACCT puts the tail on the menu's painting passes (a 512 B piece
~5 ms in `blit_pump`, plus 4-6 ms of QMK's own pass, wider under the gate's
polling) and the close's restore (15 ms). **The piece's cost is mostly its
window**: 11 bytes each through a whole `spiSend()`. Fixed in the build
plan's revision 14: the polled sends' windows are polled too.

## 14. The gate's third run: the polled window (10-24)

Firmware `gremlin/s1` `b245bd84` (dev, token `0x0897c9b3`): the build plan's
revision 14, the polled sends' window polled; HC_POLLFAULT with a skip count.
Codex: safe to flash, its notes done first
([`review-codex-s1-step4-2026-10-24.md`](review-codex-s1-step4-2026-10-24.md)).
`history/config-menu-s1-20261024/gate-b245bd84.json`.
- **A piece costs 4,378 us** (5,370 before): the window saved ~1 ms, less
  than the 1.8 estimated, so the payload loop is the larger part.
- **The LEDs:**
  - the sustained windows 1.001, 1.001;
  - every transition kind's mean 0.998-1.001, its minimum 0.994-0.999.
- **Completions inside 1,000 ms:**

  | Kind | Completion |
  |---|---|
  | Fn+D in | 744-924 ms |
  | open | 743-877 ms |
  | layout | 706-894 ms |
  | Camera, Fn+D out, close | 234-360 ms |
- **Continuous:** exactly 5 slots committed in each of the 20 buckets, and
  the final target in 245 ms.
- **The timing still fails: two passes over 15 ms, the longest 17,525 us**
  (four and 17,050 before). The display probe's worst stage is 6.1 ms, so
  it's a pairing, not a stage. HC_ACCT's worst Fn+D and Camera passes put
  the page's composition (5-9 ms) and a glyph's DMA arm (~3 ms) in one
  pass. The pump now yields in a pass where the page composed, as it
  already does after the clock's second.

**JD, typing on the keyboard on gremlin while the gate runs (10-24): "the
keyboard still seems to type just fine when you're running through these
sequences of pages."** An informal look at the typing test that S1's gate
keeps, because no counter proves a keypress wasn't lost.

## 15. The gate's fourth run (10-24)

Firmware `gremlin/s1` `9902ff5b` (dev, token `0x2a2e20e9`): the debug page's
pump yield, the 10 Hz composition deferred in a pass the pump painted, and
C10's pass timing at the pass's start. Codex:
[`review-codex-s1-step5-2026-10-24.md`](review-codex-s1-step5-2026-10-24.md).
`history/config-menu-s1-20261024/gate-9902ff5b.json`.

**It aborted at the eighth Fn+D entry: "completed after 1000 ms".** Up to
there no other check failed.

| Kind | Completion (repeats run) |
|---|---|
| Fn+D in | 755-940 ms (seven repeats) |
| Camera | 308-412 ms |
| Fn+D out | 273-334 ms |
| open | 739-827 ms |
| layout | 738-803 ms |
| close | 255-318 ms |

Every LED window was 0.993-1.003. The timing totals weren't read: the run
stopped first.

**The cause is the Fn+D page's own painting.** It's about 135 glyphs, one
per pass, and each glyph's DMA arm still sends its window a byte at a time
through `spiSend()` (~1.8 ms of the ~3.4 ms per glyph). The composition
deferral added a little on top; codex warned the margin was 76 ms.

**Next: the build plan's revision 15.** `lcd_blit_flash()` sends its window
polled, *after* `spiSN32FlashDmaPrepare()` (which runs with the panel's CS
high) and *before* it clears `blit_done`. That should roughly halve every DMA
arm (glyphs, clears, images) across the whole display; the gate measures it.

## 16. The S1 gate passes (10-24, ~14:05)

Firmware `gremlin/s1` `a8b98bc0` (dev, token `0x3304a081`, heap gap 256 B;
devfault 152, daily built clean): the build plan's revision 15, the DMA
arm's window polled between `Prepare()` and `Fire()`. Codex: safe to flash,
its should-fixes done first
([`review-codex-s1-step6-2026-10-24.md`](review-codex-s1-step6-2026-10-24.md)).
`history/config-menu-s1-20261024/gate-a8b98bc0.json`.

**`scripts/menu_s1_gate.py`: PASS, every C10 check.**

| Check | Result |
|---|---|
| Longest pass in the armed interval | **13,813 us**, none over 15,000 |
| Piece, op, repaint | 4,304 us, 35,946 us, 736 ms; the largest clear band 2 ms |
| Sustained LED ratio | 1.000, 1.000 |
| Fn+D in | mean 1.000 (min 0.998), completed in 649-841 ms |
| Camera | mean 1.000 (min 0.999), 263-371 ms |
| Fn+D out | mean 1.000 (min 0.999), 218-310 ms |
| open | mean 1.000 (min 0.999), 738-824 ms |
| layout | mean 1.000 (min 0.998), 724-822 ms |
| close | mean 1.000 (min 0.998), 223-312 ms |
| Camera's second | completed within the poll, five of five |
| Continuous | 200 detents, none late; 5 commits in each of the 20 buckets; 200 created, 200 settled or superseded; the final target in 242 ms |

The road here took five runs:
1. the timebase (Windows' 15.6 ms monotonic clock);
2. revision 13's signature resume;
3. Camera's composition and the restore's split stages;
4. revision 14's polled window;
5. the debug page's pump yield;
6. revision 15's polled DMA window.

**Still to run before S1's paint work:** the failure paths on the devfault
build. These are HC_POLLFAULT at each window send (fill and DMA) and at the
payload, in both modes, each followed by a SPI1 read, a CPU draw and a DMA;
and a lost completion followed by a failing retry window.

## 17. The polled sends' failure paths: 24 of 24 (10-24)

The devfault build of `a8b98bc0` (token `0x49f8e1e1`), run by
`scripts/menu_s1_fault.py` (`history/config-menu-s1-20261024/fault-a8b98bc0.json`).
HC_POLLFAULT `[n, mode, skip]` faulted, in mode 0 (gave up halfway) and
mode 1 (after every byte):
- **a row fill:** skips 0-4 are its five window sends, 5 its payload; a
  selection change paints rows only;
- **a title glyph's DMA arm:** skips 0-4, its five window sends, which are
  revision 15's new path; a pattern change paints the title first;
- **a lost completion** (HC_BLITFAULT 1) whose retry's window gave up (skip
  5).

**Every case passed:**
- the menu owner took exactly one loss and repainted its target;
- a later DMA (the title, with its flash read on SPI1) and a later fill both
  worked;
- no fault stayed armed;
- `invariant_fail` held only `0x20` (`PO_FAIL_SPI0_POLL`, sticky, expected);
- the owner stayed MENU;
- no blit timeouts, except the retry cases' one each;
- none after any case.

This is codex's acceptance item for revisions 14 and 15. `dma_unprepare()`
put SPID1 back each time.

The keyboard on gremlin is back on dev `a8b98bc0`.

## 18. Real spins, and the encoder's waits (10-24, afternoon)

JD spun the knob by hand with the fixture open, recorded by a scratch
watcher (sub 10 armed for the whole run, so its maximum spans everything
the board did in it). Nothing dropped and no pass reached 25 ms in either run.

| Build | Run | Passes over 15 ms in the menu | Worst pass | Record |
|---|---|---|---|---|
| `a8b98bc0` | ~55 s of spinning | 6 | 15.6 ms, in the menu | `spin-a8b98bc0.json` |
| `cbcf93b6` | ~50 s of spinning, after ~13 min on the dashboard | 2 | 17.7 ms, **on the dashboard** at 93 s, before the menu opened; the menu's own maximum isn't separable | `spin-cbcf93b6.json` |

- **Why the synthetic gate (§16) didn't see it:** op 27's turns bypass
  `quantum/encoder.c`, whose drain waited `ENCODER_MAP_KEY_DELAY` (1 ms)
  after each half of every detent, captured by the menu or not.
- **`cbcf93b6`** skips those waits for halves the menu swallowed
  (`encoder_map_delay_wanted_kb()`, a weak hook; codex,
  `review-codex-s1-encoder-2026-10-24.md`). Over 15 ms in the menu went
  from 6 to 2. That isn't proof: the runs differ, and the second's maximum
  is the dashboard's.
- **JD (cbcf93b6):** "if I spun fast it registered but looked like it would
  change before the item finished redrawing, which is about what I'd
  expect."
- **Next time:** `scripts/menu_s1_spin.py` arms sub 10 only when the menu
  opens, and reads HC_ACCT's slow-pass ring whenever a pass over 15 ms
  appears, so each one comes with its per-scope breakdown.

## 19. The mono text on F3 (10-24)

`3f0275ca` + `158e876d` (codex's fixes): `lcd_blit_mono` through the
stream, the generated Cozette face, `menu/menu_text.c`, and the fixture's
F3 (op 27 sub 0 patterns 16-19: lit/half, lit/full, inverted/half,
inverted/full).
- **The failure paths, 36 of 36** on devfault `158e876d` (token
  `0xcf21c59e`; `fault-158e876d.json`): §17's 24 again, plus 12 mono cases,
  a give-up at each of a piece's five window sends and at its payload, in
  both modes. Each: one loss, the repaint, a later style change and
  selection change both fine, `invariant_fail` only `0x20`.
- **The cost per style** on dev `158e876d` (`scripts/menu_s1_styles.py`,
  `styles-158e876d.json`; sub 10 re-armed for each interval):

  | Style | Piece max | Pass max (switch / moves) | Over 15 ms (switch / 10 moves) | A move | A style switch |
  |---|---|---|---|---|---|
  | lit, half rows | 7.7 ms | 17.2 / 16.4 ms | 15 / 8 | 208 ms | 1,103 ms |
  | lit, full rows | 8.8 ms | 16.9 / 17.7 ms | 13 / 35 | 209 ms | 948 ms |
  | inverted, half rows | 7.7 ms | 16.3 / 16.8 ms | 8 / 9 | 214 ms | 959 ms |
  | inverted, full rows | 8.8 ms | 16.7 / 17.2 ms | 22 / 33 | 208 ms | 955 ms |

  **The mono piece fails C10's 15 ms target:** a 488 B mono piece cost
  7.7-8.8 ms against 4.3 ms for a 512 B fill piece (§16). The composing
  went a pixel column at a time and the expansion a bit test and two byte
  stores a pixel, which the M0 pays ~3.7x for under the row ISR. Full rows
  cost more per piece than half rows at the same byte count: the composer's
  per-column overhead. The op latency saturates sub 10's u16 for full rows
  (65,535 us). `cdde64e8` rewrites both stages (a cell at a time; a
  halfword a pixel); codex is reviewing it.

### 19b. The faster composer, and JD's verdict (10-24, ~16:25)

`cdde64e8` + `cbb51ac1` (codex: `review-codex-s1-mono-2026-10-24.md`, the
follow-ups): `mt_bits` composes a cell at a time, `lcd_blit_mono` stores a
halfword a pixel from a two-colour table.

| Style | Piece max | Pass max (switch / moves) | Over 15 ms | A move | A style switch |
|---|---|---|---|---|---|
| lit, half rows | 5.1 ms | 13.5 / 13.3 ms | 0 / 0 | 165 ms | 764 ms |
| lit, full rows | 5.2-5.4 ms | 13.6 / 14.5 ms | 0 / 0 | 158 ms | 717 ms |
| inverted, half rows | 5.1 ms | 13.1 / 13.5 ms | 0 / 0 | 166 ms | 766 ms |
| inverted, full rows | 5.2-5.4 ms | 13.5 / 13.5 ms | 0 / 0 | 158 ms | 723 ms |

(`styles-cbb51ac1.json`.) A mono piece now costs ~5.1-5.4 ms against a
fill's 4.3. **The failure paths, 36 of 36 again** on devfault `cbb51ac1`
(`fault-cbb51ac1.json`).

**JD on the panel** (the slow build `158e876d`, then held open on F3):
- "Oof that text is small, but... it kind of is what it is"; later
  "_tiny_ ... maybe a font size is going to be useful. But that's a
  massive redesign. For now let's proceed with the tiny fonts."
- "Yellow 'lit' text and gray unselected looks pretty good"; of both:
  "both are decent but I think I'd lean the 'lit' rows". **Lit text.**
- Half and full rows: "I can't see any meaningful difference" -> by
  efficiency: **half rows** (plan "Open" 2).
- "if I scroll at just the right speed I can make most of the options turn
  yellow": a fast spin starts new highlights before the old rows are
  repainted grey (BACKLOG, for P1).
- A slow-build session on F3 with the HC_ACCT ring (`look-158e876d.json`):
  every pass over 15 ms was the menu's piece (blit_pump 7-8 ms) plus
  QMK's unaccounted work (keyboard task, RGB effect, USB: 5-7 ms) plus the
  CH582F and the battery (~1 ms each).

**The gate on `cbb51ac1` FAILED on timing** (`gate-cbb51ac1.json`): the
longest pass 20.3 ms, 2 over 15. The gate never shows F3, and nothing on
F1's paths changed, so it's a dashboard or debug-page path: the real spin
on `cbcf93b6` also showed 17.7 ms on the dashboard before the menu opened.
`scripts/menu_s1_dashwatch.py` is watching the dashboard to name it.

### 19c. The gate's long pass, named: the dashboard's text slot (10-24, ~16:45)

- **The idle dashboard is clean:** `menu_s1_dashwatch.py`, 15 min on
  `cbb51ac1` with no track change: the longest pass 13.2 ms, none over 15
  (`dashwatch-cbb51ac1.json`).
- **The gate again on `cbb51ac1`: PASS** (`gate2-cbb51ac1.json`): the
  longest pass 13.3 ms, none over 15; every LED window at least 0.998;
  completions inside 1,000 ms. The gate now tags any pass over 15 ms with
  the step it came in (no extra reads). The first run's 20.3 ms was
  intermittent.
- **Six host text pushes** (`hostagent/ak820text.py`, two lines each)
  during a 70 s watch: one 19.6 ms pass, `display_hk` 13 ms of it (the
  HC_ACCT ring; `dashwatch-text-cbb51ac1.json`).
- **The display probe** over long two-line and short one-line texts
  alternating: `hk: text slot` 13.40 ms; inside it `text icon` 3.71 ms and
  `band clear` 2.66 ms each. A change between layouts clears the old icon,
  draws the new one, clears the vacated cells and the retired line, and
  redraws a clobbered icon, all in one pass. This is a dashboard path from
  before the menu, so it likely explains the 17.7 ms in §18 as well.
- **`f78e1157` stages it:** one heavy step a 10 Hz tick (the forced
  restore path unchanged). Codex reviewing (`review-prompt-s1-textslot.txt`).

### 19d. The staged text slot on the board: the gate passes (10-24, ~17:30)

`ffa80947` (dev, token `0x73928d54`, heap gap 232 B): `f78e1157` plus
codex's two fixes (`review-codex-s1-textslot-2026-10-24.md`: line 1 retires
before line 0 paints whenever it retires; one heavy step a main-loop pass).
- **Six alternating long two-line and short one-line texts** (as §19c)
  during a 75 s watch: the longest pass 13.2 ms, none over 15
  (`dashwatch-text-ffa80947.json`). The probe: `hk: text slot` 4.00 ms
  (13.40 before), `text icon` 3.49, `band clear` 2.62.
- **The gate: PASS** (`gate-ffa80947.json`): the longest pass 14.8 ms, none
  over 15; sustained ratios 1.002; every transition window at least 0.998;
  completions Fn+D in 631-770 ms, Camera 251-345, Fn+D out 214-312, open
  711-793, layout 705-786, close 219-313; Camera's second 92-100 ms;
  continuous input 5 commits in every bucket, the final settle 245 ms.
  The longest pass is closer to 15 ms than §16's 13.8: run-to-run spread,
  with no step tagged over 15. Thin margin, noted.
- **Not yet seen:** the staged text on the panel after real track changes
  (no clipped title, no fragments). One look for JD.
- **JD's look (10-24, ~17:50), music playing, five or six real track
  changes on `ffa80947`:** "titles looked clean". No clipped title, no
  fragments, the icon whole. The staged text slot is accepted on the panel.
- **The timing during JD's track changes** (`dashwatch-tracks-ffa80947.json`,
  300 s, 13 track changes): one pass over 15 ms, 16.2 ms, and not the
  display's (`display_hk` 1 ms, the CH582F 2, the battery 1, **unaccounted
  12**: QMK's own work, the key and USB paths, the RGB effect). A lead, not
  chased yet: if a key or the knob skipped the track, the modified-consumer
  path's deliberate 8 ms gap (`MODIFIED_CONSUMER_GAP_MS`, config.h) fits.

## 20. P1a on the board: the real menu (10-24, ~18:40-19:30)

Dev `5527c898` (token `0x69ff475f`, heap gap 192 B): the tree, the session
kind, one lit row at most, `MENU_ENABLE` on (codex: `review-codex-p1a-code-2026-10-24.md`,
two rounds). `scripts/menu_p1a_board.py` drives every screen by op 27: Reset
counters' two pages and a cancel outside the measured interval, then in it
the open, moves both ways with wraps, Power and Clock committed and put
back, a Clock cancel by a hold, Help's four topics paged to their ends and
back, About, Health and Camera handed off and back, the hint, the close.
- **Every step lands where it should**, in 9 runs (621 steps): the screen
  id (16 + the node) and the cursor each time, both Diagnostics returns on
  their rows, the settings committed and restored, `invariant_fail` 0.
  Screens settle in 170-990 ms by the script's 100 ms polls (opens
  ~800-900 ms, a move ~170 ms).
- **Timing, C10's 15 ms: a marginal, sporadic miss.** Six of nine runs had
  one or two passes over 15 ms, each in a different step, at 15.1-16.8 ms
  (most 15.1-15.4); three runs passed (longest 14.2-14.8 ms). Nothing near
  25 ms. Polling at 10 ms, 50 ms or the gate's 100 ms made no clear
  difference, so it isn't the measurement's traffic. Two Clock commits under
  HC_ACCT made no long pass (longest 14.4 ms), so it isn't the settings'
  saves. A menu text piece costs ~5.6 ms (a fill piece of the same size
  4.3, F3's mono piece 5.1): with QMK's own varying work in the same pass,
  about one pass a minute of driving goes just over. Next: measure where the
  piece's time goes (the composition, the expansion, the send) before
  choosing a fix; smaller pieces would push the opens past 1,000 ms.

### 20b. Where a menu text piece's time goes (10-24, ~19:45)

Dev `62bb64f9` (token `0x7658391c`): op 27 sub 12's maxima over a full
`menu_p1a_board.py` run (`p1a-board6-62bb64f9.json`):

| Part | Max |
|---|---|
| the window (11 bytes, 5 polled sends) | 0.58 ms |
| the expansion (244 px into the scratch) | 1.02 ms |
| the sends (488 B) | 3.50 ms |
| the whole mono call | 4.50 ms |
| the composition (`mt_bits`, before the call) | 0.86 ms |

- **The send dominates,** and it's what a fill pays too: 488 B is 0.16 ms on
  the wire at SPI0's 24 MHz (`clkdiv` 0, already the fastest), so ~3.3 ms is
  the polled loop's CPU time under the row ISR's ~73%.
- **Everything runs 4-5x slower than its instruction count predicts**
  (`mt_bits` ~1,100 instructions, 0.86 ms; the expansion ~1,400, 1.0 ms):
  most likely the flash's wait states (no cache) on top of the ISR's share.
  The real cure is the hot loops in SRAM, which costs SRAM the dev build
  doesn't have (160 B over the floor with this build's diagnostics).
- **JD (on `62bb64f9`):** Back/Exit's #FF9A9A "reads well. It's clearly
  different but bright enough to be visible on a dim screen." The
  scrollbar first: "_definitely_ the right call. It's nearly instant so the
  user knows where they are as the text fills in."

### 20c. A flash that stuck in the bootloader (10-24, ~20:00)

Flashing `1e84bf17`: the firmware's jump worked and the bootloader
enumerated (`0C45:7140`), but the flasher got "Device failed to init" and
then "failed to fetch flash version" on every retry, in two runs
(`%TEMP%/ak820flash.hnQpqU`, `.q1YVAx`). **Neither erased anything** (no
"Erasing" line), so `62bb64f9` stayed on the chip; the board looked dead to
JD ("not coming up at all and I can't type on it"). The 19:37 flash had one
"failed to init" and then succeeded. **Recovery:** JD power-cycled it (the
slider to cable, unplugged ~10 s, replugged); it came back as `0C45:8009` on
`62bb64f9`, and the next `flash.sh` succeeded at once. Cause unknown: the
bootloader's handshake, sometimes. If it recurs: check `Get-PnpDevice` for
7140 (no HID enumeration), check the flasher log for "Erasing" before
worrying, and power-cycle.

### 20d. JD's icons on the board (10-24, ~21:05)

`925f029b` (dev, token `0x58ddeb40`; codex: no fix,
`review-codex-p1a-icons-2026-10-24.md`): the wrench, ◀ ▶, the circled
check, the cursor in x 0-2 and the top-level icons (the design doc's "JD's
icons"). The flash went on first time. `menu_p1a_board.py`
(`history/config-menu-s1-20261024/p1a-board-925f029b.json`): **all 69 steps
right**; the longest pass 15.26 ms, 3 over 15 (C10's line, which JD's (b)
relaxes to ~16-17 ms for menu painting), against 15.1-16.8 ms before; the
piece 5.84 ms, ~4% more for the row's 64 px first half. The one pass whose
causes were logged was the radio and the dashboard's blit pump on the way
back from the Health page, not a text piece.

### 20e. P1b on the board: Lighting, Screen, the editors (10-24, ~22:30-22:50)

Flashed with JD's wake-dark-frame fix merged in (`52acdffe99`, at JD's ask
via the session on Buzz; codex: no must-fix,
`review-codex-wake-dark-merge-2026-10-24.md`). P1b's code had codex's review
(`review-codex-p1b-code-2026-10-24.md`): one must-fix, a click queued behind
an external cancel showed "Saved", fixed in `04adb63f` with regressions.

- **`04adb63f`** (dev, token `0xdea4348f`): `menu_p1a_board.py` with its P1b
  pass (Lighting, the Effect choice previewed and cancelled, Brightness up and
  down and cancelled, then reopened on the original value, Hue up four and a
  fast turn down, cancelled, the Screen up and cancelled; sub 14 says each
  edit closed): **all 97 steps right**, but each turn in the hue editor took a
  pass to 16.3-18.8 ms (`p1a-board-04adb63f.json`). The band's pixels came
  from a callback a pixel.
- **`07b51f58`** (dev, token `0x8a933567`; the bands fill a row at a time,
  `lcd_blit_rows`; codex: no must-fix): **all 97 steps right, PASS**: the
  longest pass 16.25 ms (a list move with the radio busy, not the editor),
  7 over 15 ms, the hue editor's turns 15-16 ms
  (`p1a-board-07b51f58.json`); the text piece 5.9 ms.
- Heap gaps at `04adb63f`: dev 152 B, devfault 200, daily 2,288.

Owed before P1b is accepted (codex's review, item 4; the design's tests):
the board's order-observing writer checks (VIA get/set/save/indication
mid-edit, dev ops 4/5), a Save with the lights off and Lights saved, the
visibility from Screen Off and level 0, persistence across a reboot, C10's
gates on the editors; the host's long-idle and 32-bit-wrap cases, the
editors' piece-boundary loss/DMA/close-reopen cases, the forced-save
semantics; JD's session.
