**NOT READY TO FLASH.** The seventh verify’s finding 1 is **fixed**, including both 360.990 ms traces. The detector remains **partly fixed**: another exclusion-recovery ordering can prematurely classify continuously moving frames as stopped and then accept a separate aliasing silence.

Reviewed **`25fefd2cc3`**, the nine fixes, prior reviews, dispositions, decoder and bench script. The supplied ELF matches HEAD’s manifest SHA-256. No files were modified or hardware accessed.

**1. Remaining P1 — re-prime can age recovery using time from before exclusion release.**

Both exclusion-release paths advance the generation and stale the frames, but leave `time_stamp` unchanged: [thread release, rowisr.c:360](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:360), [I-class release:388](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:388).

The next [guarded re-prime:300](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:300) adds the entire gap since that older stamp. Consequently, [recovery expiry:340](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:340) can count pre-release time as time spent waiting for a frame **after** release.

The observer-order model reproduced:

| Time | HEAD behavior |
|---|---|
| **10.020 ms** | Last observation; timer stamp 1,878. |
| **10.025 ms** | Exclusion entered. |
| **18.010 ms** | Final exclusion release; generation advances; current FRMNO 18 becomes the stale/pending baseline. Timer stamp remains 1,878. |
| **18.015 ms** | Tick reads timer 3,377. Gap **1,499 ticks**, below the guard, is imported by re-prime. Pending remains set, barely. |
| **18.030 ms** | Row adds three ticks. Recovery expires although release was only **20 µs ago**, legitimately before the next SOF. It commits `valid=1, bus=1, fresh=0, pending=0`. |
| **718.030 ms** | A subsequent 700 ms observation silence leaves **178 ticks**. Frames advanced by 700, but [the starting qualification:820](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:820) skips USB judgment. The interval enters valid statistics. |

**Result: one loss, zero USB rejections, and a healthy service across the second silence.** SOFs remain continuous throughout; this is not the declared stopped-frame blind spot.

This requires the release to precede an observer delayed across almost eight milliseconds—for example, a silence overlapping its masked release. Ordinary tick cadence avoids it. The model establishes the state-machine failure; I have not demonstrated that timing on hardware.

Rebasing the timer stamp at the final release, while retaining its generation change, kept recovery pending and made the same model reject the subsequent alias. An equivalent fix must ensure recovery ages only from its new baseline.

This defect also reproduces on **HEAD~1**; it is newly identified, **not introduced by HEAD**.

**2. Seventh verify’s adopted-baseline finding — fixed.**

[Invalidation now advances the generation unconditionally:322](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:322), and final exclusion release advances it again. An adopted VALID baseline can no longer remain continuous across that exclusion.

| Replayed trace | HEAD result |
|---|---|
| Rejection at **360.990 ms** → refused re-prime at **2,408.990 ms**, gap **56,320 ticks** → row at **2,409.010 ms** | **Two losses, one USB rejection, one guard rejection.** Returning row is INVALID, not spurious. The later row at **2,409.395 ms** can accept only its replacement interval. |
| Rejection at **360.990 ms** → exclusion through **660.995 ms** → silence **661.000–2,409.000 ms** → tick at **2,409.010 ms**, gap **74 ticks** → row at **2,409.030 ms** | **Two losses, one USB rejection, no guard rejection.** Generation mismatch excludes the interval; `serviced_valid` does not advance. HEAD~1 reproduces the previous false acceptance. |

I found no further surviving-baseline path across an unmarked discard. Observations during exclusion still discard time without individual generation increments, but their snapshots remain INVALID and final release breaks continuity. Guard rejection and refused re-prime each advance the generation.

**3. Three-state trust — ordinary transitions fixed; release-time aging remains the exception.**

[`take_snapI():473`](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:473) retains bus-up, freshness and recovery independently. Freshness is strictly **less than 750 extension ticks**, or 4 ms.

| Transition | Verified behavior |
|---|---|
| Guard rejection or refused re-prime | Captures current FRMNO as stale/pending; movement inside discarded time does not restore freshness. |
| Exclusion | Tracking stops; final release captures a new stale baseline. Clearing an already-clear exclusion does nothing. |
| Pending start, fresh end | Runs the frame comparison. |
| Pending start, nonfresh end | Excludes the interval as unjudged. |
| Recovery with ordinary observations and no movement | Expires after 1,500 additional extension ticks. The P1 concerns which time enters those ticks. |
| Handler’s frame-counter rejection | Preserves freshness, preventing the earlier duplicate rejection before the next SOF. |
| Frames stop without a flag | Freshness ages out; fresh-start/stale-end rejects once. Subsequent known-stopped starts enter the declared blind spot. |

**4. Conditional adoption and accounting — fixed for the reviewed races.**

[Adoption:862](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:862) requires both current validity **and** `time_gen == s1.gen`.

| Before the handler’s rejection | Adoption | Accounting |
|---|---|---|
| No intervening invalidation | Yes | One loss immediately |
| Tick invalidated; still INVALID | No | One loss at next entry |
| Tick invalidated and re-primed | No | One loss at next entry |
| Exclusion changed the generation | No | Change remains visible at next entry |

The **84 modeled rejection/guard/exclusion/re-prime/commit combinations** preserved those rules. Ordinary rejection followed by recovery counts once; a separate subsequent alias counts again. Sleep’s entry, release and refused first re-prime coalesce into one loss when no row observes between them.

One accounting distinction: an exclusion with row services inside it can produce losses at both entry and release. Those are separate consumer intervals, not a promise of one counter increment per exclusion episode.

**5. Spurious suppression and deep-sleep cancellation — remain fixed.**

The [zero-boundary return:813](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:813) precedes USB judgment and preserves the baseline. The coincident bus-event case cannot produce another pulse in the already-serviced epoch.

Both dev and ladder deep sleeps reach [common teardown, sleep.c:484](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:484), and therefore [unconditional cancellation:1048](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1048), including with the tick already stopped. The earlier admission return does not sleep. Plain WFI/PMU light sleep remains separate.

**6. Silence firing and report — mechanism fixed; measurement limits unchanged.**

[Firing-time logical checks:214](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:214) precede masking; the [actual pin check:176](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:176) remains inside it. A high pin prevents firing.

HEAD’s ELF confirms:

- Mask at **`0x253c0`**; rising store at **`0x253d4`**, nine intervening instructions.
- Falling store at **`0x253f8`**, immediately followed by unmask at **`0x253fa`**.
- Length arithmetic and bookkeeping outside the masked function.

**There is no 200 µs wait.** [The code uses `wait_ms(2)`:230](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr_diag.c:230), compiled as `chThdSleep(375)`. The report copies state before firing and after that scheduler delay. Its later VALID bit describes recovered state; it does not retain the actual last-before/first-after observer pair.

Actual decoder checks passed for recovery packing, saturation, equal-gap attribution and counter wrap. **5,600 nominal injection phase/cadence/order cases passed**, but they do not exercise the exclusion-release recovery-aging counterexample above. **That remaining P1 decides the NOT READY verdict.**