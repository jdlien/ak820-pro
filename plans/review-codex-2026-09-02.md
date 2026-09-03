# Codex review — LOOP-BUDGET-PLAN, 2026-09-02

Verbatim `codex exec` output (codex-cli 0.147.0). Adversarial review requested;
findings integrated into the plan rewrite of the same date.

---

## Verdict

Do not implement Phases 2–3 as written. They provide useful telemetry and probabilistic avoidance, but they do not bound worst-case matrix latency. The scheduler only budgets one portion of the loop, while several existing paths can still block for 20–250 ms, 100 ms per attempt, or indefinitely.

### Critical findings

1. **The cooperative scheduler does not impose a latency bound.**

It checks time only after a sub-task returns, so the actual bound is:

`HK_BUDGET + worst-case duration of the last task started`

That duration is currently unbounded. `lcd_blit_wait()` can spin for approximately 250 ms ([lcd_bus.c:646](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:646)); internal-flash busy waits have no timeout ([hal_efl_lld.c:118](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:118)); and sector erase waits synchronously ([wear_leveling_efl.c:141](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/platforms/chibios/drivers/wear_leveling/wear_leveling_efl.c:141)).

`must_run_every_tick` makes this worse: if such tasks run despite exhaustion, the budget is no longer a bound; if they run first, they can starve optional work. A task table is structural only if every entry is a resumable, nonblocking step with a separately enforced WCET.

2. **The scheduler covers only the tail of the real main loop.**

QMK scans the matrix, runs RGB/encoder/Bluetooth, processes raw HID and deferred callbacks, and only then enters housekeeping ([main.c:47](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/main.c:47), [keyboard.c:710](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/keyboard.c:710)). Important bypasses include:

- RGB EEPROM flush inside `rgb_matrix_task()`, before housekeeping ([rgb_matrix.c:311](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:311)).
- Raw HID drains packets with no per-pass cap ([usb_main.c:517](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/tmk_core/protocol/chibios/usb_main.c:517)).
- USB sends wait up to 100 ms per attempt and retry in a `while (true)` loop ([usb_main.c:392](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/tmk_core/protocol/chibios/usb_main.c:392), [usb_driver.c:253](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/tmk_core/protocol/chibios/usb_driver.c:253)).
- The deferred full dashboard redraw performs synchronous clears and images ([display.c:717](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:717)).
- `display_second_edge_task()` invokes the whole display housekeeping function outside the proposed 10 Hz scheduler ([display.c:1868](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1868)).
- BT/mode callbacks synchronously draw LCD images on input paths ([display.c:1927](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1927)).

Therefore Phase 2 can report a clean 4 ms housekeeping block while the complete loop stalls for 100+ ms.

3. **The quiet gate does not make flash safe and the 30-second force explicitly violates the goal.**

Past quiet does not protect against a press beginning immediately after the gate check. Worse, `kb_eeconfig_task()` can enter the pre-write hook, which itself waits for LCD DMA and can consume 250 ms ([ak820pro.c:560](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:560)). A key beginning during that wait remains vulnerable.

Forcing a write every 30 seconds of continuous typing deliberately introduces the exact blind window the plan claims to eliminate. Do not force while typing.

It also increases persistence exposure: kb config is already delayed five seconds ([kb_eeconfig.c:38](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:38)); the proposal can extend that to 30 seconds. The slider routinely causes LVD brownouts and destroys RAM ([hardware.md:7](/Users/jdlien/code/ak820-pro/docs/hardware.md:7)). The affected data includes the selected BT slot and RTC trim, not merely cosmetic preferences ([kb_eeconfig.c:20](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/kb_eeconfig.c:20)).

Use a pre-erased, CRC-protected append journal or double-buffer so normal commits are short and atomic; perform erase/consolidation only at boot or verified idle. Preserve the old valid record until the new record is complete.

4. **VIA must be covered, but a simple quiet gate cannot cover it correctly.**

VIA keycode, macro, reset, encoder and buffer commands write immediately in raw-HID context ([via.c:390](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:390)). A keycode is two separate EEPROM operations, and buffer commands can issue 28 operations ([nvm_dynamic_keymap.c:94](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/nvm/eeprom/nvm_dynamic_keymap.c:94), [nvm_dynamic_keymap.c:140](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/nvm/eeprom/nvm_dynamic_keymap.c:140)). Brownout can therefore create torn keycodes.

The pre-write hook cannot defer them: it returns `void`, after the caller has already committed to writing. Buffer VIA transactions in RAM, provide read-your-writes through a shadow, and expose pending/committed status—or reject writes explicitly while persistence is unavailable. Also mediate all other EEPROM writers; magic keys currently write synchronously from key processing ([process_magic.c:169](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/process_keycode/process_magic.c:169)).

5. **Phase 1 can perturb the result and its clock is not trustworthy enough for proof.**

The plan says per-pass instrumentation is banned, then adds a histogram and pass count per pass ([LOOP-BUDGET-PLAN.md:62](/Users/jdlien/code/ak820-pro/plans/LOOP-BUDGET-PLAN.md:62), [LOOP-BUDGET-PLAN.md:71](/Users/jdlien/code/ak820-pro/plans/LOOP-BUDGET-PLAN.md:71)). The histogram addition is probably small because the timer read already exists, but it still needs hardware A/B validation.

