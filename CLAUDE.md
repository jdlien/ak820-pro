# AK820 Pro → QMK

Workspace for putting **fpb's QMK port** onto JD's **AJAZZ AK820 Pro** keyboard,
with VIA remapping and a customizable 0.85″ LCD.

This folder **is** a git repo (it was not, originally — that claim survived here
long after it stopped being true). It holds four independent upstream clones plus
a local toolchain; the local files — `CLAUDE.md`, `hostagent/`, `assets-src/` —
are tracked and committed to `main`. The **nested clones are not** part of it: do
not commit into them unless asked, except `qmk_firmware-ak820pro`, which carries
the board work on its own `ak820pro-jdlien` branch.

The authoritative background document is
[`ak820pro-builds/AK820PRO-HANDOFF.md`](ak820pro-builds/AK820PRO-HANDOFF.md)
(same content as `handoff.html`). **Read it before doing anything substantive** —
it carries the hardware IDs, flash memory map, asset pipeline, and a list of
upstream project docs that are stale and should be ignored. This file summarizes
the workspace; the handoff explains the device.

---

## Current state (as of 2026-08-29) — QMK IS FLASHED AND RUNNING

- Build environment on this Mac (Gizmo, macOS Tahoe 26.6.2, Apple Silicon): **done and verified**.
- **QMK VIA firmware flashed successfully** on 2026-08-28. Flash verification
  checksum OK; the board rebooted on its own into QMK.
- Keyboard now enumerates as **`0C45:8009`**, product name **"AK820 PRO"**.
- `ak820ctl` sees the QMK raw HID interface (`usage_page=0xFF60 usage=0x61`,
  iface 1). **No Input Monitoring permission was needed** — handoff §4's warning
  did not apply in practice.
- **LCD assets provisioned** to `0x0CE0000` — **195584 B, 11 assets**, verified on
  device with **`crc32=0x46139223`** (2026-08-29, the bunny splash). RTC set.
  The earlier 184064 B / 8 assets / `0xAF49C1FA` figures are superseded.
- **LCD orientation and inversion fixed** (see local firmware edits below) —
  confirmed on hardware: right way up, white text on black, clean to every edge.
- RGB default set to dim warm white, though EEPROM still holds whatever was last
  set by hotkey/VIA.
- **LED field rate 121 → 1046 Hz**, DLP-rainbow artifact much reduced (not
  eliminated — it is inherent to time-slotted R/G/B and no achievable rate
  removes it).
- **LCD backlight is now dimmable** — software PWM, **10** perceptually-spaced
  levels, `Fn`+`PgUp`/`PgDn`. Boots at level 5 of 9 (`LCD 56%`).
- **Clock**: divider trim implemented and converging; seeded at the measured
  value. Was ~4 s/min out, now holds inside the 2 s threshold.
- **Freeze while adjusting RGB**: fixed by an eeconfig flush guard. Not yet proven
  over normal use.
- **Bluetooth (2026-08-29)**: ACK timeouts **0.38 → 0.042 per frame**, zero
  dropped, at the *highest* row-ISR rate. Root cause was an inverted interrupt
  priority table — see that section, and check it FIRST on any regression.
- **Four CH582F state bugs fixed**, all wire-traced: missed `5B 32`, media keys
  gated on a stale flag, `A6 51` dropped mid-connect, and `A6 <slot>` being a
  no-op while advertising.
- **Pairing UX**: 2 s hold that fires under the finger with a progress bar, and a
  status band that says what the blinking digit means.
- **Boot splash is JD's bunny logo**; the file is still named `sonixqmk.png` on
  purpose (asset ids are sorted by filename).
- Measured matrix scan rate **~390-400 Hz** (1396 stock) at `SPD_STEP 128`.
  A 2.5 ms scan period; confirmed on hardware as "nearly instant" over
  Bluetooth. See the scan-rate table.

### Working with VIA

Load `keyboards/a_jazz/ak820pro/via.json` (identical to the
`ajazz-ak820-pro/QMKFWBinaries/` copy) — the board is not in VIA's database.
usevia.app in Chrome/Edge only (WebHID); Settings → **Show Design tab** →
**Load Draft Definition**. Verified to match the running firmware
(`0x0C45`/`0x8009`).

Layers are `WINBASE=0, WINFN=1, MACBASE=2, MACFN=3` — the mac/win dip switch
selects the base, so per-key remaps usually need doing on both 0 and 2.
`menus: ["qmk_rgb_matrix"]` gives a full lighting picker; 20 custom keycodes
(`BT*`, `RGBM_*`, `SCR_TOG`, `SCR_UP`, `SCR_DN`, `ANIM_TOG`) are exposed.

**VIA's stored keymap overrides the firmware default.** A keycode newly bound in
`keymap.c` will NOT appear if the dynamic keymap in EEPROM already has that key
assigned — assign it in VIA instead, or reset the EEPROM keymap.

### The VIA keymap survives a flash now — `ak820keymap.py`

Flashing erases the emulated EEPROM, so every firmware update used to mean
re-entering the VIA keymap by hand. `./flash.sh` now dumps it first and writes
it back afterwards.

```sh
python3 hostagent/ak820keymap.py dump      # -> ~/Documents/ak820pro-keymap.json
python3 hostagent/ak820keymap.py restore
python3 hostagent/ak820keymap.py show      # inspect a saved file
```

**It saves the RAW dynamic-keymap buffer (720 B = 4 layers x 6 x 15 x 2), not
VIA's `.layout.json`.** That export stores keycode *names*, so restoring it
would need a QMK name-to-value table that drifts as QMK renames keycodes —
exactly the class of problem that made `RM_SPDD` look broken. The raw buffer
round-trips whatever the board holds and needs no table.

**Encoders are a SEPARATE command** (`0x14`/`0x15`, outside the keymap buffer).
Skipping them would silently drop the knob mapping — on this board that includes
`LSA(KC_VOLD/U)` on the Mac layers, whose absence looks like the fine-volume
feature breaking rather than a backup gap.

Guards: refuses an all-zero dump (a failed read cannot overwrite a good backup),
writes via temp + atomic rename, and refuses to restore a file whose matrix or
layer count disagrees with the board. **Wired mode required** — raw HID replies
route through the active host driver, the same reason `ak820ctl` and VIA need
the cable.

Verified 2026-08-31: dump -> restore -> dump returns byte-identical keymap and
encoders, and the decoded encoder values match JD's own VIA export on all four
layers.

### Stock-keymap shortcuts (as shipped, before any VIA remaps)

Identical on `WINFN` and `MACFN`. `Fn` is the physical key right of right-Cmd.

