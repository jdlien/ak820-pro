# Codex review of the audit's fourth batch, writing assets (2026-10-31)

Codex (gpt-6-astra, xhigh, read-only) on `qmk_firmware-ak820pro`
`2bea8fa0de` (F-015, the animation slot's end), `d5a42a2b88` (F-018, the
asset index's entries checked), `ed1e779acd` (F-014, a blit during an erase
reported lost) and `d998a97d1e` (F-001 and F-044, one chip operation a pass,
a CRC slice bounded by time, a CRC that waits for a program), and
`time-util-ak820pro` `803ab85` (ak820ctl's top-down erase and its unlock
turned off), with their host tests (prompt: `review-prompt-audit-batch4.txt`).
Verbatim below; it held F-001 on one P1 and found four P2s and two P3 gaps,
and found F-015's boundary, F-018's ID handling, the shipped assets and the
CRC and write retry state sound.

Dispositions (Buzz's session), in the firmware's `f79515e37a`, `ad917da23d`
and `cd9fce3039` and `time-util-ak820pro` `4cc6571` (pinned in `deps.lock`):

- **P1, reply backpressure starving the watchdog: fixed.** tmk_core's
  `raw_hid_task()` handles at most `RAW_HID_TASK_MAX_REPORTS` reports a call
  (the board's config.h: 4, at most ~400 ms a pass at the reply's 100 ms
  timeout); unset, on every other board, it drains as before.
  `scripts/raw_hid_drain_test` runs the real `send_raw_hid()` and
  `raw_hid_task()` against a model of the IN endpoint's blocking send and
  codex's host (the OUT queue always full, a reply taken every 50 ms): capped,
  the worst gap between housekeeping passes is 200 ms; uncapped, the control,
  the model starves the watchdog at 12 s.
- **P2, an idle blit dropping the mid-erase mark: fixed.**
  `flash_wip_settle()` is the one idle transition, used by both paths: a mark
  becomes `blit_lost` before the latch clears. `scripts/flash_wip_blit_test`
  gains codex's interleaving (a look while busy, then an idle blit, then the
  look that must still report the loss), which fails on the old code.
- **P2, ak820ctl's unlock cleanup: fixed.** `relock()` turns the unlock off
  and reports a failure; it runs after an `unlock(1)` that failed (the
  command may have landed with only its reply lost) and at every exit, in
  `flash write` and `flash erase`, and a failed relock fails the run.
- **P2, ak820ctl's reply correlation: fixed for the flash channel.**
  `xfer_flash()` takes only a full report echoing the request's command,
  channel and sub-command, discarding others within the 2 s deadline. The
  clock keeps `xfer()`: a foreign clock reply is well formed, so correlation
  cannot help it (one clock process at a time is what makes it right), and
  its timing is pinned by `scripts/clock_oracle.c`. Serializing flash
  sessions is not done: two writers sending the same commands still can't be
  told apart, and only one provisioning tool exists (the agent's flash client
  is info-only).
- **P2, FC_INFO during WIP: fixed.** It answers `FS_BUSY` while the chip is
  busy; `ak820ctl` re-sends up to 2,000 times, the agent's `read_info` 8 (an
  info mid-erase there now reports busy, not a floating id).
- **P3, the tests: done.** `scripts/flash_channel_test` no longer replays an
  old copy of `cmd_write()`: it builds `ak820ctl.c` itself (its `main()`
  renamed) against `fake_hidapi/hidapi.h`, a device whose handler is the
  firmware's extracted flash channel, with faults injected: the `unlock(1)`
  and `unlock(0)` replies lost in a write and in an erase, another agent's
  text echo ahead of every `FS_BUSY` reply over a second write of 40 KB, an
  info straight after an erase (the chip's JEDEC read now floats while busy,
  as its READ does). All six of those checks fail on `803ab85` with the
  firmware's old `FC_INFO`. `scripts/asset_index_test` loads the shipped
  `assets-src/current/flash_assets.bin` through the real
  `flash_assets_init()` and `flash_asset()`: twelve kept, each id finding its
  own entry; with the first, a middle and the last entry corrupted, nine kept
  and every other id still its own. USB backpressure is
  `raw_hid_drain_test`'s, the idle-blit interleaving
  `flash_wip_blit_test`'s.
- **P3, docs/display.md's 244 frames: fixed** (243, `ANIM_MAX`, and the
  count's check of 1 to 243).

---

I found **one P1, four P2s, and two P3 gaps**. The watchdog issue prevents treating F-001 as fixed.

This was read-only: I inspected the commits, callers, tests, and asset blobs. I did not access devices, run builds/tests, or edit files.

1. **P1 — Reply backpressure can still prevent the watchdog kick.**  
   [usb_main.c:519](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/tmk_core/protocol/chibios/usb_main.c:519), [usb_driver.c:273](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/tmk_core/protocol/chibios/usb_driver.c:273).

   The budget limits flash work, but `raw_hid_task()` still drains indefinitely, and every `FS_BUSY` produces a reply. A host streaming OUT reports while consuming one IN reply every 50 ms keeps the input queue populated and blocks successive replies without triggering the 100 ms send timeout. Housekeeping never runs, the budget never clears, and the watchdog kick at [ak820pro.c:685](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:685) remains unreachable.

   **Fix:** cap reports processed per `raw_hid_task()` invocation. Test the actual receive/reply loop with backpressure and assert housekeeping progress; the current direct-handler flood test cannot establish this.

