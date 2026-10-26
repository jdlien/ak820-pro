# Codex review: S1, the second increment (2026-10-24)

Prompt: [`review-prompt-s1-step2.txt`](review-prompt-s1-step2.txt). Reviewed: `gremlin/s1` `01bd2982` (C10's instrumentation, the restore's blank shadows) and the first `scripts/menu_s1_gate.py`. Verbatim `codex exec` output (`-m gpt-6-astra`, reasoning xhigh, read-only), then the dispositions.

---

**Safe to flash `01bd2982` to gremlin’s test board; I found no flash-safety blocker. C10 measurement acceptance should wait for the should-fixes below.** I found no new stray-glyph path from the blank-shadow optimization.

I compared the two commits through local Git objects and verified that the changed workspace files match `01bd2982`. I also checked the saved build hashes and ELF heap bounds. Process execution was unavailable, so I did not independently rerun the C tests, rebuild, or exercise hardware. All file access stayed inside the workspace.

1. **Should-fix — DMA timing measures observation rather than completion.**  
   [menu_slots.c:147](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:147), [menu_slots.c:59](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:59).

   For a glyph, `layout->paint()` returns after arming DMA. `piece_max_ticks` therefore stops **before CS release**, contrary to C10. Conversely, `last_op_ticks` ends when `settle_ops()` next observes an idle bus, potentially a main-loop pass after the actual completion.

   An owner change makes the discrepancy larger: close while a title glyph is outstanding, let the handoff quiesce it, then remain on DASH. The scheduler retains `ops_inflight`; a later state read or reopening can end its timing long after the transfer ended.

   There is also a snapshot-order problem: [menu_ops.c:158](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:158) reads the latency **before** `ms_ops()` settles that completed DMA, so one reply can contain the new operation count and the previous operation’s latency.

   **Fix:** capture completion/give-up timestamps at the bus endpoint, including [CS release](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:887), and consume them before snapshots and owner handoffs. Keep the current software extension main-thread-only; do not simply call it from the DMA ISR. Test completion followed by an independently advanced clock, a read, and an owner exit.

2. **Should-fix — the checksum does not provide C10’s exact composition identity.**  
   [display.c:1061](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1061).

   Different composed targets can have the same 16-bit polynomial checksum, leaving `dbg_gen` unchanged. A concrete counterexample: `"00:00:21"` and `"00:12:00"` have identical checksum contributions. A Camera clock correction between those compositions, with the other cells unchanged, will not advance the generation.

   Dirty-cell tracking still paints the change, so this is a measurement-identity defect rather than panel corruption. A script waiting for a new generation can miss the update or time out.

   **Fix:** detect actual changes while composing the active grid, comparing new cells against the previous composed cells before replacing them. `cam_set()` already performs that comparison. Avoid counting Camera’s temporary Health-grid compositions as visible changes.

3. **Should-fix — an already-satisfied new target is not settled at its first truth.**  
   [menu_slots.c:82](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_slots.c:82).

   Start with A settled, request A again, then request B before a pump or `ms_settled()` read. The second A target was immediately satisfied, but `target_settled` remains false and B counts it as superseded. Re-requesting the current pattern or turning by eight rows can produce this case.

   The books can still balance while the **classification and repaint latency are wrong**. Normal final-slot commits are recorded correctly.

   **Fix:** evaluate and latch settlement immediately after creating the new target. Add a case that performs both retargets without an intervening pump or status read, and check exact settled/superseded deltas.

4. **Should-fix — an awake stall can silently alias the extended clock.**  
   [menu_meas.c:21](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_meas.c:21).

   The extension works only when successive calls are less than **349.525 ms** apart. A gap of exactly 65,536 ticks returns the same low counter value and can appear to take zero ticks. Longer stalls can consequently understate pass, operation, or repaint latency without invalidating the measurement session.

   C10’s independent `ge25` check should reject such a run when the QMK timebase remains healthy; that protection does not make these timing fields accurate.

   **Fix:** use a reliably extended tick source, or fail the interval explicitly when an independent elapsed-time check makes the extension ambiguous. Reuse existing timing information where possible instead of adding another expensive timer conversion every pass.

   The **first call is sound** for relative measurements: its arbitrary epoch cancels in subtraction. I found no current off-main-thread caller. Deep sleep stops this hardware counter at [sleep.c:477](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:477), so sleep does not cause missed wraps—but its duration is excluded. A wall-time measurement must reject or separately account for a span containing sleep.

