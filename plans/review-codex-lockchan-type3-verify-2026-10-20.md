**No new must-fix blocker for supervised testing. Three original findings are fixed; the seek finding is only partially closed. I would still withhold routine-use clearance on gremlin.**

Reviewed `256bb6a` and `d77e2d6` against `5813827`. During review, main advanced to `1e8ff94` with the wake-delay change; it does not alter these findings. Links below use that checkout’s line numbers. **This was static verification:** process launching was denied, so I could not execute the Rust tests or mutation tests.

| Original should-fix | Verdict |
|---|---|
| Recheck transport eligibility at pick | **Fixed.** The pick updates text identity and rejects transport unless the current now-playing text is the successfully sent generation. [sender.rs:695](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:695) |
| Position’s as-of instant | **Fixed for the reported defects.** macOS uses snapshot time rather than source freshness; Windows reads/extrapolates the timeline before waiting for metadata. [agent.rs:426](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:426), [windows/smtc.rs:208](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/smtc.rs:208). Sampling qualification below. |
| Seek cancellation, credit and repeat | **Partially fixed.** Position-only seeks now cancel an obsolete transport and prevent completion credit. Between-step seeks receive a new policy generation and repeat. A warm-up race still loses the repeat. [sender.rs:499](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:499), [sender.rs:669](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:669), [sender.rs:725](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:725) |
| Clamp before seek comparison | **Fixed.** The shared extrapolator clamps current position to duration for comparison and picking. Host positions remain full-width; wire saturation remains separate. [sender.rs:240](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:240) |

1. **Should-fix — A seek during transport warm-up can still lose its change repeat.**  
   [sender.rs:499](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:499), [sender.rs:677](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:677), [sender.rs:700](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:700).

   Concrete sequence: the initial repeats have settled; seek A sends successfully and schedules its two-second repeat. That repeat starts while A is still current. During its warm-up, seek B arrives with unchanged title, icon and duration.

   The pick accepts B’s position but uses the previously captured `seek_rev`. No policy change occurs. Completion records B as `sent_pos`, so the next step no longer detects B as a seek. B gets one transmission followed by the 60-second refresh, rather than its own change repeat.

   Record the seek/repeat obligation at pick as well as step entry. Also preserve that obligation when an in-flight seek is detected without a `sent_pos` baseline—for example, immediately after a text refresh clears it.

2. **Should-fix — The mid-transport seek regression test does not test the new seek checks.**  
   [sender.rs:1485](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1485).

   It starts a **Pause** transport and changes to **Play** at write `n0 + 10`. That bumps `tr_epoch`, so the old implementation already aborts at the next write. Moreover, the picked pause has `pos=None`, so the new position-based check cannot be responsible.

   Keep title, icon, playback presence and duration unchanged; change only position during a playing transport. Add a separate final-write hook to verify withheld credit, since an earlier cancellation does not exercise that branch.

The four tests’ regression value, by tracing their assertions against the old code:

| Test | Detects the old defect? |
|---|---|
| [End of track:1410](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1410) | **Yes.** Aging `300/300` becomes an apparent seek without the current-position clamp, producing writes the test forbids. |
| [Seek repeat:1435](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1435) | **Yes.** It settles startup repeats first; old `force()` produces only one new-position transmission. It misses the warm-up race above. |
| [Title change during warm-up:1451](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1451) | **Yes.** Old code sends Bravo’s transport before Bravo’s text. **Note:** also assert that a Bravo transport eventually exists; the current ordering loop passes vacuously if transport never resumes. |
| [Seek mid-transport:1485](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:1485) | **No.** The existing epoch check already handles its Pause→Play transition. |

**Notes on the other requested paths:**

- **Policy content is sound:** appending `seek_rev` makes `Policy::set` rearm the repeat without treating normal ticks as changes. Those revision bytes stay out of the wire payload. The issue is when the revision advances. [sender.rs:247](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:247)
- **The `None` pick reschedules sensibly.** `frame::run` returns `Abandoned(Superseded)` after only the two warm-up writes, which ended on the user’s baseline. No payload, credit, sequence increment or failure backoff follows. The sender immediately steps again; changed text goes first, then its successful completion forces transport. CLEAR/staleness keeps transport gated off. [frame.rs:240](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/frame.rs:240), [sender.rs:763](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/lockchan/sender.rs:763)
- **SMTC ordering removes metadata-latency double-counting.** It remains an approximation: `observed` precedes the synchronous timeline calls, while timeline age is measured inside them. A slow timeline call would retain some skew; timeline and metadata are also not an atomic snapshot. These tests cover neither case. [windows/smtc.rs:139](C:/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/windows/smtc.rs:139)

**Gremlin verdict: supervised testing remains reasonable; routine use is not yet cleared.** Besides the remaining sender repeat race, the Mac handoff still lists two firmware **should-fixes**: type 3 renewing an unrelated stale title’s lease, and repeated optimistic media-key presses rebasing the host anchor. The overlay-exit stale paint remains a **note/P3**. Those dispositions are explicit at [LOCK-LED-CHANNEL-PLAN.md:1128](C:/Users/jdlien/code/ak820-pro/plans/LOCK-LED-CHANNEL-PLAN.md:1128); the sender’s improved eligibility checks cannot repair silent text-frame loss at the receiver.