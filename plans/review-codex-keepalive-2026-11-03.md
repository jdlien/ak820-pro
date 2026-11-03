# Codex: the BT keep-alive (2026-11-03)

The review of `gremlin/keepalive` (`qmk_firmware-ak820pro`), on `cfe6c2d3a57`
(v0.3.1's base): `6cbbb8df653`, the keep-alive in `sleep.c` and `sleep.h`,
then `3b04a983a24`, the fixes for this review. Codex (Astra, xhigh,
read-only), with the prompts in
[`review-prompt-keepalive.txt`](review-prompt-keepalive.txt) and
[`review-prompt-keepalive-verify.txt`](review-prompt-keepalive-verify.txt);
the raw reviews are [`review-codex-keepalive-raw.md`](review-codex-keepalive-raw.md)
and [`review-codex-keepalive-verify-raw.md`](review-codex-keepalive-verify-raw.md).

**What it is for:** the CH582F ends a BLE link 30 min after the last
traffic it hears from either side (docs/wireless.md, "The module ends the
link 30 min after the last thing it hears"), and a deep-sleeping board sends
none, so the key that wakes it after a longer sleep is lost while the link
comes back (2.4 s to the Mac's keyboard device). JD chose a keep-alive over
the ~1.5 s hold (11-03): a ladder sleep with a BT link up wakes after ~25
real minutes, its usual recovery sends the battery poll as the traffic, and
the ladder sleeps again; only for 18 h asleep since the last input, so "it
would survive a typical evening after leaving work and coming back in the
morning" and a weekend away lets the link go. The cap is in counted
seconds, which run slow asleep, so each PCF-timed sleep measures the rate
for the next. White's logger put the held link at ~0.14 mA asleep (six
drops, 11-03); each wake is ~3 s awake and dark. `ak820 sleep` names the
wake reason 7 "keep-alive" (`ak820-agent/src/sleepdiag.rs`).

Verdict on `3b04a983a24`: no P1; approved for black's dev build over
Windows. The builds: dev token `0xf7ddd286` (heap gap 136 B, floor 128),
daily gap 2272 B.

## Dispositions

1. **P2, a same-millisecond trigger kept the absence.** The reset compared
   `last_input_activity_elapsed()` with the time since the wake, strictly,
   and `recovery_begin()`'s knob trigger often lands in the wake's own
   millisecond, so a knob wake with no decoded detent kept the old absence
   and could end the keep-alives early. Fixed (`3b04a983a24`):
   `recovery_begin()` notes `last_input_activity_time()` before its
   triggers, and any change since is input, with no 64-bit divides. The
   verify: fixed; boot and input-free charge or stray wakes cause no false
   reset.
2. **P3, the "use left" notice lost on a return inside a keep-alive's
   recovery.** That wake skipped the notice and the next sleep's reset
   forgot the absence. Fixed: such a wake owes the notice, given at the
   first input before the board sleeps again (`sleep_task`, a flag test).
   The verify: fixed; it clears before delivery and cannot re-arm.
3. **Note, the 18 h stretches to ~20.4 h if PCF reads fail** (the counted
   fallback at 872 per mille). Taken.
4. **Note, the ~3.1 s USB step stays.** A cable-out board and a suspended
   host look alike (`sleep.c`'s USB watch), so skipping the re-attach at a
   keep-alive needs its own validation. Taken: a follow-up after the bench's
   M3 measures the real per-wake cost.
5. **Note, the poll is module-side traffic.** The recovery queues `A6 53
   F9` and gets the ACK and `5C` back; that this restarts the module's 30
   min is the hardware premise, for white's with-run (no reason-719 drop over
   2+ h of keep-alive sleeps).
6. **P3 (the verify), bench only: an armed sleep after input skips the
   reset.** The dev bench's arm (HC_DEVHOOK op 14) sleeps without
   `ka_cap()`, and its wake replaces the snapshot, so input before an armed
   sleep does not start the absence over. Taken: the keep-alive applies to
   the ladder's own sleeps, and the with-run uses those; an arm after input
   can shorten the keep-alives that follow it until the next input.
