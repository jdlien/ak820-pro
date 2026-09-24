# Wireless: the CH582F module, Bluetooth, and 2.4G

Everything about the BT/2.4G link. Driver: `bluetooth/ch582f_ajazz.c`; UI in
`bt_ui.c`. Protocol reference: `ajazz-ak820-pro/docs/CH582F_PROTOCOL.md` — but
note the disassembly it derives from has been wrong before (`0xA1` is
keystrokes, not "channel connect"; `5C` is battery percent, not brightness).

## Basics

- The CH582F handles BT **and** 2.4G over one UART (UART2). QMK's
  `CONNECTION_HOST_2P4GHZ` is not wired, so both wireless slider positions map
  to `CONNECTION_HOST_BLUETOOTH`; our own `A6` profile-select tells the module
  which radio to use.
- **The protocol is live only in BT/2.4G mode; in USB mode the CH582F is
  bypassed entirely.** So the `Fn`+`Q/W/E/R` keys are inert in wired mode, and
  the module's reported state is stale there (the panel deliberately shows
  nothing).
- **Raw-HID replies return over USB in ANY slider position** — the cable
  just has to be connected. QMK's default routes replies through the active
  host driver, and the BT driver's `send_raw_hid` is a weak NO-OP, so they
  used to be silently discarded in BT/2.4G ("no reply" with the cable in,
  measured 2026-08-28). Fixed by overriding `bluetooth_send_raw_hid()` to
  send over USB (`ch582f_ajazz.c`, commit 4b86d95014, 2026-08-29; round-trips
  re-verified in the BT position 2026-09-01 — see
  `history/clock-sync/phase-0-facts.md` F1). So `ak820ctl`, VIA and
  `ak820keymap.py` work in any mode; only an unplugged cable (no HID
  interface) blocks them. Ignore older "wired mode required" notes.
- **UART2 must be the highest interrupt priority** — it is the only peripheral
  where being late loses data. The full priority table and the two bugs the
  inverted default caused are in [leds.md](leds.md). **If BT throughput ever
  regresses, check that table FIRST**, not the ISR rate.
- The slider is also a **power-source switch** — most flips brown-out the MCU.
  See [hardware.md](hardware.md) before reasoning about state across a flip.

## Slot selection, pairing UX

