**INFERRED:** The strongest explanation is repeated corruption of the LCD address window, followed by software shadows that incorrectly record successful painting. The widening window model explains the thin bands and right-hand blocks unusually well.

**INFERRED:** H1 is a plausible trigger, but it does not yet explain the repeated, selective corruption of every glyph. Its late-RX, `BUSY`, and partial-CASET behaviours remain hardware assumptions.

**INFERRED:** The proposed fix is useful but insufficient for safety approval. It also needs bounded RX processing, complete TX accounting, explicit DMA teardown ordering, and preservation of the completion-race protections.

I read the specified sections and pinned code before reading H1 and the earlier trace. Nothing was modified; no build or board test ran.

Citation shorthand below:

- **B** = `qmk_firmware-ak820pro@4790208267`, paths under `keyboards/a_jazz/ak820pro/`.
- **D** = `qmk_firmware-ak820pro/lib/chibios-contrib@5a1674e905`, file `os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c`.
- Documentation citations refer to the repository notes, not independently verified silicon behaviour.

## Part 1 — Independent diagnosis

### Ranked candidates

| Rank | Candidate | Confidence |
|---|---|---|
| 1 | Repeated SPI0 window/framing corruption, particularly around polled-send completion or the DMA-to-polled handoff | **INFERRED: high for the failure class; moderate for the particular boundary** |
| 2 | Repeated polled-send entry refusals, leaving glyphs unpainted until recovery | **INFERRED: low–moderate; incomplete explanation of the speckle** |
| 3 | Corrupted text, glyph data, or flash-source data | **INFERRED: low as the common explanation** |

**PROVEN:** Both transports eventually call the same text setters. Those setters copy the strings into RAM and request repainting when their contents change. The large song glyphs then come from an internal-flash bitmap and are expanded into a CPU-polled pixel stream. They are not fetched from the external asset flash.  
`B/bluetooth/ch582f_ajazz.c:600–607`; `B/hid_protocol.c:407–423`; `B/graphics/display.c:2278–2316`; `B/menu/menu_text.c:7–24`; `B/graphics/lcd_bus.c:898–925`.

**PROVEN:** `queue_line()` records its new shadow before the queued glyphs reach the panel. The pump subsequently consumes one glyph per pass. An identical incoming title does not normally request another repaint. Therefore, a physically incorrect write that returns success can leave old text visible indefinitely while RAM and the shadow contain the new title.  
`B/graphics/display.c:3203–3218,2990–2995,2306–2316`.

**INFERRED:** That mechanism explains E2–E4 particularly well: transport-independent damage, successful repaint from RAM, and no DMA fault counters. A detected poll failure is a different case: it sets `blit_lost`, which the display hands to its recovery machinery. Pure refusal therefore needs repeated failures or another fault to explain persistent damage.  
`B/graphics/lcd_bus.c:176–192`; `B/graphics/display.c:3045–3069`; `B/menu/panel_owner.c:215–250`.

### Why every letter, and why this shape?

**PROVEN:** Every large glyph establishes its own window and sends its entire 8×14 cell, including its background: 112 pixels, or 224 bytes. The two-line positions are y=27 and y=42; their x origins are 14 and 2.  
`B/graphics/lcd_bus.h:80–82`; `B/graphics/lcd_bus.c:369–378,412–441,898–902`; `B/graphics/display.c:134,144,2180–2184,3341–3343`.

**INFERRED:** A single corrupted glyph cannot explain an entire line. Either the peripheral remains in a bad state, the same boundary fails repeatedly, or corruption propagates between operations. Merely identifying one preceding DMA is insufficient.

**ASSUMED:** Suppose each glyph’s start column and row are accepted, but its end column remains at visible x=127. Also suppose RAM writes advance across that wider window in the expected raster order.

**INFERRED:** The glyph’s 112 pixels then occupy approximately

\[
\frac{112}{128-x}
\]

rows, instead of fourteen:

