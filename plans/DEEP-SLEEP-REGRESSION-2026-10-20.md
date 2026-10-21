# Deep sleep broken on the dev builds since the 2.4G work (found 10-20)

The diagnostic branches below (`mac/sleep-*`) were deleted on 10-21; their
commits are kept as patches in
[`../history/firmware-branch-archive-20261021/`](../history/firmware-branch-archive-20261021/README.md).

## What happens

On `b2a07e0d37` (dev, token `0x398a2e17`), over 2.4G, on the pack, every
deep sleep ends after **exactly one counted second**. The record calls it
a **charge** wake (`SLEEP_WAKE_CHARGE`), and the ladder sleeps again about
3 s later: ~1 s asleep, ~2 s awake, about 25 times a minute.
- Found with the daemon's radio test (`scripts/deep_sleep.py --hold-after`)
  at 08:17 10-20, then `deep_cycles.py --n 2 --board-only` (ladder path):
  `history/uart-latency-20261020/deep-cycles-2g4*/`,
  `radio-sleep*/`.
- The record (op 14 sub 4) reads `p1 = 0`, with `strays 0`. With intact
  masks a charge wake must store the CHRG bit in `ds_p1_ris`
  (`sleep.c:466-470`), so the record contradicts its own path.
- The dev wake ring (op 24) holds `p1 = 00 20 10 bd` in every entry,
  including a key wake. Those bytes are Thumb code
  (`movs r0,#0; pop {r4,pc}`). In the image, the ring reads p1 through
  `r7`, which holds `&ds_p1_ris`. So `r7` holds a code address by the
  write, and the wake's own store through it went astray. That explains
  the zero.

## Ruled out (10-20, at run time)

| switch | result |
|---|---|
| The daemon's radio held off (its flock held; `radio: contended`) | same |
| UART2 back at priority 1 (op 20 sub 3) | same |
| The PCF transfer under the old transaction lock (op 20 sub 2) | same |
| CHRG (B16) watched at 10 Hz for 30 s on the pack | high throughout |

## Where it came in

- **Passed:** an hour asleep over 2.4G on `7387d18947` (10-19,
  `history/ladder-sleep-20261019-hour2/`). 10 of 10 2.4G cycles on
  `83d8768c64` (`history/deep-cycles-20261019-2g4/`).
- **Since then:** `e7f6890e06` (stage 1's pause fix, the overrun/Caps
  build), raw81 stage 2, `145a8234bf` (the long clock's virtual timer),
  `0ae4cf8c80`, the UART-latency build (`ce70c8da41`), and `b2a07e0d37`.
- **Gremlin's suspect:** `r81_long_vt` (`bluetooth/ch582f_ajazz.c`). It
  re-arms every half wrap (~175 ms) from the first task pass on every dev
  build since `145a8234bf`, radio traffic or not.

## Codex (`review-codex-sleep-vt-diag-2026-10-20.md`)

- **The diagnostic `0d765b362d` passes the gate** for a short bench test.
  It is `b2a07e0d37` with the timer never armed (branch
  `mac/sleep-vt-diag`, local; `via-dev-0d765b362d-20261020-083839.bin`,
  token `0xa28d67b8`).
- **P1, the evidence points to corrupted execution state, which ordinary
  VT operation does not explain.** Entry stops SysTick and CT16B5; a
  pending interrupt under PRIMASK would read as a stray, not charge. No
  hidden unlock in the locked section. The ARMv6-M context switch
  preserves r4-r11; the HardFault handler is terminal. Codex's next step:
  capture r7, SP/MSP/PSP, PRIMASK and the raw GPIO flags into fixed SRAM
  just before and after the WFI, and around the final unlock.
  **Taken** as the next build if the bisect does not settle it.
- **P2, the diagnostic breaks raw81 expiry across stalls over one wrap**
  (349.5 ms): a 3 s stall reads as 204 ms. **Accepted for the bench test
  only.** The diagnostic never goes in a merge.
- **Codex's caveat, which matters:** removing the timer also moves the
  code. A pass on the diagnostic implicates the timer *or* the layout.
  - The way to separate them: one image with a run-time switch for the
    timer (a dev op that stops and re-arms it), A/B in the same layout.

## The plan (each flash on JD's go)

**The run-time switch replaces the layout-moving diagnostic.** Gremlin
wrote it in its own file: `981631b925` on `gremlin/vt-switch`, which is
`b2a07e0d37` plus op 17 sub 6 (`[5]` 1 arms, 2 stops with `chVTReset`, 0
reads; reply `[5]` armed). The timer boots armed, and nothing re-arms it
after a stop. Built here as `via-dev-981631b925-20261020-085445.bin`
(token `0x2e634654`); codex's gate is Gremlin's,
`review-codex-vt-switch-2026-10-20.md`.

1. Flash `981631b925` once codex clears it.
2. Run `deep_cycles.py --n 2 --board-only` over 2.4G with the timer armed,
   then stopped, then armed again: an ABA in one layout.
   - It fails armed and passes stopped: the timer is the cause, and
     Gremlin's fix (the timer stops after 1 s of raw81 idle and re-arms
     on the next frame) goes through codex.
   - It fails both ways: not the timer. Build codex's register capture.
   - It passes both ways: the layout moved it. The register capture, and
     the flash timing around the wake, are the lead.
