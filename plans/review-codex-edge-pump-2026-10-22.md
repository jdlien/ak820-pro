# Codex review: the blit pump skips the clock's second (2026-10-22)

The change is `26b36e3ea0` on `mac/edge-pump`, on top of `36afff30e8`. The problem is in
[`history/ge10-per-second-20261022/`](../history/ge10-per-second-20261022/README.md).
The model was gpt-6-astra at xhigh, read-only. Codex's answer follows verbatim, then the dispositions.

---

**No must-fix or should-fix correctness issues found in `26b36e3ea0`.** The flag is placed correctly, and I found no new starvation, deadlock, or same-pass dependency. The expected timing improvement is credible, but neither pass is guaranteed to stay below 10 ms.

I found two documentation nits:

1. **Nit — the header overstates which passes skip the pump.**  
   [display.h:27](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.h:27), also [display.c:3416](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3416).  
   **Scenario:** the 10 Hz call reaches the latch after the pump has already run. Setting the flag then does nothing to that pump call, and `display_pass_end()` clears it before the next pass. The commit message explains this correctly; these comments do not.  
   **Fix:** say “Skips when the 1 Hz latch has already run in this pass,” and describe the setter as marking the pass for any subsequent pump call.

2. **Nit — the commit message incorrectly exempts the lost-blit heal from delays.**  
   Relevant location: [display.c:2956](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2956).  
   **Scenario:** a lost blit is awaiting healing, its five-second cooldown has elapsed, and the second-edge latch runs. The new return precedes `lcd_blit_lost_take()`, delaying the heal’s initiation. The lost flag remains latched, so progress is preserved.  
   **Fix:** change the commit message to distinguish an **active restore**, which is unaffected, from a **pending heal**, which can wait until the next eligible pass.

The correctness checks resolve as follows:

- **Flag lifetime and consecutive passes:** there is one setter, after all owner and queue gates, and an unconditional clear in [display_pass_end()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3341). Its caller has no intervening early return and clears it before sleeping. No ISR accesses this flag, so plain `bool` is appropriate.

  `rtc_get_seconds()` returns the interrupt-based uptime counter, not calendar seconds. Ordinary clock sets do not move it backwards. Sleep accounting and coarse wake correction can change it discontinuously, but the latch records the new value directly; it does not replay missed seconds.

  **Consecutive sets are possible**, for example when a delayed 10 Hz latch catches up just before another RTC edge while the clock is off or showing an unchanged date. That is harmless. Crucially, once either `gq` or `lq` contains work, the queue gate prevents the latch from setting the flag again until that work drains. This is the strongest protection against starvation.

- **Pump owners and recovery:** `debug_active`, `display_paused`, and `debug_exit_step` all return before the setter. Debug composition therefore does not suppress its pump, and the staged restore retains its independent advancing call. Animation continues through `anim_task()`.

  Skipping preserves `blocked`, `blocked_since`, and `last_heal`. The 50 ms recovery grace remains elapsed-time based; the skip neither resets it nor postpones it repeatedly. Initial busy detection can occur a pass later. Once queued work is blocked, the queue gate prevents another latch-induced skip. The heal flag is consumed only when healing actually starts.

- **Wake repaint, backlight, and sleep blockers:** [wake_paint_step()](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3315) calls `draw_clock()` directly, which does **not** set the new flag. That wake path can still pump its newly queued clock glyph in the same pass.

  `clock_gen_painted` records preparation of the repaint, but release also requires the queues and final DMA to be idle. Thus delaying a glyph cannot falsely declare the repaint complete. `DSB_DISPLAY` likewise sees pending queues and prevents premature sleep. The existing 500 ms backlight timeout remains unchanged; a coincident skip can consume a little of that margin, but introduces no unbounded hold or early-success path.

- **Battery, retries, playback, titles, and Caps:** `batt_painted_this_pass` remains independent and still limits painting across the edge call, wake work, and 10 Hz call. `gq_retry_clock` survives until housekeeping can service it after the queues drain. Playback advances from timestamps, not pump-call counts. Lock-channel commits update RAM state and leases independently of painting. The Caps queue retains priority over `gq`. None requires a glyph to be pumped in the same pass as `draw_clock()`.

  Date mode and clock-off still execute the latch, even when they produce no clock glyphs. They can therefore delay newly queued title or Caps work by one pass. That is unnecessary in some cases, but harmless and keeps the policy simple.

The timing estimate is:

| Pass | Typical estimate | With overlapping 10 Hz work |
|---|---:|---:|
| Second edge | `3 + 4 + 1 ≈ 8 ms` | Can still approach/exceed 10 ms |
| Following glyph pass | `2 + 4 + 1 ≈ 7 ms` | Adding battery `1–3` and display housekeeping `1` gives roughly **9–11 ms** |

The pump’s approximately 2 ms share really is removed from the edge pass; its tiny early-return overhead remains. The work is deferred, and the pump still performs at most one glyph on the following pass—it does not catch up with two.

The saved ring contains seven 10 ms edge passes and two heavier edge passes at 12 and 13 ms. Subtracting the reported pump share alone predicts approximately **8, 10, and 11 ms** respectively. Keeping a glyph queued can also make the later display-housekeeping call return early, saving additional work. Conversely, shortening the edge pass can move the 100 ms threshold crossing into the following pass. Scope rounding and varying radio/core costs prevent a strict bound.

**I would retain this implementation.** Reusing `pass_deferred` would suppress more work; setting the flag inside `draw_clock()` would broaden it to wake and restore paths; moving the pump into housekeeping would violate the restore invariant. A separate pass-local flag is a small, clear solution.

This was a static review plus `git diff --check`, which passed. No files were changed, and no build, flash, or hardware timing validation was performed.
---

## Dispositions (ak820-pro-32, 10-22), fixed in `ce229f87c6`

No must-fix and no should-fix, so the code stands as reviewed. `ce229f87c6` changes comments
only. Its build (`via-dev-ce229f87c6-20261022-165642.bin`, token `0xa0889ccf`) differs from
`26b36e3ea0`'s in four bytes, all of them immediates of the token's construction: the same code.

1. **Nit, the header overstates which passes skip: agreed, fixed.** `display.h` and the setter's
   comment now say that only a pump call after the latch in the same pass skips. A latch reached from
   the 10 Hz call, which comes after the pump, does not stop it.
2. **Nit, the heal: agreed.** A commit message can't be changed once pushed, so `ce229f87c6`'s
   message corrects `26b36e3ea0`'s: a pending heal can wait one pass when the latch ran first. Its
   flag stays latched, so nothing is lost. An active staged restore is unaffected.

**The timing caveat, taken into the test:** the pass after the edge carries the pump's glyph. When
the 10 Hz block lands on it, codex estimates 9-11 ms, and an edge pass that the 10 Hz block lands on
can still cross too. So `count_ge_10ms` should fall well below the clock's cadence, but not to zero.
The test on gremlin's board reads the HC_ACCT ring for a pass that stacks `blit_pump` with the 10 Hz
scopes (`battery`, `display_hk`, `leds`). If those are what is left, take the battery scope's 64-bit
math out next (`BACKLOG.md`).