| Keys | Does |
|---|---|
| `Fn`+`Q` / `W` / `E` | Bluetooth slots 1 / 2 / 3 |
| `Fn`+`R` | 2.4 GHz dongle |
| `Fn`+`P` | ~~pair (hold)~~ — **UNBOUND 2026-08-29**, see below |
| `Fn`+`←` / `→` | RGB hue − / + (step 8) |
| `Fn`+`↑` / `↓` | RGB brightness + / − (step 16) |
| `Fn`+`6` / `7` | RGB saturation + / − (step 16) |
| `Fn`+`X` | RGB on/off |
| `Fn`+`\` | next RGB effect |
| `Fn`+`-` / `=` | effect speed − / + |
| `Fn`+`Esc` | `QK_BOOT` — bootloader |
| `Fn`+`Delete` | `ANIM_TOG` |

**BT keys are inert in wired mode.** `CH582_PROTOCOL.md`: the protocol is live
only in BT (`== 1`) or 2.4G (`== 2`) mode; in USB mode the CH582F is bypassed
entirely. Set the `bt/off/cable` dip switch first.

Pairing UX — **the "10 s" description that was here was wrong**; no such logic
exists in the code, and there is no "aborts if the link comes up" behaviour.
What `process_record_kb()` actually does with `BT1`/`BT2`/`BT3` (Fn+Q/W/E):

| Action | Effect |
|---|---|
| **Press** (any slot, selected or not) | `ch582_set_profile()` — selects the slot and starts a connect. State goes to `LINKING`; the digit slow-blinks. |
| **Held past `BT_PAIR_HOLD_MS` (2 s)** | `ch582_enter_pairing()` — the slot starts advertising. Digit fast-blinks. A `Pair: ======` bar fills during the hold. |
| **Release** | Disarms only. |

**Pairing used to fire on key-UP, not at the threshold** — so holding did nothing
visible until you let go, contradicting the code's own comment. Fixed 2026-08-29:
`bt_pair_hold_task()` runs on the 10 Hz housekeeping tick and fires the instant
the threshold passes while the key is still down. Both the slot keys and `Fn`+`P`
now only arm/disarm in `process_record_kb()`.

**The hold is 2 seconds** (was 1 s until 2026-08-29). **A slot-key press also
issues a select/reconnect**, so a merely slow tap at 1 s would drop a live link
and start advertising, and recovering needs a re-select. Pairing is rare and
deliberate; reconnecting is the common action, so the gesture must sit well clear
of any tap. The cost of a longer hold is only frustration when nothing shows it
is working — hence the progress bar, which is what makes 2 s *better* rather than
merely safer.

**Expect ~200 ms MORE than the constant by stopwatch, at any threshold.**
`bt_pair_hold_task()` runs on the 10 Hz housekeeping tick and the band redraws on
that same tick, so a 1 s threshold measured as ~1.2-1.3 s by hand. That is tick
granularity, not slack — **do not "correct" the constant for it.**

**The original 1 s figure was MEASURED, not assumed.** `BT_PAIR_HOLD_MS` in
`ak820pro.c`. Captured 2026-08-29 with temporary instrumentation:

```
[pair] press slot=3
[5b] 36  x2            slot unreachable, fails instantly
[pair] fire at 1066ms  our threshold
[pair] A6 51 queued
[5b] 31                MODULE ADVERTISING, same second
[pair] release at 2942ms armed=0
```

`5B 31` lands ~1.1 s after the press, so **there is no downstream delay** — the
module does not defer the pair command behind the in-flight connect attempt, a
theory that looked plausible and was wrong.

**Why it felt like 3 s (worth understanding before "fixing" the number).** Two
separate causes, both about feedback rather than timing:

1. Pairing used to fire on key-UP. Holding 1 s then releasing *did* work, but
   nothing was visible until the release, so the whole gesture read as one long
   action. Fixed by `bt_pair_hold_task()`.
2. Even firing correctly, the hold was **silent until it fired** — being 100 ms
   short looked identical to the feature not working, so the natural response is
   to hold longer and longer. Hence `display_set_pair_hint()`: the band shows
   `Hold to pair` from the press until it resolves.

The hint **outranks every link state** in `conn_status_update()`. During the hold
the state is whatever the press kicked off, and on an unreachable slot that is
`REJECTED` — so without the override the panel read `Link failed` while the user
was still mid-gesture. Nothing has failed yet at that point.

**Do not raise `BT_PAIR_HOLD_MS` to match the old 3 s guess.** That would make the
firmware genuinely require what was only ever a feedback artifact.

### ⚠️ `A6 <slot>` is DECLINED while the module is advertising

**Symptom:** pair to a device, enter pairing mode again, then try to go back —
it will not reconnect until you switch to another slot and back.

**Captured on the wire 2026-08-29** (`Fn`+`W` = slot 2, phone already paired):

```
[tx] A6 51 pair      -> [rx] 5B 31   module advertising
[tx] A6 32 select    -> [rx] 5B 23   idle. NO 33 (attempting), NO 32.   <-- declined
[tx] A6 33 select    -> [rx] 5B 36
[tx] A6 32 select    -> [rx] 5B 32   works, after the back-and-forth
```

**It is NOT a lost frame.** The module answers — with `5B 23`. It stops
advertising and then simply never starts connecting. A working select is answered
`33`/`34`/`32` inside a second (measured, both in this trace and elsewhere), so
the absence of any of those is a reliable "it declined".

**Why it never recovered:** the select is issued exactly once. The cold-boot
retry below is gated `connect_requested && !module_alive`, so once the module has
ACKed anything it is never re-issued — deliberately, and for a good reason.

**RETRYING DOES NOT WORK. Four hypotheses died here; do not re-derive them:**

| # | Hypothesis | Killed by |
|---|---|---|
| 1 | Lost UART frame | The module *replies* — with `5B 23`. |
| 2 | Timing; retry until it takes | **8 selects over 10 s drew ZERO responses.** |
| 3 | Retry when it goes idle (`5B 23`) | It emits *nothing at all* while advertising, so the trigger never fires. |
| 4 | **Same-slot select is a no-op; a DIFFERENT slot is required** | Matches every trace, and is why the manual `Fn`+`Q` workaround works. |

The module ignores `A6 <slot>` for the whole BLE advertising window — **minutes**,
confirmed by the user ("it does eventually pair, but it takes a few minutes").
Naming a *different* slot forces a state change immediately.

An earlier trace made this look like timing: recovery came at +9 s. But that
recovery was an `A6 33` — a **different slot**. The delay was incidental; the slot
change was the cause. Reading it as timing cost two failed fixes.

**Fix — the cancel-pairing bounce.** Pressing a slot key while THAT slot is
advertising now does automatically what the user did by hand: send a different
slot, wait `CH582_BOUNCE_MS` (700 ms), then send the real target (which, being
different from the bounce, is honoured). Verified 2026-08-29, ~1 s recovery:

```
[tx] A6 51 pair              -> [rx] 5B 31   advertising
[tx] A6 32 select (cancel-pairing)
[tx] A6 31 bounce            -> [rx] 5B 32   state forced
[tx] A6 32 after bounce      -> [rx] 5B 33, 5B 32   reconnected
```

**⚠️ The bounce slot can briefly CONNECT.** In the verification trace the bounce
to slot 1 returned `5B 32` — it really did link to slot 1 for ~700 ms before
moving on. Unavoidable: forcing the state change requires naming another slot, so
this is the same exposure the manual workaround has. If it becomes annoying,
prefer a bounce slot recently seen to fail (`5B 36`), which is usually an empty
one. Only reachable when cancelling pairing, never on an ordinary slot change.

`select_pending` (re-issue after `CH582_SELECT_CONFIRM_MS`, up to
`CH582_SELECT_MAX_TRIES`) is **kept as a backstop** for genuinely dropped
selects, but note it cannot fix the advertising case — that is what the bounce is
for.

**⚠️ The retry MUST stop the moment `5B 33`/`34` arrives, and it does.** That is
the whole reason the old blanket 500 ms retry was removed: re-selecting a module
that is *already attempting* restarts its advertising and starves a slow
reconnect. A phone reconnects in <500 ms and beats the retry, but **macOS
directed advertising takes longer and never completes**, which previously forced
a manual pairing entry. Retrying only while the module has NOT started an attempt
is what makes this safe — do not widen the condition.

### ⚠️ `A6 51` is ignored while a connect attempt is in flight

**The real cause of "hold 1 s: nothing, 2 s: nothing, 3 s: works".** It is not a
timing threshold at all — it is *state*-dependent, and it defeated a measurement
that looked conclusive.

Pressing a slot key calls `ch582_set_profile()`, which issues a connect (`A6
<slot>`). The module then reports `5B 33`/`34` (attempting) for a while. A
hold-to-pair fires **straight into that window**, and the single `A6 51` is
silently dropped. Only once the attempt is abandoned (`5B 36`) is the module
listening — which is why the *third* press works: by then it has given up.

**How this hid from instrumentation.** A one-shot capture caught the module
already in the abandoned state (earlier presses had left it there), so `A6 51`
landed first try and `5B 31` arrived ~1.1 s after the press. That reads as clean
confirmation of the 1 s threshold and is nothing of the kind — a single
measurement of state-dependent behaviour only ever confirms the state it caught.
The user's repeated press/release pattern was the more informative experiment.

**Fix:** pairing is confirmed by `5B 31`, not by having sent `A6 51`.
`pairing_pending` resends every `CH582_PAIR_RETRY_MS` (400 ms) up to
`CH582_PAIR_MAX_TRIES` (12, ~4.8 s), and clears on `5B 31` (confirmed), `5B 32`
(connected instead), or `ch582_set_profile()` (superseded).

`conn_state` is still set to `PAIRING` **optimistically** on the first send, so
the band reacts immediately; the retry makes it true. Waiting for `5B 31` to
update the display would leave `Link failed` on screen for seconds after the user
did exactly the right thing.

**If it still needs multiple presses**, the next thing to try is explicitly
cancelling the in-flight connect before sending `A6 51`, rather than outwaiting
it. Retrying is the less invasive option and was tried first.

### The clock: architecture, two doc errors, and the divider trim

Two physical clocks. A battery-backed **PCF8563** (a CHMC D8563F clone) is the
reference; the **SN32 internal RTC** is the live 1 Hz clock the display reads,
seeded from the PCF and disciplined to it.

**`config.h` and `rtc.h` were both wrong about how this works.** They claim
calibration *"snaps the phase and trims the divider so the clock self-locks on
any hardware (no hardcoded SECCNTV)"*. It did not. `rtc_clock_discipline()` only
ever called `rtcSetTime()` — a phase snap. `rtc_lld_set_period()` existed (added
by `rtc_lld.diff`) and was never called. `config.h` also cited a
`RTC_CAL_INTERVAL_S` that does not exist, at "~1/min", when `rtc.c` defaulted
`RTC_CHECK_INTERVAL_S` to **3600**.

Why it mattered: `SN32_RTC_CLK_SOURCE` is `SN32_RTC_CLK_SRC_ILRC`, the **internal
RC oscillator**, with `SN32_RTC_PERIOD_DEFAULT 32000` assuming exactly 32 kHz.
This unit's ILRC runs ~34.3 kHz — **~4% fast**, entirely normal for an untrimmed
RC. Snapping alone left a sawtooth as big as an interval's drift: **±5 minutes**
per hour at the stock 3600 s interval.

Now implemented: a real divider trim, measured over a window built from two
**snap-immune** quantities — `rtc_seconds_count` (free-running tick count,
untouched by `rtcSetTime`) and the PCF's own absolute time. Verified converging
on hardware:

```
trim 32000 -> 32695  (360 ticks / 345 s)   +695
trim 32695 -> 33019  (360 ticks / 353 s)   +324
trim 33019 -> 33251  (360 ticks / 355 s)   +232
trim 33251 -> 33330  (420 ticks / 418 s)   +79
trim 33330 -> 33376  (720 ticks / 718 s)   +46
```

Steps shrink and **windows lengthen on their own** as it locks. Phase snaps
stopped entirely once converged.

**Three traps, all hit during development:**

1. *Restarting the window on a phase snap.* The snap fires exactly when drift is
   large, so the trim never survived to take a second sample and **never ran
   once**. Hence the snap-immune window.
2. *Trimming on any nonzero difference.* The reference has 1 s resolution, so a
   60 s window always shows ±1 whether or not the clock is wrong. The window
   never grew, resolution stayed at 1.7%, and it **limit-cycled** between the two
   adjacent quantised answers (33103 ↔ 33664) forever. Hence
   `RTC_CAL_MIN_WINDOW_S 300` and `RTC_CAL_MIN_DIFF_S 2`.
3. *Applying the full correction.* A quantisation-sized overshoot becomes a
   standing oscillation. Hence half-step damping — costs iterations, buys
   convergence.

`RTC_PERIOD_INITIAL 33400` seeds the measured value because **the trimmed period
is not persisted** — every boot otherwise re-climbed from 32000 over ~40 minutes
with the display visibly jumping. It is a per-unit, temperature-dependent RC
value: a starting point, never a substitute for the trim. Re-measure by removing
it and watching the trims converge from stock.

**⚠️ THE PCF8563 DRIFTS ~58 ppm — ABOUT 5 s/DAY. A SCHEDULED RESYNC *IS* NEEDED.**
An earlier note here said the opposite ("still within 2 s… no scheduled
`ak820ctl clock` job is needed"), measured a few hours after setting it. Over a
few hours the error is still inside the ±2 s snap threshold and looks like
nothing. Measured again at **24 h: 5 seconds fast**, i.e. ~58 ppm, ~3 min/month.
Normal for an uncompensated 32.768 kHz crystal, worse in a clone.

**The divider trim is not at fault and cannot help.** Everything above disciplines
the SN32 *to the PCF*, so the trim faithfully reproduces the reference's error.
The trim is doing its job perfectly on a reference that is wrong. Do not go
looking in `rtc.c` when the clock drifts by minutes per month.

**Fix: `hostagent/ak820-clocksync.sh` + `com.jdlien.ak820pro.clocksync.plist`,
every 6 hours** (`StartInterval 21600`, plus `RunAtLoad`). At 58 ppm that bounds
the error to ~1.3 s — inside `RTC_DRIFT_THRESHOLD_S`, so the display never
visibly jumps. Log: `~/Library/Logs/ak820pro-clocksync.log`.

**It needs `ak820ctl clock --no-wait`, a flag added for this.** `cmd_clock` used
to read a reply, and raw-HID replies route through the **active host driver** — so
in BT/2.4G mode the answer goes over the air and the command fails *even with the
cable plugged in*, which is the normal way this board is used. The write-only path
(`xfer_nowait`) sidesteps that exactly as `ak820text.py` does. A clock set needs no
confirmation: a silent miss is corrected by the next run.

**It still requires the USB cable** — the HID interface has to exist. On battery
there is no sync path at all, so a board left unplugged for days will drift the
full ~5 s/day. `RunAtLoad` catches it as soon as the machine is back.

**±2 s is the design bound, not residual error.** `RTC_DRIFT_THRESHOLD_S 2` is
where the phase snap fires, so the loop guarantees it. `1` would halve it at the
cost of the display jumping a second more often.

**~1 s is the hard floor regardless of trim quality.** The PCF exposes whole
seconds only — no sub-second register — so the reference itself is quantised.
Beating that needs a different reference (USB SOF timing, or a host-assisted
calibration protocol over raw HID), which is a lot of machinery for a keyboard.

**RTC_PERIOD_INITIAL is 33600, MEASURED on this unit 2026-08-30.** It was
33400, which ran ~0.5% fast from boot (-7.2 ms/s) and hit the 2 s snap threshold
in ~4.5 minutes -- visibly drifting and jumping while the trim spent ~7 minutes
converging. Two independent estimates agreed on ~33600: the firmware's own trim
computed 33587 from a 360-ticks/358-s window, and a host phase measurement after
that trim implied 33607.

| | seed 33400 | seed 33600 |
|---|---|---|
| drift from boot | -7.2 ms/s | **+0.82 ms/s** |
| time to the 2 s snap | ~4.5 min | **~40 min** |

The sign flip shows 33600 slightly overshoots (ideal ~33572); left alone, since
the trim absorbs 820 ppm easily.

**⚠️ NEVER UPSTREAM THIS VALUE.** The ILRC is an untrimmed on-chip RC oscillator
that varies part to part and with temperature. 33600 is right for this board and
would start another unit further off than the nominal 32000 does. The durable fix
is **persisting the converged period** -- one eeconfig field written when the trim
settles -- which works for any unit and makes the seed irrelevant. Not yet built.

**Post-sync phase is a fixed offset that DIFFERS PER SYNC**: measured +67 ms in
one run and -229 ms in another, each with near-zero internal spread. That is the
signature of an uncontrolled prescaler -- but note the display reads the **SN32**,
and `rtcSetTime()` evidently does not reset its divider either. Rachel's brief
proposed a PCF STOP-bit sequence for this; the measurements say the PCF is fine
(no uniform-second scatter remains) and the residual is on the SN32 side. If the
last few hundred ms are ever wanted, that is where they are -- and it is a change
to the SN32 set path, not the PCF one. Inferred from two samples; get more before
acting.

 First boot with `RTC_PERIOD_INITIAL 33400`: **zero**
`[rtc]` events — no trims, no snaps — in the first 11 minutes, against five
`corrected drift` corrections in the same window on the previous boot climbing
from 32000. Observed offset ~0.5 s behind host.

**That residual ~0.5 s is a fixed phase offset, not drift.** Seeding/snapping
sets the SN32 to whatever whole second the PCF reports, but the read lands at an
arbitrary point *within* that second, so a systematic lag averaging 0.5 s is
baked in. It does not accumulate. To remove it you would poll the PCF at init
until the seconds register is observed to roll over, then set the SN32 at that
instant — costs up to a second of I2C polling at startup, buys half a second.
Judged not worth it; noted so nobody re-derives it.

### LCD backlight brightness (software PWM)

`PANEL_BKL` (**A16**) is a plain GPIO — stock firmware only had on/off
(`SCR_TOG`), so brightness is done in software.

**Hardware PWM on this pin is impossible — verified in the SN32F299 datasheet,
do not re-investigate.** `P0.16`'s only alternate function is `CT16B5_CAP0`, a
capture *input*. There is no PWM output route to A16. (An earlier note here said
this was "unverified" and that a dedicated timer would be "a second kHz ISR for
no gain" — both wrong, and the timer turned out to be the fix.)

The tick comes from **CT16B3 (`GPTD4`) at a measured 20 kHz**, not from the RGB
row ISR. See "The backlight/indicator PWM tick is a dedicated timer" for why that
move mattered and the `MCTRL` gotcha that makes it work.

- `BKL_PWM_TICKS 48` → 20000/48 = **417 Hz** switching, floor 1/48 = 2.1%.
  Confirmed flicker-free on hardware 2026-08-29. It was sized while the tick was
  silently losing 23% of its interrupts; now that the tick is steady there is
  headroom to lengthen the period for a dimmer floor.
- Levels are **perceptually spaced**, not linear:
  `bkl_duty[] = { 0, 1, 2, 3, 5, 8, 12, 18, 27, 48 }` — **10 entries, indices
  0..9**, so `BKL_MAX_LEVEL` is 9. (This table used to be documented here as
  twelve entries ending `26, 37, 50, 64`. It never was; anyone computing a level
  from that list got the wrong index.) An even spread wastes steps at the top
  where they are indistinguishable and gives nothing usable at the bottom, which
  is the end that matters in a dark room.
- **The `Fn`+`PgUp`/`PgDn` readout is the LEVEL INDEX, not the duty** —
  `level * 100 / 9`, so level 1 shows `LCD 11%` and level 5 shows `LCD 56%`.
  Because the spacing is perceptual, level 5 is duty **8/48 ≈ 17%** of the actual
  PWM period. The two numbers are meant to diverge; do not "fix" one to match.
- `DISPLAY_BRIGHTNESS_DEFAULT 5` (`LCD 56%`, duty 8/48) — **was 1** (`LCD 11%`,
  1/48 ≈ 2.1%) until 2026-08-30. Level 1 was chosen in a dark room against a
  mostly-blank panel and is genuinely too dim against real content: the lit
  pixels are a small fraction of the area, so they carry the whole impression.
  Middle of the range is the better compromise and is still far below stock.
- **Not persisted.** Every kb-eeconfig write is an internal-flash program/erase,
  i.e. the thing that wedges this board. Change the default in `config.h`.

**Minimum brightness is 1 tick, so a dimmer floor needs a LONGER period, which
lowers the switching rate.** That is now the *whole* trade — period against
floor, at a fixed 20 kHz tick.

It used to be a three-way coupling, because the tick came from the RGB row ISR:
`SPD_STEP`, `BKL_PWM_TICKS` and the switching rate all moved together, so tuning
the LED field rate for the rainbow silently retuned the backlight. **That is no
longer true** — the tick has its own timer. Old notes claiming `SPD_STEP` was
raised "so the backlight period could double" describe a design that no longer
exists.

`SCR_UP` / `SCR_DN` keycodes are on `Fn`+`PgUp` / `Fn`+`PgDn`, beside the
existing `Fn`+`Home` toggle.

> **Adding custom keycodes:** the `ak820pro_keycodes` enum is **index-matched** to
> `via.json`'s `customKeycodes[]` (both map onto `QK_KB_0`). **Append only** —
> inserting anywhere else shifts every later keycode and silently corrupts
> existing VIA keymaps.

### ⚠️ Interrupt priority ordering — the single most important tuning fact here

**The ChibiOS defaults had this inverted, and it caused two apparently unrelated
bugs that cost most of a session.** Set in `mcuconf.h`; on Cortex-M0 a LOWER
number is a HIGHER priority.

| Prio | Source | Why it sits there |
|---|---|---|
| **1** | `SN32_SERIAL_UART2` | The CH582F link. **The only peripheral here where being late means LOSING DATA.** Defaulted to 3 — the bottom. |
| **2** | `SN32_GPT_CT16B3` | Backlight/indicator PWM tick. Tiny, but must be *regular* or the display visibly flickers. |
| **3** | `SN32_PWM_CT16B0/1/2` | RGB row scan. Long and very frequent, but a few µs of jitter on an LED is invisible. Defaulted to 2. |

Every symptom below is a consequence of getting this wrong:

- **UART at the bottom (default)** → the row ISR preempted byte servicing, so
  frames to and from the CH582F were mangled. Outbound: ACK timeouts, TX queue
  overflow, dropped keystrokes — *you could out-type the Bluetooth link*.
  Inbound: dropped `5B 32` frames, which is the connection-digit blink bug.
  **Same root cause, both directions** — they were chased separately for hours.
- **GPT at 3 (below the row scan)** → 23% of PWM ticks were lost, measured as
  **15,385 Hz against a configured 20,000**. Symptom: LCD backlight flicker that
  got worse the dimmer it went.
- **GPT at 1 (above the UART)** — an intermediate wrong fix. It restored the tick
  to 19,997 Hz but tripled ACK timeouts (0.38 → **1.14 per frame**), because the
  tick then preempted the UART.

Only the ordering above satisfies all three. **Measured on hardware 2026-08-29
at `SPD_STEP 128`** (row ISR ~18,800/s — the load that supposedly "broke
Bluetooth"), across a real typing burst of 430 frames:

| | Timeouts / frame |
|---|---|
| Old baseline, `SPD_STEP 16` | 0.38 |
| GPT at priority 1 (wrong fix) | 1.14 |
| **This ordering, `SPD_STEP 128`** | **0.042**, `dropped=0` |

**Bluetooth is now ~9x healthier at the HIGHEST row-ISR rate than it was at the
stock rate with the priorities inverted.** That is the whole lesson: the ISR rate
was never the fault, only a proxy for it. Backing off `SPD_STEP` treated the
symptom and cost the LED field rate for nothing.

Measure the ratio over a *sustained burst*, not a short sample — boot traffic
runs ~0.58/frame and will make a healthy board look broken.

**If Bluetooth throughput ever regresses, check this table FIRST.** The tempting
move is to lower `RGB_MATRIX_SPD_STEP` to slow the row ISR down; that treats a
symptom and costs LED field rate, which is the DLP-rainbow knob.

### The backlight/indicator PWM tick is a dedicated timer, not the row ISR

Originally the LCD backlight and the three indicator LEDs were software-PWM'd
from `sn32_rgb_isr_hook()` inside the RGB row ISR. That worked but **welded the
PWM switching rate to `RGB_MATRIX_SPD_STEP`** — so tuning the LED field rate for
the rainbow artifact silently re-tuned the backlight into or out of flicker.

They now run from **CT16B3 (`GPTD4`) at a verified 20 kHz**, set up in
`pwm_tick_init()` in `ak820pro.c`. `SPD_STEP` no longer affects them at all.

Enabling it needs three things, and the third is not obvious:

1. `halconf.h`: `#define HAL_USE_GPT TRUE` before `#include_next`.
2. `mcuconf.h`: `SN32_GPT_USE_CT16B3 TRUE`, plus the priority above.
3. **`SN_CT16B3->MCTRL = CT16_PWM_UNLOCK(SN_CT16B3->MCTRL | mskCT16_MRnRST_EN(0));`**
   after `gptStartContinuous()`.

Without (3) the timer fires **once and never again** — the SN32 GPT LLD enables
the match interrupt but never sets reset-on-match, so the counter runs away past
the match value instead of restarting. Symptom seen on hardware: the backlight
blinked at full brightness roughly every 4-5 seconds and was otherwise black.
It looks exactly like a brightness bug and is not one.

**Hardware PWM on the backlight pin is NOT available — checked, don't re-derive.**
`PANEL_BKL` is **A16**, and the SN32F299 datasheet gives `P0.16` the alternate
function `CT16B5_CAP0` — a capture *input*. There is no PWM output route to that
pin. Software PWM off a dedicated timer is the correct answer, not a workaround.

### Matrix scan rate vs row-ISR rate (measured)

| Row ISR | Matrix scan | Notes |
|---|---|---|
| 2,189/s | 1396 Hz | stock |
| 8,963/s | ~1050 Hz | `SPD_STEP 64`, field rate 498 Hz (no GPT tick yet) |
| 18,800/s | **389-404 Hz** | `SPD_STEP 128`, field rate 1046 Hz — **current, measured 2026-08-29** |

The 585 Hz once predicted for this row was measured **before** the dedicated
20 kHz PWM tick existed. With the GPT running there are ~38,800 interrupts/s
between the two sources, and the real figure is ~390-400 Hz. Confirmed on
hardware as feeling "nearly instant" to type on over Bluetooth.

**The millisecond timebase runs ~1.2% slow at this load — a saturation canary.**
`[pwmtick]` reports 20,150-20,260 Hz for a timer that is configured at, and was
measured at, exactly 20,000. The timer cannot have sped up; QMK's `timer_read32()`
ms counter has slowed, because systick interrupts are occasionally lost under
~38,800 interrupts/s. The reading tracks row-ISR load exactly, which is the tell.

Consequences are benign and worth knowing rather than fixing: the clock reads the
SN32 RTC's hardware registers and the divider trim uses `rtc_seconds_count` plus
the PCF's absolute time, so **neither is affected**; debounce becomes 5.06 ms.
But if this number climbs much further, the board is out of CPU — treat a rising
`[pwmtick]` as the first sign, before typing feel degrades.

Cost scales **worse than linearly** — ISR entry/exit overhead on a Cortex-M0
dominates a handler this small. 585 Hz is a 1.7 ms scan period; typing latency is
dominated by switch travel and debounce, both far larger, and it feels fine on
hardware. This is the first thing to back off (`SPD_STEP` → 64) if typing ever
regresses.

### Indicator LEDs (Caps / Win Lock / Charging)

All three are plain GPIOs — Caps `D15`, Win Lock `C15`, Charging `B18` — and were
searchlights at full drive. They are software-PWM'd on the same tick as the LCD
backlight (`sn32_rgb_isr_hook` in `ak820pro.c`, which also calls
`display_backlight_tick()`), with **per-LED levels**.

- `INDICATOR_BRIGHTNESS_DEFAULT 1` — Caps and Win Lock, dimmest lit step.
- `CHARGING_LED_BRIGHTNESS 0` — **off**. Not user-controllable, and the battery
  icon now shows charging anyway.
- `phase < duty` handles both ends without special cases: duty 0 never fires
  (genuinely off, not a short pulse), duty == period is always on.

**Caps Lock had to be claimed from QMK core.** It was driven by
`led_update_ports()` from `indicators` in `keyboard.json`. `led_update_kb()`
returning `false` skips that write so the pin is ours — but the `indicators`
entry is **kept**, because it is what defines `LED_CAPS_LOCK_PIN` and configures
D15 as an output at init.

**Brightness and flicker are the same knob.** At these levels the LED is lit for
exactly one tick per period, so one pulse per period *is* the flicker frequency —
dimmer necessarily means slower. Measured on this unit:

| Ticks | Switching | Min duty | Result |
|---|---|---|---|
| 64 | 293 Hz | 1.6% | no flicker, slightly too bright |
| **96** | **195 Hz** | **1.0%** | current — accepted |
| 128 | 146 Hz | 0.78% | Caps visibly flickered, looked intermittent |

The only escape is a faster ISR, which costs matrix scan rate. If flicker
returns, **shorten** `IND_PWM_TICKS` (brighter, faster) rather than reaching for
`RGB_MATRIX_SPD_STEP`.

### Caps Lock LED is unreliable over Bluetooth — same root cause as the digit bug

Confirmed on hardware 2026-08-28: flaky in BT, reliable wired.

`host_keyboard_leds()` dispatches to the **active host driver**. Wired, that is
the USB LED report — direct and reliable. In BT/2.4G it is
`bluetooth_keyboard_leds()` → the CH582F's `host_leds`, which `ch582f_ajazz.c`
gates on `is_module_connected` and zeroes on every `5B` link-down code. So a
wrong link state **silently drops every `5A` LED frame** and the Caps LED stays
dark while the host thinks Caps is on. Same fragility as the BT channel-digit
quirk; the `5A` promotion heuristic helps but does not guarantee it.

**Not a bug: the laptop's Caps LED and the AK820's do not sync.** macOS tracks
Caps Lock state per HID device, so each keyboard keeps its own state and LED.
Capitalisation is global once Caps is on; the indicators are independent.

### Battery display

