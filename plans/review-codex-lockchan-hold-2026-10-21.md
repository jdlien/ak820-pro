# Codex review: the lock-light frame hold (2026-10-21)

The review of `HOLD_IDLE` in `ak820-agent/src/lockchan/sender.rs`, run as
`codex exec -m gpt-6-astra -c model_reasoning_effort=xhigh -s read-only`. The prompt is kept
below the review, and the dispositions follow it.

## The review, verbatim

**I found no must-fix regression and nothing that blocks installing this on the Mac’s daemon.** The ordinary hold/wake path is sound. These are the findings, ranked:

1. **Should-fix — early returns can bypass the new wake delay.** [sender.rs:584](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:584), [sender.rs:691](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:691)  
   If already-open lights become “locks unknown” before 45 seconds, every idle pass returns before setting `held`. When input and known locks return together, `wake_guess` fires, but `held` is false. `force(now + WAKE_DELAY)` cannot postpone an overdue frame, and lock recovery also calls `force(now)`. The old media state can therefore start immediately, before the player reports its change. This preserves an existing wake race; it does **not** strand content. Recording the idle hold before those early returns would cover it.

2. **Should-fix — the first test does not exercise the claimed 60-second title refresh or retention of the held title.** [sender.rs:1679](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1679)  
   Alpha becomes stale at 30 seconds, before its refresh. Bravo also becomes stale during the hold; `set_text(Bravo)` at wake supplies it afresh. The test does verify suppression—including an implicit CLEAR—and the four-second floor, but a regression specific to refreshing a continuously observed title could pass. Keep observations fresh throughout the hold and verify the pending title resumes without supplying it anew at wake.

3. **Nit — the sleep-safety claim is too strong.** [sender.rs:44](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:44)  
   Host idle ≤ board idle does not bound how long the board has been idle. For example, board idle can be 59 seconds while host idle is 44 seconds following trackpad activity: an admitted frame can run across the board’s sleep one second later. **45 seconds is a reasonable cutoff:** with a common last input, 45 + 12 leaves three seconds before Lights out’s 60-second sleep. It is a heuristic, not a guarantee. The snapshot also precedes opening/recovery/warm-up, rather than marking the receiver’s frame start.

4. **Nit — `held` can outlive the content it describes.** [sender.rs:716](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:716), [sender.rs:584](/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:584)  
   After a hold, `input() == None` opens the gate and permits the pending content to send, without clearing `held`. If input sampling later returns with a changed tick, an unrelated pending change inherits the four-second floor. This is a bounded extra delay, not starvation. Also, `.due().is_some()` marks future scheduled work as held, even before its deadline.

The other interactions check out:

- **Resending and ownership:** With valid input samples, the same snapshot arms the wake guess and applies the hold. Even if a wake is missed, removing the gate exposes the existing pending deadline. Revocation, unknown locks and absent lights retain policy work; acquisition or lock recovery supplies another resend reason. Once `held` has established the wake floor, consuming the flag before an early return is safe—the floor persists.
- **`not_before`, force and acquisition:** `set()`, `force()` and `acquired()` cannot defeat the floor. Max-merging correctly preserves whichever is later: handover or wake delay. Old floors become inert after their deadlines; never clearing them does not create an accumulating delay.
- **Repeats, CLEAR and staleness:** The two-second repeat remains owed until a successful send; superseding content replaces it. A held CLEAR can send after `CLEAR_FOR`, including its still-owed change repeat, but does not restart another 180-second retry window. Staleness continues during the hold, correctly replacing unobserved media with CLEAR.
- **Seeking:** Seek checks continue while held and update the baseline/revision. The eventual transport builds its position from the latest observation at pick time, so it does not replay the position from before the hold.

**Clock:** Eligible text still precedes transport, then clock. Holding media removes that competition, so a due clock frame can indeed be more likely to start between 45 and 60 seconds, and can finish after 60. Its existing gate and `woke()` behavior remain unchanged; acquisition occurs before `woke()`, preserving its wake delay. This does not restore the overnight minutely media traffic. In this checkout, Mac `BleLights` still inherits the default unmeasured clock latency, so actual type-4 transmission there remains disabled.

**Windows:** [GetLastInputInfo failure returns `None`](/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/lock_lights.rs:384), so the gate fails open, as on macOS. Ordinary tick-counter rollover is handled by `wrapping_sub`; it does not manufacture a changed last-input tick. A continuous idle exceeding \(2^{32}\) milliseconds—about 49.7 days—does wrap the measured idle and briefly reopen the gate. Neither case permanently suppresses resending.

The second test correctly proves admission at **44 seconds**; together with the first, it checks suppression at **45 seconds**. Its frozen input timestamp does not test crossing the threshold during a frame. The most useful missing cases are a transport-only pause/seek held behind unchanged text, CLEAR held beyond `CLEAR_FOR` and then exhausted, and wake combined with unknown-lock recovery or acquisition/handover.

Static review only; no files changed or tests run. `git diff --check` passed.
## The prompt