| Glyph x | Effective width | Rows of pixel data |
|---:|---:|---:|
| 2 | 126 | 0.89 |
| 14 | 114 | 0.98 |
| 74 | 54 | 2.07 |
| 110 | 18 | 6.22 |
| 118 | 10 | 11.20 |

This naturally produces a thin band near the line’s top, becoming taller toward the right. A ten-character title ends with its last cell at x=74, whereas a full artist line reaches x=118. That fits E5’s thin title band and deeper artist block. These are pixel-stream extents; black pixels and overlapping later writes determine the visible outline.

**PROVEN:** Shortening a line clears the vacated suffix separately, using a black-frame DMA. The new glyphs overwrite the retained cells without first clearing them.  
`B/graphics/display.c:3203–3211`; `B/graphics/lcd_bus.c:491–500`.

**INFERRED:** E5’s ten surviving old cells are consequently strong evidence that the suffix clear succeeded while the replacement glyphs missed their intended rectangles.

**INFERRED:** The geometry supports a wrong-window diagnosis, but does not establish *why* the window is wrong. It also does not explain pixels left of a preserved start column, or above a preserved start row. The photographed coordinates are approximate; accurately locating such pixels would constrain the hypothesis further.

### Why daily fails and dev does not

**PROVEN:** The source contains real flavour differences around this work:

- Dev adds display timing probes and scratch/stream checks.  
  `B/graphics/display.c:36–58`; `B/graphics/lcd_bus.c:244–265,363–374,390–397`.
- Dev enables `ROWISR_USB_DETECT`, adding snapshot and judgment work in the row ISR.  
  `B/config.h:536–542`; `B/rgb/rowisr.c:621–630,1224–1264`.
- Dev uses a buffered radio receive path; daily reads individual bytes.  
  `B/bluetooth/ch582f_ajazz.c:2045–2058`.

**INFERRED:** These differences change instruction timing, interrupt alignment and potentially compiler layout. They make a timing-sensitive peripheral fault credible without requiring different rendering rules. They do **not** prove that dev catches stale RX and repairs the screen.

**PROVEN:** `POLL_FAIL()` adds its dev-only call only after failure has been detected. It cannot itself explain prevention of the first failure.  
`B/graphics/lcd_bus.c:155–180`.

**INFERRED:** Console instrumentation is not a supported explanation for these ordinary daily/dev builds: the board defaults console off, and the supplied build flags do not request it.  
`B/keyboard.json:18–24`; brief E1.

## Part 2 — H1 and O1–O6

### What H1 establishes, and what it assumes

| H1 step | Assessment |
|---|---|
| DMA teardown leaves SPI0 RX unflushed and changes 16→8 bits before releasing panel CS | **PROVEN.** The handler resets SPI1, not SPI0; the later callback releases CS. `D:306–335`; `B/graphics/lcd_bus.c:1088–1101`. |
| A DMA-related RX entry becomes visible only after the next poll entry check | **ASSUMED.** The code creates a boundary worth investigating, but does not establish delayed RX visibility. |
| The sender counts that entry as its own completion | **PROVEN, conditional on the entry arriving.** Every available RX word increments `rx`; its origin is not checked. `B/graphics/lcd_bus.c:211–214`. |
| The sender can return with TX still queued because `BUSY` briefly reads clear | The absence of a `TX_EMPTY` test is **PROVEN**; the required hardware state is **ASSUMED**. `B/graphics/lcd_bus.c:216–226`. |
| The next caller operation changes DC | **PROVEN.** Actual overlap with an unfinished byte remains **ASSUMED**. `B/graphics/lcd_bus.c:308–314`. |
| A truncated CASET updates XS but retains the previous XE | **ASSUMED.** The consulted repository notes do not document this partial-command behaviour. |
| Dev rejects the residue, sets the sticky bit and initiates repair | The conditional software path is **PROVEN**; its occurrence during the clean dev run is **unmeasured**. `B/graphics/lcd_bus.c:155–192`; `B/graphics/display.c:3067–3069`; `B/menu/panel_owner.c:238–250`. |

**INFERRED:** H1 is compatible with much of E1–E8, but is not yet a complete explanation:

- **E1:** Fits timing sensitivity; the proposed dev rejection mechanism needs measurement.
- **E2:** Fits the shared painting path.
- **E3:** Fits RAM being correct while the physical panel and shadow disagree.
- **E4:** Fits silent corruption. Zero DMA fault counters also do not exclude polled give-ups, which have separate accounting.  
  `B/graphics/lcd_bus.c:154–180,1391–1413,1463–1469`.
- **E5:** Strong geometric fit under the partial-CASET assumptions.
- **E6:** Compatible with a wider window, but the isolated block could also be a glyph that painted correctly while its neighbours failed.
- **E7 and E5’s corner speckle:** Require additional explanation. The channel clear is x109–121, y0–23; retaining that clear’s window cannot reach x122–127.  
  `B/graphics/display.c:1505–1509,1550–1553`.
- **E8:** Compatible with a transient fault followed by a successful write or repair; it does not establish a transport-specific recovery mechanism.

### O1 — What makes every glyph fail?

**PROVEN:** There are several opportunities to break the proposed echo chain:

1. The sender drains up to sixteen RX entries before restoring interrupts.
2. The next sender checks that RX is empty.
3. The idle FIFO interrupt handler also drains RX.

`B/graphics/lcd_bus.c:189–194,223–225`; `D:105–117`.

**INFERRED:** One leftover entry is therefore not enough. H1 needs either recurring production of residue or a demonstrated chain that survives those drains and checks.

**INFERRED:** Selectivity is another substantial gap. The sequence is:

`CASET command → four column bytes → RASET command → four row bytes → RAMWR command`.

If the first one-byte command returns early, its command byte can cross into DC=data. Why should the failure repeatedly spare those one-byte sends, XS and Y, but damage `XE_lo`? The source provides no such discriminator.  
`B/graphics/lcd_bus.c:303–315`.

**PROVEN:** Excess RX can also make `rx > tx`; the unsigned expression `tx - rx` then underflows and prevents further filling. That tends toward a give-up rather than a cleanly sustained one-byte offset.  
`B/graphics/lcd_bus.c:195–214`.

### O2 — Where could the stray come from?

**PROVEN:** The normal completion changes `DL` to 7 with panel CS still asserted, restores RX interrupts, and never explicitly drains or resets SPI0 RX. SPI0 was previously switched to 16-bit frames for the DMA.  
`D:218–227,306–335`; `B/graphics/lcd_bus.c:1088–1101`.

**PROVEN — repository documentation:** The MCU notes say that changing `CTRL0` while enabled requires `FRESET`. The completion’s 16→8 change has no such reset; neither does Fire’s 8→16 change.  
`docs/sn32f299.md:864`; `D:218–227,310–318`.

**ASSUMED:** Whether those transitions produce delayed RX words, reinterpret residual words, disturb the shifter, or generate unintended clocks is undocumented here. Likewise, the code does not establish how SPI0’s receive FIFO behaves throughout this DMA mode.

**INFERRED:** This is a credible source of bad peripheral state, but “unflushed RX exists” and “a byte arrives after the next entry check” are different propositions.

### O3 — Can BUSY be clear with TX nonempty?

**PROVEN — repository documentation:** `BUSY` and `TX_EMPTY` are separate status fields. The notes do not define their relationship at frame boundaries.  
`docs/sn32f299.md:858–870`.

**ASSUMED:** The particular transient state H1 requires is possible on this silicon. It must be measured; it cannot be inferred merely from the existence of two flags.

**INFERRED:** Waiting for both is nevertheless the stronger completion condition. The existing DMA completion already uses both.  
`D:307–309`.

### O4 — What does the GC9107 do with incomplete CASET?

**ASSUMED:** Retaining old XE while committing new XS is essential to H1’s geometry, but is not established by the consulted repository documentation. The effect of interpreting `XE_lo` as another command is likewise unknown.

**PROVEN:** `XE_lo` equals `x1 + 1`, because the window applies `LCD_OFF_X=1`. It varies with glyph position; it is not a harmless constant.  
`B/graphics/lcd_bus.c:38–39,303–307`.