Bottom strip (`STATUS_Y 106`): battery icon bottom-left, percentage still
right-aligned. 24x12 body plus terminal nub, drawn with `lcd_fill_rect` as four
1px edges so the interior stays background and the fill is independent.

- Colour by level: green >50%, amber 21-50%, red <=20%.
- **Charging overrides with cyan**, on the outline as well as the fill, so it
  reads as a state change rather than a level change.
- Fill **rounds up** — any nonzero charge shows at least one column, because an
  empty outline at 3% reads as "dead" rather than "nearly dead".
- Redraw triggers on **charging state as well as level**. Easy to miss: the
  level can sit unchanged for an hour while the cable goes in.
- **9x14 charging bolt** right of the icon, shown only while actively charging
  (`CHRG` low AND `STDBY` high — plugged in with a full battery is "done", not
  charging, so the bolt stays hidden). Redundant with the cyan, deliberately:
  colour is a fine cue once you know it, the bolt is legible immediately.
- Icon at `BATT_X0 5` and percentage right-aligned to `PANEL_WIDTH - 4`, not the
  panel edges — **the LCD is recessed and the bezel clips the outermost columns**
  when viewed from the right.

**Drawing diagonals: rasterise, do not hand-place.** Two hand-built zigzags of
rectangles both read as the digit "4". Diagonals only look like diagonals when
they step one pixel at a time, so define the shape as a polygon, rasterise it
with PIL, and emit the horizontal runs as `lcd_fill_rect` calls (11 rects for the
bolt). Reusable for any future glyph.

**Runtime estimate: considered and rejected.** The CH582F reports whole percent
only, so with a multi-day battery **1% ≈ 1.2 hours** — no rate is observable in
under an hour, and ~5% of drop (≈6 h unplugged) is needed for even ±20%. RGB
brightness swings the draw by perhaps 5-10x, so a rate measured under one load
does not predict another, and this board lives plugged in, which resets the
history constantly. It would be wrong far more often than right, and a
confidently wrong number is worse than a blank space. Would need a voltage read
or current sense; the protocol doc is explicit that `5C <pct>` is all there is.

### LCD lock / layer indicator band

The clock (Regular-30, 34 tall at `CLOCK_Y 49`) ends at y82 and the battery row
starts at `STATUS_Y 106`, leaving **exactly 23px** — which is the Medium-20 cell
height, so one row of status text fits precisely.

```
[padlock]  CAPS      WIN      FN|SCR
   x=4     x=20      x=64      x=96
```

- Labels appear **only when active**; the band is left black otherwise. This
  board lives on a desk in a dark room, so a permanently-lit row of words defeats
  the point.
- **Yellow padlock** appears for *lock* states only — CAPS, WIN, SCR. A held Fn
  layer is not a lock and lights its slot without one; that stays correct if Fn
  is ever made a toggle.
- **Third slot is shared.** Scroll Lock wins when actually set, but the board has
  no Scroll Lock key and macOS effectively never sets it, so in practice it is
  the Fn indicator. Both fit: `FN` → x115, `SCR` → x125.
- Redraws on the **~10 Hz housekeeping tick**, not the 1 Hz clock path, so a Caps
  press shows immediately. Self-guards on state change.

**Labels are white because `lcd_draw_flash_text()` has no colour parameter.** The
atlases are RGB565 with colour baked in, and a glyph blit paints its whole cell
*including* the black background — there is no transparency and no tinting.
Colour is only available from `lcd_fill_rect`, which is why the padlock is drawn
from rectangles rather than being a glyph. Real icons would mean regenerating
`flash_assets.bin` + `flash_assets.h`, a firmware rebuild **and** re-provisioning
— the coupling the handoff warns about.

The padlock is 13×16: body plus a 9px shackle whose crown steps in two rows (5
wide, then 7). A first attempt at 11×14 with a 5px flat-topped shackle read as a
blob — too narrow against the body and visibly square on top.

**"WIN", not "GUI".** The flag is `keymap_config.no_gui`, which technically
disables Cmd on a Mac — but GUI-lock exists so the Windows key cannot yank you
out of a fullscreen game, and on macOS locking Cmd would disable most hotkeys and
nobody would enable it deliberately. The label names the only context where the
feature is meaningful. (Also: nobody outside keyboard firmware calls it "GUI".)
The accessor stays `lock_state_gui()` to match QMK.

Fn detection uses the raw layer bitmask `(1<<1)|(1<<3)` for `WINFN`/`MACFN`,
because that enum lives in `keymap.c` and is not visible from `ak820pro.c`.
**Update the mask if layer indices are ever rearranged.**

### Caps Lock did not capitalise — RESOLVED, cause never confirmed

**Resolved 2026-08-28 after a reflash; root cause unknown.** Recorded because it
cost real time and would look identical if it recurs. Observed: pressing Caps on the AK820 makes
macOS show the caps indicator under the cursor, but typed letters are NOT
capitalised. The MacBook's own Caps works normally. Not explainable by the LED
code, which cannot affect keycode processing.

**The NKRO theory below was never confirmed and was NOT the fix** — the console
proves the Command combo never fired, so NKRO was never toggled. Most likely a
state desync between macOS and the board that a reset cleared. Kept as the first
thing to check if it returns.

Hypothesis: `nkro: true` means the board presents **two** keyboard HID
interfaces (confirmed via `ak820ctl list`: `usage_page=0x0001 usage=0x06` on both
iface 0 and iface 2). macOS tracks Caps Lock state **per HID device**, so the
toggle can register on one interface while ordinary keystrokes arrive on the
other — indicator on, capitalisation not applied. The internal keyboard is a
single device and has no such split.

Against it: `NKRO_DEFAULT_ON` is **false**, so NKRO is off unless something
enabled it — in which case both keystrokes and the Caps toggle use the same boot
interface and macOS has nothing to split.

**To investigate if it recurs**, no binding needed (`command: true` is on):
hold **both Shifts**, then tap **`S`** — dumps `keymap_config.nkro`,
`keyboard_protocol` and `host_keyboard_leds()` to the console. **`N`** toggles
NKRO, **`H`** lists all magic keys. `IS_COMMAND()` is
`get_mods() == MOD_MASK_SHIFT`, i.e. *exactly* both shifts and nothing else — a
third modifier held silently prevents it firing.

**Confirmed real, and the source of the confusion: macOS tracks Caps Lock state
per keyboard**, not globally as on a PC. The MacBook's Caps and the AK820's are
independent — separate states, separate LEDs. Expected behaviour, not a bug.

### ⚠️ `flash write` ERASES FIRST — a failed write leaves the panel blank

Hit on 2026-08-28. `ak820ctl flash write` erases all 48 sectors before writing,
so a write that fails after starting destroys the existing assets. Symptom: the
LCD shows **only the battery icon** — because that is drawn from `lcd_fill_rect`
rectangles, while everything else (clock glyphs, connection strip, OS logo) comes
from flash. That contrast is the fastest way to recognise it.

The firmware announces the state clearly, and recovery is exactly what it says:

```
[assets] NO VALID INDEX at 0xCE0000 -- panel stays blank.
[assets] provision with: ak820ctl flash write 0xCE0000 flash_assets.bin
```

**Verify raw HID responds BEFORE starting a write** (`ak820ctl info`). The write
needs QMK running and the raw-HID interface free; if it is blocked, the erase
still happens and you are left with nothing.

**The usual cause is BLUETOOTH MODE, not a busy interface.** Confirmed in
`tmk_core/protocol/host.c`:

```c
void host_raw_hid_send(uint8_t *data, uint8_t length) {
    host_driver_t *driver = host_get_active_driver();   // BT driver in BT mode
    (*driver->send_raw_hid)(data, length);
}
```

Raw-HID **replies route through the active host driver**. In BT/2.4G mode the
firmware receives the USB request, handles it, and sends the answer over the
*wireless* link — where `ak820ctl` is not listening. So **`ak820ctl` and VIA both
require the dip switch in wired mode.** Same host-driver indirection that makes
the Caps LED unreliable over BT; third symptom of one cause.

A browser can also hold the interface (usevia.app claims it exclusively while
connected, and closing the tab in one browser does not help if it is open in
another), but check the dip switch FIRST — it is the more common cause and
costs nothing to rule out.

Signature either way: `ak820ctl` says `no reply` while `qmk console` keeps
printing scan rates — **console alive + raw HID silent is NOT the hang**. The
hang kills both.

**Do not reflash firmware to fix this** — the firmware is fine, and the
bootloader is the wrong direction: provisioning needs QMK *running*. If the board
is already in the bootloader, flashing the same binary is the quickest way back
(sonixflasher reboots into QMK afterwards).

**Do not touch the mode switch during a write.** Flipping `bt/off/cable`
re-points the active host driver and drops the HID stream mid-transfer — seen at
84% with `IOHIDDeviceSetReport failed: (0xE00002ED) device not responding`. The
erase has already happened by then, so it leaves the same blank panel. Same
hazard class as the browser holding the interface, different trigger. The board
itself stays perfectly healthy throughout; just re-run the write.

**Assets load at boot**, so after a successful write the panel stays blank until
a power cycle. Watch for `[assets] index ok, N entries`.

### ⚠️ A CRC MATCH DOES NOT MEAN THE BOARD IS RENDERING THE NEW ASSETS

Hit 2026-08-30 and worth its own heading, because every check you would normally
run **passes** while the panel draws garbage.

The index is parsed into RAM **once, at boot**. Provision after that and flash
holds the new blob while RAM still describes the old one. `ak820ctl flash crc`
reads the *flash*, so device and local agree perfectly — both sides are correct,
and the stale copy is the one nobody is looking at.

What it looks like, using the Cozette swap as the worked example:

- The 13px atlas sat at the same offset `+0x001500` in both blobs, so it was
  found — but the cached index said `cell_w=7` against 6-wide tiles. Glyph `n` is
  read at `n * cell_w * cell_h * 2`, i.e. 196 B per glyph out of a 168 B/glyph
  array, **so the skew compounds along the alphabet**.
- Worse, that atlas *shrank* 18,620 → 15,960 B, so **every later asset moved
  2,660 B earlier**. The 20px font, the clock, the connection strip and the icons
  were all read from the wrong addresses.

**Power-cycle after every provision, before judging anything on the panel.** Dip
switch to `off`, ~10 s, back to `cable` — the board is battery-backed, so pulling
the cable alone does not cold-boot it.

### The firmware reads `cell_w` from the flash index AT RUNTIME

`lcd_bus.c` takes `a->cell_w` from the index sector and `lcd_draw_flash_text()`
advances by it, so **changing a font's cell size does not shift any asset id**
and the regenerated `flash_assets.h` differs by its dimension COMMENT only. That
is why 7x14 → 6x14 needed no coordinated re-provision of the kind the handoff
warns about.

What *is* compile-time, and so does need a rebuild: `DISPLAY_TEXT_MAX_L0`/`_L1`,
and the hardcoded `adv = big ? 10 : 6` in `draw_playback()`. **That one is easy
to miss** — it is the only place a cell width is written out by hand.

**Always confirm the on-device CRC against the local blob**, since a partial
write can still report progress:

```sh
python3 -c "import zlib;print(hex(zlib.crc32(open('assets/flash_assets.bin','rb').read())))"
```

### Parameter overlay (info band shows what you just changed)

Adjusting a setting puts a readout in the text band for `PARAM_OVERLAY_HOLD_MS`
(2 s), then hands the band back. Covers RGB hue / sat / brightness / speed /
effect, **RGB on-off**, **NKRO**, and **LCD backlight**.

**NKRO is the one with no other feedback anywhere.** It is toggled by a magic key
(both shifts + `N`), which is easy to hit by accident, and finding out what state
it was in previously meant attaching a console — see the Caps Lock investigation.
The other magic-key toggles (`swap_control_capslock`, `swap_lalt_lgui`,
`swap_grave_esc`, `swap_backslash_backspace`, `swap_lctl_lgui`, `swap_rctl_rgui`)
are equally invisible and equally accidental; they were left off as clutter, but
**a mysteriously misbehaving key is worth checking against that list.** Both
shifts + `H` lists them, both shifts + `S` dumps status.

**`Fn`+`X` is `RM_TOGG`, QMK's built-in — NOT the custom `RGBM_TOG`.** It never
reaches `process_record_kb`'s custom-keycode switch, so a keycode hook would have
missed it entirely. Polling the flag catches it, the custom keycodes, and VIA.

```
Bright  53%     Hue    180     Sat     55%
Speed   50%     Chevron        Jellybean
```

**Removable by design — one define.** `#define PARAM_OVERLAY` in `config.h`;
comment it out and the poll task (`ak820pro.c`), the string slot (`display.c`) and
the declaration (`display.h`) all compile out. Nothing else references it. Keep it
that way — it is a personal nicety and should not entangle the rest.

**POLLED, not hooked into `process_record_kb`.** Five byte comparisons on the
10 Hz tick catch the `Fn` hotkeys, the `RGBM_*` custom keycodes **and anything VIA
changes**, without caring which path made the change. Intercepting keycodes would
miss VIA entirely. A `primed` flag skips the first pass so the band does not flash
a readout at every boot for a change that never happened.

**Effect names are a LOCAL table, deliberately not `rgb_matrix_get_mode_name()`.**
That function is gated behind `RGB_MATRIX_MODE_NAME_ENABLE`, costs flash for all
~40 effect names, and returns the raw enum spelling — `RAINBOW_MOVING_CHEVRON` is
22 characters against a 12-character band. Only **10 animations are enabled**
(`keyboard.json`), so a hand-written table is smaller *and* more readable. Each
case is `#ifdef`'d on its own `ENABLE_RGB_MATRIX_*` so the build survives a change
to the animation list; anything unlisted falls through to `Mode N`.

**Percentages, not raw 0-255** — `53%` is legible where `136` needs you to know
the scale. Hue is the exception: it is circular, so degrees are the meaningful
unit. To show step counts (`16/31`) instead, change the `snprintf` formats.

**Priority: pair hint > RGB > link state > host text.** An active gesture wants
immediate feedback; a link state is passive and will still be there in two
seconds.

**The freeze risk here is smaller than it looks.** The hang fires when an eeconfig
flash write races a flash→LCD DMA blit, and RGB adjustment is exactly when it used
to happen — so adding LCD activity there is a fair worry. But the eeconfig flush is
**synchronous on the main loop**, and `rgb_matrix_eeprom_flush_allowed()` already
blocks starting a flush while a blit is in flight, so the two are mutually
exclusive. If anything the extra blits *defer* flash writes, which is protective.

### Wireless status overlay (firmware-owned words in the text band)

The icon strip says *which* link and the digit says *which slot*, but a blinking
digit only means something if you already know ~200 ms = pairing and ~700 ms =
connecting. This puts it in words, in the same 24px band as the host text slot.

| Link state | Shown | Note |
|---|---|---|
| `PAIRING`, BT | `Pair with:` ⟷ `AK820 5.1-1` | Alternates every 1.5 s (`CONN_STATUS_ALT_MS`), reading as one sentence. The name is the **exact advertised string**, slot digit included — the point is telling you what to look for in the phone's list, so a tidier name would be a lie. Tracks the slot: `-2`, `-3`. |
| `PAIRING`, 2.4G | `Pairing 2.4G` | The dongle pairs; there is no advertised name, so nothing to alternate with. |
| `LINKING` | `Connecting` | |
| `CONNECTED` | `Connected` | **~3 s only** (`CONN_STATUS_HOLD_MS`), then the band is released. |
| `REJECTED` | `Link failed` ⟷ `Hold Fn+W` | Symptom alternating with the **remedy**, naming the single key for the slot that failed (`Q`/`W`/`E` for BT 1-3, `R` for the dongle). `Hold Fn+Q/W/E` is 13 chars — over budget — and worse advice, since the slot is known. |
| wired | *nothing* | The CH582F is bypassed in USB mode, so its state is stale — report nothing rather than the last wireless session's. |

**The remedy is shown for `REJECTED` only — deliberately NOT for a long-lived
`LINKING`.** A persistent `LINKING` is ambiguous: it is equally a dropped
`5B 32` on a link that is actually **up** (the known bug), and telling someone to
hold the slot key there would tear down a working connection to fix a display
bug. `REJECTED` has no such ambiguity — nothing is working either way, so
re-pairing costs nothing. This also makes the advice robust against the `0x36`
uncertainty below: "re-pair this slot" is sane for any stuck wireless state, so a
wrong reading of the code costs the label, not the instruction.

**Dirty-tracking gotcha (was a real bug).** `conn_status_buf` is shared by the
pairing and remedy strings, so a change of *state* must mark it dirty as well as
a change of *slot* — `REJECTED` → `PAIRING` on the same slot rewrites the buffer
while its POINTER is unchanged, and a pointer compare alone leaves the previous
message on the panel. Both feed `changed` in `conn_status_update()`.

**`5B 36` — CAPTURED ON THE WIRE 2026-08-29, and it is absent from the protocol
doc's state table** (which lists only `0x31`, `0x32`, `0x33`/`0x34`, `0x23`).
Selecting an unreachable slot produced:

```
5B 34            connect attempt
5B 32  x2        link established        <- a DIFFERENT, successful slot
5B 23            idle
  --- Fn+E pressed, selecting an unreachable slot ---
5B 33  x2        connect attempt
5B 36            ATTEMPT ABANDONED
5B 23  x2        idle  (ignored by the parser)
```

So `0x36` follows failed attempts and then **persists** — the module never
retracts it, and the trailing `5B 23` is deliberately ignored, so `REJECTED`
sticks until something else changes state.

**It means "the attempt failed", NOT "not paired".** A bonded host that simply
happens to be powered off would look identical. That is why the panel says
`Link failed` and not `Refused` (asserts the host decided) or `Not paired`
(asserts an absent bond) — both claim more than the capture supports. The
disassembly has been wrong before in ways that mattered: it called `0xA1`
"channel connect" when it carries keystrokes, and `5C` "brightness" when it is
battery percent.

**The digit must NOT be blanked in this state.** It originally was, which is what
made a failed connect look like a display bug — the slot is still the one you
selected, so hiding it discards real information. It now shows on a **2 s pulse**
(`CONN_BLINK_FAILED_MS`), reading as dormant rather than busy; solid could not be
reused because solid already means connected.

**The advertising name cannot currently be changed, and "5.1" is meaningless.**
It is Bluetooth-version marketing with no functional role. `0xA9` (device name)
exists but **this port never sends it**, so the name comes from the module's own
stored value; it appends the slot to a prefix, giving `AK820 5.1-1`. Renaming
would mean sending `0xA9` with framing documented only as `"AK820 5.1-$"` plus a
separate length field, **none of it verified on the wire**, writing to module
storage **that cannot be read back** (there is no dump path off this board).
Capture what the stock firmware sends before attempting it.