3. Put `b2a07e0d37` back, or the fix. `e7f6890e06` (no timer, no stage 2)
   stays available as a control if the answer is unclear.

## Results (10-20, 09:26-09:36): it follows the image, not the timer

`981631b925` flashed 09:2x (built here, token `0x2e634654`), the slider on
2.4G, `deep_cycles.py --n 2 --board-only` each:

| run | the timer | result |
|---|---|---|
| `vt-ab-1-armed` | armed (as it boots) | 2/2, asleep 41 and 45 s, woke on the key |
| `vt-ab-2-stopped` | stopped (op 17 sub 6, 2) | 2/2, 32 and 30 s |
| `vt-ab-3-armed` | armed again | 2/2, 32 and 37 s; the ring's p1 `0x0` |

Then `b2a07e0d37` flashed back, so a clean reset from the bootloader and
not a brown-out boot (`b2a0-after-clean-boot`): **2/2 fail at once**, the
1 s charge wake, and the ring's p1 `0xbd102000` again.

- **The timer is cleared.** Gremlin's fix is not needed.
- **The boot is cleared.** The morning's failures followed the slider's
  brown-out reset; this one followed a clean reset.
- **The image decides.** `981631b925` is `b2a07e0d37` plus 37 lines in
  `ch582f_ajazz.c` and `hid_protocol.c`, which only move the layout. The
  instructions after the WFI are identical between the two, only shifted:

  | image | WFI | mod 16 | sleep |
  |---|---|---|---|
  | `b2a07e0d37` | `0x120d2` | 2 | fails |
  | `981631b925` | `0x121b6` | 6 | holds |
  | `7387d18947` | `0x10064` | 4 | held (10-19) |
  | `83d8768c64` | `0xf9a4` | 4 | held (10-19) |

- **The lead:** a flash fetch on waking from Deep-sleep that depends on
  where the code sits. It is not proven.
  - The test: the WFI pinned at each 2-byte offset within a 16-byte line
    (NOPs before the DSB), one build each, or one build with several
    copies chosen at run time.
  - The fix, once the failing offsets are known: a wake path that does
    not depend on the layout, codex's register capture if the offsets
    don't separate, and the manual's Deep-sleep wake requirements for the
    flash (`docs/sn32f299.md`).
- **Every dev or daily build is a lottery until then:** a change anywhere
  below `sleep.c` in the link can move the WFI. `b2a07e0d37` is back on
  the board, with this bug.