```text
Read only files inside /Users/jdlien/code/ak820-pro; do not search or list anything outside it, and there is no AGENTS.md.

Review an uncommitted change to the Rust host daemon's lock-LED channel sender: ak820-agent/src/lockchan/sender.rs (and one doc comment in ak820-agent/src/status.rs). See it with `git diff` in /Users/jdlien/code/ak820-pro.

What it is for. The daemon sends now-playing frames (type 1 text, type 3 transport/play times; type 4 is the clock) to the keyboard over Bluetooth by toggling the lock LEDs. In an overnight soak the board deep-slept while the Mac, unlocked and idle with music playing, kept sending the 60 s title refresh (ak820-agent/src/lockchan/policy.rs REFRESH): each frame cost the board's radio module ~13 mA for 8-11 s, ~1.6 mA on average on top of 3.0 mA asleep (history/mainline-soak-20261020/README.md, plans/BACKLOG.md "Lock-light frames into a sleeping board"). The change holds text and transport frames once the host's input (HIDIdleTime on macOS, GetLastInputInfo on Windows, via Platform::input) has been idle HOLD_IDLE = 45 s, and lets the existing wake guess (IDLE_ARM = 30 s, fires on the first new input) resend them, with a not_before of WAKE_DELAY so an overdue held frame does not go at once under a media key's change still in flight. The clock's own gate (clock.rs IDLE = 60 s) is unchanged.

Facts to check against: the board's power ladder (qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c, `ladders[]`): Lights out sleeps at 60 s idle, Power saver at 3 min, Balanced at 20 min; the board's idle is last_input_activity_elapsed() (keys and the knob), and lock-LED frames do not count as activity. A frame lasts at most LOCKCHAN_LIFETIME_MS = 12 s (lockchan.h). The board expires host text 3 min after the last frame, and a deep sleep's wake expires it too (plans/LOCK-LED-CHANNEL-PLAN.md, the policy section). Host input idleness is never more than the board's, because the board's keys are host input.

Please look for:
1. Correctness of the gate and the `held` flag: any path where held content is never resent once the input returns (the wake guess not armed, not granted, locks unknown, the lights absent, an acquisition in the same pass, the handover's not_before), or where `held` stays set and later delays an unrelated frame.
2. Interaction with Policy::not_before (it is max-merged and never cleared), force, acquired, the 2 s repeat, CLEAR's bounded repeats (CLEAR_FOR), staleness (STALE_AFTER), and seek detection (seeked / sent_pos) across a hold.
3. Interaction with the type-4 clock: precedence, the clock's own IDLE and woke(), and whether a clock frame between 45 and 60 s of idleness is now more likely or matters.
4. Whether 45 s is right given the facts above, and whether a frame begun just before the hold can still run into a sleeping board.
5. Whether the two new tests (nothing_goes_while_the_input_is_idle_and_the_held_change_after_the_wake, the_hold_begins_at_hold_idle_not_before) test what they claim, and what test is missing (for example the transport held, or CLEAR held).
6. Windows: the same sender runs there; anything platform-specific about Platform::input returning None or wrapping.

Report findings ranked by severity (must-fix, should-fix, nit), each with file:line and a concrete failure scenario. Say plainly if you find nothing that blocks installing this on the Mac's daemon.
```

## Dispositions

| # | Finding | Disposition |
|---|---|---|
| 1 | Should-fix: the "locks unknown" early return skips setting `held`, so an unlock with a key sends at once | **Fixed.** The hold is worked out before the early returns, every pass. `locks_unknown_through_the_hold_still_give_its_wake_the_delay` covers it, and it fails with the mark moved back after the returns (mutation-checked). |
| 2 | Should-fix: the first test let Alpha go stale before its refresh and handed Bravo in afresh at the wake | **Fixed.** The test observes afresh in 10 s strides through the hold, past Alpha's 60 s refresh, then wakes with no new observation. Added `a_seek_while_idle_is_held_and_its_transport_goes_after_the_wake` (type 3: held, then picked from the latest observation). Not added: CLEAR held past `CLEAR_FOR`; the policy's CLEAR rules did not change. |
| 3 | Nit: the sleep-safety claim is too strong (the trackpad can make host idle shorter than the board's) | **Accepted.** `HOLD_IDLE`'s comment now calls 45 s a heuristic, with that example. |
| 4 | Nit: `held` can outlive what it describes (input `None`), and it marked future work | **Fixed.** `held` is recomputed every pass, false on any pass not idle (`None` included), and true only for content already due (`<= now`). |
| Clock | A clock frame is likelier between 45 and 60 s, and can finish after 60 | **For Gremlin's session**, which owns type 4: it will move the clock's gate to `HOLD_IDLE` after this commit, with its own test and review. On the Mac, type 4 is still off (no measured latency). |
| Windows | `None` fails open; a 49.7-day idle wraps | **No change.** Both fail open, and neither strands content. |

After the fixes: 536 tests pass (4 new). Three mutants were run: no hold, no
wake floor, and the mark after the early returns. Each fails the tests that
claim it.