**It borrows the band; it does not own it.** There is no spare vertical space
(top strip 0..24, text 25..48, clock 49..82, locks 83..105, battery 106..), so
the overlay outranks host text *while active* and hands it straight back. A track
title is displaced for seconds, never lost.

**`CONNECTED` is a confirmation, not a readout.** The solid digit already says
"connected" indefinitely; holding the word there would permanently cost the music
slot to convey nothing new.

**The overlay gets TWELVE characters; the host slot gets fewer.** The overlay
draws no icon, so it starts at `CONN_STATUS_X` (4) rather than `TEXT_X` (16):
4 + 12*10 = 124, inside the 128px panel and keeping the same 4px margin the
battery row uses for the recessed bezel. Host text, which must clear the icon
gutter, would run to x=136 at 12 glyphs and get clipped — so that path is
effectively 11. Widening the overlay by one character is exactly what let the
full advertised name fit.

**No icon is drawn.** The icon IDs are media transports (play/pause/stop) and
would misdescribe a link event.

Implementation is `conn_status_update()` in `graphics/display.c`, called from the
~10 Hz housekeeping tick *before* `draw_text_slot()` so an appearing or releasing
overlay repaints on the same tick. State is a `const char *` to a string literal,
so the change check is a pointer compare.

### Host text slot (arbitrary data pushed to the LCD)

A single line the host pushes over raw HID, drawn in the 24px band at **y25..48**
between the top row and the clock. **The firmware attaches no meaning to it** —
a host script decides what it says. Media is just the first producer.

```
channel 0x12 TEXT_CHANNEL
  0x01 TEXT_SET    [icon][up to 12 ASCII bytes]
  0x02 TEXT_CLEAR
```

**One packet carries everything, so there is no framing.** The band fits 12
glyphs (128px / 10px advance) against ~27 usable bytes per raw-HID report, so
offsets, commits and partial-render states were all designed away rather than
solved. This is why the feature stayed small.

- `icon`: `0 none, 1 play, 2 pause, 3 stop` — an ICON ID, not a "media state",
  so other producers can reuse it without the name lying. Drawn from
  `lcd_fill_rect` (green/amber/red) because colour is unavailable from the font
  atlases.
- **No scrolling, deliberately.** A marquee would redraw at ~10 Hz and keep the
  flash→LCD DMA busy far more than the current cadence — the same resource the
  eeconfig-write freeze was about. Truncation is also less distracting.
- **Non-ASCII becomes `?`** in firmware (the atlases are printable-ASCII only, so
  anything else indexes off the glyph table). The host script transliterates
  first — curly quotes, em-dashes, accents — so `?` is a last resort.
- **Expires after `DISPLAY_TEXT_TIMEOUT_MS` (3 min)** and blanks itself on the
  10 Hz tick, without the host having to do anything. Stale data presented
  confidently is worse than none: agent crashes, sleep and unplug all end with a
  blank slot rather than last night's track.

**Optimistic play/pause.** `process_record_kb` catches `KC_MEDIA_PLAY_PAUSE` and
flips the icon immediately, then the next host poll overwrites it with the truth.
The host stays authoritative, so a wrong guess self-corrects within one interval
— unlike tracking playback locally, which desyncs permanently. It returns
**true** (the keypress must still reach the host) and deliberately does **not**
touch `text_stamp`, since a guess is not evidence the agent is alive.

**NOT A BUG: a track from hours ago in the band is usually correct.** It looks
exactly like the expiry having failed, and is not. `nowplaying-macos.sh` pushes on
`paused` as well as `playing`, so an open player sitting on last night's track
keeps reporting that track — it is the live answer to *"what plays if you hit
play"*, refreshed every 3 s. The `DISPLAY_TEXT_TIMEOUT_MS` expiry only fires when
**nothing refreshes the slot**, which is why it never triggers here. Confirmed
2026-08-29: Music reported `paused` / `Memoirs (VIP)` while the band showed it.

To make paused blank the band instead, drop the `paused)` case in the poll loop —
but note that makes the firmware's optimistic play/pause icon flip incoherent, as
it would flip to a pause icon that is about to vanish.

**Installed as a LaunchAgent** (`hostagent/com.jdlien.ak820pro.nowplaying.plist`,
copied to `~/Library/LaunchAgents/`). `KeepAlive` with `ThrottleInterval 30`, so
unplugging the keyboard retries every 30 s rather than spinning. Log at
`~/Library/Logs/ak820pro-nowplaying.log`. Three absolute paths need changing on a
different machine: the script path, the log path, and `PY` in the script.

**The push is write-only, so it works in BT mode** — unlike `ak820ctl` and VIA.
Those break wirelessly because the firmware routes raw-HID *replies* through the
active host driver; `ak820text.py` only ever calls `h.write()`, so there is no
reply to misroute. It does still need the USB cable connected for the HID
interface to exist.

**AppleScript needs Automation permission.** Launched from `launchd` rather than a
terminal, the consent prompt may not surface and queries silently return empty —
band stays blank, nothing in the log. Fix in System Settings → Privacy & Security
→ Automation.

**Host side** lives in `hostagent/`, outside the QMK clone:

| File | What |
|---|---|
| `ak820text.py` | the dumb pipe — text + icon, one packet. Knows nothing about music. |
| `nowplaying-macos.sh` | one producer: polls Spotify/Music every 3 s, pushes on change |

Uses the `hid` package's `hid.Device(path=…)` API (a QMK CLI dependency), not
hidapi's `hid.device()`. Match on `usage_page 0xFF60 / usage 0x61` — the board
publishes several HID interfaces and only that one is QMK raw HID.

`nowplaying-macos.sh` checks `is running` **before** querying player state:
asking Music for its state will otherwise **launch** the app, which is a rude
side effect for a background poller.

**AppleScript, not MediaRemote** — app-specific (so no browser/YouTube media),
but stable. Apple has progressively restricted MediaRemote and third-party
wrappers break between OS versions. **Windows is better here**: 
`GlobalSystemMediaTransportControlsSessionManager` is a public API *and*
browsers register SMTC sessions, so YouTube works. The firmware is
platform-agnostic — a Windows producer sends the same bytes, no reflash.

### How the text band paints: a DMA pump and a cell diff

The band used to repaint by issuing **one blocking flash->LCD DMA per glyph**
on the loop that also scans the matrix. A two-line update measured **~53 ms** --
enough to swallow a keystroke. The media poller is what made it frequent enough
to notice, which is why "starting the poller breaks typing" was the symptom.

Two independent fixes, and **the order they are understood in matters**:

**1. Keep the DMA, drop the wait.** `lcd_draw_flash_glyph_try()` arms one glyph
and returns; `display_blit_pump()` drives it from `housekeeping_task_kb()` at
**main-loop rate (~390 Hz)**, outside the 10 Hz block. A line lands in ~50 ms of
wall clock and ~0 ms of CPU -- each iteration either arms a transfer or returns
on a single `lcd_blit_busy()` compare.

> ⚠️ **One glyph per HOUSEKEEPING tick was tried first and looked identical on
> paper.** At 10 Hz a 20-glyph line takes **2 seconds** and visibly crawls in
> letter by letter. The granularity was never wrong; **the clock was.** If the
> band ever crawls again, check which hook the pump is on before changing
> anything else.

**2. Do not clear before repainting.** A glyph blit paints its **whole cell
including the background**, so overwriting a cell fully replaces it. The band
diffs against a shadow of what is on the panel and blits only the cells whose
character changed -- `Bright 25%` -> `Bright 26%` is **one glyph, not a wipe and
eleven**. Clearing is confined to three cases: cells a shorter string vacates, a
line that moved or changed font, and a line being retired.

**The wipe WAS the flicker.** The band sat empty for the whole paint interval,
three times over while a held key stepped the value. This is the same technique
the clock has always used, which is exactly why the clock never flickered while
this band did -- worth noting, because two builds were spent making the repaint
*faster* when the fix was to make it *smaller*.

**⚠️ COMPOSING THE LINE IN RAM AND BLITTING IT ONCE IS WORSE -- do not
re-derive it.** It is the obvious "elegant" answer and it is wrong on this
hardware: `flash_read_bytes()` pulls every pixel through `spi1_rw()`, which is a
full **`spiExchange()` driver call PER BYTE** -- ~5.5 KB of them for a single
12-char line at 20px. That converts a transfer the DMA does for free into a
CPU-bound loop, i.e. exactly backwards for a board where the display must never
compete with the matrix scan. It also cost **5.9 KB of SRAM** (RAM went 28% ->
48%) for the line buffer.

Measured after both changes: **252 typed characters, zero drops, zero blit
timeouts**, with the poller pushing -- against 5 dropped from 215 before.

**`[lcd] blit timeout` remains the health signal.** Zero under load means the
pump is not fighting the bus.

### Playback position replaces the clock while playing

`2:34/18:45` in the clock band, from `TEXT_PLAYBACK` (0x04) —
`[state][pos_hi][pos_lo][dur_hi][dur_lo]`, whole seconds, 16-bit (18.2 h).

**The firmware advances the timer itself on the 1 Hz tick**; the host only
re-asserts an absolute position every poll. Without that it would jump three
seconds at a time and read as broken. It costs **no extra panel work** — this
band already repaints once a second for the clock's seconds, and the render
redraws only the character cells that changed, exactly as the clock does.

**Font adapts, and only past an hour.** 20px normally (`2:34/18:45` = 100px);
13px once a duration needs `H:MM:SS` (`1:02:34/2:15:00` = 150px at 20px, over
the 128px panel). A 20px cell is 23 rows against this band's 22, so it borrows
one row from the gap below — hence `CLOCK_BAND_H 23`, which **must** cover
everything either owner draws or switching between clock and timer strands a
row. Same clear-rect coupling that stranded the padlock.

**Only the PLAYING state takes the band.** A frozen timer is less useful than
the time of day, so pause hands it straight back.

**The media key freezes it immediately** (`display_playback_key()`), the same
optimistic trick the transport icon uses — otherwise it kept counting for up to
a poll after a pause, which is the one thing a paused timer must not do. Resume
needs no guess about the position: **position does not change while paused**, so
the held value is still correct and only the *advancing* flag is in doubt.

It freezes rather than restoring the clock outright because the keypress may
have gone to a browser tab the agent cannot see, in which case the player is
still going and the host re-asserts it. A frozen timer that resumes is a smaller
lie than the clock flashing up and being replaced.

**Expires after `PLAYBACK_TIMEOUT_MS` (20 s)** so a dead agent or a sleeping
machine cannot leave a timer counting up forever.

**⚠️ Duration units differ by app: Music reports SECONDS, Spotify
MILLISECONDS.** Getting it wrong shows a 3-minute track as 3 seconds and looks
exactly like a firmware bug.

**⚠️ Browser media is invisible to all of this**, as it is to the song text —
AppleScript only talks to apps with a scripting dictionary, and browsers do not
publish media state that way. The only route is the private MediaRemote
framework (what `nowplaying-cli` wraps), which Apple has progressively locked
down and which breaks between OS versions. Deliberately not used.

### Boot splash is JD's bunny logo (2026-08-29)

**The file is still named `sonixqmk.png` and that is deliberate.** Asset ids are
assigned by **sorted filename** in `mkraw.py`, so renaming it shifts every id
after it, which forces a firmware rebuild *and* a synchronised re-provision —
with a window where the LCD renders garbage if the two disagree. Keeping the name
made this an **assets-only** change: the generated `flash_assets.h` came out
byte-identical to the firmware's copy, which is the check that authorises
skipping a rebuild.

Source art (`assets-src/bunny-source.png`, 612x792 RGBA) is **black ink on a
transparent ground**, so the alpha channel IS the shape. Two non-obvious steps:

1. **Inverted.** The panel draws on black, so ink becomes white and transparent
   becomes black. The artwork's negative space (face, inner ear, eye) then reads
   as dark, which is how the logo is meant to look on a dark ground.
2. **Trimmed BEFORE scaling.** The artboard carries ~99px of empty margin left
   and 86 right. Scaling the canvas rendered the bunny at only ~63x98 inside a
   128px panel; trimming to the ink bbox (427x667) first gets it to **78x122**,
   ~22% larger each way. Always trim to the alpha bounding box.

Downsampling is an **area average**, not point sampling — 427x667 -> 78x122 is a
5.5x reduction and nearest-neighbour shreds the thin ear strokes. Grey edge
values cost nothing since the target is RGB565.

The design is 0.640 aspect (tall and narrow) against a square panel, so it cannot
fill the width without distortion. It is JD's own logo — **do not stretch it.**

Regenerate with `assets-src/mkbunny.py` (stdlib only; **no Pillow on this
machine** — it reuses `mkraw.decode_png`), then `mkraw.py --flash`, diff the
header, and provision. Original splash kept at
`assets-src/sonixqmk-original-splash.png`.

### The animation slot is stock, orphaned, and empty

`Fn`+`Delete` (`ANIM_TOG`) plays a full-screen frame animation straight from
external flash by DMA — an AJAZZ feature the stock firmware used. Frames live at
`ANIM_BASE 0x540000`, `ANIM_STRIDE` 32 KB each, one per 100 ms off the
housekeeping tick. While it runs it **owns the SPI bus**: the dashboard is
suspended and RTC polling must stop, because the bit-banged RTC I2C (A14/A15)
shares port A with the flash SPI1 pins (A12/A13) and glitches them mid-DMA.

**On this board it does nothing, and that is correct.** Probed 2026-08-29 with
`ak820ctl flash crc` (there is no read command, but a CRC against a known pattern
answers the question):

| Region | CRC | Means |
|---|---|---|
| `0x540000` +256 (header) | `0x0D968558` | **exactly the CRC of 256 zero bytes** — frame count is 0 |
| `0x540100` +4096 (frames) | `0xC71C0011` | neither blank (`0xFF`) nor zero — real pixel data |

So orphaned stock frames are still sitting there under a zeroed header. That
region is **below `FLASH_ASSET_BASE`**, so `ak820ctl` will not write it without
`--unlock` — which is why provisioning the QMK assets never disturbed it.

**Pressing it used to blink the screen black for ~1 s.** `anim_toggle()` paused
the dashboard and flipped the panel orientation *before* checking the header, then
undid both — and `display_set_paused(false)` forces a full repaint. Fixed
2026-08-29 by reading the header first; an empty slot is now a true no-op. Safe
there because the dashboard does SPI1 flash reads constantly anyway.

**There is NO validation** — no magic, no checksum. The zero count is the only
thing protecting the panel; a bad header paints garbage rather than failing. To
provision one, `mkanim.py` in `time-util-ak820pro/assets/` converts a GIF to a
frame blob. Ceiling is 244 frames, derived from the room between `ANIM_BASE` and
the asset region rather than guessed.

### `Fn`+`P` (BT_PAIR) is unbound by default — redundant, and destructive

Dropped from both Fn layers 2026-08-29. **The keycode stays in the
`ak820pro_keycodes` enum and in `via.json`** — that pairing is INDEX-MATCHED, so
removing an entry shifts every later keycode and corrupts existing VIA keymaps.
Only the default binding changed; assign it in VIA if you want it back.

| Mode | What it did | Why that is not worth a key |
|---|---|---|
| Bluetooth | pairs the currently-selected slot | Holding `Fn`+`Q`/`W`/`E` already selects **and** pairs — strictly better |
| 2.4G | the only pairing key that works there | Drops a working dongle link, and almost certainly cannot complete |

**Confirmed on hardware:** pressing it in 2.4G showed `Pairing 2.4G` and killed the
dongle link; toggling the slider brought it back. That recovery is the tell —
**the dongle never lost its bond**, so the keyboard's broadcast was half a
handshake with nothing answering. A bare USB receiver with no button realistically
needs vendor software to enter pairing, which customers do not get.

Note the gating asymmetry that made this the only 2.4G pairing route:

```
BT1/BT2/BT3   ->  wireless_mode == WL_MODE_BT     (Bluetooth only)
BT24G         ->  wireless_mode == WL_MODE_24G    (2.4G only)
BT_PAIR       ->  wireless_mode != WL_MODE_USB    (ANY wireless mode)
```

**Recovering from an accidental trigger:** slide to `bt`, then back to `2.4G`.
Sliding *directly* back does not work — a select for the profile that is currently
advertising is declined (see the `A6 <slot>` entry). The cancel-pairing bounce
that automates this is scoped to BT slots only, so 2.4G still needs the two-step
by hand. Worth extending only if the key is ever rebound.

### ⚠️ Modified consumer keycodes race the endpoints — `LSA(KC_VOLU)` on the knob

`Shift`+`Alt`+Volume is macOS's quarter-step fine adjustment, and binding
`LSA(KC_VOLD/U)` to the encoder *mostly* worked — which is the tell.

**Symptoms, all three from one gesture:**

| What the host saw | Result | Rate (default config) |
|---|---|---|
| both modifiers | quarter step (correct) | ~2/3 |
| no modifiers | full step | ~1/3 |
| Alt only | opens the Sound settings dialog | rare |

Three different outcomes from one action is a host sampling a **transient
modifier state**, not a mapping error.

**Root cause: the two reports go out on DIFFERENT USB ENDPOINTS.** `usb_main.c`
sends consumer/extra on `USB_ENDPOINT_IN_SHARED`; the keyboard report has its own
endpoint (`KEYBOARD_SHARED_EP` is not defined). The host polls them independently
and guarantees **no ordering between them**. QMK's `register_code16()` registers
the mods and fires the consumer usage back-to-back with zero gap, so macOS can
service the shared endpoint first.

**`ENCODER_MAP_KEY_DELAY` is NOT the fix, though it looks like one.** It defaults
to `TAP_CODE_DELAY`, which defaults to 0 — and at 0 the delay is `#if`'d out of
`quantum/encoder.c` entirely, so encoder press and release are adjacent
instructions. Setting it to 10 took the failure rate from ~1/3 to ~1/8. **Better
but still wrong**, because it spaces press from release while the race is INSIDE
the press. A partial improvement here is a warning sign, not progress.

**The fix: `process_modified_consumer()` in `ak820pro.c`** — register the mods,
`send_keyboard_report()` to flush them, `wait_ms(MODIFIED_CONSUMER_GAP_MS)` (8) so
the host has polled and applied them, *then* the consumer usage. Release unwinds
in reverse. Confirmed rock solid on hardware 2026-08-29. Applies to any modified
consumer keycode, not just the encoder.

