1. **Fixed — P3, mid-tick hold recheck.** [radio.rs:538](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:538) checks before each text line, after revocation; [radio.rs:557](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:557) checks before the readout. Failed probe, text and readout paths use [radio.rs:404](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:404), releasing the acquisition when the failure crosses the hold.

2. **Fixed — P3, macOS input rejected across sleep.** [input.rs:78](/Users/jdlien/code/ak820-pro/ak820-agent/src/input.rs:78) accepts the previously rejected fall. Tests cover genuine input before sleep and sleep without input, with either HID sleep-counting behavior.

**No new P1/P2/P3 findings from these fixes.** In particular:

- Poisoning happens before the hold recheck, which is skipped when poisoned. The guard remains deliberately retained and the state stays abandoned.
- A hold between lines returns before [radio.rs:549](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:549) commits the publisher. Release resets the qualification generation; the next session forces a complete text refresh.

84 tests passed using the existing November 9 test binary, including the new regressions. No rebuild; no files modified.

**READY**