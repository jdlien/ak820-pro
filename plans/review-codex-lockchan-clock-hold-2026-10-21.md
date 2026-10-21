**Yes—HEAD `aa2a4be` is suitable for installation on gremlin after JD’s morning cable-out test passes, retaining the previously approved supervised-day conditions.** I found no must-fix or new should-fix regression.

- **Wake and scheduler paths check out.** The same input snapshot arms the guess at 30 s and holds admission at ≥45 s. Acquisition precedes `clock.woke()`, which independently moves an overdue clock to wake +4 s; it does not depend on `self.held`. Acquisition, refresh, offset/wall-step corrections, `again()` and `RETRY` all pass through the shared gate. Holding hides eligibility without consuming the pending deadline, and the ownership floor remains effective. [sender.rs:567](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:567), [sender.rs:623](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:623), [sender.rs:728](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:728), [clock.rs:114](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:114).

- **Note — the four-second delay has an existing exception.** `observe()` runs after `woke()`. A wall step or offset change detected on the wake pass—or during its delay—sets `due = now`, potentially admitting the clock before wake +4 s. A change already observed *during the hold* is fine: its overdue deadline receives the wake delay. This exception predates HEAD; the new gate neither introduces nor fixes it. [sender.rs:637](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:637), [clock.rs:140](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:140).

- **Note — `"held"` remains a media status.** A clock-only hold with neither media policy due leaves `self.held = false` and reports `"idle"`. That affects observability, not delivery: the sender continues ticking and clock wake scheduling still runs. Keep the media wake-floor flag separate; broaden only the status calculation if `"held"` should describe clock-only suppression. [sender.rs:659](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:659), [sender.rs:735](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:735).

- **Note — the new test bites, but is not an exact boundary/wake test.** At 50 s idle, restoring the 60 s gate or removing it lets the overdue refresh complete and breaks the first assertion. The second assertion rejects permanent suppression. However, it admits at **40 s**, and keeps the same last-input tick, so no wake fires. Exact 45 s admission boundaries and a real wake from 45–60 s remain useful additions; the existing 61 s test covers the ordinary wake path. [sender.rs:2381](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:2381), [sender.rs:2361](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:2361).

- **Note — soften the new sleep-safety comment.** “Ends before Lights out’s sleep” is stronger than warranted. With a common last input, 45 +12 leaves three seconds; trackpad activity and delays after the input snapshot can defeat that margin. The existing `HOLD_IDLE` documentation correctly calls it a heuristic. [sender.rs:726](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:726), [sender.rs:44](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:44).

The prior **should-fix production latency validation** remains open; +38 ms is still provisional. [windows/lock_lights.rs:341](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/lock_lights.rs:341).

Validation: inspected exact HEAD/parent Git objects and matching source; independent admission/scheduler models passed. Process launch was denied, so I could not run `git show` or rerun the Rust tests/mutants. No files changed.
---

## Dispositions (gremlin session, 10-21)

Verdict: no must-fix, no new should-fix; installable on gremlin after JD's morning cable-out test.

- **Note: the four-second delay's exception (observe after woke).** Predates aa2a4be, as the review says: an offset change or wall step seen on the wake pass sends at once. Left. That is the immediate send the step rule wants, and it is rare.
- **Note: "held" is a media status.** Left. Delivery is unaffected; `lockchan_clock_last` shows clock suppression.
- **Note: the test is not an exact boundary or wake test.** Taken: the test now holds at exactly HOLD_IDLE and sends 1 ms short of it, and a new test, `a_clock_held_at_fifty_seconds_goes_at_the_wake`, wakes from 50 s idle and checks WAKE_DELAY. Mutation-checked: `>=` changed to `>` in `idle_for` fails it, as do the 60 s gate and no gate.
- **Note: soften the comment.** Taken: it now says "likely" and calls the margin a heuristic, as HOLD_IDLE's doc does.
- **Open from earlier:** the +38 ms production latency validation, unchanged.