**Making it keep up with a fast spin took three more steps**, and the ordering of
what mattered was not obvious:

1. **Hold the modifiers across a burst** (`MODIFIED_CONSUMER_HOLD_MS` 150).
   Re-establishing them every detent cost the full ordering gap each time. Now
   only the FIRST click pays it; the rest just send the usage. Uses REAL mods,
   not weak ones — the action layer clears weak mods on ordinary keypresses,
   which would silently drop them mid-spin.
2. **`ENCODER_MAP_KEY_DELAY` 10 → 1.** `wait_ms()` BLOCKS THE MAIN LOOP, and the
   main loop is what samples the encoder — so this delay did not merely slow the
   knob, it made fast spins **drop detents outright**. It is also largely
   unnecessary: `usb_endpoint_in_send()` writes into an output buffer queue
   (`obqWriteTimeout`), so consecutive consumer reports already serialise across
   USB frames and cannot coalesce. Kept at 1 rather than 0 because QMK's comment
   says these delays "cater for Windows", and 0 compiles the block out entirely.
3. **`MAX_QUEUED_ENCODER_EVENTS` 4 → 32.** The default is
   `MAX(4, NUM_ENCODERS_MAX_PER_SIDE + 1)` = **4**, and it is a RING buffer, so
   usable depth is 3. Events past that are **dropped outright, not delayed** —
   the direct cause of "moderate turns fine, fast turns lose a lot". Each event
   is an index plus a direction, so 32 costs tens of bytes.

**Remaining ceiling, accepted deliberately.** The encoder is sampled once per
main-loop iteration and the matrix scan is ~390 Hz (down from 1396 stock, because
`SPD_STEP 128` drives the row ISR at ~18,800/s for the rainbow). At
`resolution: 2` that aliases somewhere around 90-100 detents/s. Dropping to
`SPD_STEP 64` would roughly double the headroom — **and it is NOT worth it**: the
rainbow is visible every time you look at the board, ramming the volume is rare.
Do not "fix" the encoder by spending the field rate.

**The keymap is platform-aware.** `LSA` is on the Mac layers only; `WINBASE`/
`WINFN` keep plain `KC_VOLD/U`. Shift+Alt is meaningless to Windows volume — and
worse, **`Alt`+`Shift` is Windows' input-language switch hotkey**, so `LSA` on a
Windows layer would cycle keyboard layouts on every click.

**Useful diagnostic precedent:** the same VIA mapping worked reliably on a
Keychron V1. Identical config behaving differently across boards pointed at a
per-board default rather than QMK-wide behaviour, which is exactly where it was.

### Fonts: the atlas pipeline, and why the sizes are what they are

There are **two** importers, and which one you want depends on the source:

- `assets-src/mkfontatlas.py` renders a TTF/OTF (Pillow, in the venv). `--probe`
  reports natural metrics so you can pick a cell; `--aa` only for large glyphs.
- `assets-src/mkbdfatlas.py` imports a **BDF bitmap font**. No ppem, no hinting,
  no threshold — it copies pixels a human already placed. This is what the 13px
  face now uses; see the Cozette section below.

Both emit what `mkraw.py` expects: fixed cells, magenta marker at each cell's
top-left, marker spacing = advance.

**Render MONOCHROME via `getmask(mode="1")`, not antialiased-then-thresholded**
(TTF path only). They are different FreeType render modes and give different
results; thresholding a grey render throws away the hinting.

| Asset (filename) | Really is | Cell | Chars/line | Used for |
|---|---|---|---|---|
| `Iosevka-Medium-13` | **Cozette** | 6x14 | **19 / 21** | host text slot (song titles) |
| `Iosevka-Medium-20` | Iosevka | 10x23 | 12 | status band, connection digit, battery % |
| `Iosevka-Regular-30` | Iosevka | 15x22 | 8 | clock (**cropped** from 15x34) |

Chars/line for the 13px face is **19 beside the transport-icon gutter, 21 on the
full-width line** — see `DISPLAY_TEXT_MAX_L0`/`_L1`.

### ⚠️ `Iosevka-Medium-13.png` CONTAINS COZETTE (2026-08-30)

**The filename is a lie on purpose.** `mkraw.py` assigns ids by sorted filename,
so renaming would shift every later id and force a synchronised rebuild and
re-provision. Keeping the name is what made the swap assets-only — the same trick
as the bunny splash still being `sonixqmk.png`. **Do not "fix" it.**

**Why the swap: Iosevka kept losing the quantisation lottery at 13px.** Measured
defects in the shipped atlas, not impressions:

| Glyph | Was |
|---|---|
| `j` | **2px stem** where every other lowercase stem is 1px, plus a broken `##.#` tail |
| `A` | legs stepping at different rows (left 2→1, right 4→5) over a lumpy crossbar |
| `d` | flat 5px bowl top merging into the stem, while the mirrored `b` was round |
| `l` | near-indistinguishable from `1` — `klmnop` reads as `k1mnop` |

Those join the capital P at size 20, the doubled `t` at 14, and the hand-closed
b/h/p arch joins already recorded below. **That is a pattern, not bad luck**: an
outline font at a ppem with no pixels to spare. Each patch was individual and
none survived a regeneration.

Cozette is drawn by hand at **6x13**, which is exactly this grid — the classic
terminal-bitmap size, along with misc-fixed 6x13, uw-ttyp0 t0-13 and ProggyClean.
MIT licensed; `assets-src/cozette.bdf` + `COZETTE-LICENSE` are committed.

**The baseline is PINNED to row 9, and that is load-bearing.** `display.c` centres
text on the transport icon by cap-to-baseline ink (`TEXT_FONT_DY`, `TEXT_BIG_DY`,
the `icon_y` ladder), and the two-line layout stacks cells `TEXT_LINE_H` apart.
Landing the new baseline where Iosevka's sat keeps all of that correct. Let it
float and you buy a firmware change for nothing. `mkbdfatlas.py` **refuses to
clip** rather than silently shaving descenders — the failure that cost the clock
atlas its `g`/`p`/`q`/`y` tails.

**Cell went 7x14 → 6x14**, Cozette's own design advance. The 7px cell spent a
column of letterspacing per glyph for nothing; native bought three characters per
line. Cozette carries a 1px left bearing (ink cols 1..6), so the importer
normalises the leftmost ink to col 0 — otherwise every string moves a pixel right
and eats the margin the recessed bezel wants at the 21-character end.

**⚠️ PROPORTIONAL WIDTH WAS MEASURED AND REJECTED — do not re-derive.** Ink-width
histogram across the 95 glyphs: `1px×3, 2px×6, 3px×8, 4px×3, 5px×73, 6px×2`.
**73 of 95 are already exactly 5px**; only `!"'(),.:;I[]`jl|` have slack. Real
titles save 4–12%:

```
Bohemian Rhapsody   102 -> 98px    4%      The Chain     54 -> 50px    8%
Everlong             48 -> 46px    5%      Little Wing   66 -> 59px   11%
Smells Like Teen Spirit  138 -> 122px  12%
```

That is one to two characters, against a format change spanning `mkraw.py`, the
flash index, `lcd_draw_flash_glyph`/`lcd_text_width` and the host's truncation.
**And it would look worse**: you cannot make a proportional font by trimming a
monospace one. Cozette's `I` is serifed (`.###.`/`..#..`/`.###.`) *deliberately*,
to fill its box and stay distinct from `l`. Trimmed to 3px it sits jammed against
its neighbours with sidebearings nobody drew.

### Legibility ceiling: it needs leaning in, and that is accepted

Cap heights, measured on the shipped atlases:

| Face | Cap height | ≈ physical | at 60 cm |
|---|---|---|---|
| 13px (two-line) | **8 rows** | 1.35 mm | ~7.7 arcmin |
| 20px (single-line) | 15 rows | 2.53 mm | ~14.5 arcmin |

Comfortable reading wants roughly 16–20 arcmin of cap height, so the two-line
face is **under half** that at normal typing distance — leaning in to ~30 cm
doubles the angle, which is exactly why leaning in works. This is physics, not
typography: no font fixes a 0.85″ panel angled away from you.

**The only lever is the 20px face, and it costs the artist line.** The firmware
already selects it automatically, but only when line 1 is empty, so dropping the
artist from `nowplaying-macos.sh` would buy it — a host-side change, no rebuild.
It fits **11 characters**, though, so most titles fall back to 13px anyway.

**Accepted deliberately.** The slot's real job is *recognition*, not reading: it
answers "what is this song I already know" at a glance. A familiar word shape
resolves well below the acuity that novel text needs, and for genuinely new music
a title alone was never going to be enough. Cozette HiDPI (12x26) was considered
and is strictly worse — 16-row caps but only 9–10 characters, against the 20px
face's 15 rows and 11.

**⚠️ The capital P defect at size 20 is IOSEVKA, not the toolchain.** Measured
across sizes 16-26 in true monochrome hinted mode: **size 20 is the only one in
that range where P's stem collapses to 1px** (start col 2, width 1) while B/D/R/H
all get (1,2). Hinting does not fix it; it reproduces exactly.

**Size 19 is NOT the answer** — it fixes P but collapses every glyph's RIGHT stem
to 1px, which is worse and more widespread. The shipped atlas has **P hand-fixed
at size 20**, which is the best available combination. Do not "fix" it by
re-rendering at another ppem.

**⚠️ Iosevka Aile (proportional) is WIDER than Iosevka mono.** Measured at 20px:
Aile fits 10 characters where the mono fits 12. Iosevka's monospace is famously
condensed (0.5em advance), so going proportional here LOSES density. Proportional
rendering and a per-glyph width table were investigated and abandoned for this
reason — the lever for more characters is a smaller size, not variable advance.

**Size 12 was built, compared on the panel, and rejected** — 20 chars/line, but
the counters (the enclosed spaces in a/e/o/g) start closing at that density, and
word shapes stop reading at a glance. 14 was chosen as the knee of the curve.

**⚠️ ADDING OR REMOVING A FONT SHIFTS EVERY LATER ASSET ID** — `mkraw.py` assigns
ids by **sorted filename**. So an asset change needs a firmware rebuild with the
new `flash_assets.h` AND a re-provision, applied together. Between the two the
panel draws garbage; that is expected, not a fault.

**Font is chosen PER STRING.** <= `TEXT_BIG_MAX` (11) chars uses the 20px face,
longer uses the 13px one. Most titles are short and there is no reason to render
"Everlong" tiny just because "Bohemian Rhapsody" would not fit.

**Text is aligned to the TRANSPORT ICON, not the band.** The icon spans rows
31..42 (centre 36.5). Each face is centred on that by its **cap-to-baseline mass,
not its cell** — the cell includes descender space that is empty for most strings
and drags the apparent centre down, which is what made it look 2px high. 20px
needs `TEXT_BIG_DY` 0, 13px needs `TEXT_FONT_DY` 4; **one constant for both
misaligns one of them.** Any new face needs its ink rows measured and its own DY.

**Hand-fixed in the 13px atlas: the stem->shoulder join on `b`, `h`, `p`**, where
the arch sprang off the stem with a 1px hole and read as disconnected. **`k` was
deliberately left alone** — its similar-looking gap is the diagonal arm
approaching the stem, which it meets two rows lower. A naive "close every gap"
pass would break it.

**⚠️ Do NOT try to thicken the 13px face.** Synthetic emboldening (dilate 1px)
closes every counter — `m` becomes a solid white block. At a 7px advance the
glyphs are ~5px wide, and three stems plus two gaps is 5px minimum at 1px each,
so there is no room for 2px stems at this density. **A real Bold weight cannot
rescue it either; the geometry does not permit it.** Density and weight are the
same dial here. Going up a size instead: 15-16 give inconsistent stems, 17-18
give uniform 2px but only 13 chars, barely better than the 20px face.

### Two lines of text: what it would cost

Not possible in the current band, and the transport bites before the layout does.

| Limit | Number |
|---|---|
| Text band height | 24px |
| Two 13px lines (ink + 2px gap) | **28px** — 4px short |
| Clock in the 20px face instead of 30px | frees 11px -> band 35px, **2 lines fit** |
| Hiding the clock while playing | band 58px, 3 lines |

**But the raw-HID packet is the real ceiling.** The text channel is deliberately
ONE packet with ~27 usable bytes, which is what let the design skip offsets,
commits and partial-render states. Two lines at 16 chars is 32 bytes — over
budget. **Two lines of ~13 chars is 26 bytes and fits.** So the transport forces
shorter lines than the panel could physically show, and adding a second packet
would reintroduce all the framing the design avoided.

**Remaining easy win: the clock font stores 95 glyphs to draw eleven.**
Iosevka-Regular-30 is 96,900 B of the ~199 KB blob, and the clock only ever draws
`0`-`9` and `:`. Subsetting it would reclaim ~86 KB.

### ⚠️ The bootloader looks EXACTLY like a dead board

No RGB, dark LCD, no typing — there is no subtle indicator. Hit 2026-08-30
right after a flash: the board had flashed fine, rebooted into QMK, and a second
`Fn`+`Esc` put it straight back into the bootloader, where it read as a hang.

**Check `0x7140` before assuming a hang.** The armed-flasher loop exits after
one flash, so nothing is watching to catch a second entry.

```sh
ioreg -p IOUSB -w0 -l | grep -q '"idProduct" = 28992' && echo BOOTLOADER
```

Recovery is re-running the flash, NOT a power cycle. Distinguishing the two:

| | bootloader | the hang |
|---|---|---|
| USB id | `0x7140` | `0x8009` |
| `ak820ctl info` | interface absent | **I/O Timeout** |
| fix | re-flash | power cycle (switch to `off`, unplug 10 s) |

### ⚠️ Keyboard feels slow / drops keystrokes? CHECK THE HOST FIRST

2026-08-30: the board became close to unusable — severe keystroke loss, **in
wired mode as well as Bluetooth**. It looked exactly like a firmware regression
and was diagnosed as one. It was not.

**A/B tested afterwards: the suspected firmware change runs perfectly clean.**
Flashing the exact patch back reproduced nothing.

What actually correlated was **host-side process accumulation**. Over one long
session ~24 background captures, watchers and flashers were started, several
without reliably killing their predecessor. One log alone holds **2,736 lines of
`exclusive access and device already open`** — two `qmk console` instances
spinning in a tight retry loop against the macOS HID subsystem.

**Before suspecting firmware:**

```sh
pgrep -fl "qmk console|ak820ctl|clock-phase"   # leftover pollers?
launchctl list | grep ak820                    # agents running?
```

`qmk console` claims the interface exclusively, so a second instance retries in a
loop. Kill everything, then retest.

**Two process failures made this much worse than it needed to be, both mine:**

1. **Three changes were flashed in one build** (read-back opcode, a logging flag,
   host-side transmit alignment), so when the board broke there was nothing to
   bisect against.
2. **The "fix" killed every poller AND reverted the firmware in one step**, then
   credited the firmware. That destroyed the evidence a second time.

The correct order is the one that eventually worked: **reproduce first, bisect
second.** Re-flashing the full patch answered it in one step and made three
planned bisect flashes unnecessary.

### The clock atlas is cropped to its ink — where 12 rows came from

`Iosevka-Regular-30.png` was a **15x34** cell, cut for full ASCII with room for
ascenders and descenders. The clock only ever draws `0`-`9` and `:`, which use
neither, so **12 of its 34 rows were blank by construction** — 5 above the
digits, 7 below. Cropping to the measured ink (2026-08-30) freed those 12 rows
of panel *and* cut **34 KB** off the blob (96,900 -> 62,700 B).

That is what paid for the even gaps around the lock row and for keeping the
battery percentage at 20px. Before it the panel was full to the row and every
spacing choice was a trade against another one.

**It was a CROP of the existing atlas, not a re-render** — the glyphs are
untouched pixel for pixel, so the clock looks exactly as it did. Re-rendering
would need the Iosevka **Regular** TTF (only Medium is in `FONTS.md`) and would
risk changing the hinting for no gain.

**The colon is hand-shifted UP 3 ROWS, and that is not a crop artifact.**
Iosevka's colon is positioned for lowercase text, where it sits between
x-height letters. Digits are full cap-height, so a text colon reads visibly low
between them — it was 3 rows low in the original 34-row atlas too. Clock faces
normally centre it. Measured, both centres now land on 10.5:

```
before   digits 0..21 centre 10.5   colon 6..21 centre 13.5   +3.0 low
after    digits 0..21 centre 10.5   colon 3..18 centre 10.5    0.0
```

Re-applying after any atlas regeneration: shift the `:` cell's pixels up 3,
fill the vacated rows with background, and **re-paint the magenta marker at the
cell's top-left** — `mkraw.py` reads markers from row 0 only.

**A glyph moved INSIDE its existing cell is an assets-only change.** Dimensions
do not change, so `flash_assets.h` comes out byte-identical — which is the check
that authorises skipping a firmware rebuild, and it means no mismatch window at
all. Confirm the header really is identical rather than assuming it; and confirm
the blob CRC actually CHANGED, since a swallowed `mkraw` failure provisions a
stale blob that a device-vs-local check still passes, both sides being equally
wrong.

**⚠️ Descenders are clipped in that atlas.** `g`/`p`/`q`/`y` lost their tails.
Harmless because nothing but the clock uses `FONT_CLOCK`. If general text is
ever drawn at this size, regenerate at the full 15x34 cell and hand the 12 rows
back — do not nudge offsets to compensate.

To re-crop: measure the ink extent of `0123456789:`, crop to it, then re-paint
one magenta pixel at each cell's top-left. `mkraw.py` reads markers from **row 0
only** and marker spacing IS the advance, so a crop that removes row 0 destroys
the grid unless the markers are restored.

Copies of the shipped atlases and blob are in **`assets-src/current/`** — the
originals live in `time-util-ak820pro/assets/`, an upstream clone whose changes
are uncommitted, and **there is no way to read assets back off the board.**

### ⚠️ Panel spacing is set by INK, not by band boundaries

The 20px cell carries **4 blank rows above its caps and 4 below its baseline**,
so a band boundary sits nowhere near where the eye puts the edge. This is why
"move the lock row down 1px" is never one constant.

Balancing the gaps either side of the lock row took **three coupled moves**:

| Move | Why it was forced |
|---|---|
| `LOCK_Y` 81 -> 82 | what was actually asked for |
| `STATUS_Y` 104 -> 105 | the 20px cell needs all 23 rows, so the lock band cannot grow without pushing the battery down |
| `CLOCK_Y` 57 -> 56 | the first two alone give 7 and 8; this makes them exactly equal |

