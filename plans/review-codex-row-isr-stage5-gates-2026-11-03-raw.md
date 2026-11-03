**I would keep 125 µs and terminal 1,535, revise the 20% target, and allow a small nonzero omission budget.** Neither 39.6% nor this omission rate alone warrants blocking release. I would still withhold release qualification until the outstanding operational gates are closed. Some claims in the measurement narrative also need narrowing.

**1. CPU: 20% is a target to revise, not an established operating limit.**

The old driver’s successful operation at 72.8% is useful evidence that 39.6% is tolerable. It does not establish that the new deadline-driven driver has sufficient margin under every workload. The relevant release evidence is delivery, UART overruns, tick regularity, main-loop stalls and omissions under load.

Also, 39.6% is **elapsed occupancy between the hooks**, including higher-priority preemption and excluding the wrapper. It is neither exclusive CPU consumption by the row code nor total interrupt utilization. That is appropriate for the plan’s *elapsed-share* comparison, but it should retain that label. [health.c:80](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/health.c:80)

My ranking:

| Rank | Change | What I would expect |
|---|---|---|
| 1 | **Section 2 in SRAM on daily** | Largest plausible saving without weakening the diagnostic contract. Budget roughly **10 µs/slot, potentially low teens**, as an engineering estimate requiring measurement. |
| 2 | **Cheap instruction-count reductions** | A few µs are plausible from width conversion; smaller savings elsewhere. I would try these first because they are cheap. |
| 3 | **Every-eighth USB judgment** | Approximately **8 µs**, taking 49.5 to 41.5 µs and 39.6% to **33.2%**. Useful, but insufficient by itself and accompanied by a real diagnostic concession. |

For SRAM, **do not apply “halve it” to the entire 49.5 µs**. The 37.9 µs section measurement predates the scan and stage-5 changes; it also includes preemption. SRAM does not accelerate peripheral transactions, settle time, preempting handlers, or helpers left in flash. Extract the relevant block and include its hot helpers and literal pools in the size calculation. The archived 5d vector is **3,404 bytes**, before the separate scanner, so moving the whole handler does not fit the daily gap. The section-sized proposal remains credible; the dev gap does not. [Cost diagnostic:536](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/README.md:536), [existing SRAM placement:397](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:397)

There are two concrete cheap candidates:

- **Width conversion:** the archived ELF expands multiplication by 300 into five shift/add/subtract instructions, followed by rounding and shifting, for each real LED column. A 256-entry `uint16_t` table in flash costs 512 bytes of flash and no SRAM, and can replace that sequence. Preserve the existing unrolled register writes. I would expect a few µs, not promise a number before measuring flash-data loads. The algebraically equivalent `(75*b + 8) >> 4` is an even smaller experiment. [rowisr.c:1140](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1140)
- **`rec.serviced++` is now unread.** Its former wire location contains `elapsed_crossed`; the increment remains in the emitted code inside the commit’s masked section. Removing it saves only a small fraction of a microsecond, but it is genuinely unnecessary work. [rowisr.c:925](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:925), [wire record:668](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:668)

The every-eighth proposal is **more than coarser attribution**. The 00:22 counterexample permanently loses evidence of a second aliasing silence, and previously credited statistics can remain apparently valid. It does not remove the hardware arm deadline or pending-match protection, so I could accept a deliberately weaker diagnostic contract for production. I would not describe the rejected implementation as preserving today’s guarantee. At 125 µs, eight ordinary services are nominally **1 ms**, not the earlier 2.1 ms. [Cadence judgment:3](/Users/jdlien/code/ak820-pro/plans/review-codex-row-isr-cadence-2026-11-03-raw.md:3)

**2. Omissions: acceptable rate, but the cause is not yet established.**

First, the actual ordering is **UART2 0, SysTick 0, USB 1, PWM tick 2, row/SPI0/SPI1 3**. UART and USB are reversed in the question. [mcuconf.h:81](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/mcuconf.h:81), [docs/leds.md:12](/Users/jdlien/code/ak820-pro/docs/leds.md:12)

The credible sources are:

- **SPI0 completion and SPI1 FIFO handling at equal priority.** They cannot be preempted by the row handler. SPI0 completion includes a TX-empty/BUSY wait, controller restoration and a callback. This makes the display path worth investigating, although it does not prove a normal completion takes 75 µs. [hal_spi_v2_lld.c:306](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:306)
- **USB, UART and SysTick**, including combinations of their service with the 20 kHz tick. Pausing the daemon does not stop USB SOFs, OS timers or autonomous radio traffic.
- **PRIMASK sections**, regardless of the interrupted code’s priority.

A 74.9 µs maximum does **not** demonstrate one 75 µs interferer. It can include several handlers and masked intervals. Moreover, the latency stamp is taken after the wrapper, entry hook and part of the snapshot work. Nor does the aggregate record establish that each omitted pulse entered late: a handler can enter promptly and be preempted before its arm. [rowisr.c:978](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:978), [snapshot:532](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:532)

**`overrun_diag.py mon` cannot, as built, name every candidate.** It measures gaps in the priority-2 tick. An unmasked priority-3 SPI handler can delay the row while the tick remains perfectly regular. Its context field explicitly records where the main loop was, not the cause. The maximum includes shorter gaps, but counters start at 128 µs and the event ring at 197 µs. A clean monitor therefore does not acquit SPI. Use its USB/SysTick/UART timing alongside direct SPI/row timing for attribution. [overrun_diag.c:200](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/overrun_diag.c:200), [threshold handling:234](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/overrun_diag.c:234)

My remedy order is:

