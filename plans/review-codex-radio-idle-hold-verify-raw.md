The two P2s are fixed. The mid-tick hold fix is incomplete, and the macOS filter introduces another P3 edge case.

1. **Fixed — P2, playback lease expiry.** [radio.rs:178](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:178) derives renewal timing from the effective cadence; [radio.rs:356](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:356) caps the interval at 3 seconds while a confirmed readout’s lease runs. The loop uses that deadline at [agent.rs:470](/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:470). Lost-renewal tests cover 0.5, 3, 5 and 11 seconds.

2. **Fixed — P2, input shortly after capped silence ignored.** Input changes are latched at [radio.rs:409](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:409), then consumed without bypassing the backoff. The regression test includes the single key 500 ms after silence.

3. **Not fixed completely — P3, crossing the hold mid-tick.** The successful-probe case now releases the session and lock correctly. However, [radio.rs:513](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:513) checks neither between text writes nor after the revocation callback: starting text at idle 179.990 seconds with a 20 ms first reply starts the second write at 180.010. Also, a probe timeout crossing the boundary returns through [radio.rs:480](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:480), retaining the acquisition until another tick. Recheck before each text request and on completed failure paths, preserving poisoned-lock handling.

4. **Fixed — P3, Windows idle wrap mistaken for input.** [input.rs:64](/Users/jdlien/code/ak820-pro/ak820-agent/src/input.rs:64) compares `dwTime` identities and accumulates elapsed ticks while that identity stays unchanged. Ordinary rollover and continuous 50-day idleness are covered.

**New P3 — the macOS plausibility check can discard genuine input across sleep.** [input.rs:72](/Users/jdlien/code/ak820-pro/ak820-agent/src/input.rs:72) compares `HIDIdleTime` against elapsed `Instant` time, although the file’s documented clock model counts sleep only in the former. Example: sample idle 200 seconds; input one second later; sleep for 20 seconds; sample after three seconds of total awake time. Raw idle is 22 seconds, but the filter rejects it and retains 203 seconds. Subsequent consistent readings preserve that false hold until another input. Use compatible elapsed-time clocks or explicitly handle resume, and test input between the last sample and sleep. This is a source-derived counterexample, not a hardware reproduction.

The other interactions check out:

- USB clears the radio lease and returns to the configured cadence.
- `lock_lights_may_carry` is behavior-identical to the previous expression.
- Media-source polling load is unchanged; Windows already caps SMTC polling at 500 ms.
- The clock retains its independent 15-second scheduler.

I attempted `cargo test`; the sandbox blocked Cargo’s build lock before compilation. **53 targeted tests passed using the existing November 9 test binary**, without rebuilding. No files were modified.

**NOT READY**