Measure ink-to-ink when judging spacing:

```
icons -> text   2
text  -> clock  2
clock -> lock   8      (was 6 -- visibly lopsided against the 8 below)
lock  -> batt   8
```

### ⚠️ Provision assets AFTER flashing firmware, not before

Assets and firmware must change together, and there is always a window where
they disagree and the panel renders garbage. **Which order decides how alarming
that window looks.**

Provisioning first (assets new, firmware old) was tried 2026-08-30 to get a
single reboot. It makes the WHOLE panel mangled, because the firmware reads
15x34 cells out of a 15x22 atlas and every glyph lands wrong. It reads as a
dead board.

Flash the firmware first. The mismatch is then confined to the clock, which is
obviously one broken element rather than a broken keyboard.

Either way: **raw HID round-trip (`ak820ctl info`) is the liveness probe.** A
board that answers it is fine no matter what the panel shows.

### Two-line text slot, and the vertical budget

The panel is **exactly full** -- 128 rows with nothing spare:

```
0..24     connection strip   25
25..26    gap                 2
27..54    text (2 lines)     28   two 6x14 cells, at 27 and 41
55        gap                 1
56..77    clock              22   Regular-30, CROPPED to its ink
78..81    gap                 4
82..104   lock band          23   20px face
105..127  battery            23   20px face
```

**A glyph blit paints its WHOLE cell, background included**, so cells cannot
overlap and two lines cost exactly 2x the cell height. That is why the 13px
atlas is a **tight 6x14 cell** -- at the original 7x17 it wasted 4 rows per line
and two lines would not fit. (The hand-fixed b/h/p joins and the hand-drawn `%`
that used to need re-applying after every regeneration are **gone with Iosevka**
-- a BDF import needs no patching, which was much of the point.)

**Protocol: `TEXT_SET_LINE` (0x03)** = `[line][icon][ASCII...]`. One line per
packet, because 32 bytes leaves ~27 for text after framing and two lines is 40.
Torn updates are harmless -- the lines are independently meaningful and the
producer polls every 3 s. `TEXT_SET` (0x01) still works and **clears line 1** so
a single-line producer cannot strand a stale artist.

**⚠️ THE TWO LINES HAVE DIFFERENT BUDGETS.** Only line 0 sits beside the 14px
transport-icon gutter, so it gets `(128-14)/6 = 19`; line 1 starts at `TEXT_X2`
(2) and gets `(128-2)/6 = 21`. `DISPLAY_TEXT_MAX_L0` / `_L1` in `display.h`,
mirrored by `MAXLEN = {0: 19, 1: 21}` in `hostagent/ak820text.py`.

**The producer puts the ARTIST on line 0 and the TITLE on line 1**, so the title
gets the wider line -- the artist is the more expendable of the two. Both lines
end at the same column, so the last cell's ink lands at 126 and there is **no
bezel margin left** on a string long enough to use every character.

**Single-line text keeps the adaptive size** (20px if <= 11 chars). Only a real
second line costs legibility, since two 20px cells would need 46 rows.

**The battery percentage is 20px again** (2026-08-30). It had been forced down
to 13px when the band was 17 rows against a 23-row cell -- "something else has
to give: the two text lines, the clock, or the lock labels." The clock gave: it
was carrying 12 blank rows it never used. See the clock-crop section.

**Rows 126-127 were dead space.** `LCD_OFF_Y 2` is a controller offset, not lost
rows -- the full 0..127 is visible. One row of bottom margin is kept on purpose:
the bezel clips the outermost pixels, the same reason `BATT_X0` is 5.

**⚠️ The padlock must fit inside the lock band's clear rect.** It is 16px drawn
at `LOCK_Y+3`, so it needs a band of at least 19. While the band was briefly
17px its bottom two rows sat outside `lcd_clear_rect(0, LOCK_Y, W, STATUS_Y-LOCK_Y)`
and stayed lit forever once the locks cleared. If the band is ever shrunk again,
move the padlock or shrink it too.

**⚠️ `mkraw.py` validates the cell markers -- CHECK ITS EXIT STATUS.** Editing a
glyph by hand can clobber the magenta marker at its cell's top-left, and marker
spacing IS the advance. It then fails with `non-uniform glyph advance` -- but if
the failure is swallowed, the STALE blob gets provisioned and a device-vs-local
CRC check still passes, because neither side has the change. **Confirm the blob's
CRC actually changed after regenerating**, not just that the device matches.

### ⚠️ Two LED glitches during RGB adjustment — different causes, one fixed

Both look like "the LEDs flash wrong for a moment while adjusting". They are
unrelated, and the TIMING tells them apart.

**One row briefly lit a wrong colour, DURING a hold — FIXED 2026-08-31.**
`sn32f2xx_flush()` memcpy'd into `led_state[]` from the main loop while the row
ISR reads that same array to set each channel's duty. No lock, so the ISR could
land mid-copy and drive a frame that is part new, part old. **The split falls at
whatever byte the copy reached, which is why it shows as ONE ROW** — that
spatial localisation is what identifies it; a timing artefact would not be
localised. Now wrapped in `chSysLock()`: ~10-16 µs for an 82-128 LED copy at
48 MHz against a 53 µs row-ISR period. Board-agnostic, upstreamable.

Hold-to-repeat probably made a long-latent race VISIBLE — 83 steps/s produces
far more frame updates than tapping ever did.

**A brief DARK flash — QMK's flush is a RATE LIMIT, not a debounce.** This one
surprised us and the fix is board-side:

```c
// quantum/eeconfig.h -- eeconfig_flush_##name##_task
if (timer_elapsed(flush_timer) > timeout) { flush(); flush_timer = timer_read(); }
```

It fires every `RGB_MATRIX_EEPROM_WRITE_DELAY` ms for as long as the config
stays dirty — **including throughout a held adjust key**, not once after it
settles. Each write makes the internal flash array busy for milliseconds, the
row ISR cannot run to arm the next row, and the matrix goes dark.

`rgb_matrix_eeprom_flush_allowed()` in `ak820pro.c` now also waits for the RGB
values to stop moving (`RGB_SETTLE_MS`), turning "a write every 750 ms while
adjusting" into "one write once you settle". That also cuts flash wear and cuts
exposure to the still-unexplained RGB-adjust hang, whose trigger is an
internal-flash write.

### The rainbow is a GEOMETRY problem, not a flicker problem

Do not reason about it with flicker-fusion intuition. Flicker has a threshold
(~60-90 Hz) above which more rate buys nothing. **Saccadic colour breakup has
no threshold** — the eye sweeps at 100-500 deg/s and sequential colour fields
land on different retinal positions, so fringe width scales LINEARLY with field
rate.

```
field rate   slot gap   fringe @200 deg/s   @500 deg/s
   121 Hz     2755 us         33.1'            82.6'    stock
  1042 Hz      320 us          3.8'             9.6'    current
  2083 Hz      160 us          1.9'             4.8'    max realistic here
  4000 Hz       83 us          1.0'             2.5'    ~invisible
```

Foveal acuity is ~1 arcmin. **Doubling the field rate halves the fringe; it
does not remove it.** Reaching invisibility needs ~4x current (row ISR ~72,000/s),
well past this M0. Do not spend scan rate expecting a cure.

**⚠️ COLOUR CHOICE IS A FREE 2x — bigger than any achievable frequency change.**
The slot order is **R -> B -> G** (`SN32F2XX_RGB_MATRIX_ROW_CHANNELS 3`), so what
matters is how far apart a colour's lit channels sit:

| Colour | Channels | Slots | Gaps apart | Fringe @200 deg/s |
|---|---|---|---|---|
| white / warm white | R+B+G | 1,2,3 | full cycle | worst |
| **orange / amber** | R+G | 1,3 | **2** | 7.6' |
| **purple / magenta** | R+B | 1,2 | **1** | 3.8' |
| cyan | B+G | 2,3 | 1 | 3.8' |
| pure R, B or G | one | — | 0 | **none** |

Magenta over amber halves the fringe for free — the same win doubling the field
rate would buy, at zero CPU cost. **Amber is the worst two-channel colour on
this hardware.** A single saturated channel has no sequential fields at all.

### If the LEDs ever stop being worth their cost

`SN32F2XX_RGB_MATRIX_ROW_CHANNELS` is a parameter. Modelled, not measured:

```
config                            slots  row ISR/s  field Hz  total IRQ  scan
full RGB, now (psc 9)                18     18,750     1,042     38,750   370
RED ONLY, PWM clock cut 3x (psc 29)   6      6,250     1,042     26,250  ~546
RGB off entirely, LCD kept            0          0         0     20,000  ~717
RGB off + backlight tick 10 kHz       0          0         0     10,000 ~1434
```

**The ISR fires once per PWM PERIOD, not once per row**, so cutting channels
3 -> 1 does NOT cut CPU by itself — it TRIPLES the field rate. Cutting CPU needs
a slower PWM clock, which single-colour can then afford.

Single channel makes rainbow **structurally impossible**, at any frequency.
`ROW_CHANNELS 1` is untested here and rgb_matrix effects would render only their
red component.

### Known quirks

**⚠️ THE HANG IS A CRAWL, NOT A DEAD CPU — the entry below is WRONG about the
mechanism, and it cost hours.** Captured on the console 2026-08-30:

```
16:57:24  matrix scan frequency: 391
16:57:32  matrix scan frequency: 178      <- 8 s gap, then HALF rate
```

**A parked CPU or a HardFault cannot emit that line.** The board is alive the
whole time. Every earlier reading — "CPU parked in WFI with no pending interrupt
left to wake it" — was inferred from `ak820ctl info` timing out and the LED mux
stopping, neither of which distinguishes dead from slow.

**Mechanism:** `blit_done` is cleared when a DMA blit is armed and set only by
`blit_done_cb` off the SPI0 completion IRQ. **Miss that IRQ once and the flag is
false forever** — nothing else in the tree writes it. Every later wait then
burns its full bound, **~1 s at 48 MHz**, several times per housekeeping pass.
Raw HID times out, typing is lost, power cycle only. Indistinguishable from a
hang from outside, and nothing recovered from it.

`lcd_blit_flash()` already carried the comment *"it never completes, the caller
spins out its timeout, and SPI0 is left in DMA mode with FLASH_CS asserted"* —
**the consequence was documented and simply never handled.**

**Fix: `lcd_blit_wait()`** tears the bus down as a completion would, declares the
blit done, counts it, and prints `[lcd] blit timeout #N`. Bound cut 4,000,000 ->
1,000,000 (~250 ms). The animation player's wait was **unbounded** — same
failure, no exit at all — and is now bounded too.

**`[lcd] blit timeout` in the console is now THE signal.** Zero under load means
the cause is gone; a climbing count means the recovery is only covering for it.

**Why it got worse "recently": blit COUNT.** The bug is old and latent, but it
scales with how many blits run. The two-line text slot, the per-second playback
readout and more frequent host pushes all landed 2026-08-30 and all add blits.
None of them created it; they roll the dice more often.

**The diagnostic that cracked it was the timestamped console log**, exactly as
the recipe below prescribes. Run it BEFORE theorising:

```sh
qmk console 2>&1 | while IFS= read -r l; do printf "%s %s\n" "$(date +%H:%M:%S)" "$l"; done \
  >> ~/Library/Logs/ak820pro-console.log
```

Then `awk` the timestamps for gaps — a gap FOLLOWED BY MORE OUTPUT is a stall;
a gap with nothing after it is a real death. That single distinction redirected
the whole investigation.

**Interrupts are now masked across the per-line flash PROGRAM window**
(`efl_ramtext.diff`). The `.ramtext` move keeps the flash routines executing
while the array is busy, but the vector table and every ISR still live in flash,
and this board runs ~39,000 interrupts/s between the row scan and the 20 kHz GPT
tick — so a handler fetched out of a mid-program array is near certain. **Sector
erase is deliberately NOT masked**: it is milliseconds, and masking that long
starves UART2, where being late means losing CH582F data.

**FIXED (symptom) — hard freeze while adjusting RGB.** Predates any of this
session's changes. Symptom: a row of keys stuck on one solid colour (whichever of
the 18 hardware row slots the mux stopped on) and the board completely dead until
a power cycle.

Confirmed live on 2026-08-28, not inferred:

| Signal | During hang |
|---|---|
| USB `0x8009` on bus | present |
| 6 HID interfaces | present (**OS-cached — proves nothing**) |
| `ak820ctl info` raw-HID round-trip | **`no reply`** |
| `matrix scan frequency` on console | **silent for 2m14s** |
| LED row mux | frozen, one row energised |
| Recovery | power cycle only |

USB peripheral alive, nothing at application level running = CPU parked in `WFI`
with no pending interrupt left to wake it. `config.h` already documented the
mechanism: an eeconfig/VIA flash write stalls instruction fetch long enough that
the SPI0 DMA completion IRQ is missed and the WFI wakeup is lost. Every RGB
adjustment step writes eeconfig, which is why tuning LEDs triggers it.

`efl_ramtext.diff` (applied) narrows this race but **does not close it**.

**`CORTEX_ENABLE_WFI_IDLE FALSE` was tried first and DID NOT FIX IT.** The
config.h comment describes two failures from one cause — a missed SPI0 DMA
completion IRQ *and* a lost WFI wakeup — and that only addresses the second. It
reproduced on the very next build, log ending on `rgb matrix set hsv [EEPROM]`
exactly as before. Kept `FALSE` anyway (free on a plugged-in board, removes one
half), but **do not mistake it for the fix**.

The actual fix is two-layered:

1. `RGB_MATRIX_EEPROM_WRITE_DELAY 750` — QMK's `eeconfig_flush_rgb_matrix_task`
   debounce, which this tree had but wasn't calling. Cuts writes from ~8/s while
   a key is held to ≤1.3/s. Good for flash wear independently.
2. `rgb_matrix_eeprom_flush_allowed()` in `ak820pro.c` returning
   `!lcd_blit_busy()` — never *start* an internal-flash write while a flash→LCD
   DMA blit is in flight. Aims to close the race rather than narrow it.

Deliberately **not** gated on `anim_active()`: the animation player runs
continuous DMA, so that would mean RGB settings never persist while an animation
plays. Blits are short, so per-blit gating still finds gaps.

**⚠️ IT CAME BACK — AND THE FIRST FIX WAS AIMED AT THE WRONG THING.** Reproduced
2026-08-29 by **assigning keys in VIA**: one bright green row, board dead until a
power cycle. `rgb_matrix_eeprom_flush_allowed()` only gates RGB's *own* eeconfig
flush, which was simply the trigger we happened to notice first. VIA's
dynamic-keymap writes take a completely different path and were never covered.

**The bug was never about RGB.** It is about ANY internal-flash program/erase
overlapping the flash->LCD DMA. Gating one producer left every other one open.

**Real fix: `backing_store_pre_write_hook()`**, a weak hook added to
`platforms/chibios/drivers/wear_leveling/wear_leveling_efl.c` and called from
`backing_store_unlock()`. Unlock brackets the *whole* program/erase sequence, so
it catches every writer — eeconfig, VIA keymaps, wear-levelling consolidation —
instead of whichever one was noticed. The board's override in `ak820pro.c` drains
any in-flight blit first.

**Waiting is sufficient, not merely a narrowing.** Flash writes are synchronous on
the main loop and blits are started from the main loop too, so once the in-flight
blit drains, no new one can begin before the write completes.

**VIA key assignment is now the RELIABLE REPRODUCTION** — the first one we have
had. Every earlier attempt was "hammer the brightness keys and hope", which is why
"it stopped happening" was such weak evidence. Retest with VIA, not with RGB.

**Diagnostic recipe** (reuse for any future hang): raw-HID round-trip
(`ak820ctl info`) is the liveness probe — USB enumeration and `ak820ctl list` are
**not**, they answer from OS-cached descriptors. `DEBUG_MATRIX_SCAN_RATE` and
`console: true` are both already on, so `qmk console` prints a scan-rate line
every second; the second it stops is the second the main loop died. Capture it
with timestamps to a log so the *next* hang leaves the preceding lines:

```sh
qmk console 2>&1 | while IFS= read -r l; do printf "%s %s\n" "$(date +%H:%M:%S)" "$l"; done >> log
```

**The stuck-LINKING state silently KILLED MEDIA KEYS over Bluetooth — fixed
2026-08-29.** This is the part that made the bug look cosmetic when it was not.
`bluetooth_send_keyboard()` sends `0xA1` frames **unconditionally**, but
`bluetooth_send_consumer()` was gated on `ch582_kbd_output_active()`, i.e.
`connect_requested && is_module_connected`. So while stranded in `LINKING`:

| Path | Frame | Gated? | Result while stuck |
|---|---|---|---|
| Typing | `0xA1` | no | **works** |
| Volume / media (encoder) | `0xA3` | on `is_module_connected` | **silently dropped** |

Hence "Bluetooth mostly works" — half the input path was dead and the other half
was fine. The gate is now `connect_requested` only, matching the keyboard path:
a consumer frame sent to a link that is genuinely down just goes nowhere, which
is strictly better than dropping it on a link that is actually up. The now-unused
`ch582_kbd_output_active()` helper was removed.

**There is no way to ASK the module its state — checked, do not re-derive.**
`0xA5` "Status" is documented as inert with no reply, and `CH582F_PROTOCOL.md`
forbids `5C` battery as a connection signal in bold. `5B 32` is a one-shot
announcement and `5B 23` (idle) is emitted both connected and disconnected, so a
dropped `5B 32` and a genuinely failed link produce **byte-for-byte identical**
traffic from then on. The driver cannot distinguish them; only heuristics remain.

**Most likely root cause: the interrupt priority inversion.** `5B 32` is a single
inbound UART frame, and UART2 sat at the LOWEST priority while the row ISR ran at
up to 18,800/s — the same starvation that mangled outbound frames. Intermittent
by nature ("mostly works, occasionally not"), which matches the observed
behaviour. Priorities were fixed 2026-08-29; **watch whether the blink recurs on
that firmware before adding any further heuristic.**

**Real bug — BT channel digit blinks forever after a successful pair.**
Observed 2026-08-28: paired fine and typing worked, but the channel digit kept
blinking. Flipping the dip switch to wired and back to BT fixed it.

