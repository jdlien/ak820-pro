# Codex verification: the build plan, revision 9 (2026-10-24)

Prompt: [`review-prompt-config-menu-build-plan-rev9.txt`](review-prompt-config-menu-build-plan-rev9.txt). Reviewed: revision 9 (`d440c8f`). Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Revision 9 is not ready for S1’s code.** The lifecycle fix is complete; the measurement contract still has gaps.

I checked revision 9 against `d440c8f`, compared it with `caebe72`, and checked the cited firmware at `4b899118`.

| Accepted disposition | Verification |
|---|---|
| 1. Piece/stop lifecycle | **Met.** C4 fixes the ordering hole in `menu_slots.c`, preserves reached stops and clear progress, documents both releases, and separates operations from pieces. |
| 2. Timing fields and retained maxima | **Partly met.** Operation latency, failure/abandonment semantics and reset/readout are specified. The retained pass measurement excludes required work. |
| 3. Completion and progress | **Partly met.** MENU counters are useful; debug completion still lacks sufficient target identification and composition handling. |
| 4. Numerical LED gate | **Partly met.** Numbers are present, but counter validation and transition coverage need correction. |

The recorded throughput—roughly **357–417 ms per full fixture repaint**—supports a 1,000 ms paced deadline as a reasonable target. It does **not** prove the spin rule unreachable: selection changes repaint two rows, not the full fixture. However, with a new target every 50 ms, “one settled target every 500 ms” implicitly requires some complete selection repaints **within their approximately 50 ms target lifetime**. It is substantially stronger than a 500 ms painting-progress bound. Likewise, the recorded 1 s transition averages do not validate the new 500 ms thresholds. Those remain prospective S1 acceptance targets. [Recorded results](/C:/Users/jdlien/code/ak820-pro/plans/GREMLIN-RESULTS.md:475)

Only the required changes follow.

1. **Must-fix before S1’s code — measure the whole workload covered by the timing gate.**

   **Where:** [C10’s timing fields](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:899), versus [C4’s dashboard/restore requirement](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:636).

   Bytes 10–13 measure passes only while the owner is not DASH or a session exists. Ordinary close and standalone debug exit produce **DASH/NONE while restoration runs**. A 20 ms restore pass therefore escapes these fields and does not increment ge25. The required ≤15 ms gate can pass despite that violation. Ordinary dashboard RAM painting is excluded too.

   **Fix:** Retain the maximum and violation count over an explicitly armed measurement interval covering the entire supported workload, including transition passes, restoration through DONE and required dashboard work. Include layout clears in the clear-band maximum; byte 19 currently names only restore/debug clears. Reconcile “≤15 ms” with the zero **≥15 ms** count: use a **>15,000 µs** violation counter if equality is allowed.

2. **Must-fix before S1’s code — bind debug completion to an actual composed target.**

   **Where:** [C10 `debug_done`](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:913); [debug reset](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1216) and [deferred composition](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:840).

   Page reset initializes both grids to spaces, clears dirty flags and sets `dbg_force_recompose`. Thus “clear finished, no dirty cells, idle, no loss” can describe a blank page **before its first composition**. Also, a boolean cannot distinguish completion of a particular update from an earlier settled state; an entire dirty/clean cycle can occur between reads. Sub 10’s generations and completion counters cover MENU’s `pixels_done`, not Health/Camera updates.

   **Fix:** Require completion of the selected page’s initial/pending composition. Expose the debug page identity and composed/completed generation—or an equivalent retained completion token—so the script can associate each tested update with its completion and deadline. Keep the final-DMA and pending-loss checks.

3. **Must-fix before S1’s code — make counter and sampling validation executable.**

   **Where:** [C10 counter/timebase rules](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:918).

   “A delta … more than twice the host’s elapsed time” needs a named field and units. Applied to ISR entries versus milliseconds, healthy behaviour fails: approximately 1,863 entries in 500 ms exceeds 1,000. Raw uptime going backwards also rejects legitimate u32 wrap, contradicting the preceding rule. Conversely, [`health_reset()`](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/health.c:178) resets counters without resetting uptime.

   Finally, 25 ms is not an established HID uncertainty bound: the existing [health transaction](/C:/Users/jdlien/code/ak820-pro/hostagent/ak820health.py:148) permits a 500 ms response wait.

   **Fix:** Specify field-specific modular arithmetic and plausibility bounds; apply elapsed-time comparisons only to time-valued quantities. Define reset detection independently of ordinary wrap, with observable reset/boot identity where necessary. Bound sampling intervals so u8 deltas cannot conceal complete wraps. Timestamp request/reply brackets and enforce the uncertainty budget supporting the fixed 25 ms allowance.

4. **Must-fix before S1’s code — reconcile transition thresholds and cover the complete transition.**

   **Where:** [C10 LED/transition/deadline rules](/C:/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:925).

   “Each activity window ≥0.98” makes the transition-specific ≥0.95 allowance ineffective unless transitions are explicitly exempted. Also, a single 500 ms window cannot guarantee coverage “through DONE” when settlement is allowed to take 1,000 ms: work after the window can escape the transition gate.

   **Fix:** Explicitly separate sustained-activity and transition acceptance rules. Measure successive bounded windows through observed completion, or choose another fully specified rule covering that entire interval. Define the averaging group per transition kind. Preserve failure on every settlement timeout.

This was static verification; no files changed, builds ran or board measurements were taken.
---

## Dispositions (Warren, 10-24): all four accepted, C10 rewritten as revision 10

1. **The whole workload's timing: accepted.**
   - **The interval:** sub 10's `arm` 1 starts an interval in which every
     pass counts, under any owner, the restore through DONE after a close
     and the dashboard's own work included.
   - **The violation count** is over 15,000 µs, so 15 ms itself is allowed.
   - **Byte 19** covers the layout's clear bands too.
2. **Debug completion bound to a composition: accepted.** Sub 10 exposes
   the page (byte 20), `dbg_gen` (21), which moves only when a composition
   makes a different target, the first after a page reset included, and
   `dbg_done_gen` (22). `debug_done` requires a composition since entry and
   the generations equal. Scripts tie an update to its completion by
   generation, never by the boolean alone.
3. **Executable counter checks: accepted.** C10 now has per-field rules:
   - `uptime_ms` is the only quantity compared with host time;
   - the ISR rate has to lie in 1,000 to 10,000 a second;
   - ge deltas can't exceed passes, nor passes 500 a second;
   - modular deltas per width;
   - `boot_id` (sub 10, bytes 26-27) tells a reboot from a wrap, and a
     health reset shows as a delta beyond its bound;
   - every read is bracketed, with a bracket over 25 ms retried three times
     and then failing the run, the tolerance built from the actual
     brackets;
   - u8 counters are read every 100 ms, so none can wrap unseen.
4. **Transitions apart: accepted.** The sustained rule (at least 0.98 per
   5 s window) and the transition rule are now separate. A transition is
   measured in successive 500 ms windows until its observed completion,
   plus one more window. Each window must be at least 0.95, and the mean
   per kind over its ten repeats at least 0.98. Completion within 1,000 ms
   stays, and every timeout fails.

**The note on the spin rule, also taken:** progress during a burst is now
the committed-slot count (byte 23) rising in every 500 ms. Settled whole
targets live ~50 ms each, so "one settled every 500 ms" asked more than
intended. Final settlement within 500 ms and the books still apply.