**INFERRED:** Different positions can therefore invoke different unintended commands, potentially producing effects beyond a wider window.

**PROVEN:** The preceding valid endpoint is not necessarily 127. Ordinary shortening clears only the previous run’s suffix; full-width clears occur on the unknown-shadow path.  
`B/graphics/display.c:3199–3211`.

**INFERRED:** A trace must identify the actual preceding accepted window. Assuming a full-width clear immediately before every faulty glyph overstates what the paint sequence guarantees.

### O5 — Why did USB eventually paint?

**PROVEN:** USB and Bluetooth use the same setters and renderer, but their arrival paths and timing differ. Identical title refreshes normally leave `text_dirty` unchanged.  
`B/hid_protocol.c:407–423`; `B/bluetooth/ch582f_ajazz.c:600–607`; `B/graphics/display.c:2306–2316`.

**INFERRED:** Different interrupt alignment, subsequent changed text, or a detected loss initiating repair could explain E8. “USB retries the pixels successfully” is not established by the observation. A duplicate unchanged title alone is not a sufficient explanation.

### O6 — Timing, or compiler behaviour?

**PROVEN:** The polling algorithm’s ordinary TX/RX loop is shared between flavours. The identified dev conditionals add diagnostics and checks; they do not supply a missing `TX_EMPTY` wait.  
`B/graphics/lcd_bus.c:155–226,244–265,363–397`.

**INFERRED:** Timing and layout are the leading explanations for the flavour difference. I found no source evidence establishing miscompilation or a missing compiler barrier. That narrower theory would require comparing the pinned binaries’ disassembly; adding a barrier without identifying an ordering violation would not establish a fix.

### The best immediate board measurement

**INFERRED — proposed experiment:** On the unchanged dev build, obtain a baseline, perform repeated title changes that change every displayed cell, then read op 27 sub 5 again after painting has settled. Avoid continuous polling during the experiment.

**PROVEN:** Bytes 24–25 contain the sticky failures; `PO_FAIL_SPI0_POLL` is bit 5 (`0x20`). The bit is OR-latched by any polled give-up.  
`B/menu/menu_ops.c:215–254`; `B/menu/panel_owner.h:113–120`; `B/menu/panel_owner.c:45–46`; `B/graphics/lcd_bus.c:155–180`.

**INFERRED:** A clean screen with that bit still clear strongly rejects H1’s specific explanation that **dev looks clean because entry refusals trigger repainting**. A newly set bit supports that explanation, but does not distinguish stale RX from the other entry failures or polling timeouts.

**PROVEN — diagnostic correction:** At this commit, the numeric give-up count has a dev C accessor, but I found no op-27 reply field that calls it. Op 27 exposes the sticky bit; the count should be explicitly wired into a diagnostic reply before relying on a numeric delta.  
`B/graphics/lcd_bus.c:154–156`; `B/graphics/lcd_bus.h:165–167`; `B/menu/menu_ops.c:215–309,440–457`; `B/menu/menu_glue.c:493–494`.

## Part 3 — Fix assessment and required verification

### Is the plan sufficient?

**INFERRED:** Waiting for `TX_EMPTY && !BUSY` attacks H1’s dangerous consequence directly: changing DC while bytes remain outstanding. Draining stale RX at entry is also sensible **after establishing exclusive, idle ownership**.

**INFERRED:** Those changes alone are insufficient. They do not prove that all requested bytes were submitted, bound every drain, repair an invalid peripheral configuration, or make DMA teardown safe. They also cannot establish the broader window-corruption diagnosis if mode changes themselves disturb the wire.

### Required changes

**1. Make successful polling mean a complete send.**

**PROVEN:** The current outer loop terminates on RX count alone. Its inner RX drain has no independent bound; the spin-limit check occurs only after that drain finishes.  
`B/graphics/lcd_bus.c:195–218`.