Root cause is a genuine fragility, not a coding slip. `ch582f_ajazz.c` derives
connection state *only* from `5B` event frames, and `CH582_PROTOCOL.md` states
`5B 32` is **"the only 'connected' signal."** The module sends it **once**, on
link-up, and never re-asserts — the doc notes the RX line is *"otherwise silent
at steady idle."* So the driver is edge-triggered (`conn_state =
CH582_CONN_LINKING; /* attempting until 5B says otherwise */`), and one missed
frame strands it in `LINKING` indefinitely while the link is actually live.

Blink rate identifies the stuck state: **~200 ms = `PAIRING`**,
**~700 ms = `LINKING`** (`CONN_BLINK_PAIRING_MS` / `CONN_BLINK_LINKING_MS` in
`graphics/display.c`).

**Fix implemented and flashed 2026-08-28. Early hardware testing looks good** —
switching to BT gave a solid icon + solid digit, and pairing a phone to an empty
slot behaved correctly (fast blink while advertising, then settled). Not yet
*conclusively* proven: the original bug was intermittent, and a solid digit is
also what the normal `5B 32` path produces, so a handful of good cycles cannot
distinguish "fixed" from "did not recur." Treat as probable-good, not confirmed.
Promotes `LINKING` → `CONNECTED` on a `5A` host-LED frame (a host only sends LED
state to a device it is connected to). The naive version is unsafe, because the
existing `5A` guard exists precisely to reject forged frames from the *power-up /
2.4G link-up burst* — the same window a promotion would fire in. So it is gated
three ways:

1. same plausibility mask as the existing guard, `(d & ~0x1F) == 0`;
2. state must be exactly `LINKING` — never `IDLE`/`REJECTED`/`PAIRING`;
3. `CH582_5A_PROMOTE_MS` (3000 ms) must have elapsed since `LINKING` began.

The dwell is what makes it safe: a genuine `5B 32` arrives at link-up and would
already have won, so anything still `LINKING` 3 s later is a missed frame, not
one in flight. The promoting frame deliberately does **not** apply its LED bits —
lighting Caps off the frame that establishes the link is the exact failure the
original guard prevents; a real host repeats its LED state.

`linking_since` is a dedicated 32-bit timestamp, **not** `last_attempt_time`,
which the connect retry resets every 500 ms and so never accumulates. It is
stamped at both `LINKING` entry points, guarded on the `5B 33/34` path so
repeated frames do not restart the window.

**Known gap:** only recovers from `LINKING` (slow blink). A stuck `PAIRING`
(fast blink) is not covered — during pairing the module is advertising and no
host should be sending LED frames, making promotion a weaker inference there.

**Do not use the `5C` battery reply for this** — the protocol doc warns in bold
it must never be treated as a connected signal, and the driver already polls it
every 5 s.

**To validate:** several pair/re-pair cycles; digit should go solid within ~3 s
of link-up. Confirm Caps Lock still mirrors over BT.

**Mitigated — "DLP rainbow" color sparkle** on the RGB, visible peripherally / on
eye movement. `SN32F2XX_RGB_MATRIX_ROW_CHANNELS 3 // R, B, G` means R/G/B light
in separate time slots, so saccades separate the fields. Inherent to the driving
scheme, not the LED packages. **Halved by doubling the field rate to 242 Hz** —
see "RGB field rate" under the local firmware edits for the math, the coupled
constants, and the next lever. Not fully eliminable at any achievable field rate.
- **`sonixqmk` boot splash has a white background** (the PNG is 52% pure white —
  fpb authored it that way). It only looked black before because the panel was
  inverting. To darken it: edit the PNG, re-run `mkraw.py --flash`, re-provision
  with `ak820ctl` — **no firmware rebuild needed**, since asset count and
  dimensions are unchanged so `flash_assets.h` stays identical.

**The shipped v1.10 is gone permanently.** The AJAZZ Windows driver installer was
never grabbed, so the rollback floor is fpb's
`StockFWBinaries/AJAZZ_AK820PRO_PID_8009_V1.13_SN32F290.bin`.

### Re-entering the bootloader

The pin short is **no longer needed**: `ESC` while plugging in, or `Fn`+`ESC`
from a running keyboard. Re-flashing is now cheap.

### If you ever do need the pin short again

It is a **2-pin female header** in the spacebar channel, just left of the
spacebar switch — not a pair of exposed pads (`ajazz-ak820-pro/img/bootloader-pins.jpg`).

Hard-won details:

- **A pair of SIM-eject tools works far better than tweezers.** Stiff, right
  pitch, won't skate off mid-insertion. Seating something that *stays* put beats
  trying to pinch contacts at the same instant you seat the USB connector.
- The ISP pin is sampled **only at power-on reset**. This is a tri-mode board
  with a battery, so put the `bt/off/cable` dip switch in **cable** (or off) and
  wait ~10 s unplugged, or the MCU may never actually cold-boot and the short
  does nothing no matter how good the contact is.
- **Bootloader mode looks completely dead** — no RGB at all, LCD dark, no
  typing. If anything lights up, it booted stock/QMK instead. There is no subtle
  indicator.
- Bootloader mode is **latched**. Once `0C45:7140` appears you can remove the
  short — and you should, or `sonixflasher`'s post-flash reboot lands right back
  in the bootloader.

---

## Environment

`source env.sh` sets `QMK_HOME` and `PATH` for everything below.

> The handoff and `ak820pro-mac-setup.sh` assume `~/ak820pro`. **That directory
> does not exist.** Everything was built in place here instead, to reuse the
> clones that were already present. Translate paths accordingly when following
> the handoff.

```sh
source env.sh
cd "$QMK_HOME" && qmk compile -kb a_jazz/ak820pro -km via
```

Toolchain: xpack `arm-none-eabi-gcc` 13.3.1, venv `qmk` CLI 1.2.0 (fine on the
system Python 3.14), Homebrew `hidapi` 0.15.0 + `pkg-config`.

### ⚠️ SonixFlasherC MUST be built with `USE_LIBUSB=1`

**`make sonixflasher` silently produces a binary that cannot flash on Tahoe.**
This cost real time — do not repeat it.

Being on fpb's `fix_for_macos_tahoe` branch is **not sufficient**. Look at the
Makefile: the fix lives in `hid_wrappers.c`, and `OBJS=hid_wrappers.o` sits
inside an `ifeq ($(USE_LIBUSB), 1)` block. Without the flag, `hid_wrappers.c` is
never compiled, the binary links against plain hidapi, and it fails — while
still reporting itself as `sonixflasher 2.0.8`, exactly like a good build.

```sh
brew install libusb
cd SonixFlasherC && make clean && rm -f sonixflasher && make USE_LIBUSB=1
nm sonixflasher | grep -c libusb     # must be > 0
```

**Failure signature** (all five retries, no other diagnostic):

```
ERROR: Could not open the device (Is the device connected?).
Device failed to open, re-trying in 3 seconds. Attempt 1 of 5...
```

**Do not chase this as a permissions problem.** The tell is that
`ioreg -p IOUSB` shows the device present while **no `IOHIDDevice` node exists
for it**:

```sh
ioreg -c IOHIDDevice -w0 -l | grep -c '"ProductID" = 28992'   # 0 on Tahoe
```

On Tahoe, macOS enumerates the SN32 bootloader as a USB device but publishes no
HID interface, so hidapi has nothing to open. **`sudo` does not help** — there
is no HID node to gain permission to. Neither does Input Monitoring, and neither
does disabling the agent sandbox (all three were tried). libusb talks to the USB
device node directly and sidesteps the whole problem.

### ⚠️ Local firmware edits — uncommitted, in an upstream clone

`qmk_firmware-ak820pro/` is a pristine clone with **uncommitted local changes**.
A `git checkout`/`git pull`/`git stash` there silently reverts them and the
keyboard regresses. Check `git status` before touching that repo.

**Two of these are in QMK CORE, outside `keyboards/`** — easy to miss when
looking for local changes. `git status` in `qmk_firmware-ak820pro/` is the only
reliable inventory.

Inside `keyboards/a_jazz/ak820pro/`:

| File | Change | Why |
|---|---|---|
| `graphics/lcd_bus.c` | `MADCTL_270` (`0xA8`) → `MADCTL_DASH` (`0x68`) | **This unit's LCD is mounted 180° from fpb's** and rendered upside down. Traded MY for MX. |
| `graphics/lcd_bus.c` | added `0x21, 0, 0` (INVON) to the init sequence | This panel renders the firmware's white-on-black as black-on-white without it. |
| `keyboard.json` | `rgb_matrix.default` += `hue 21, sat 140, val 64` | Dim warm white instead of QMK's default full-brightness red (`val 64` against the 255 ceiling ≈ 25%). |
| `config.h` | `RGB_MATRIX_MAXIMUM_BRIGHTNESS 255`, `HUE_STEP 16`, `VAL_STEP 8`, `SPD_STEP 128` | LED field rate 121 → **1046 Hz** for the DLP-rainbow artifact. Only safe with the priority ordering in `mcuconf.h` — see that section. |
| `config.h` | `CORTEX_ENABLE_WFI_IDLE FALSE` | Removes one half of the hang mechanism. **Did not fix the hang** — kept because it is free on a plugged-in board. |
| `config.h` | `DISPLAY_CLOCK_SHOW_SECONDS TRUE` | Was `FALSE` with no stated reason; `display.c` defaults it on. |
| `config.h` | `RTC_CHECK_INTERVAL_S 60`, `RTC_PERIOD_INITIAL 33400` | Calibration was hourly; the ILRC divider is measured, not nominal. See the RTC section. |
| `config.h` | `RGB_MATRIX_EEPROM_WRITE_DELAY 750` | Debounces eeconfig writes (~8/s → ≤1.3/s). Half of the hang fix. |
| `rtc/rtc.c` | divider trim in `rtc_clock_discipline()`, seed in `rtc_init()` | The trim the docs claimed existed but never did. See the RTC section. |
| `bluetooth/ch582f_ajazz.c` | `CH582_5A_PROMOTE_MS`, `linking_since`, `5A` promotion branch | Recovers from a missed `5B 32`. See the BT quirk entry. |
| `ak820pro.c` | `rgb_matrix_eeprom_flush_allowed()` → `!lcd_blit_busy()` | The actual hang fix. See the hang entry. |
| `ak820pro.c` | `SCR_UP` / `SCR_DN` cases in `process_record_kb` | LCD brightness keys. |
| `ak820pro.c` | `TEXT_CHANNEL 0x12`, `is_text_cmd`, `text_command` | Host text slot — see its section. |
| `ak820pro.c` | `KC_MEDIA_PLAY_PAUSE` case (returns **true**) | Optimistic play/pause icon flip. |
| `graphics/display.c` `.h` | text slot buffer, render, expiry, transport glyphs | ditto. |
| `graphics/display.c` | `conn_status_update()`, `CONN_STATUS_HOLD_MS`, overlay render | Wireless status words in the text band — see its section. |
| `config.h` | `PARAM_OVERLAY`, `PARAM_OVERLAY_HOLD_MS` | One switch that compiles every readout in or out entirely. |
| `ak820pro.c` | `param_status_task()`, `rgb_mode_short()` | Polls RGB / NKRO / RGB-enable on the 10 Hz tick; local short-name table for the 10 enabled effects. |
| `graphics/display.{c,h}` | `display_set_param_status()`, `display_get_brightness_max()` | Stores and renders the readout; formatting stays in `ak820pro.c` so the RGB API is out of the graphics layer. |
| `ak820pro.c` | `SCR_UP`/`SCR_DN` push `LCD nn%` | LCD backlight readout, level index as a percentage. |
| `graphics/lcd_bus.c` | `anim_toggle()` reads the header BEFORE pausing | An empty animation slot blinked the screen black for ~1 s and did nothing. This board's stock header reads **zero frames**, so that was all `Fn`+`Delete` did. Upstreamable. |
| `ak820pro.h` | `SCR_UP`, `SCR_DN` **appended** to `ak820pro_keycodes` | Index-matched to `via.json` — append only. |
| `graphics/display.c` | backlight software PWM + brightness API, ticked from `GPTD4` | See the dedicated-timer section. |
| `graphics/display.h` | `display_{get,set}_brightness`, `display_brightness_{up,down}` | ditto. |
| `config.h` | `DISPLAY_BRIGHTNESS_DEFAULT 5`, `INDICATOR_BRIGHTNESS_DEFAULT 1`, `CHARGING_LED_BRIGHTNESS 0` | LCD boots mid-range (`LCD 56%`, duty 8/48) — the dimmest step was too dim against real content. Indicators stay at the dimmest lit step; charging LED off. **No longer coupled to `SPD_STEP`** — the PWM tick moved to its own timer. |
| `graphics/display.h` | `DISPLAY_TEXT_MAX_L0 19`, `DISPLAY_TEXT_MAX_L1 21` | Per-line budgets — only line 0 loses the transport-icon gutter. |
| `graphics/display.c` | `TEXT_X2`, 6px-advance comments, `adv = big ? 10 : 6` | The 6x14 cell. The `adv` in `draw_playback()` is the one hand-written cell width in the tree. |
| `graphics/res/flash_assets.h` | dimension comment `7x14` → `6x14` | Generated. Comment-only: ids unchanged, `cell_w` is read from flash at runtime. |
| `keymaps/via/keymap.c` | `SCR_UP`/`SCR_DN` on `Fn`+`PgUp`/`PgDn`, **both** Fn layers | Beside the existing `Fn`+`Home` toggle. |
| `mcuconf.h` | **`SN32_SERIAL_UART2_PRIORITY 1`, `SN32_GPT_CT16B3_IRQ_PRIORITY 2`, `SN32_PWM_CT16B0/1/2_IRQ_PRIORITY 3`** | The defaults were inverted. Fixes Bluetooth throughput AND backlight flicker. See the priority section. |
| `mcuconf.h` | `SN32_GPT_USE_CT16B3 TRUE` | Dedicated 20 kHz PWM tick. |
| `halconf.h` | `HAL_USE_GPT TRUE` | ditto. |
| `ak820pro.c` | `pwm_tick_init()`, `pwm_tick_cb()`, `MCTRL` reset-on-match | The 20 kHz tick. The `MCTRL` line is mandatory — see the timer section. |
| `ak820pro.c` | `indicators_tick()`, `led_update_kb()` → `false` | Per-LED indicator PWM; claims Caps from QMK core. |
| `bluetooth/ch582f_ajazz.c` | `tx_stat_sent` / `tx_stat_timeout` / `tx_stat_drop` counters | **KEPT** — prints `[ch582]` every 5 s *on change only*. The BT path is the fragile one; this is how the priority inversion was caught. |
| `bluetooth/ch582f_ajazz.c` | `bluetooth_send_consumer()` gated on `connect_requested` only | Was also gated on `is_module_connected`, which silently killed media keys whenever the digit was stuck blinking. See the digit entry. |
| `ak820pro.c` | `[pwmtick]` per-second print **REMOVED** | Served its purpose; the recipe to re-add it (and how to read the number) is in the comment above `pwm_tick_cb()`. |
| `ak820pro.c` | `bt_pair_hold_task()`; slot keys + `Fn`+`P` only arm/disarm | Hold-to-pair fires at the threshold under the finger, not on key-up. |
| `graphics/display.{c,h}` | `display_set_pair_hint()`, `Hold to pair` | Feedback during the hold; outranks link state. |
| `graphics/display.c` | `CONN_BLINK_FAILED_MS`, digit shown on `REJECTED` | A failed link kept its slot digit instead of blanking it. |
| `bluetooth/ch582f_ajazz.c` | `pairing_pending`, `CH582_PAIR_RETRY_MS`, `CH582_PAIR_MAX_TRIES` | Resend `A6 51` until `5B 31` confirms — the module drops it during a connect attempt. |
| `ak820pro.c` | `BT_PAIR_HOLD_MS` 1000 → **2000** | A slow tap at 1 s could accidentally drop a live link and start advertising. |
| `graphics/display.{c,h}` | `display_set_pair_hint(int16_t pct)` → `Pair: ======` bar | Progress during the hold; a static label at 2 s reads as "nothing is happening". |
| `bluetooth/ch582f_ajazz.c` | `select_pending`, `CH582_SELECT_CONFIRM_MS`, `CH582_SELECT_MAX_TRIES` | Backstop retry for a dropped select. Stops on `5B 33`/`34`. |
| `bluetooth/ch582f_ajazz.c` | `bounce_pending`, `CH582_BOUNCE_MS` | Cancel-pairing bounce — the only thing that gets the module out of advertising. |
| `via.json` | `SCR_UP`, `SCR_DN` **appended** to `customKeycodes[]` | Must stay index-aligned with the enum. |

**In QMK core — these are the ones a `git checkout` will silently eat:**

| File | Change | Why |
|---|---|---|
| `quantum/rgb_matrix/rgb_matrix.c` | weak `rgb_matrix_eeprom_flush_allowed()` hook; `rgb_task_sync` uses `eeconfig_flush_rgb_matrix_task(RGB_MATRIX_EEPROM_WRITE_DELAY)` | QMK already had the debounce helper and simply wasn't using it. The weak hook defaults to permissive, so behaviour is unchanged for every other keyboard. |
| `drivers/led/sn32f2xx.c` | weak `sn32_rgb_isr_hook()` called from `rgb_callback` | Gives a board a kHz-rate tick without its own timer; the AK820 Pro software-PWMs the LCD backlight with it. Empty no-op by default, so other boards are unaffected. |
| `drivers/led/sn32f2xx.c` | `periodticks = RGB_MATRIX_MAXIMUM_BRIGHTNESS + 1` | `pwm_lld_start` writes the period match as `period - 1`, so a full-value colour channel wrote `MR = 255` against a counter resetting at 254 — a match that **never fires**, blanking that channel at exactly 100%. Looked like the colour lurching at max brightness and brief flashes while stepping. |

**The LCD changes are unit-specific, not general fixes.** fpb's units need
`0xA8` and no INVON. Do not upstream them without a flag.

How the inversion was diagnosed, since it is counterintuitive: `display.c`
defines `COL_BG 0x0000` (black) and `COL_FG 0xFFFF` (white), and the source art
is white-on-black (font atlas measured at 80.6% black background). The board
showed black-on-white, and an *asset-free* board showed solid **white** — which
is the black clear-to-background being inverted. Both symptoms, one cause.

`LCD_OFF_X 1` / `LCD_OFF_Y 2` did **not** need adjusting after the 180° flip —
verified on hardware, pixels reach every edge with no garbage band.

#### RGB field rate — why those three constants move together

`drivers/led/sn32f2xx.c` lights the 18 hardware rows (6 key rows × R,B,G) one at
a time, one row per PWM period, so a key's three colour channels fire in separate
time slots. The full R→B→G cycle rate is:

