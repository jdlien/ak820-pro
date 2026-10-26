# Codex's review of the encoder drain (S1), 2026-10-24

Prompt: [`review-prompt-s1-encoder.txt`](review-prompt-s1-encoder.txt). Reviewed:
qmk_firmware-ak820pro `gremlin/s1` commit `98147f0a`. Model `gpt-6-astra`,
reasoning xhigh, read-only.

## Dispositions (Warren)

- **1, the bound per call, not per task (split boards):** resolved by
  removing the bound (`cbcf93b6`).
- **2, a retained backlog and the split transport's drain ack:** resolved
  by the same removal; the drain is upstream's again.
- **3, no multi-detent backlog on this board:** accepted. The quadrature
  driver is polled once a pass and one sample enqueues at most one detent,
  so the bound was inert here. Removed rather than kept as documentation of
  a case that can't happen; what stays is the skipped waits for swallowed
  halves, the change that can help. The comments that blamed a backlog are
  gone with it. The point that zero menu drops can't prove no quadrature
  transitions were missed between samples goes to the backlog (a 15 ms
  pass samples the knob at ~67 Hz).
- **4, validate the limit:** moot after the removal.
- **Before flashing, a current daily build:** done on `cbcf93b6`,
  `via-daily-cbcf93b6-20261024-153641.bin`, heap gap 2,360 B; dev
  `via-dev-cbcf93b6-20261024-153809.bin`, token `0xde3d5c12`, gap 248 B.
- **After flashing, repeat the physical spin** before claiming the gate:
  planned (one action for JD).

## The review, verbatim

**I found no code defect that must be fixed before a test flash on this AK820 Pro.** There are two real split-board issues, plus documentation/configuration follow-ups. **Build clearance remains outstanding:** I could not execute `build.sh daily` because process creation is denied here. The archived daily build is `a8b98bc0`, not this commit.

I verified the exact commit and parent through Git’s stored objects, and confirmed the reviewed source files match `98147f0a`. All reads stayed inside the requested directory.

1. **[P2, can wait for this board] The bound is per drain call, not per task.**  
   [quantum/encoder.c:54](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/encoder.c:54)

   `delayed` starts at zero inside `encoder_handle_queue()`. A split master calls that function at both lines 98 and 112.

   Failing sequence: queue two paced detents, configure the limit as one, call `encoder_task()`. The first drain processes one; the second processes the other with a fresh budget. One task spends four waits.

   Fix before enabling this on a split board: initialize the budget in `encoder_task()` and share it across both drains. The AK820 Pro takes only the second call.

2. **[P2, can wait for this board] Retained master backlog exposes event loss in split transport.**  
   [quantum/split_common/transactions.c:249](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/split_common/transactions.c:249)

   The receiver attempts to enqueue the slave’s events, but still sends `CMD_ENCODER_DRAIN` when an enqueue fails after processing has begun.

   Concrete sequence with the default four-slot ring, usable capacity three:

   - Receive three slave detents; the two bounded drains process two, leaving one.
   - Before the next master pass, the slave accumulates another three.
   - Only two fit in the master’s remaining space. Enqueueing the third fails.
   - `actioned` is already true, so the slave receives a drain acknowledgment and discards its queue—including the untransferred event.

   Previously, draining the master completely made room for that next batch. Fix before split adoption with capacity-safe transfer/acknowledgment handling; simply retrying a partially transferred batch would also need duplicate protection. Macro-unset builds retain their existing behavior.

3. **[P3, can wait] The backlog explanation does not describe this board’s real producer.**  
   [config.h:394](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/config.h:394), [encoder_quadrature.c:215](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/encoder/encoder_quadrature.c:215)

   This board has one encoder, resolution two, polled once by `encoder_driver_task()` per pass. I found no interrupt producer or override. One sample can enqueue at most one detent.

   Starting empty, each pass therefore produces at most one event and consumes it. **Ordinary physical spinning cannot build the described multi-detent backlog**, either before or after this patch. The new cap is inert on that path; skipping the menu’s two waits is the change that can help the observed overruns.

   Describe backlog handling as an injected/future-producer case, not an established explanation for the 15.6 ms pass. Also, zero menu-input drops does not prove that quadrature transitions were never missed between samples.