More concerning is always-on per-site attribution: the previous profiler’s timer calls cost roughly 2 ms/pass and reduced scanning from 270 to 175 Hz ([ak820pro.h:88](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.h:88)). Reuse one timestamp after each scheduled task for both budget and attribution; do not use begin/end timer reads.

Also, `timer_read32()` already loses approximately 1.2% of ticks under current ISR load and will under-report more precisely when overloaded ([leds.md:78](/Users/jdlien/code/ak820-pro/docs/leds.md:78)). It cannot be the sole proof clock. Use the free CT16B4 hardware timer for sub-millisecond measurements ([mcuconf.h:42](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/mcuconf.h:42)) and validate with a GPIO/logic-analyzer trace.

The existing `HC_GET` payload already exactly fills its 28-byte body ([hid_protocol.c:403](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:403)); the plan also needs a versioned second page or new command.

### Answers to the five open questions

1. **Is 4 ms right?**  
   Only as a soft throughput quota. Use these separate contracts:

   - Whole-loop hard limit: **10 ms**
   - Housekeeping admission budget: **3 ms**
   - Maximum one task step: **1 ms**
   - No blocking call inside a scheduled step

   With the current approximately 2.9 ms normal pass, that leaves useful ISR/core headroom. Any task needing more than 1 ms must be converted into a state machine. A literal structural guarantee is better obtained by a 1 kHz, RAM-resident raw-matrix sampler with an edge queue; otherwise every path in the entire QMK loop must satisfy the 10 ms bound.

2. **Which tasks cannot be deferred?**  
   Do not use a Boolean `must_run_every_tick`; use deadlines.

   - `modified_consumer_task`: deadline-critical because delayed release leaks real Alt/Shift into later typing ([consumer_mod.c:63](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/consumer_mod.c:63)). Move its cheap timer check per-pass or allow at most about **25 ms lateness**.
   - `bt_pair_hold_task`: at most **100 ms lateness**; it need not run every tick.
   - `anim_task`: fully deferrable; one missed invocation merely drops a frame.
   - Display, health and eeconfig: deferrable.
   - RTC’s phase machine is separate and has an actual **10 ms** release window ([rtc.c:1323](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1323)); it cannot be folded casually into a 10 Hz round-robin scheduler.

3. **Gate VIA?**  
   Yes—along with every NVM writer—but through a global transactional NVM arbiter, not a last-key-time check in the existing synchronous call. Keep the blit-drain protection, but make bus-idle an admission condition rather than entering a 250 ms wait after admission. Remove the 30-second forced write.

4. **Histogram shape?**  
   Use `max` plus cumulative saturating counters for `>=5`, `>=10`, `>=20`, and `>=40 ms`. Common-path work should be one `gap >= 5` branch; do not increment a `<5` bucket every pass. One total `uint32_t` pass count is sufficient to recover percentages. Reject instrumentation if three paired, console-off A/B runs show more than a **2%** scan-rate reduction or introduce a new `>=5 ms` tail.

5. **Other paths worth bounding?**  
   Yes, all three named ones and several more:

   - Glyph pump calls the 250 ms recovery wait after 50 ms ([display.c:1628](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1628)).
   - `rtc_fast_task()` uses 20 ms synchronous bit-banged I²C ([rtc.c:25](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:25)); boot acquisition actually performs up to three transactions in one call despite the “at most one” comment ([rtc.c:1431](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1431)).
   - Modified-consumer handling deliberately blocks 8 ms inside key processing ([consumer_mod.c:43](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/consumer_mod.c:43)).
   - CH582F writes use `TIME_INFINITE` ([hal_serial.h:268](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/hal/include/hal_serial.h:268)), while its queue explicitly drops reports when full ([ch582f_ajazz.c:532](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:532)).
   - Flash programming masks interrupts ([hal_efl_lld.c:330](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/SN32F290/hal_efl_lld.c:330)); UART priority cannot protect the CH582F’s approximately 1.4 ms FIFO during those windows.

### Phase 4 would currently give false confidence

`scripts/soak.py` is wired-only and generates no physical matrix input ([soak.py:37](/Users/jdlien/code/ak820-pro/scripts/soak.py:37)). It serializes host transactions, and its present gap handling only prints a warning above 60 ms rather than failing ([soak.py:260](/Users/jdlien/code/ak820-pro/scripts/soak.py:260)). It cannot prove BT/2.4G delivery or that a physical press overlapping a stall survives.

Also, `HK_BUDGET_MS` and the whole-loop limit must not be the same assertion. Existing intentional 8 ms waits would immediately violate a 4 ms loop-gap test.

A credible gate needs:

- An electrical/physical matrix fixture issuing randomized and phase-swept **25 ms presses**, not firmware-injected keycodes.
- Deterministic overlap with VIA 28-byte writes/reset, wear-level consolidation/sector erase, DMA-completion loss, I²C held low, USB host not polling IN, CH582F UART congestion, boot’s deferred dashboard redraw, and modified-consumer/encoder bursts.
- Brownout tests after setting changes at 0, 50, 250, 1000, 5000 and 30000 ms, including cuts during an actual write.
- The exact daily build, console disabled.
- `loop_gap_max <= 10 ms`, zero `>=10 ms` gaps, zero NVM torn-state failures, and exact fixture-event equality.

Six hundred clean characters only gives an approximate 95% upper confidence bound of **0.5%** aggregate drop rate; it is not structural proof and does not cover individual keys. Thirty thousand clean fixture presses lowers that statistical bound to about **0.01%**, while deterministic phase-overlap tests provide the more important causal evidence.