5. **Should-fix — arming retains the previous pass’s timing origin.**  
   [menu_meas.c:52](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_meas.c:52).

   `meas_arm()` clears the maxima and counts but retains `pass_have` and `pass_last`. The next `meas_pass()` includes work performed before the arm request. A slow preceding pass can therefore contaminate a freshly armed interval.

   **Fix:** establish a new pass boundary when arming—normally discard the crossing pass and start with the first complete subsequent pass. Test arming after a deliberately long pre-arm interval.

6. **Should-fix — the current gate’s sampling and instrumentation are not C10’s.**  
   [menu_s1_gate.py:54](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:54), [menu_s1_gate.py:141](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:141), [menu_s1_gate.py:164](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:164).

   I inspected this current workspace script in addition to the firmware diff. Only the health reads use `bracketed()`. Sub-10 and state/completion reads bypass the 25 ms discard/retry rule.

   Instrumentation load also differs substantially: baseline polling sleeps 100 ms, while `settle_menu()` repeatedly issues two HID reads without sleeping. Debug transition polling uses another cadence. These differences can change the measured ISR ratio.

   **Fix:** bracket every measurement read and use matched, scheduled instrumentation for baseline and activity windows. Preserve each sample’s midpoint and uncertainty.

7. **Should-fix — the continuous-input script does not enforce the specified workload.**  
   [menu_s1_gate.py:271](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:271).

   Each detent includes mutation/acknowledgement time followed by a fixed 45 ms sleep; it is not scheduled every 50 ms. Measurement reads similarly add delay to their nominal 100 ms cadence. The final deadline starts after the last sleep, granting extra settling time, and the last progress bucket can remain unchecked.

   **Fix:** schedule detents, reads, and bucket boundaries against absolute deadlines; record the last detent’s actual issue/application bracket; enforce the final 500 ms from that event and check the final bucket.

8. **Should-fix — the gate can omit required failures and debug-second evidence.**  
   [menu_s1_gate.py:149](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:149), [menu_s1_gate.py:190](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:190), [menu_s1_gate.py:229](C:/Users/jdlien/code/ak820-pro/scripts/menu_s1_gate.py:229).

   Several `wait()`/`to_dash()` results are ignored, although those helpers return timeout/failure values. `settle_menu()` accepts completion before checking whether its deadline expired, and its deadline begins after earlier mutation handling. The Camera test never implements C10’s expected second `S`, `dbg_sec == S`, and three-discard rule.

   **Fix:** make every failed wait terminal, enforce deadlines from the cause, and implement the generation-and-second completion procedure. A `PASS` from the current script does not establish all of C10.

9. **Note — the board acceptance script still treats sub 10 as unknown.**  
   [menu_s0_accept.py:76](C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_accept.py:76).

   The C test moved to 31, but board case A1 still sends 10 and will fail against this firmware.

   **Fix:** change that probe to 31. Also expose byte 31 in the shared state decoder so consumers can read `debug_done` consistently.

The **blank-shadow change looks correct**, with one misleading comment to repair at [display.c:1493](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1493). The literal claim about stages 1–5 avoiding the clock rectangle is false: stage 2 explicitly calls `draw_clock()`. That is safe because the clock updates its own shadow.

The actual geometry is:

| Painter | Inclusive rows |
|---|---:|
| OS/transport images; channel digit | 0–23; digit through 24 |
| Two small text lines | 27–40 and 41–54 |
| Large text / connection-status overlay | 29–51 |
| Single small text line | 35–48 |
| Clock digits; date/large playback | 56–77; through 78 |
| Small playback; AM/PM ink | 60–73; 59–74 |
| Locks; battery | 82–104; 105–127 |

The icon stays in columns 0–11; ordinary line 0 starts at 14. In the two-line layout its rows end at 38, above line 1. Connection-status text starts at column 4 but requests no icon.

I checked the intervening paths:

- Housekeeping and wake painting are gated during restore; overlay updates change state without painting those rows.
- `queue_line()` consumes the blank mark when it queues content. Dropped glyphs leave the shadow invalid and nonblank, requesting a retry.
- Keeping `shadows_trusted` does not override an individual shadow’s `valid == false`.
- Loss marks the restore damaged and prevents DONE until repair; owner changes discard queues and shadows.
- WAITING starts a fresh clear from band 1; it does not resume an old restore cursor.
- Preserving the clock and AM/PM shadows through the text stage is appropriate.