4. **[P3, can wait] Validate the configured limit.**  
   [quantum/encoder.c:34](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/encoder.c:34)

   With positive key delay, a limit of zero prevents **all** dequeuing, including unpaced events. Values above 255 cannot be represented by `delayed`, defeating the intended bound through wraparound or producing compiler diagnostics. Reject values outside `1..255`; keep “unset means unbounded.” The board’s value of one is fine.

The remaining requested paths check out as follows:

- **Flag lifetime and early exits:** [menu_glue.c:74](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:74) writes the flag for the recognized encoder half; the immediately following delay hook reads and clears it. A forwarded recognized half explicitly writes false. A half bypassing the menu inherits false from the previous hook invocation. Matrix events cannot set it.

  [action.c:133](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/action.c:133) bypasses preprocessing only for `TICK_EVENT`; generated encoder events remain encoder events even when their timestamp wraps to zero. The earlier short-circuit handler is `pre_process_record_modules()`; combos come **after** the keyboard hook. An early module rejection therefore keeps the wait. Swap hands changes the encoder index, preserves its event type, and does not bypass preprocessing; an unrecognized index also keeps the wait. I found no reachable stale-true sequence in this firmware.

- **Tap-hold buffering:** Yes, a forwarded encoder half can enter the tapping buffer. [action_tapping.c:148](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/action_tapping.c:148) can later process several buffered records together. The flag still describes the original half’s menu verdict, and its wait is retained. Those waits already occurred at submission time upstream; they never guaranteed spacing between reports emitted during later buffer replay. Captured halves never enter tapping. Previously forwarded buffered halves can still reach the host after the menu opens—existing behavior, not a new leak.

- **Bound and activity accounting:** The left operand of `&&` checks the budget before dequeuing, so hitting the bound loses no event. Remaining entries and counters stay intact. Both halves finish before incrementing the budget, including when only one half waited. Any processed detent sets `changed`, and [keyboard.c:742](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/keyboard.c:742) refreshes encoder/input activity even for captured input. `encoder_signal_queue_drain()` remains an intentional discard used by split acknowledgment; there is no board caller.

- **Sleep:** [sleep.c:218](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:218) checks sampled pin state, **not queue emptiness**. Nevertheless, normal sleep is protected: draining a retained detent refreshes activity before `power_sleep_wanted()` checks idle time, and OPEN/PENDING sessions block sleep. Ordinary input cannot leave a backlog on this board anyway. A deliberately injected backlog could survive into the dev forced-sleep path, which bypasses idle eligibility; queued events would resume after wake. Add an explicit queue-empty blocker if that becomes a supported bench scenario or an interrupt producer is introduced.

- **Overflow and choosing one versus more:** The ring holds **31**, not 32, events. A genuinely asynchronous producer could overflow it: at a total 15 ms/pass, one paced event/pass serves about 66.7 events/s. But that producer does not exist here. Raising the bound would not recover transitions missed between polls, and has no demonstrated benefit for this board. Keep one.

- **Modified consumer reports:** The implementation now lives in [consumer_mod.c:34](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/consumer_mod.c:34). Forwarded halves retain both 1 ms waits. A new modifier set still receives the 8 ms ordering gap; subsequent detents reuse the held modifiers, and releases refresh the 150 ms idle threshold. A hypothetical backlog gains inter-detent separation and a later final modifier release, but preserves ordering. This cap does **not** bound time spent inside `action_exec()`, including that initial 8 ms gap.

- **Opener with queued input:** Matrix processing precedes encoder processing. Once Fn+knob opens the session, remaining undequeued detents are judged under its current state: OPEN captures/coalesces them; PENDING consumes them without buffering. [menu_input.c:95](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_input.c:95) preserves each press’s release disposition. No half-detent gets stranded, and already-forwarded tapping records retain their original disposition.

- **Build combinations:** By inspection, the weak default preserves waits, an unset macro preserves full draining, zero key delay removes both delay accounting and bounding, and map-disabled builds retain `encoder_update_kb()`. The prototype/definition guards agree. I found no new unused-variable problem in these configurations, but this is source inspection, not compiler verification.

**Before flashing:** obtain a successful current-source daily build and the intended test build. No board-specific code correction is required by this review. After flashing, repeat the physical-spin measurement before claiming the 15 ms gate passes. Any claimed backlog coverage needs actual encoder-queue injection; op 27’s synthetic menu turns bypass this drain.