**INFERRED — recommendation:** Require all `n` TX bytes to have been submitted, valid RX accounting, and an empty/nonbusy transmitter before success. Detect `rx > tx`, unexpected extra RX and overflow instead of allowing unsigned-credit underflow or silently accepting them. Bound every RX drain, including the main-loop inner drain.

A final TX-empty check cannot repair bytes that were never queued.

**2. Acquire the idle bus before draining or resetting it.**

**PROVEN:** The current entry test checks `blit_done`, driver readiness, `BUSY` and RX emptiness, then masks IE. It does not check TX emptiness or the extension’s busy state directly.  
`B/graphics/lcd_bus.c:183–194`; `D:230–232`.

**INFERRED — recommendation:** Establish no live DMA/FIFO owner, mask the relevant FIFO interrupt safely, verify TX empty and nonbusy, then drain/count residue with a fixed bound. If ownership is inconsistent, refuse without dismantling another owner’s transfer. If an owned transaction fails, release its selection and perform bounded recovery.

Do this at a transaction boundary before asserting CS where possible; avoid introducing resets between CASET/RASET segments while the panel is selected.

**3. Make DMA teardown an explicit, ordered handoff.**

**PROVEN:** The current completion waits at most 200,000 iterations for TX empty/nonbusy, but does not test whether that wait expired. It then changes width and ultimately calls the success callback.  
`D:306–335`.

**INFERRED — recommendation:** Replace that silent fall-through with a short, measured bound and an explicit failure result. On successful completion:

1. Establish that the DMA and transmitter have finished.
2. Deassert the panel and flash CS before changing framing/resetting controllers.
3. Restore and reset the 8-bit configuration as required; bound reset completion and RX cleanup.
4. Restore SPI1’s vector and the appropriate FIFO interrupt state.
5. Publish completion exactly once, after cleanup.

**PROVEN:** Simply moving the existing callback earlier also moves `blit_done=true` earlier, because CS release and completion publication currently share that callback.  
`B/graphics/lcd_bus.c:1088–1101`.

**INFERRED — recommendation:** Separate “release selections” from “publish completion,” or otherwise preserve that ordering explicitly. Apply equivalent cleanup to abort and failed preparation.

**4. Preserve the DMA arm’s polled-window contract.**

**PROVEN:** Prepare disables SPI1’s vector and configures SPI0 before the polled window. `blit_done` remains true during that window; it becomes false before Fire. Failed windows use `dma_unprepare()` because Abort returns immediately before Fire.  
`D:193–227,252–256`; `B/graphics/lcd_bus.c:1109–1117,1151–1183`.

**INFERRED — recommendation:** The stronger entry guard must still admit this legitimate prepared-but-not-fired phase. Keep bus quiescing outside the window helper; do not turn preparation into a state that makes its own window refuse or wait for a nonexistent completion. Preserve the failed-window path that restores SPI1 and never fires DMA.

**INFERRED — recommendation:** Audit Fire’s 8→16 transition too. If satisfying the documented reset requirement entails a CS break after RAMWR, verify that the panel retains the write transaction across that break. That panel behaviour is **ASSUMED** here; blindly inserting a reset while selected is not a demonstrated safe solution.  
`D:218–227`; `docs/sn32f299.md:864`.

**5. Preserve completion handling and narrow every IC write.**

**PROVEN:** The DMA handler clears its initial observed flags, then rechecks for a completion that raced the clear. This second check is essential to the existing lost-completion workaround.  
`D:278–305`; `docs/sn32f299.md:906–912`.

**INFERRED — recommendation:** Preserve both the observed-bit acknowledgement and the recheck. Do not add a blanket clear or NVIC pending clear after a new DMA can start.

**PROVEN:** The existing code still contains broad `IC=0x3F` writes in Fire and Abort. Its rescue path can also write the TC bit after detecting `DMAEN==0`, even if the re-read did not observe TC.  
`D:218–227,252–269,298–304`.

**INFERRED — recommendation:** To meet the requested strict rule, acknowledge only bits captured in the relevant RIS snapshot. An engine-complete observation may synthesize a *software completion decision* without synthesizing an unobserved hardware IC write.