**Note:** the clock’s own full-band clear remains: stage 2 sets `clock_force_repaint`, and both clock/playback paths clear their band. Correct the comment’s implied clock-stage saving; the text-stage saving is supported by the code.

The remaining measurement mechanics look sound: `menu_task()` samples under every owner; **2,813 ticks** is the correct first representable duration over 15,000 µs; clear-band timing covers all three requested sources; token issuance, health-reset generation, wrapping counters, and wire offsets match the contract. Apart from the checksum identity problem, `debug_painted()` implements the required clear/grid/composition/RTC-second/transfer/loss predicate. Reset, loss, and first composition advance generations as specified.

**Note on cost:** [debug_painted()](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3467) calls `rtc_get_time()` on every otherwise-clean debug pass. This invokes `localtime_r()` and calendar conversions, not merely a register read; it performs no PCF I/O. The checksum scans 233 characters per composition. `meas_pass()` itself is small, lock-free work. Measure the clean-debug-page overhead; an optimization should cache against RTC edge **and correction generation**, preserving the calendar-second semantics.

The ELF bounds confirm:

| Build | Heap gap | Above 128 B floor |
|---|---:|---:|
| dev | 272 B | 144 B |
| devfault | 168 B | 40 B |
| daily | 2,384 B | 2,256 B |

The fixed interrupt/main-thread stacks remain 1,024/2,048 B. The added `blank` field fits existing padding: the shadow array remains 102 B. RAM meets the stated gate, including devfault, but runtime stack headroom still needs the planned board measurement.
---

## Dispositions (Warren, 10-24)

Safe to flash, no blocker; the blank shadows confirmed correct. Every
should-fix was fixed before the flash, in firmware `0aaefca2` and the
scripts.

1. **DMA timing at observation, not completion: fixed.**
   - **The endpoint:** `blit_done_cb()` and the give-up path stamp the 16-bit
     tick at CS release (`lcd_blit_end_tick16`). The main thread extends it
     (`meas_ticks_at16`, never from the ISR).
   - **The scheduler** ends a glyph op and its piece there.
   - **The menu task settles every pass, under any owner,** so an op left in
     flight by a handoff ends at its DMA's end. op 27 settles before it reads
     the latency.
   - **Host test:** a glyph op noticed 50,000 ticks late is still timed to
     its DMA's end.
2. **The checksum: replaced.** `dbg_row()` and `cam_set()` compare as they
   compose. Only the page showing's change moves `dbg_gen`; Camera's
   background Health grid doesn't.
3. **An already-satisfied target: fixed.** `ms_retarget()` checks settlement
   at once. Host test: A again and then B with no pass between gives settled
   +1, superseded unchanged.
4. **The extended clock's aliasing: fixed.** `meas_pass()` takes
   `timer_read32()`, already read for the menu task. A pass of 340 ms or more
   marks the interval ambiguous (sub 10 byte 31; the gate fails it) and is
   counted at its millisecond length. Deep sleep lands there too, so a span
   containing one is rejected.
5. **Arming's stale origin: fixed.** `meas_arm()` clears `pass_have`; the
   pass it lands in isn't counted.
6. **The gate's sampling: rewritten.** One poller reads sub 5 and sub 10
   every 100 ms, bracketed, in every window. Completions are judged only
   from its reads.
7. **The continuous workload: rewritten on absolute deadlines.** Detents
   are due every 50 ms; a late one (over 25 ms) fails the run. Buckets come
   from the poller, the final bucket is checked, and the final 500 ms runs
   from the last detent's cause.
8. **The gate's missed failures: fixed.**
   - **Every wait** is terminal on failure, with its deadline from the
     cause.
   - **The Camera second procedure** follows C10: S, its arrival, a
     generation tagged S, that generation's completion, three discards.
9. **A1's sub: fixed.** It now uses 31, and the shared decoder reads byte
   31 as `debug_done`.

**Notes:** the blank-shadow comment no longer claims a clock-stage saving.
`debug_painted()`'s per-pass `rtc_get_time()` on a clean debug page is left
as it is; its cost shows in the gate's Fn+D windows. The devfault heap gap
is 160 B against the 128 floor.