2. **P2 — An idle observation can discard the pending WIP damage report.**  
   [lcd_bus.c:681](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:681), [lcd_bus.c:1435](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:1435).

   After a corrupted blit sets `blit_in_wip`, suppose `lcd_blit_lost_take()` still sees busy, then the next blit sees idle. `flash_wip_note_blit()` clears `flash_wip` without transferring `blit_in_wip` into `blit_lost`. Subsequent loss checks require `flash_wip`, so the earlier corrupted glyph can remain indefinitely.

   **Fix:** centralize the idle transition: whenever either path observes idle, promote pending WIP damage to `blit_lost` before clearing the latch. Add this interleaving to the test.

3. **P2 — Unlock cleanup still misses an exit and ignores failure.**  
   [ak820ctl.c:479](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:479), [ak820ctl.c:514](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:514).

   If `unlock(1)` reaches the board but its acknowledgement is lost, the early return sends no `unlock(0)`. Separately, a failed final `unlock(0)` is ignored, allowing successful verification and exit status zero while stock slots remain writable. The standalone erase branch has the same weaknesses.

   **Fix:** enter cleanup before attempting unlock; attempt relocking even after an ambiguous enable failure, and propagate/report relock failure. Normal post-unlock command failures already reach the new cleanup correctly.

4. **P2 — Host reply correlation can defeat otherwise-correct busy retries.**  
   [ak820ctl.c:80](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:80), [ak820ctl.c:109](/Users/jdlien/code/ak820-pro/time-util-ak820pro/ak820ctl.c:109).

   This predates the batch but matters to its retry guarantee. `xfer()` checks neither full reply length nor channel/command. On Windows, a concurrent agent’s line-zero text echo starts `07 12 03 00`; `fcmd()` interprets its fourth byte as `FS_OK`. A write packet actually refused with `FS_BUSY` can therefore be counted as consumed, or a CRC command can return text bytes as its result.

   **Fix:** require a complete, matching reply and discard unrelated reports within the transaction deadline. Serialize flash sessions because matching headers alone cannot distinguish two writers using the same commands.

5. **P2 — `FC_INFO` still reads the chip during WIP and reports success.**  
   [hid_protocol.c:248](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:248).

   An immediate `info` after the final erase—or a concurrent Windows info request—issues JEDEC `0x9F` while programming/erasing. Under the NOR behavior modeled by the supplied tests, that command is ignored, yet firmware returns `FS_OK` with floating-bus identification bytes.

   **Fix:** return `FS_BUSY` before reading JEDEC when the chip is busy. Both production info clients already have busy-retry handling.

6. **P3 — The tests omit important integration guarantees.**  
   [flash_channel_test/test.c:149](/Users/jdlien/code/ak820-pro/scripts/flash_channel_test/test.c:149), [asset_index_test/test.c:29](/Users/jdlien/code/ak820-pro/scripts/asset_index_test/test.c:29), [flash_wip_blit_test/test.c:127](/Users/jdlien/code/ak820-pro/scripts/flash_wip_blit_test/test.c:127).

   The channel test reproduces the **old** bottom-up writer and success-only relock. Its flood bypasses USB replies. The asset test checks synthetic entries through the predicate, without exercising loading, compaction, or lookup. The WIP test consumes the loss before another idle blit can clear the latch.

   **Fix:** exercise the actual host code with transport failures; include USB backpressure, rejected first/middle/last index entries with preserved IDs, the shipped blob, and the idle-blit interleaving.

7. **P3 — Animation documentation still promises 244 frames.**  
   [docs/display.md:696](/Users/jdlien/code/ak820-pro/docs/display.md:696).

   It also says there is no validation beyond zero count. Firmware rejects counts above 243, so the documented limit describes an unplayable file.

   **Fix:** document 243 frames and the upper-count check.

What I checked and found sound:

- **F-015’s firmware boundary is correct.** A 243-frame file ends at `0xCD8100`; its last erased sector ends at `0xCD9000`, below `0xCE0000`. The other slot windows remain unchanged. Top-down erase protects the audit’s old-boundary refusal case by encountering that refusal before erasing the old header; its preservation guarantee depends on the highest sector being refused.
- **F-018 preserves IDs.** Compaction copies the stored `id`; `flash_asset()` searches that ID rather than indexing by position. All index consumers handle missing entries, and `flash_assets_count()` is used for logging. Bounds arithmetic and the panel guard are sound.
- **The actual shipped assets pass.** Both asset blobs are byte-identical, 177,408 bytes, with 12 entries: five 24×24 icons, three 79×24 rows, one 128×128 splash, and 95-glyph fonts at 6×14, 10×23, and 15×22. Every extent fits both the blob and permitted chip region.
- **CRC and write retry state is sound for correctly correlated replies.** Busy guards precede CRC reset/advancement; page-boundary rollback preserves the packet for retry. `ak820ctl` retries identical packets, rejects exhausted busy retries, and consumes CRC bytes only after completion. I found no additional production erase/write/CRC sender in `hostagent/` or `scripts/`; Rust’s flash client is info-only.
- **Other post-write commands are appropriate:** status reads RDSR; unlock and write-begin change RAM state; buffered data/end only require idle when flushing. `FC_INFO` is the exception above.
- **The display repair consumer works once notified.** The pump sends a loss to the panel owner: dashboard damage gets staged repair with the five-second cooldown; menu/debug invalidate; animation stops.
- **Timing remains a deliberate limitation.** Eight milliseconds is a CRC stopping threshold, with up to another chunk’s work before checking. The unchanged per-byte page program still costs the audit’s estimated 12–50 ms and can lose typing during provisioning. With functioning SPI it is well below the watchdog timeout; the unbounded USB drain is the remaining watchdog problem.