**PROVEN:** SPI0’s top-level dispatch selects the DMA handler from raw DMA flags without checking IE or active DMA ownership.  
`D:346–354`.

**INFERRED — recommendation:** Ensure stale DMA flags cannot invoke teardown during a polled transaction. Add an ownership guard or equivalent explicit state handling while preserving legitimate late completions.

### Safety verdict

| Requirement | Assessment |
|---|---|
| No new hang | **INFERRED:** Not established by the prose plan. Ownership, failed preparation and SPI1 restoration must remain correct. |
| No unbounded wait | **PROVEN:** The current inner RX drain lacks a bound. Every new wait/drain needs one. `B/graphics/lcd_bus.c:211–218`. |
| No pass ≥25 ms | **INFERRED:** “A byte or two at 24 MHz” describes healthy operation, not fault latency. It is not a safety bound. |
| No lost completion | **INFERRED:** Achievable only with the existing recheck preserved and completion published exactly once after cleanup. |
| No IC write wider than observed flags | **PROVEN:** The pinned implementation does not satisfy this literally everywhere; the reviewed change must address the relevant writes identified above. |

**INFERRED — recommendation:** Budget elapsed wall time as well as polling work, including interrupt preemption and multiple operations within one pass. Use a timer that continues advancing during the relevant waits, plus a finite work cap. Stop the current operation on failure and recover through later pump passes rather than accumulating retries in one pass.

**PROVEN:** Existing DMA recovery contains a large progress-loop cap and one synchronous retry, so a strict whole-path latency claim must include those paths too.  
`B/graphics/lcd_bus.c:1278–1297,1328–1342,1432–1438`.

### Board test that would establish the fix

**INFERRED — proposed acceptance test:** Use the original daily build as the reproducing control, then a fixed build retaining daily compilation paths. Alternate strings that change every cell, including full-width artist/title strings and long-to-short transitions. Exercise USB and Bluetooth, all song faces, playback ticks, channel redraws and Fn+D restoration.

**INFERRED:** A clean screen alone demonstrates improvement, not H1. The decisive capture is **SPI0 SCK, MOSI, DC and panel CS across a failing window**, correlated with a small buffered record of TX/RX counts and status at the send boundary. Establish whether `XE_lo` actually crosses a DC transition, and whether the preceding endpoint really is the one the geometric model requires.

**INFERRED — deliberate fault tests:**

- **Stale RX at entry:** With CS high and no owner active, clock a disposable byte and deliberately leave its RX word pending. The fixed sender must drain/count it and paint correctly.
- **Late RX credit:** Add a narrowly scoped test hook that introduces one synthetic RX credit after the entry check, targeting each window segment and the payload. Verify complete TX submission, no DC transition before physical completion, and bounded recovery on inconsistency. This tests tolerance of H1’s premise; it does **not** prove that the silicon naturally produces it.
- **Stuck status:** Inject non-clearing `BUSY`, nonempty TX and nonempty RX observations separately. Each must terminate within the pass budget, latch damage, and allow later operations to complete.
- **Existing recovery hooks:** Exercise every window segment and payload with `HC_POLLFAULT`, and missed DMA interrupts with `HC_BLITFAULT`. These already exist under `WDT_TEST_HOOKS`; the former forces give-ups rather than reproducing late RX.  
  **PROVEN:** `B/hid_protocol.c:608–617,1049–1064`; `B/graphics/lcd_bus.c:161–174,199–225,1206–1210`.

**INFERRED — acceptance criteria:** Correct final pixels; no unintended CS/DC changes during transmission; injected faults counted and repaired; no extra completion callbacks; subsequent SPI1 reads and DMA blits succeed; no watchdog reset; and no ≥25 ms main-loop pass, including deliberate fault cases.

**INFERRED:** Nonzero residue counts with a clean screen would validate the cleanup’s usefulness. Proving H1 requires observing the late residue and wrong-DC byte—or falsifying one of those necessary steps—not merely seeing the symptom disappear.