`Fn`+`Q/W/E` = BT slots 1-3, `Fn`+`R` = dongle. Tap = select the slot
(`A6 <slot>`, reconnects the bond); hold past `BT_PAIR_HOLD_MS` (**2 s**,
`bt_ui.c`) = enter pairing on that slot. A `Pair: ======` progress bar fills
during the hold; pairing fires **under the finger** from `bt_pair_hold_task()`
on the 10 Hz tick (it used to fire on key-up, which read as "holding does
nothing").

- **2 s, not 1 s**: a slot press also issues a select/reconnect, so a slow tap
  at 1 s would drop a live link and start advertising. Reconnecting is the
  common gesture; pairing is rare and deliberate.
- **Expect ~200 ms more than the constant by stopwatch** — 10 Hz tick
  granularity, not slack. Do not "correct" the constant for it.
- The pair hint outranks every link state in the status band — on an
  unreachable slot the underlying state is `REJECTED`, and without the
  override the panel said `Link failed` mid-gesture.
- **The last-selected BT slot is persisted** (kb_eeconfig, coalesced ~5 s
  deferred flush) and re-selected at boot / on re-entering BT mode. Verified
  on hardware 2026-09-01.

`Fn`+`P` (`BT_PAIR`) is **unbound by default** (2026-08-29): in BT it is
strictly worse than holding a slot key, and in 2.4G it drops a working dongle
link into a pairing broadcast that a button-less receiver can't answer.
The keycode stays in the enum and `via.json` (index-matched — append only);
rebind in VIA if wanted. Recovering from an accidental 2.4G trigger: slide to
`bt`, then back to `2.4G` — sliding directly back is declined (see below).

## ⚠️ `A6 <slot>` is DECLINED while the module is advertising

Symptom: pair, enter pairing again, then try to go back — it will not
reconnect until you switch to a different slot and back. Captured on the wire
2026-08-29: the module answers a same-slot select with `5B 23` (idle) and
never starts connecting. **Four hypotheses died here; do not re-derive:**

| # | Hypothesis | Killed by |
|---|---|---|
| 1 | Lost UART frame | The module *replies* — with `5B 23`. |
| 2 | Timing; retry until it takes | 8 selects over 10 s drew ZERO responses. |
| 3 | Retry when it goes idle (`5B 23`) | It emits nothing at all while advertising. |
| 4 | **A DIFFERENT slot is required** | Matches every trace; the manual `Fn`+`Q` workaround works. |

The advertising window lasts **minutes**. Naming a *different* slot forces a
state change immediately. (An earlier trace looked like timing — recovery at
+9 s — but that recovery was an `A6 33`, a different slot. Reading it as
timing cost two failed fixes.)

**Fix — the cancel-pairing bounce**: pressing a slot key while THAT slot is
advertising sends a different slot, waits `CH582_BOUNCE_MS` (700 ms), then the
real target. Verified ~1 s recovery. **The bounce slot can briefly CONNECT**
(~700 ms) — unavoidable, same exposure as the manual workaround. Scoped to BT
slots only; 2.4G still needs the manual two-step.

## ⚠️ `A6 51` (pair) is ignored while a connect attempt is in flight

The real cause of "hold 1 s: nothing... 3 s: works" — it was never a timing
threshold. A slot press starts a connect (`5B 33/34`); a hold-to-pair fires
into that window and the single `A6 51` is silently dropped. Only after the
attempt is abandoned (`5B 36`) is the module listening.

**Fix:** pairing is confirmed by `5B 31`, not by having sent `A6 51`. The
pair request resends every `CH582_PAIR_RETRY_MS` (400 ms) up to ~4.8 s, and
clears on `5B 31` / `5B 32` / supersession. `conn_state` still goes to
`PAIRING` optimistically on first send so the band reacts immediately.

Lesson recorded because it defeated instrumentation: a one-shot capture caught
the module in the abandoned state, so the pair landed first try and "confirmed"
the 1 s threshold. **A single measurement of state-dependent behaviour only
confirms the state it caught.**

## The pending-action machinery (2026-09-01 refactor)

Bounce, select-retry and pair-retry are one `pending_action` struct
(`{kind: PA_NONE/BOUNCE/SELECT/PAIR, target, last_send, tries}`) in
`ch582f_ajazz.c`. Rules that were bugs once:

- **PA_BOUNCE must survive `5B 31`/`32`** — clearing it on those frames
  strands the user on the bounce slot.
- The select backstop **must stop the moment `5B 33`/`34` arrives**:
  re-selecting a module that is already attempting restarts advertising and
  starves a slow reconnect (macOS directed advertising takes longer than a
  phone's <500 ms). Do not widen the retry condition.
- The cold-boot retry is separate, gated `connect_requested && !module_alive`.

**TX coalescing**: when the TX ring is nearly full (used ≥ LEN-4), a new
`A1`/`A3` frame overwrites the **last** queued frame of the same type instead
of dropping — newest state supersedes. Never `A6` (commands), and never the
first match (which would deliver older state after newer). Normal typing never
engages it; `tx_drops` in the health counters stays 0.

## `5B 36` — attempt abandoned (absent from the protocol doc)

Follows failed connect attempts, then **persists**; the trailing `5B 23` is
deliberately ignored, so `REJECTED` sticks until something changes state. It
means "the attempt failed", NOT "not paired" — a bonded host that is powered
off looks identical, which is why the panel says `Link failed`, not
`Refused`/`Not paired`. The slot digit is NOT blanked in this state (it shows
on a lazy 2 s pulse) — hiding it discards real information and made a failed
connect look like a display bug.

## The stuck-LINKING digit, and the `5A` promotion

`5B 32` is **the only "connected" signal**, sent once at link-up. One missed
frame strands the driver in `LINKING` (digit slow-blinks ~700 ms; fast
~200 ms = `PAIRING`) while the link is actually live. Worse, it used to
silently kill media keys: `bluetooth_send_consumer()` was gated on
`is_module_connected` while typing (`0xA1`) was not — half the input path dead,
half fine. The gate is now `connect_requested` only, matching typing.

**Fix:** promote `LINKING` → `CONNECTED` on a `5A` host-LED frame (hosts only
send LED state to connected devices), gated three ways: plausibility mask
`(d & ~0x1F) == 0`; state exactly `LINKING`; and ≥ `CH582_5A_PROMOTE_MS` (3 s)
in `LINKING` — a genuine `5B 32` would have won by then. The promoting frame
does NOT apply its LED bits (that is the forged-frame failure the original 5A
guard exists to prevent). Known gap: does not recover a stuck `PAIRING`.

**There is no way to ASK the module its state — checked, do not re-derive.**
`0xA5` is inert; `5C` battery must never be treated as a connection signal
(protocol doc, in bold); a dropped `5B 32` and a failed link produce
byte-identical traffic forever after.

**Most likely root cause of missed frames was the interrupt priority
inversion** (fixed 2026-08-29, see [leds.md](leds.md)); the promotion is the
backstop.

## Caps Lock LED over Bluetooth

Flaky in BT, reliable wired — same host-driver indirection. In BT,
`host_keyboard_leds()` comes from the CH582F's `5A` frames, gated on link
state, so a wrong link state silently drops LED updates. Also **not a bug**:
macOS tracks Caps per HID device, so the laptop's Caps LED and the AK820's
never sync; capitalisation is global, indicators are per-device.

## Host switch: clear the outgoing host's report first

`bt_ui_mode_slider()` calls `clear_keyboard()` before routing flips (analysis
credit: Rachel). QMK's `handle_host_changed()` never clears report state, so a
key held across the slide would in principle press on one route and release on
the other. **Tested on hardware 2026-09-01: the stuck key did NOT reproduce on
macOS** — but the saving mechanism is unidentified, so the explicit clear
stays. It MUST run in the slider handler, not
`connection_host_changed_kb()` — by then `desired_host` has already flipped
and the clear would zero-report the NEW host, stranding the old one.

## The advertising name

`AK820 5.1-<slot>` is the module's own stored prefix + slot; "5.1" is
BT-version marketing. `0xA9` (set name) exists but this port never sends it,
its framing is unverified on the wire, and module storage cannot be read back.
Capture what stock firmware sends before ever attempting a rename. The pairing
overlay shows the exact advertised string on purpose — it is what to look for
in the phone's list.

## The 50% `tx_timeouts` rate is a mistuned deadline, not a broken link

`ak820health.py` shows roughly half of all module frames timing out — 352 of 711
at one reading. It looks alarming and is not, but the reason is worth writing
down because two of the numbers involved are easy to misread.

**Measured 2026-09-03, wired mode, over 60 s:** `tx_sent` +12, `tx_timeouts` +6,
`tx_drops` **+0**.

- **12 frames per minute is exactly the 5-second battery poll** (`A6 53`,
  `CH582_BATTERY_POLL_MS`). In wired mode that is the *only* thing on the link:
  QMK's `host.c` routes reports to `bt_driver` only while Bluetooth is the active
  connection host, so keystrokes never reach `ch582_send_keyboard_report()`. Do
  not read `tx_sent` as keystroke traffic.
- **`tx_drops` is 0, so nothing is ever lost.** A frame is only dropped after
  `CH582_TX_MAX_RETRIES` (8) consecutive timeouts. Every frame is ACKed; about
  half need one 10 ms retransmit first.
- **`tx_*` are SINCE BOOT.** `health_reset()` cannot clear them — they live in
  the CH582 driver behind `ch582_tx_stats()` with no reset hook. Comparing them
  against freshly-reset counters like `consumes` or `key_presses` gives nonsense
  ratios. (Done once, in this session, before it was noticed.)

So in wired mode the entire cost of the 50% is that a battery poll is sometimes
10 ms late, and nothing is waiting on it.

**It would matter over Bluetooth**, where every keystroke is a frame and the
code comment at `ch582_tx_pump()` already warns that ACK loss shows up as
throughput collapse — you can out-type the link — rather than as mild latency.
The 24-deep queue and newest-supersedes coalescing absorb a lot, but a 10 ms
stall on half of ~10 frames/s at speed is real.

**Measured 2026-09-23 (instrumented builds, wired mode, ~2,200 ACKs over three
hours): the module's turnaround is BIMODAL**, and the 10 ms deadline sits
between the two modes.

| ACK after first send | 3–7 ms | 8–14 ms | 15 ms and over |
|---|---|---|---|
| share | ~47% | ~6% | **~47%** (worst 36 ms) |

The slow half is the module itself: the share was the same before and after
the serial driver's lock fix (ChibiOS `a3fdffe26d`). The likeliest reading is
wake-up latency, since in wired mode it hears from us only every 5 s. It is
not established. The instrumented build prints the histogram once a minute
(`[ch582] ack ms:` then 16 one-millisecond buckets, the last holding
everything at 15 ms or more; then the worst case, retransmitted frames, and
orphans). It is measured at parse time, so it is an upper bound.

**Do not raise `CH582_TX_ACK_TIMEOUT_MS` from wired-mode data.** Over
Bluetooth the module is kept busy by keystrokes and may never be in its slow
mode, and a longer deadline slows recovery from a genuinely lost frame.
Measure the same histogram in Bluetooth mode first. Until then a slow ACK
costs one harmless retransmit: frames carry state, so a repeat is idempotent.

**Fixed 2026-09-23: the TX pump ran BEFORE the RX drain** in `ch582_task()`,
so an ACK already sitting in the input queue could not stop a needless
retransmit. That retransmit's own ACK then arrived with nothing in flight
(an orphan) or, worse, popped the NEXT frame: `61 0D 0A` carries no sequence
number. With the pump after the drain, orphans fell from 23 in 24 minutes to
**1 in 3 hours**.

### `61 0D 0A`: an ACK, not a heartbeat (evidence 2026-09-23; one comment still disagrees)

`ch582_task()`'s header comment calls it a *"periodic IDLE HEARTBEAT ... emitted
while connected too"*. The parser 130 lines below calls it *"the per-frame ACK
the module returns for what we send ... silent at idle"* — and treats it as the
ACK that releases the in-flight frame.

Both cannot be true. If it were also periodic, a heartbeat could release a
frame the module never acknowledged. **The 2026-09-23 measurement favours the
ACK reading:** with the pump reordered, an ACK arriving with nothing in flight
happened once in three hours (about 2,200 frames). A periodic heartbeat would
make orphans steadily. That is wired mode, observed at parse time; a logic
analyzer at idle would still settle it outright. Until then, treat the
header comment's "heartbeat" as the suspect one.
