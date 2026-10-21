**Yes—d557e13 clears the blocker for installation on gremlin with `--clock --radio --lockchan`, followed by a supervised first day on the reviewed firmware.** Both requested findings are closed. I found no new must-fix or should-fix in this patch; production latency validation remains open.

| Classification | Verdict |
|---|---|
| **Must-fix 1 — Closed** | Rebase uses the frame’s own `(anchor, w0, payload_offset)`, without sampling a newer clock. A change after final validation remains visible to the next `observe()`. The new regression leaves the final check on the old wall clock, then exposes a +60-second step and requires a credited resend carrying the new time. Restoring the old rebase would swallow that step. [sender.rs:1033](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1033), [test:2440](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:2440). |
| **Should-fix 2 — Closed** | `d.min(t).max(earliest)` makes the four-second wake delay a lower bound, including when the existing deadline is just ahead. The separate ownership floor still applies. The added test catches the reported near-refresh case: relative wake at 599, refresh due at 600, new deadline 603. [clock.rs:128](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:128), [test:265](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:265). |
| **Should-fix — Production latency validation remains open** | Retain **+38 ms provisionally**. The CLI shares the writer and late-payload executor, but uses `CliNever`; the daemon adds wall sampling and local conversion during guarded writes. Measure the daemon path before calling the constant validated or adjusting it from these residuals. [windows/lock_lights.rs:341](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/lock_lights.rs:341), [cli.rs:1181](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/cli.rs:1181), [sender.rs:946](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:946). |
| **Note — Bench evidence is narrower than “after each”** | The file records **ten sends but six numeric post-send measurements**; four entries are blank. Those six show board-minus-host offsets of −13.6 to −2.6 ms after 20 seconds. This supports useful accuracy with +38 ms, but does not establish ten measured residuals or the daemon’s latency distribution. [run1.txt:1](C:/Users/jdlien/code/ak820-pro/history/lockchan-clock-bench-20261020/run1.txt:1). |

For the supervised day, watch these:

- **Liveness and ownership:** `updated` keeps advancing; `clock=this daemon`; inspect `board`, `transport`, `radio_qualified`, and `lockchan_granted`. USB or a carrying radio should revoke lockchan. On BT, `transport=none` can coexist correctly with `lockchan_granted=yes`: that transport field describes raw-HID media. [agent.rs:434](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:434), [status.rs:40](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/status.rs:40).

- **Clock cadence:** `lockchan_clock_frames` should advance and `lockchan_clock_last` reset during eligible BT use; `lockchan_clock_off` should be absent on gremlin. Expect roughly ten minutes between ordinary completed frames, idle suppression after 60 seconds, and wake scheduling after four seconds subject to the normal five-minute wake throttle. After this process’s USB clock attempt, allow the **735-second ownership floor**. Media has priority. These are host transmission counts, not board acknowledgments; ordinary `clock_syncs` is separate. [clock.rs:32](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/clock.rs:32), [sender.rs:695](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:695), [status.rs:248](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/status.rs:248).

- **Sender health:** watch deltas in `lockchan_retries`, `lockchan_failures`, and `lockchan_writes`, alongside `lockchan_last_error` and `lockchan_restore_pending`. Occasional retries during lock changes are explainable; persistent restore pending, repeated failures, or `lockchan=poisoned` need investigation. Verify typing, media changes, lock restoration, sleep/wake, and USB/radio handovers. [status.rs:232](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/status.rs:232), [sender.rs:488](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:488).

**Board op 17 sub 8 is the acceptance check.** Record baseline and checkpoint deltas:

| Field | What to watch |
|---|---|
| `applied` | Advances during eligible BT clock transmissions. |
| `refused` | Explainable around ownership transitions; sustained growth after the floor is suspicious. |
| `rejected` | Should remain unchanged for valid daemon payloads. |
| `retried`, `pending`, `dropped` | A retry may recover; pending should clear within the two-second retry window. Drops during wake/link/USB takeover can be expected; repeated steady-state drops are not. |
| `off`, `status` | `off` is **target minus board before correction**, not post-sync residual. Status describes the last successful application: 0 stepped, 1 slewing. Repeated large corrections during steady awake use warrant investigation. |

These counters are u16; account for wrap and reboot. Their layout and semantics are at [ch582f_ajazz.h:107](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.h:107), with retry handling at [lockchan_media.c:150](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/lockchan_media.c:150).

Use sparse board checkpoints: reconnecting USB changes ownership and can restart the floor. Also compare the daemon’s cached `health_stall_ge_25ms_nonflash`, timeout and watchdog counters, checking `health_read_at` for freshness. [status.rs:193](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/status.rs:193).

Validation: I inspected the exact commit/parent Git objects and regression code; independent boundary models passed for wall steps, zone changes, near-future deadlines and ownership floors. Process launch was denied, so **I could not rerun the Rust/C suites**.