1. **Identify and shorten the interference**, where practical. That improves every colour and other latency-sensitive work.
2. **Move scan bookkeeping behind the arm.** Keep column release, row select, settle, GPIO capture, row deselect and column restoration before it. Save the sample locally, then publish it and perform health/rig accounting after the arm, retaining the acquisition timestamp. That removes software work from the deadline path without trying to scan through a live PWM pulse. [scan_key_row:817](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:817)
3. **Terminal 1,279**, only if the remaining measurements justify it. It buys just **5.33 µs** while reducing brightness headroom to about 7%.

Moving the **entire electrical scan** after the arm is not a cheap reorder: releasing the shared columns would truncate the pulse. It needs a guaranteed post-pulse dark interval with enough time for scanning and preemption. The current latest-arm allowance leaves no such scan budget.

I would accept approximately one isolated omitted pulse per 3.4 seconds for release once the existing mixed-load and optical checks pass. I would keep 1,535 rather than spend the remaining headroom to chase an absolute zero. But “invisible” is not established by the count alone, and a longest global omission run of one does not exclude repeated omissions of the same row-colour on successive fields.

There is also a factual correction: **the record is not all red**. Its 89 omissions comprise **61 R, 15 B and 13 G**. Page 7 reports 87 earlier; the scripts read these sequentially, so the two additional omissions are consistent with different snapshot times. The 5c record likewise has nonzero B/G counts. Red is disproportionately vulnerable; it is not the only affected colour. [record-stage5d.txt:1](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/record-stage5d.txt:1), [record-stage5.txt:3](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/record-stage5.txt:3)

**3. The 8 ms result is consistent with the debounce/main-loop boundary—not a fundamental 2.25 ms sampling limit.**

All 100 presses and releases reached the scanner, and all 200 raw transitions reached the main-loop consumer. Only 88 presses reached `process_record_kb`. That strongly supports the stated debounce explanation for these ordinary keys. The field called `cooked_changes` does **not** prove debounce accepted them: it counts changed rows before debounce. [presser result:12](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/presser-gate-stage5.json:12), [health.c:123](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/health.c:123)

The improvement follows qualitatively from the faster matrix. At 4.806 ms, an approximately 8.1 ms physical closure can appear in the sampled matrix for only one 4.806 ms period—shorter than debounce. At 2.25 ms it ordinarily spans three or four periods, 6.75 or 9 ms.

However, debounce runs when the **main loop** consumes and checks that state, not at every row interrupt. Consumer delay, the next check after expiry and millisecond quantization still matter. Thus the cadence explains improved capture probability; it does not derive **88%**. I would retain 10 ms as the demonstrated reliable dwell, without shortening debounce to make the 8 ms batch green. [sym_defer_pk.c:37](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/debounce/sym_defer_pk.c:37)

That presser result belongs to **5c**. It is encouraging evidence for 5d, but does not itself validate 5d’s shortened settle.

**4. The most consequential gaps are in what the measurements are claimed to establish.**

- **49.5 µs/39.6% is not a 300-second average in this runner.** After the 300-second hold, `ak820 health --isr` takes a **two-second pair**. Mean, rate and share come from that pair; min/max are retained extrema. This does not make the result implausible, but the populations differ. The scheduler counts also continue through the readout, so they do not isolate every omission to untouched quiet time. [stage5_flash.sh:60](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/stage5_flash.sh:60), [macOS CLI:177](/Users/jdlien/code/ak820-pro/ak820-agent/src/platform/macos/cli.rs:177), [rate calculation:612](/Users/jdlien/code/ak820-pro/ak820-agent/src/health.rs:612)

- **Full-white total current is well preserved; incremental LED current within 0.4% is not independently established.** The runner subtracts **4b’s 31.1 mA dark reference**, without measuring a new dark hold. Changed CPU occupancy can change that base. The literal gate also requires individual colours, value 64, fixed-exposure brightness and the model refit. One full-white hold cannot close those. [stage5_flash.sh:69](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/stage5_flash.sh:69), [gate:1304](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1304)

- **The low-code gate has a concrete reason to exist.** Code 1 becomes five ticks. Against 4b’s ten ticks, cadence-normalized duty changes by `5/2250 ÷ (10/4806) = 1.068`: **+6.8% before transistor effects**. Full-white calibration does not establish low-end preservation. Digital monotonicity also cannot establish optical monotonicity at approximately 104 ns pulses. [width definition:146](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:146)

- **The camera supports the narrow writer gate, not the claimed attribution of the other dips.** The raw report describes the 10.425 s and 10.450 s events as **two and three frames**, whereas the README calls them single-frame events. “One omitted slot is 5.5% of a field, therefore two make an 11% camera dip” also assumes exposure integration, spatial weighting and colour weighting that were not established. The seconds redraw is a plausible cause; the clip does not count its omitted slots. [camera report:35](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/camera-write-stage5d-dips.txt:35), [README:1253](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/README.md:1253)

- **A bounded latency tail has not been demonstrated by a maximum alone.** Page 7 drops boundary-crossing elapsed samples—four here—and its cumulative sum wrapped. Page 4 supplies useful inclusive extrema, but the wrapper bound, tick-rate/gap result, SPI DMA size sweep and mixed-load distribution remain relevant. The clock gate also includes transaction timing, bracket/release accuracy and stuck-bus recovery, beyond filming two writes. [rowisr.c:1201](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1201), [clock gates:1286](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1286)

The 35 timeouts out of 73 transmissions likewise remain **unclassified**, rather than demonstrated harmless idle-link behaviour. The owed radio-kind comparison is the right discriminator.

Read-only inspection included the archived 5d ELF. No files changed, builds run or board accessed.