```
freq / periodticks / SN32F2XX_RGB_MATRIX_ROWS_HW
```

with `periodticks = RGB_MATRIX_MAXIMUM_BRIGHTNESS` and — the non-obvious part —

```c
freq = HUE_STEP * SAT_STEP * VAL_STEP * SPD_STEP * LED_PROCESS_LIMIT
```

**The PWM clock is derived from the UI step sizes.** That coupling is a wart in
the SonixQMK driver, not a local choice, and it means changing a step size
silently retunes the LED field rate. `HARDWARE_PWM.md` confirms the steps were
being abused for exactly this (it lists reverting a `HUE_STEP=2` tuning as a
payoff of moving to hardware PWM).

Stock: `8*16*16*16*17 = 557056`, `/255`, `/18` = **121 Hz**. Above flicker fusion
when still, but the ~0.46 ms channel spacing smears into colour fringes during a
saccade — the DLP rainbow artifact.

**There are two levers, and they are not equivalent.** An intermediate revision
lowered `periodticks` to 128 (→ 242 Hz) — that works, but spends PWM resolution,
and this board is run *dim in a dark room*, so the low end is the worst thing to
coarsen. Raising `freq` buys the same field rate for free: `PWM_CLK` is
`SN32_HCLK` = 48 MHz against a stock `freq` of ~0.56 MHz, so there is ample
headroom. `SPD_STEP` is the right factor to spend — it sets only the
animation-speed step, meaningless on `solid_color`.

Current: `SPD_STEP` **128**, `periodticks` **255** (all 256 brightness levels).

```
freq = 16*16*8*128*17 = 4456448
psc  = 48e6/4456448 - 1 = 9         (integer division; hal_pwm_lld.c:293)
eff  = 48e6/10 = 4800000 Hz
field rate = 4800000 / 255 / 18 = 1046 Hz
```

| | Stock | Interim (128 ceil) | 64 | **Now (128)** |
|---|---|---|---|---|
| Effective PWM clock | 558 kHz | 558 kHz | 2.29 MHz | **4.8 MHz** |
| Field rate | 121.6 Hz | 242.2 Hz | 498.0 Hz | **1046 Hz** |
| Brightness levels | 255 | 128 | 255 | **255** |
| Dim steps | 15 | 16 | 31 | **31** |
| Row ISR | 2,189/s | 4,360/s | 8,964/s | **18,800/s** |
| Matrix scan | 1396 Hz | — | ~1050 Hz | **~390-400 Hz** |
| Speed steps | 16 | 16 | 4 | **2** |

Confirmed on hardware 2026-08-29: rainbow **diminished** at 1046 Hz, and typing
over Bluetooth is "nearly instant" despite the 390-400 Hz scan. All 256
brightness levels retained, which was the point of raising `freq` rather than
spending `periodticks`.

**`SPD_STEP 128` was previously backed out as "it breaks Bluetooth" — that was
wrong.** The fault was the interrupt priority inversion, not the ISR rate; at
this same 18,800/s the link now measures 0.042 ACK timeouts per frame against a
0.38 baseline at stock rate. Do not re-derive that mistake: see the priority
section before touching this constant.

Do not expect any achievable field rate to remove the artifact entirely; it is
inherent to lighting R, G and B in separate time slots.

Note the artifact's *visibility* in a dark room is mostly dark adaptation and
contrast, not the duty cycle. Duty does set how wide each colour's image is while
the R→B→G spacing stays fixed — so shorter pulses give crisper, better-separated
bars — but that is second-order.

**⚠️ ANIMATION SPEED ONLY HAS 3 SETTINGS (0 / 50% / 100%). THAT IS THE COST OF
THE FIELD RATE, NOT A BUG.** `SPD_STEP` is 128 against a 0-255 range, so the only
reachable values are 0, 128 and 255. It looks broken and is not.

**Do NOT "fix" it by lowering `SPD_STEP`** — that is the PWM clock multiplier, and
dropping it to the stock 16 takes the field rate from 1046 Hz back to 121 Hz and
the DLP-rainbow artifact returns at full strength. Nothing in the UI connects
those two things, which is exactly why this note exists.

Accepted deliberately 2026-08-29: JD does not use animated effects (the board runs
`solid_color` dim warm white), so coarse speed control costs nothing real.

**⚠️ THIS IS A GENERAL PRINCIPLE, AND IT HAS NOW BEEN USED TWICE.** `freq` is a
PRODUCT of the four UI step sizes and `LED_PROCESS_LIMIT`, so any one of them
can be made finer for free by making another coarser. What matters is the
product, not which factor carries it.

Applied 2026-08-30 to buy **hue** granularity: `HUE_STEP` 16 -> 8 (22.5 deg ->
11.25 deg, 32 values) paid for by `SAT_STEP` 16 -> 32 (16 values -> 8). Product
unchanged at 4,456,448, so psc stays 9, the effective clock stays 4.8 MHz and
the field rate stays 1046 Hz. Saturation is the cheapest factor to spend: it is
set-once, 8 values still reaches anywhere useful, and hue is the one you
actually hunt around in with the on-panel readout.

The table below is the same trick aimed at speed instead. **Do not treat these
as two unrelated tweaks** — if you need granularity anywhere, find the factor
you care least about and trade it, rather than lowering the one you want and
silently halving the field rate.

If speed granularity is ever wanted, **rebalance rather than reduce** — the
product is what matters, not which factor carries it:

| | Now | Swap |
|---|---|---|
| `SAT_STEP` | 16 | 32 |
| `SPD_STEP` | 128 | 64 |
| `freq` | 4,456,448 | **4,456,448 — identical** |
| Field rate | 1046 Hz | **1046 Hz — unchanged** |
| Speed values | 3 | 5 |
| Sat values | 16 | 9 |

Saturation is a set-once parameter where 9 values still reaches anywhere useful,
so that is the cheapest factor to spend next. Going all the way back to
`SPD_STEP 16` is not realistic: it needs an 8x increase elsewhere, i.e. 2 hue
values or 4 brightness values, both far worse than coarse speed.

**The readout says `Speed 50%`, which oversells it** — a percentage implies
continuous control. `Speed 1/2` would be honest. Not worth a flash cycle on its
own; bundle it with the next change.

**Two traps if you tune this further:**

1. `periodticks` is *also* the `val` ceiling, and the driver feeds the raw colour
   byte straight in as duty (`pwmEnableChannel(..., led_state[i].b)`). Halving it
   makes every **stored** `val` render twice as bright — EEPROM survives the
   flash, so the board comes back brighter and needs re-dimming by hand. Scale
   `RGB_MATRIX_DEFAULT_VAL` to match whenever you change the ceiling.
2. Lowering `VAL_STEP` for finer dimming **halves the field rate**, because it is
   a factor of `freq`. Compensate on another step (that is why `HUE_STEP` is 16).

**`SPD_STEP 128` is now shipped and measured** — see the table above. The CPU
cost is real (row ISR ~18,800/s, matrix scan ~390-400 Hz, ms timebase 1.2% slow)
but was confirmed on hardware as feeling near-instant to type on.

If more field rate is ever wanted, the next lever is **not** `SPD_STEP 256` —
`psc` would floor at 4 (eff 9.6 MHz, ~2092 Hz) but the row ISR would hit
~37,600/s on top of the 20 kHz GPT, which is past what this M0 has left. Buy the
headroom back first by halving the GPT tick to 10 kHz (`PWM_TICK_HZ`), which
costs backlight switching rate (417 → 208 Hz) but no field rate at all.

Do **not** reach for `periodticks` to get there — it would undo the dimming
granularity that is the whole reason `freq` was raised instead.

### The ChibiOS patches are working-tree edits

Six `.diff` files in `keyboards/a_jazz/ak820pro/` are applied by hand into
`lib/chibios-contrib/`. They are **not committed**, so **any `git submodule
update` silently discards them** and the build breaks in confusing ways. Order
matters — `spi_flash_dma` must follow `spi_fifo_pump` (same LLD file), and
`efl_ramtext` is required for VIA:

```
hardware_pwm → i2c_fallback → rtc_lld → spi_fifo_pump → spi_flash_dma → efl_ramtext
```

Reapply with the loop in `ak820pro-builds/ak820pro-mac-setup.sh` step 5, which
is idempotent (it reverse-checks each patch before applying).

### ⚠️ TWO SESSIONS CANNOT SHARE THIS TREE SAFELY — the binary path is shared

Hit 2026-08-30 with two Claude sessions working in this workspace at once.

**`qmk compile` writes to ONE path**, `$QMK_HOME/a_jazz_ak820pro_via.bin`. So
**whoever compiles last owns that file**, regardless of who armed a flasher.
One session's rebuild silently replaced the other's binary eleven seconds
before a flash; the flash then carried the wrong build and reported success.

The failure is nasty because it looks like your change simply had no effect:
verification checksum OK, board reboots normally, and the panel shows the other
session's firmware. Nothing errors.

**Guards, in order of usefulness:**

1. **`stat` the binary before flashing** and confirm the timestamp is your build,
   not merely recent. This is the only reliable check.
2. **Disarm before handing over** — `pkill -f "seq 1 900"` for the arm loop used
   here. But note this does NOT protect you: the hazard is the shared file, not
   the flasher.
3. **Say so out loud.** Cross-session messages (`ListAgents` / `SendMessage`)
   work between sessions on this machine and are the practical coordination
   channel.

Other shared resources that conflict the same way:

| Resource | Conflict |
|---|---|
| `$QMK_HOME/a_jazz_ak820pro_via.bin` | last compile wins, silently |
| `qmk console` | EXCLUSIVE; a second instance retries in a tight loop |
| raw HID (`0xFF60`/`0x61`) | `ak820ctl`, VIA and the media poller all want it |
| `flash_assets.bin` + `flash_assets.h` | must change together or the panel renders garbage |
| the six ChibiOS `.diff` patches | uncommitted working-tree edits; a `git checkout` in that tree eats them |

**Do not `git checkout` in `qmk_firmware-ak820pro/` to resolve a conflict.** That
silently discards the hand-applied ChibiOS patches and the build breaks in
confusing ways later.

### Verifying a build

Do **not** compare byte-for-byte against the GREMLIN binary — builds are not
reproducible; literal-pool pointers shift by a constant offset with the build
string. Compare *structurally* instead. A good build is ~27% nonzero across the
256 KB image with:

| | |
|---|---|
| SP | `0x20000400` |
| Reset | `0x00000191` |
| HardFault / SVC[11] / PendSV[14] | `0x00000193` |
| USB descriptor | `0C45:8009` bcd `0x0100` |

The Mac build matched the GREMLIN build on all of these. **Never compare
density against stock firmware (~90% nonzero)** — that comparison produces a
false alarm, as it did once already.

---

## Contents

### Local, not from upstream

| Path | What |
|---|---|
| `CLAUDE.md` | this file |
| `env.sh` | sets `QMK_HOME` + `PATH`; `source` it before building or flashing |
| `ak820pro-builds/AK820PRO-HANDOFF.md` | **the reference document** — hardware, memory map, flashing, LCD assets |
| `ak820pro-builds/handoff.html` | same content, styled |
| `ak820pro-builds/ak820pro-mac-setup.sh` | idempotent one-shot setup; assumes `~/ak820pro`, so paths need translating |
| `ak820pro-builds/a_jazz_ak820pro_via.bin` | firmware built on GREMLIN (Windows/WSL), kept as a reference |
| `ak820pro-builds/a_jazz_ak820pro_default.bin` | ditto, non-VIA keymap |
| `assets-src/mkbdfatlas.py` | imports a BDF bitmap font into the atlas PNG format; pins the baseline, refuses to clip |
| `assets-src/cozette.bdf` | the 13px face (MIT, `COZETTE-LICENSE` beside it) — committed, unlike the 10 MB Iosevka TTF |
| `flash.sh` | flash + keymap preservation; the normal way to flash |
| `hostagent/ak820keymap.py` | dump/restore the VIA keymap over raw HID — flashing erases it |
| `hostagent/ak820text.py` | pushes text + icon to the LCD over raw HID; knows nothing about music |
| `hostagent/nowplaying-macos.sh` | polls Spotify/Music every 3 s and feeds the pipe |

### Upstream clones (pristine — verify before assuming otherwise)

| Path | Origin | Branch |
|---|---|---|
| `qmk_firmware-ak820pro/` | `fpb/qmk_firmware` | `ak820pro-flashlcd-unified-dualspi` |
| `ajazz-ak820-pro/` | `fpb/ajazz-ak820-pro` | `main` |
| `time-util-ak820pro/` | `fpb/time-util-ak820pro` | `main` |
| `SonixFlasherC/` | **`fpb/SonixFlasherC`** | **`fix_for_macos_tahoe`** |

`SonixFlasherC` was originally cloned from upstream `SonixQMK/main`, which does
**not** work on Tahoe. An `fpb` remote was added and the branch switched. If a
future session finds it back on `SonixQMK/main`, that is a regression.

All four arrived from GREMLIN with CRLF line endings, showing as whole-file
diffs. That was normalized with `git checkout -- .`; the real diff was empty.
If they look mass-modified again, check `git diff --ignore-cr-at-eol --stat`
before believing it.

### Build artifacts (large, disposable, regenerable)

| Path | Size |
|---|---|
| `xpack-arm-none-eabi-gcc-13.3.1-1.1/` | 876 MB — ARM toolchain |
| `qmk_firmware-ak820pro/` | 1.6 GB — mostly submodules |
| `venv/` | 45 MB — `qmk` CLI |

---

## Where things live

**Firmware** — `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`

- `ak820pro.c` — raw HID channels: `RTC_CHANNEL = 0x10`, `FLASH_CHANNEL = 0x11`.
  Both are live on this branch, contrary to ak820ctl's README.
- `graphics/lcd_bus.c` — the authoritative flash memory map (`FLASH_ASSET_BASE`,
  `ANIM_BASE`, stride, frame limit). Trust this over any prose doc.
- `graphics/res/flash_assets.h` — generated by `mkraw.py`; the one firmware
  coupling to the asset set.
- `keymaps/via/` — four layers: `WINBASE`, `WINFN`, `MACBASE`, `MACFN`.
  `QK_BOOT` on Fn+Esc, `ANIM_TOG` on Fn+Delete, encoder exposed as a VIA knob.
- `*.diff` × 6 — the ChibiOS patches described above.
- `docs/LCD_FLASH_LAYER.md`, `docs/LCD_DMA_BRANCHES.md`
- `rules.mk` — contains two stale claims (RTC "does not work", a `mkraw.py` path
  that does not exist there). See handoff §2.

**Host tools**

- `SonixFlasherC/sonixflasher` — built v2.0.8 **with `USE_LIBUSB=1`** (mandatory,
  see above). Write-only; **there is no way to dump firmware off the board.**
- `time-util-ak820pro/ak820ctl` — built. `clock`, `info`, `flash write|erase|crc`,
  `list`. Confirmed working against the flashed board; `info` reports
  `jedec id 0x856017`, `writable from 0xCE0000`.
- `time-util-ak820pro/assets/flash_assets.bin` + `.h` — generated by
  `mkraw.py --flash`, already provisioned to the board. **Always diff the
  generated `flash_assets.h` against
  `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/res/flash_assets.h`
  before flashing assets** — if they disagree, the firmware needs a rebuild or
  the LCD renders garbage.
- `time-util-ak820pro/assets/` — `mkraw.py` (stills → `flash_assets.bin` + `.h`)
  and `mkanim.py` (GIF → frame blob). Python 3 stdlib only — no Pillow, no
  ffmpeg. Source PNGs: `sonixqmk` splash, five 24×24 status icons, two Iosevka
  font atlases.

**Reference material** — `ajazz-ak820-pro/`

- `docs/` — MCU/LCD/flash/RTC datasheets, `matrix.md`, `HARDWARE_PWM.md`,
  `CH582F_PROTOCOL.md`, `gc9107_init.c`
- `img/` — pinouts, wiring, **`bootloader-pins.jpg`** (needed for the pin short)
- `StockFWBinaries/` — vendor images. For rollback use
  **`AJAZZ_AK820PRO_PID_8009_V1.13_SN32F290.bin`**, *not* the v1.14 one — v1.14
  changes the PID to `8099`, which makes AJAZZ's own drivers stop seeing the board.
- `QMKFWBinaries/` — fpb's prebuilt `.bin`s for every branch, plus **`via.json`**
  to load into VIA/Vial.

---

## Re-flashing

**Use `./flash.sh`** — it preserves the VIA keymap, which the erase would
otherwise destroy:

```sh
./flash.sh                          # defaults to $QMK_HOME/a_jazz_ak820pro_via.bin
./flash.sh path/to/other.bin
./flash.sh --no-backup              # skip the keymap dump/restore
```

It dumps the keymap while QMK is still running, waits for you to press
`Fn`+`ESC`, flashes detached (an interrupted `sonixflasher` leaves the board
erased — this has happened here), waits for `0x8009`, then writes the keymap
back. **It refuses to flash if the backup fails**, since that is the one moment
the keymap is recoverable. It also prints the binary's mtime: `qmk compile`
writes one shared path, so confirm it is YOUR build, not merely a recent one.

The manual equivalent, if you need it:

```sh
source env.sh
ioreg -p IOUSB -w0 -l | grep -c '"idProduct" = 28992'   # 0x7140 — confirm first
./SonixFlasherC/sonixflasher --vidpid 0c45/7140 --file "$QMK_HOME/a_jazz_ak820pro_via.bin"
```

A good flash prints `Flash Verification Checksum: OK!` then `Rebooting.` and the
board comes back as `0x8009` on its own. Expect one benign-looking retry early —
`Code Option Table ... Expected: 0x0000 Received: 0xFFFF` triggers
`Device failed to init, re-trying`, then it succeeds on attempt 2. That is
normal, not a fault.

Rollback to stock is the same command with the v1.13 image, but **requires the
pin short again** — `Fn`+`ESC` disappears the moment you leave QMK.

### Checking USB state

`system_profiler SPUSBDataType` returns **empty** under this agent's sandbox —
use `ioreg` instead. Product IDs are decimal there:

| decimal | hex | meaning |
|---|---|---|
| `3141` | `0x0C45` | vendor (all states) |
| `32778` | `0x800A` | stock v1.10 (gone now) |
| `28992` | `0x7140` | bootloader |
| `32777` | `0x8009` | **QMK — current state** |

`scratchpad/usbwatch.sh` (this session) polls `ioreg` once a second and prints
only on state change, which is far easier than watching a terminal while both
hands are busy with the keyboard. Worth recreating if you need it again.
