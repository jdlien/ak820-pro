I found two P2 issues and two P3 edge cases. No P1 findings.

1. **P2 — Allowed poll intervals can expire the playback readout.** [radio.rs:171](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:171) waits for 12 seconds, but renewal runs only on media polls. With `--interval 11`, an unchanged playing track renews around 22 seconds, after firmware expiry; previously it renewed every 11 seconds. With interval 5, renewal occurs around 15 seconds, and a failed delivery’s next-poll retry lands after 20 seconds. Schedule renewal independently or constrain/adapt the radio interval.

2. **P2 — A genuine waking input can be ignored indefinitely.** [radio.rs:188](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:188) requires input strictly later than `silent_since + 1s`. A single key received 500 ms after the capped silence never qualifies, even after the 30-second backoff expires: its reconstructed timestamp remains inside that excluded second. An awake keyboard consequently gets no title until another input. Compare input observations across the silence rather than permanently excluding genuine input near its boundary.

3. **P3 — Qualification can cross the hold boundary and still send media.** [radio.rs:344](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:344) checks idle only at tick entry. A tick starting at 179.99 seconds can receive its probe reply 20 ms later and then initiate both text writes and playback after `HOLD_IDLE`. The existing acquisition is also retained until another tick. Recheck the aged idle sample before qualification-dependent media writes if “sends nothing while held” is intended literally.

4. **P3 — A full Windows idle-duration wrap looks like fresh input.** [windows/mod.rs:84](/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/mod.rs:84) correctly handles ordinary `GetTickCount` rollover, but after **49.7 days continuously without input**, the wrapping difference itself returns near zero. That releases the hold and can satisfy the silence gate without input. Preserve the last-input identity across samples. macOS’s full-width nanosecond duration avoids this particular wrap, but arbitrary backward idle jumps are likewise treated as input; the radio has no historical consistency check.

The remaining behavior looks sound:

- `None` deliberately bypasses both idle rules. A readable input ending a hold during backoff does **not** bypass the remaining backoff.
- A board waking independently, or through a local action that produces no host input, receives no title. That is consistent with the requested battery policy—an intentional limitation worth documenting explicitly, rather than restoring periodic probes.
- USB publication and lock-light sender logic remain unchanged. Held radio reports transport `none`, allowing the existing lock-channel grant logic; that sender retains its own idle hold.
- At the default 3-second cadence, ordinary transient renewal failures recover within the 20-second lease. Longer failure backoffs intentionally cannot preserve it.
- Playback renewals do not reset the text keepalive. Unheld text still refreshes every 30 seconds, comfortably inside its 180-second expiry.
- Steady, held and input-waiting states do not log every poll. `held` clears session/qualification; an outstanding backoff temporarily retains its diagnostic state name.

I ran **63 tests successfully using the existing November 9 test binary**, without rebuilding or modifying files. Tests cover the normal hold/resume, silence gating, readout changes/seeks and keepalive behavior. Missing coverage includes the four findings above, hold ending mid-backoff, readable/`None` transitions, and held transport/lock-channel handover.

The renewal tests are particularly incomplete: [radio.rs:763](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:763) retries a receipt-only **non-playing initial readout**, while [radio.rs:776](/Users/jdlien/code/ak820-pro/ak820-agent/src/radio.rs:776) checks constants only. Neither exercises a lost playing renewal and recovery against an actual expiry deadline.

**NOT READY**