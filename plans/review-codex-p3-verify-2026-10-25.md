# Codex verifying P3's code-review fixes and the knob's rest rule, 10-25

Prompt: `plans/review-prompt-p3-verify.txt`. Line references are to
`47567935`/`44d11c28`. The response: firmware `a7c19f85`.

## Dispositions

1. **A bounce-slot 5B 32 after the reset restores CONNECTED (must fix)** and
2. **the barrier opens on a given-up or older same-slot frame (must fix):**
   taken by backing the barrier out (`select_unsent` and the gated
   retirement of `PA_SELECT` are gone). A 5B names no slot, so every boundary
   is a heuristic with edges, and gating the retirement could restart a
   legitimate attempt if the module answers before it ACKs (codex's
   follow-up), which `docs/wireless.md` forbids. The driver's own rules are
   `a9f750ff`'s again; what stays: the facts (outside a bounce), the bounce's
   end leaving the link attempting, the last tries' windows, a 36 retiring
   `PA_SELECT`, the boot retry as pending.
   - **The safety property, by order instead of attribution:** the menu's
     pair is never sent during a bounce or a select retry, and once sent it
     queues behind the target's select, so the module pairs the slot it was
     just told (it processes commands in order).
   - **A stale 5B can't drop the pair:** `bt_pair_hold_task()` no longer
     disarms on "already advertising"; it sends anyway (stock sends A6 51
     twice). `btui.c`'s `bounce_stale` (was `bounce_boundary`): a bounce-slot
     5B 31 right after the target's select; the pair goes, behind it, and no
     other select. `already_advertising`'s second half now expects the pair.
   - **What's left, accepted:** a stale 5B can misstate the page's phase for
     a moment (advertising, or connected) until the target's own answer; a
     stale CONNECTED whose target never answers reads "Already" in the menu,
     as the band shows it connected (a9f750ff's behaviour after a bounce);
     the slot keys still re-select.
3. **The ACK ordering (could wait):** moot with the barrier gone.
4. **The knob's rest polarity is unproven (could wait):** taken now. Op 27
   sub 14 byte 17 reads the decoder's state; read on the board right after
   the flash with the knob at rest, before JD uses it: 0 or 3 confirms the
   rule, 1 or 2 means a reflash without it. My status file's "the knob would
   do nothing" was wrong: with 01/10 rests a reversal's first detent is lost
   and turns fire mid-detent (codex); corrected. `encoder_test.c`'s
   mid-detent check is strict now with the rule (it let one through).

## The review, verbatim

**Yes. Two radio bugs still need fixing before this P3 flash.** This was a static review: the reviewed working files match the supplied commits; process execution was unavailable, so I could not rerun the C tests.

1. **The bounce’s CONNECTED state can still survive a lost target select.** [ch582f_ajazz.c:1831](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1831) resets the state **before draining RX**, but [line 2086](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2086) unconditionally restores CONNECTED on a buffered bounce-slot `5B 32`, even while `select_unsent` rejects its confirmation. If the target never answers, retries expire with CONNECTED plus SEL_LOST. [menu.c:1168](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1168) then still says “Already” and refuses to reconnect. Keep pre-target frames from restoring target connection state. Combine `bounce_boundary`’s timing with `bounce_lost`’s silence; neither current test covers that combination.

2. **The confirmation barrier can open without the current target select succeeding.** [ch582f_ajazz.c:1282](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1282) identifies completion only by profile byte, and [line 1335](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1335) treats TX give-up like ACK. After an undelivered target select gives up, a delayed bounce-slot `32` can therefore confirm the target, retire PA_SELECT and release the menu’s pair onto the wrong slot. An older in-flight select with the same profile can also clear a newer request’s barrier.

   Only `set_profile()` raises the flag; bounce completion, timed retries, `23` reissues and cold-boot retries inherit it. Track the current transaction, and distinguish failed delivery from permission to attribute responses. Failure must eventually yield LOST without accepting the old slot. Do not indiscriminately re-arm every same-target retry: delayed valid attempt responses must still stop the backstop.

**The other dispositions check out.** Items 1 and 2 cancel both the menu wait and key hold, including “Already”; the new glue call respects the stand-in guard. Item 5 now provides approximately 12 seconds for SELECT and 4.8 seconds for PAIR, including their final windows. Existing exhaustion tests wait 15/16 and 6 seconds respectively; I found no caller depending on earlier expiry. Cold-boot retry correctly keeps selection pending. Direct `36` retirement and the off-BT cursor fix are correct; stand-in regression coverage remains deferred.

The bounce reset itself introduces no additional routing regression: the band uses the requested slot, `bluetooth_is_connected()` affects automatic routing while this board explicitly chooses its host, and keyboard/consumer transmission does not depend on that boolean. Clearing it appropriately stops lock-channel reception. Restarting `linking_since` gives the target its own three-second promotion window.

These follow-ups can wait for the cable bench, but remain relevant before accepting Bluetooth and encoder behavior:

- **ACK ordering has a worse failure mode than the comment promises.** [ch582f_ajazz.c:2120](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:2120) ignores a pre-ACK `33/34` for retirement, allowing a 1.5-second reselect that restarts a legitimate attempt—the documented forbidden behavior. A pre-ACK `31` can leave advertising unconfirmed; same-slot selects may then receive no answers, exhausting all eight tries rather than merely adding one resend. This can disrupt reconnection and misreport pairing, though it does not brick the board. Measure the ordering on BT.

- **The encoder’s physical assumption remains unproved.** Resolution 2 establishes transitions per detent, not resting polarity. [sleep.c:220](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:220) checks pins against stored decoder state, not A against B. With 00/11 rests, the rule correctly repairs initial phase; once aligned, sampled bounce/skipped-state sequences behave identically to before. Sleep retains that alignment. The simulator lacks retained-state wake and opposite-polarity cases; [encoder_test.c:59](C:/Users/jdlien/code/ak820-pro/scripts/encoder_sim/encoder_test.c:59) also permits a mid-detent event despite its comment. With **01/10 rests**, JD would lose the first detent after reversals, then get events mid-detent during sustained turns; alternating single detents can do nothing. [WARREN-STATUS.md:177](C:/Users/jdlien/code/ak820-pro/plans/WARREN-STATUS.md:177)’s claim of complete inactivity is incorrect.

No additional cable-position flash hazard found. The supplied 136-byte gap clears the floor by eight bytes; recheck the rebuilt artifact after fixes.