## The WFI placement diagnostic (`466aa04636`, `mac/sleep-wfi-diag`)

`b2a07e0d37` plus op 14 sub 7, which picks the sleep's WFI sequence at run
time: `0xFF` the C sequence (default), 0-7 an asm copy with the WFI at
`(2k + 6) mod 16`, 8 a copy in SRAM (`.ramtext`) with a settle loop before
it returns to flash. Built as `via-dev-466aa04636-20261020-094005.bin`
(token `0x0a4548df`). `scripts/wfi_sweep.py` runs `deep_cycles.py` on each
variant.

**Codex (`review-codex-sleep-wfi-diag-2026-10-20.md`): clear for an
attended bench flash.** It confirms the offsets from the ELF's jump table:
0 → 6, 1 → 8, 2 → 10, 3 → 12, 4 → 14, 5 → 0, 6 → 2, 7 → 4, the default
at 0.
- **P2, a sweep that passes everywhere cannot exclude the hazard.** The asm
  copies resume differently from the original loop. **Taken:** if every
  variant passes, next come layout-only moves of the original sequence (the
  register allocation checked unchanged), then the register capture.
- **P3, the settle is uncalibrated** (300 iterations of a 6-instruction
  loop, not a measured 100 us). **Taken for the fix, not the diagnostic:**
  a production settle gets measured and swept first.
- **Recovery:** the watchdog does not count in Deep-sleep, so a wake that
  wedges the CPU needs the slider. JD at hand during the sweep.
- **What would refute the lead:** corruption that shows up while waking
  through SRAM, before any return to flash.

## The sweep's result (10-20, 12:47-13:10): every variant holds

`466aa04636` flashed at 12:46. The slider was on 2.4G, on the pack. The
run was `wfi_sweep.py --n 2`, which runs `deep_cycles.py --n 2
--board-only` for each variant
(`history/uart-latency-20261020/wfi-sweep/`, `wfi-sweep.log`):

| variant | WFI | result |
|---|---|---|
| `0xFF`, the C sequence | `0x12440`, 0 mod 16 | 2/2 |
| 0 | 6 mod 16 | 2/2 |
| 1 | 8 | 2/2 |
| 2 | 10 | 2/2 |
| 3 | 12 | 2/2 |
| 4 | 14 | 2/2 |
| 5 | 0 | 2/2 |
| **6** | **2, b2a0's offset** | **2/2** |
| 7 | 4 | 2/2 |
| 8, SRAM | `0x200014f8` | 2/2 |

Every sleep lasted 27-47 s, and every wake was the relay's key. The ring's
p1 read `0x0` throughout. The sequence was put back to `0xFF` afterwards.

- **The offset alone is not the trigger.** Variant 6 puts the WFI at 2 mod
  16, as in b2a0, and holds.
  - Codex's P2 applies: the asm copies resume through different
    instructions than b2a0's loop. So the flash-fetch lead is weaker, not
    refuted.
- **This diagnostic sleeps.** It also stays on the board for now; b2a0
  cannot hold a sleep.
- **What the failure needs is still b2a0's exact image.** The sleep fails
  only there, every time, and only the instructions after the WFI are
  clearly wrong:
  - `r7` is loaded with `&ds_p1_ris` at `0x1203a`, before the loop, and no
    instruction in the loop writes it;
  - PRIMASK is set across the loop, so no handler runs;
  - yet by the store at `0x1212c`, `r7` points at code.

  So something executed that is not in the image. That leaves the fetch
  after the wake (the lead), or a bus fault on it.

## Next (each build through codex, each flash on JD's go)

1. **Probe the flash directly after the wake, from SRAM.** Straight after
   the WFI, still in SRAM, read known flash words into an SRAM buffer, with
   a count between reads. Use two kinds of word: one in the line the CPU
   last fetched before the WFI, and one far from it.
   - If the reads come back wrong, the hazard is proven. The count also
     says how long the flash takes to come back, which calibrates the fix's
     settle.
   - If every read is right from the first, the flash holds the bus until
     it is ready, at least for data. The lead weakens further.
   - Either way, the answer does not depend on where the code sits.
2. **If the probe is clean: move b2a0's own instructions.** Padding goes in
   ahead of `sleep.c` in the link, at 16, 32, 64 and 2 bytes. That says
   whether the failure follows the offset within a line, the absolute
   address, or neither. Check each build's disassembly to confirm
   `deep_sleep` is byte-identical apart from its branches to other code.
3. **The register capture** (codex's P1), on a padded build that still
   fails.

## The flash probe (`83371a49f2`, `mac/sleep-flash-probe`)

`466aa04636` plus WFI variants 9 and 10 and op 14 sub 8. The steps, all in
SRAM:
1. Read word 0 of `ds_probe_words` (`0x245c0`), the last flash access
   before the sleep.
2. Set CTRL to 2, then DSB and WFI.
3. Set CTRL to 0, then read 16 times, alternating word 1 (`0x245c4`) and
   word 15 (`0x245fc`): 8 reads back to back, then 8 more ~17 µs apart.
   The last lands ~146 µs after the wake.
4. Back in flash, `ds_probe_run` tallies the reads.

Variant 9 reads word 15 first, variant 10 word 1. Variant 8 (the SRAM
copy) is dropped to make RAM room, and now refuses. Built as
`via-dev-83371a49f2-20261020-135325.bin`, token `0xb86f33e3`.
- RAM: the gap above `.bss` is 72 bytes. The only allocators that could
  use it are newlib's tzset, which skips allocating with TZ unset, and
  sscanf's ungetc buffer, which asks for 1,024 bytes and fails at any of
  these sizes.
- Stack: ~164 bytes more during the probe, against 1,280 never touched
  after the sweep's 20 sleeps.

**Codex (`review-codex-sleep-flash-probe-2026-10-20.md`): clear for an
attended bench flash.** It checked against the ELF:
- nothing touches the flash between word 0 and the reads;
- the code's constants sit in SRAM;
- all 16 reads finish before the return to flash.

Its findings:
- **P2, a clean probe is weak evidence.** It says only that these data
  reads came back right. The M0 marks instruction fetches apart
  (`HPROT[0]`), so a flash buffer could treat them differently. A clean
  probe also does not measure a readiness delay. **Taken:** a clean result
  is reported in exactly those words.
- **P2, `wfi_sweep.py` called PASS on bad reads.** **Fixed:** the probe has
  its own verdict (CLEAN needs wakes probed and none wrong), and the
  overall pass needs both.
- **P3, the default sweep still asked for variant 8.** **Fixed.**
- **P3, "8-byte line" overstates the manual,** which documents an 8-byte
  programming unit, not a read buffer. **Taken:** words 0 and 1 are "the
  same aligned 8-byte block", word 15 a different 8-, 16- and 32-byte
  block, all in one 64-byte block. The diagnostic's comment stays as
  built, so the reviewed image's commit is unchanged.
- **Codex's next step, which matches step 2 above: move b2a0's own
  instructions.** Its `nm` check found all 884 SRAM symbols identical in
  address and size between b2a0 and `981631b925`. So `981631b925` moved
  only the code, and it slept. The probe still runs first: it costs one
  flash, and a bad read would settle the lead.

### The probe's result (10-20, 14:04-14:10): clean

`83371a49f2` was flashed at 14:0x. The first run never slept, because
relay 2 (the keyboard's 5 V) was off and `deep_cycles` refuses to start
from the battery. It was on when the sweep ended at 13:10, and the cause is
unknown. It was put back on and the run restarted.
`wfi_sweep.py --variants 9,a --n 2` (`history/uart-latency-20261020/flash-probe/`, `flash-probe.log`):

| variant | sleeps | wakes probed | wrong reads |
|---|---|---|---|
| 9, far word first | 2 slept, both woke on the key | 47 | 0 |
| 10, near word first | 2/2 | 55 | 0 |

- **Every read came back right, from the first one after each wake.**
  That covers 102 wakes and both orders, with no stale word, no all-ones
  and no zero.
  - Per codex, that says only that these data reads returned the right
    values. It doesn't show that instruction fetches straight after the
    wake are safe, and it doesn't measure a readiness delay.
- **Variant 9's first cycle counted as FAIL only on the host's timing.**
  The host found no sleep edges in the power log (`asleep_s` None), likely
  because the pack had just started charging again when relay 2 came on.
  The board's own record was a normal sleep: 19 counted seconds, 23 by the
  PCF, a key wake, no strays.
- `wfi_sweep.py` now prints `deep_cycles`'s own error when it refuses.
  Before, it threw that away, and the first run showed only "NO WAKES".

**So the lead weakens further, and moving b2a0's own code is next (step
2):** six builds on `mac/sleep-pad`, with pads of 16, 4, 8, 32, 64 and 228
bytes. `scripts/layout_diff.py` checks each against b2a0:
- all 860 RAM symbols are identical;
- all 1,369 functions are identical as symbol + offset, apart from
  `health_fill6`, whose immediates are the build token's bytes.

`scripts/pad_sweep.py` flashes them in turn. b2a0 itself goes first as the
control, and the WFI diagnostic is left on the board at the end.

## The padding series (10-20, 14:34-15:02): every placement as predicted

`mac/sleep-pad`: b2a0 with DS_PAD bytes ahead of `sleep.o`, so b2a0's own
instructions move by exactly that much and the RAM stays as it was. Codex
checked each image byte by byte
(`review-codex-sleep-pad-2026-10-20.md`, `-pad-verify-`): every difference
is a relocated BL, literal, vector, `.rodata` or `.data` word, or the
token. Flashing stayed with this session, in the foreground, after
`pgrep -x sonixflasher` and a relay check. `scripts/pad_check.py` gives the
board verdict (codex's verify of it:
`review-codex-sleep-padcheck-2026-10-20.md`, its four P2s taken).

| pad | commit | WFI | mod 8 | board |
|---:|---|---:|---:|---|
| 0 (control) | `b2a07e0d37` | `0x120d2` | 2 | regression |
| 16 | `b2b5b57377` | `0x120e2` | 2 | regression |
| 4 | `eba26f6c6e` | `0x120d6` | 6 | sleeps |
| 8 | `8268166476` | `0x120da` | 2 | regression |
| 12 | `462cb9244b` | `0x120de` | 6 | sleeps |
| 64 | `674ac4308e` | `0x12112` | 2 | regression |
| 228 | `dd0944df49` | `0x121b6` | 6 | sleeps (one 8 s sleep, one 28 ms blit) |
| 0 (repeat) | `b2a07e0d37` | `0x120d2` | 2 | regression |

`history/uart-latency-20261020/pad-sweep/`, `pad-sweep.log`.
- **Every failing placement keeps the ring's p1 at `0xbd102000`.** That
  matches `r7 = 0xbf30`, because `0xbf30` lies below every pad.
- **Pad 228's 28 ms pass was a blit,** with 2 passes of 25 ms or more since
  its boot. It is unrelated to the WFI's placement, and is probably the
  redraw at the first wake after a flash. It is open and to be looked at.
- **The board's uptime excludes deep sleep.** The system timer stops
  across it. That is not a reset.

**The mechanism (a hypothesis; the register capture would prove it).**
b2a0's WFI at `0x120d2` is the second half of the block
`0x120d0-0x120d7`: `0xbf308f4f`, then `0x64032300` (the DSB's tail, the
WFI, `movs r3,#0`, `str r3,[r0,#64]`). Straight-line code follows. Suppose
the fetch of the next block (`0x120d8`) after the wake returns that same
stale block. Then the core runs:
- `ldrh r7, [r1, #58]`, with `r1 = 0x5afa0000`, LPCTRL's key, written
  just before. Bit 1 of `0x5afa003a` takes the stale word's upper half, so
  `r7 = 0xbf30`.
- `wfi`, which returns at once with the wake pending, then `movs r3,#0`
  and `str r3,[r0,#64]`.

It skips `mov r3,fp; ldr r6,[r3,#28]; ldr r3,[sp,#20]; ldr r1,[sp,#16]`.
Then:
- `ands r6, r3` with `r3 = 0`, so **p0 = 0**;
- `ands r1, r2` with `r1` still `0x5afa0000` (port 1's mask never loaded),
  so **p1 = RIS1 & 0x5afa0000**: a stray port-1 bit gives a wake with no
  column or knob bit, which is **"charge"**;
- the store `str r0, [r7]` goes to flash at `0xbf30` and is lost, so the
  record's **p1 = 0**;
- the ring reads p1 through `r7` and gets the flash word at `0xbf30`,
  which is **`0xbd102000`**.

A one-word replay would leave `r6 = 0x241e4` and predict a key wake with
p0 `0xe0` (codex, fix review, P2). The whole-block replay explains p0, p2,
the reason, the record and the ring.
- A WFI at 6 mod 8 sits in the block's second word, so the next block was
  fetched before the sleep.
- The sweep's 2 mod 8 variants branched right after the wake, and held.
- The probe's first flash read came at least ~7 cycles after the wake. It
  says nothing about an instruction fetch within the first cycle or two.

## The fix (`mac/sleep-wake-sram`, `8b06e4dcc4`)

The Deep-sleep entry and exit run from SRAM (`ds_deep_wfi`, `.ramtext`),
in every build:
1. CTRL set to 2, then DSB and WFI.
2. CTRL set to 0.
3. A 260-pass wait, 1,298 cycles, ~108 µs at 12 MHz.
4. One flash word read and dropped.
5. The return to flash.

Built as `via-dev-8b06e4dcc4-20261020-150215.bin` (token `0x3e1c880c`) and
`via-daily-8b06e4dcc4-20261020-150240.bin` (`0xbd635765`). The code is
byte-identical to `b3f48e9c5a`, which codex reviewed; only the comment
changed, softened per codex's P3, and the token bytes differ.

**Codex (`review-codex-sleep-fix-2026-10-20.md`): clear for an attended dev
bench flash on JD's go. No P1.** It checked both ELFs:
- the helper and both its literals sit in SRAM, inside the startup copy;
- no flash fetch or flash literal load comes between the WFI and the
  dropped read;
- only r2, r3 and the flags change, and PRIMASK stays held;
- the daily build carries the fix;
- RAM: the dev gap is 144 B, the daily 2,192 B.

Its findings:
- **P2, the one-word replay predicts the wrong p0.** **Taken:** the
  whole-block replay above, still marked a hypothesis.
- **P2, the dev light-sleep hook still runs a WFI from flash in PMU Sleep
  (4).** It is off by default. **Taken:** it stays off, and gets its own
  SRAM path and validation before it is ever promoted.
- **P2, `deep_cycles`' PASS alone is not acceptance.** **Taken:** the
  validation gates on the records, the ring, the recovery's timeouts,
  resets and stalls.
- **P3, the hazard's width is unmeasured.** **Taken:** the comment says so,
  and the wait stays until it is measured and swept.
- **Validation, which codex would require:**
  - a few cycles on each transport, then 100 or more each, with the keys
    reaching the host;
  - an hour asleep with the power logger;
  - P0 and P2 keys, the knob, a charge wake, and settings persisting after
    a wake;
  - a daily smoke test;
  - the fix with its flash caller padded, and its SRAM WFI moved to 2 mod 8
    (both builds put it at 6 mod 8);
  - an overnight soak and a backstop test.
