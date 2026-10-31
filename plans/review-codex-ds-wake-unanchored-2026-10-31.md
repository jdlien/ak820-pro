# Codex: the 10-28 watchdog reset in a deep sleep, unanchored (2026-10-31)

A second opinion on the reset on black (gremlin's board) ~8 min into an
untouched deep sleep (GREMLIN-RESULTS §21; BACKLOG, "A watchdog reset inside
a deep sleep"). Codex (gpt-6-astra, xhigh, read-only) was given the facts and
the measurements but not the leads (a)-(c), and read the working tree
(`icon-only`, identical to the incident's `c4bc0852` in sleep.c, watchdog*,
power.c, fault.c, drivers/, platforms/ and the chibios-contrib pin). It did
not know about `gremlin/ds-phase`, whose phases 28-31 already cover much of
its "most informative next diagnostic". Its companion is
`review-fable-ds-wake-unanchored-2026-10-31.md`; the prompt
`review-prompt-ds-wake-unanchored.txt`.

Checked afterwards: its CT16B3 finding is right. `pwm_tick_startI()`
(`sleep.c:607`, before the unlock) calls `gptStartContinuousI()`, whose
`CT16B3_ResetTimer()` spins on `while (TMRCTRL & CRST)` with no bound
(`lib/chibios-contrib/.../CT/sn32_ct.h:421-424`), under the lock. In
`ds-phase` that is inside phase 30 (restore).

## The review, verbatim

**The record establishes a watchdog expiry while the main thread was inside `deep_sleep()`. It does not establish that the CPU was still executing WFI.** My leading possibilities are a failed RTC wake/flash return, or an unnoticed full wake followed by a peripheral interrupt hang. I found no documented, deterministic eight-minute watchdog mechanism.

I read only repository files and made no changes or device accesses. Manual page references below come from [docs/sn32f299.md](/Users/jdlien/code/ak820-pro/docs/sn32f299.md), including its distinctions between documented behaviour, measurements, and hypotheses.

For the longer references below:

- **B** = `qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/`
- **L** = `qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/`

**What the timing and record constrain**

The important sequence is:

```c
/* ak820pro.c:668, 673, 678 */
watchdog_kick();
flash_tidy_task();
sleep_task();
```

Production sleep then calls:

```c
/* sleep.c:963–965 */
if (b == 0 && rtc_sleep_prepare()) {
    battery_sleep_enter();
    deep_sleep(DS_BACKSTOP_S, false, 0);
}
```

And the recorded scope starts here:

```c
/* sleep.c:433–436 */
static bool deep_sleep(uint32_t cap_s, bool no_feed, uint32_t preset_s) {
    WDT_SCOPE(WDT_SITE_DEEP_SLEEP);
    static volatile uint32_t sacrificial;
    sacrificial++;
```

References: [housekeeping](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:665), [sleep admission](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:949), [scope entry](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:433).

Consequently:

- **The final PCF read precedes site 27.** An ordinary hang in that read would not produce this record.
- Site 27 includes shutdown, every RTC wake, clock/peripheral restoration, the interrupt unmask, and `recovery_begin()`.
- The scope remains 27 at `chSysUnlock()` on line 612. An ISR that never returns there leaves exactly this main-thread breadcrumb.
- The production call explicitly supplies `no_feed=false`, `preset_s=0`, and the daily backstop. Leftover diagnostic arm parameters cannot silently change those arguments.

The sleep loop feeds on every observed RTC second:

```c
/* sleep.c:537–540 */
bool second = take_second();
if (second) {
    if (!no_feed) SN_WDT->FEED = (mskWDT_WDKEY | mskWDT_FV);
    secs++;
```

Your unfed measurements rule out the old inference that “RTC keeps ILRC running, therefore WDT counts asleep.” The MCU notes expressly retract that inference, although an older watchdog table still repeats it.

**Therefore, the ordinary explanation needs the watchdog to resume counting and then go unserviced.** That could happen during a failed RTC wake or during full wake recovery. If it then counted normally for approximately 11.5 seconds, the failing transition was approximately 11.5 seconds before the inferred reset—not necessarily at sleep entry.

The frozen retained uptime is the last **housekeeping-entry** timestamp, not a live CPU-progress timestamp. It remains unchanged throughout all these paths.

**Ranked mechanisms**

This is a tentative plausibility ranking. The electrical cause in item 5 could trigger several of the software failure paths above it; these are not all independent explanations.

**1. Failure returning from an RTC wake: flash fetch, flash bus, or wake-clock malfunction**

This best fits a failure arising minutes into an otherwise untouched sleep **without requiring a separate GPIO wake**.

The code wakes approximately once per counted second, executes a short SRAM routine, then returns to flash:

```c
/* sleep.c:329–335 */
__attribute__((section(".ramtext"), noinline, long_call))
static void ds_deep_wfi(...) {
    *pmu_ctrl = 2u;
    __DSB();
    __WFI();
    *pmu_ctrl = 0u;
    for (uint32_t d = 260u; d; d--) __asm volatile("");
    (void)*flash;
}
```

The call is at [sleep.c:535](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:529), immediately before reading GPIO/RTC status and feeding.

Supporting evidence:

- Manual pp. **75–78** describe flash power-down and oscillator restart, but do not specify a reliable flash-fetch-ready indication or the complete flash wake timing.
- MCU-notes **erratum 37** records an actual, placement-dependent failure executing flash immediately after deep sleep.
- The present SRAM workaround is deliberate, but its own comment says:

  > “How long the flash needs is not measured either”

  [sleep.c:313–335](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:313).

Possible endings that fit site 27 are a stalled flash/bus access, execution of valid but wrong instructions that loop, or a fault whose vector/recorder cannot itself be fetched. **An ordinary successfully recorded HardFault would instead produce site 23**, so “a flash glitch caused a normal HardFault” is insufficient.

Why it fits—or does not:

- An eight-minute sleep provides hundreds of flash-return opportunities; no human input is needed.
- A marginal wake time could vary with unit, temperature, supply, or electrical environment.
- **The specific cable and distant-host connections are guesses**, unless they alter supply/noise.
- The workaround and extensive successful sleeps are substantial evidence against a routine or deterministic recurrence of the old bug. The original alignment defect is already addressed.

Cheapest useful tests:

1. **Host-only:** disassemble the incident build’s ELF and verify that the complete WFI-to-delay-to-dummy-read path is in SRAM, with no flash literal/helper access before the intended read. Use the actual incident binary: the local `c4bc085271` artifact has token `0xbad2475a`, whereas CLAUDE.md identifies the incident build as `0x189635f2`.
2. **Diagnostic firmware:** retain phases immediately before WFI, immediately after WFI **from SRAM**, after the dummy read, and after return to flash.
3. A stronger A/B keeps the entire periodic wake/status/feed loop in SRAM, returning to flash only on full wake. A failure recorded after successful flash return would move the investigation elsewhere. A longer delay alone producing several clean sleeps would be weak evidence, given the rarity.

**2. An unnoticed full wake followed by a USB interrupt storm or USB register-access hang**

This has the strongest specific connection to **physically removing the cable**, but it needs two events: something must end the sleep, then USB must prevent main-thread progress.

Sleep disables all external NVIC lines, clears their pending bits, and enables only P0/P1/P2/RTC:

```c
/* sleep.c:477–495 */
uint32_t iser = NVIC->ISER[0];
NVIC->ICER[0] = 0xFFFFFFFFu;
NVIC->ICPR[0] = 0xFFFFFFFFu;
...
NVIC->ISER[0] = wake_irqs;
```

It does **not** equivalently stop the USB driver or clear all USB peripheral causes. On full wake:

```c
/* sleep.c:589, 608, 612 */
NVIC->ISER[0] = iser;
...
bool phy_off = usb_phy_onI();
...
chSysUnlock();
```

[Wake restoration](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:582).

Two distinct USB failure paths exist:

- **Repeated IRQ entry.** `usb_lld_serve_interrupt()` reads `INSTS` and processes reset/suspend/resume/wakeup in an `if/else if` chain. A cause that continually reasserts can keep the CPU servicing USB instead of returning to site 27’s caller.
- **An unbounded endpoint SRAM handshake.** The configured driver defaults to indirect SRAM access:

  ```c
  /* L/USB/hal_usb_lld.h:91 */
  #define SN32_USB_DIRECT_SRAM FALSE
  ```

  Its FIFO routines include:

  ```c
  /* L/USB/hal_usb_lld.c:147–148 */
  SN32_USB->RWSTATUS = 0x02;
  while (SN32_USB->RWSTATUS & 0x02);
  ```

  The write counterpart waits on bit 0. An endpoint/setup event reaching these routines can wedge inside the USB ISR if the handshake never finishes.

References: [USB ISR](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:218), [FIFO waits](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.c:122), [configuration](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/USB/hal_usb_lld.h:87).

Manual support:

- p. **245**: PMU sleep automatically disables the PHY.
- pp. **241–244**: bus reset, suspend, resume and wake status/interrupts.
- p. **19**: USB requires 48 MHz. During periodic RTC wakes, this code remains on IHRC with PLL explicitly disabled.

Why it fits—or does not:

- A removed cable changes termination, capacitance and grounding compared with a disabled hub port. **Neither configuration should be assumed electrically identical.**
- The code retains USB configuration across the low-clock interval, then re-enables the PHY and its old interrupts.
- However, cable-out does **not** prove that D+/D− are simply floating: internal pull resistors and retained configuration matter.
- The initial unplug was two seconds earlier; a normal one-time suspend interrupt should already have been handled. This theory needs a later/reasserted cause, anomalous peripheral state, or a bad endpoint event—not merely “the unplug IRQ was pending.”
- **USB is not in the configured deep-sleep wake set.** The documented deep-sleep sources do not establish that USB directly woke this board. A key/knob/CHRG glitch or stray-threshold exit must normally precede this mechanism.
- The distant Bluetooth host has no direct explanatory role.

Cheapest tests:

- Retain a **before-unmask/after-unmask** phase plus USB ISR entry/exit state and the `INSTS` value already read by the handler.
- Bound the FIFO waits in a diagnostic build and retain `RWSTATUS`, `CFG`, and the endpoint operation when the bound is hit.
- Compare full disconnection with relay/uhubctl cuts, keeping host proximity constant. A diagnostic run with USB IRQs held disabled through the first post-wake main-loop checkpoint cleanly separates USB from pre-unmask failures.

**3. An unnoticed full wake followed by a stuck UART2 interrupt**

This has the strongest connection to the **distant Bluetooth host**, but ordinary dropped frames or retries are not enough.

Sleep deliberately disables RX:

```c
/* sleep.c:460–461 */
uint32_t uart_ctrl = SN_UART2->CTRL;
SN_UART2->CTRL = uart_ctrl & ~UART_CTRL_RXEN;
```

Wake restores it, drains at most 32 bytes, reads line status, resets the software input queue, then unmasks:

```c
/* sleep.c:596–599 */
SN_UART2->CTRL = uart_ctrl;
for (uint8_t k = 0; k < 32u && (SN_UART2->LS & UART_LS_RDR); k++)
    (void)SN_UART2->RB;
(void)SN_UART2->LS;
iqResetI(&SD2.iqueue);
```

The UART ISR has unbounded loops:

```c
/* L/UART/hal_serial_lld.c:301 */
while ((ii & UART_Interrupt_Status) == UART_Interrupt_Pending) {

/* :314 */
while (ls & UART_LineStatus_RDR) {
```

[UART handler](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/UART/hal_serial_lld.c:296).

If interrupt status remains pending without a condition the handler successfully retires, or RDR remains asserted indefinitely, the handler never returns. UART2 is priority **0**, equal to SysTick and above USB, GPT, RGB and RTC: [mcuconf.h:77–96](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/mcuconf.h:77). It can therefore also prevent the timer handler from running.

Manual pp. **176–188**, particularly p. **182**, support the UART status/error handling requirements. They do not document a guarantee that this particular disable/clock-stop/re-enable sequence recovers every receiver state.

Why it fits—or does not:

- A weak/lost host can change autonomous module traffic and connection state while the SN32 sleeps.
- Re-enabling RX mid-frame can produce partial bytes and errors. The code attempts recovery, but does not reset/reinitialize the hardware FIFO.
- **Normal 115200-baud traffic, isolated overruns, or a few `5B` frames do not demonstrate a sustained ISR lockup.** This needs a stuck condition, pathological interrupt behaviour, or an additional bug.
- P1.6/UART RX is not an enabled GPIO wake source; RX is disabled. A radio frame alone is therefore not a documented route into this handler during the periodic RTC-only loop.
- The PCF transfer could leave a receiver/error condition before entry, but that does not explain the eight-minute delay without a later full wake.

Cheapest test: add an ISR iteration budget that preserves the already-read `II`, `LS`, and `IE` values when exhausted. Compare wake while the bonded host is available versus deliberately unavailable, and A/B a hardware RX FIFO reset before RX re-enable. A retained pre-unmask failure would exclude this ISR route.

**4. Full wake hangs resetting CT16B3: a concrete unbounded wait**

This is the clearest unbounded wait directly inside the locked wake sequence.

The call chain is:

```text
B/sleep.c:607                 pwm_tick_startI()
B/indicators.c:217            gptStartContinuousI(&GPTD4, ...)
L/CT/hal_gpt_lld.c:482        CT16B3_ResetTimer()
L/CT/sn32_ct.h:421–424        reset-and-spin macro
```

The macro is:

```c
timer->config.TMRCTRL = (mskCT16_CRST);
while (timer->config.TMRCTRL & mskCT16_CRST);
```

References: [restart](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/indicators.c:214), [LLD call](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/hal_gpt_lld.c:480), [unbounded wait](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/CT/sn32_ct.h:421).

Manual p. **125** describes CRST as a synchronous, self-clearing reset. If the timer clock/reset machinery fails to resume, this loop has no escape. PRIMASK is still set; no handler feeds the watchdog; site 27 remains intact.

What is missing: **I found no documented reason CRST should fail after a successful clock restore**, and nothing in this loop singles out cable removal or Bluetooth range. It also requires a full wake at approximately the failure time.

Cheapest test: retain a phase immediately before and after this reset; replace the diagnostic wait with a fixed iteration bound that records TMRCTRL and the clock gates before allowing the watchdog to recover. That would identify this path decisively.

**5. A battery/regulator/ground disturbance during sleep causes one of those failures**

This is a physical explanation, not a demonstrated firmware defect.

Manual p. **78** says LVD is disabled in Deep-sleep. Thus **absence of LVDRSTF does not exclude a transient supply disturbance during sleep**. A disturbance could corrupt non-retained working state, leave a clock/peripheral malfunctioning, or compromise the flash wake. The eventual reset can still be genuinely caused by WDT.

Relevant code leaves the radio operating independently, disables the ADC during sleep, and cannot sample the supply until recovery. The MCU notes also identify unresolved VREG33/VDDIO1 behaviour: pp. **78, 245, 265**, [voltage-domain discussion](/Users/jdlien/code/ak820-pro/docs/sn32f299.md:502).

Fit:

- Physical cable removal removes electrical connections that a powered-off hub cable may preserve.
- A distant host could change radio activity/current demand.
- Unit-specific marginality and rarity fit better than a deterministic sleep sequencing bug.
- **Those connections are hypotheses.** There is no captured rail transient or documented CH582F eight-minute event here.
- A sufficiently severe brownout after wake would more naturally produce LVD/POR flags or invalid retained data, which this incident lacks.

Cheapest useful test is a bench capture of MCU VDD and the relevant 3.3 V rail, triggered on a dip, during long cable-out/host-unavailable sleeps. A low-rate battery logger alone cannot exclude a short rail transient. Keep this separate from the ongoing battery-test unit.

**6. Another restored interrupt or kernel/context-switch path prevents return**

These are lower-probability residual mechanisms, but site 27 cannot exclude them.

- **SPI interrupt storm/stuck FIFO.** Sleep admission checks software bus idleness, SPI BUSY and DMAEN, but does not require every SPI interrupt cause/FIFO flag to be clear. The idle SPI handler drains at most 16 words and clears the threshold flag; a hardware condition that continually reasserts it could cause repeated entries. The active handler has an unbounded RX drain. See [L/SPI/hal_spi_v2_lld.c:105–127](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c:105). Normal DMA-in-flight hangs are strongly disfavoured by admission.
- **SysTick/virtual-timer failure.** Wake deliberately pends SysTick at `sleep.c:605`. Its handler enters the kernel timer list, whose processing loop and callbacks can fail if their state is corrupted. See `L/SysTick/hal_st_lld.c:189–204` and `lib/chibios/os/rt/src/chvt.c:501–539`. Stopping CT16B5 across sleep is the correct protection against normal elapsed-time wrap; I found no ordinary eight-minute timer catch-up bug.
- **NMI/context-switch lockup.** ChibiOS uses NMI to complete exception return. Its assembly explicitly waits after requesting NMI:

  ```asm
  /* lib/chibios/os/common/ports/ARMv6-M/compilers/GCC/chcoreasm.S:140–144 */
  str r3, [r2, #0]
  ...
  .L1: b .L1
  ```

  The corresponding NMI handler manipulates PSP and unlocks. A fault inside NMI can lock up without the board’s HardFault recorder; `B/fault.c:14–16` explicitly acknowledges this. [NMI implementation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/lib/chibios/os/common/ports/ARMv6-M/chcore.c:54).

All require an additional malfunction or corruption; I found no concrete trigger connecting them to this incident. None naturally explains eight minutes.

Cheapest test: an independent retained “active IRQ/phase” field, plus stack high-water/canary checks and bounded peripheral loops. Do not use the ordinary main-thread scope field for transient ISR bookkeeping.

**7. Abnormal watchdog/PMU behaviour, failed feeding, or a failed software-reset request**

These remain logically possible but rank last.

The feed value is correct and matches the normal WDT LLD:

```c
/* L/WDT/hal_wdg_lld.c:117 */
wdgp->wdg->FEED = (mskWDT_WDKEY | mskWDT_FV);
```

The prescaler is correctly reset after configuration in `B/watchdog.c:96–99`. Manual pp. **71, 150–153** confirm the encoding and keyed feed. The actual formula uses **TC+1**, making the source’s TC-only calculation slightly inaccurate, not minutes inaccurate.

To explain this incident directly, one would need undocumented behaviour such as:

- WDT clocking unexpectedly resuming while the CPU remains effectively asleep;
- feed writes ceasing to take effect combined with substantial awake time;
- corrupted WDT/PMU configuration;
- a clock-timeout path calling `NVIC_SystemReset()`, but the reset request failing so its terminal spin eventually reaches WDT expiry.

There is no positive evidence for these. The 600-counted-second unfed test is particularly strong against simple cumulative watchdog counting during normal periodic wakes.

Cheapest test: retain periodic feed-progress and WDT/clock configuration snapshots in the same environmental conditions. Another normal unfed sleep only repeats evidence already obtained; it does not distinguish a rare mode transition.

**Explanations that do not fit by themselves**

- **“The RTC stopped.”** With WDT stopped in Deep-sleep, that ordinarily produces a board that stays asleep, not a watchdog reset.
- **“A stray interrupt made WFI return continuously.”** `sleep.c:559` exits after 1,000 non-second strays. The SRAM delay alone contributes roughly 0.108 seconds over 1,000 returns—not an 11.5-second spin. If RTC seconds continue, they feed the WDT. A stray storm can initiate recovery, but needs a second failure there.
- **“PLL failed to lock.”** `sleep.c:572–580` bounds the waits and calls `NVIC_SystemReset()`. Normal execution of those paths predicts the software-reset signature, not this WDT record.
- **“The 13–15% slow RTC made the feed interval too long.”** That modest slowdown cannot bridge a one-second feed cadence to an approximately 11.5-second timeout; moreover WDT pauses during the sleeping part.
- **“Eight minutes hit a counter boundary.”** Sleep seconds and local stray counters are 32-bit; the production backstop is 86,400 counted seconds. No eight-minute boundary appears in this path.
- **“The PCF write was still running asleep.”** Admission requires `ps_state == PS_IDLE`, no pending write, no slew/reload, and no acquisition/recovery. See [rtc.c:1883–1907](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1883). The external PCF is also distinct from the SN32 RTC that wakes the CPU.
- **“A lost Bluetooth ACK blocked the sleeping main loop.”** The protocol task is not executing there. TX is checked quiet twice; RX is off.

**Could the record mislead?**

**Yes about the failing instruction; much less readily about the active main-thread scope.**

1. **Site 27 spans the whole function.** It remains active through the unmask and `recovery_begin()` at lines 612–626. A USB/UART/SPI/kernel hang there is legitimately recorded as deep sleep. The enum comment saying “the reset happened asleep” is stronger than the implementation supports.

2. **Ordinary interrupts do not update the scope.** That is intentional: [watchdog_record.h:6–7](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.h:6). The record names interrupted main-thread work, not the ISR responsible.

3. **A normal return should remove site 27.** `WDT_SCOPE` uses GCC cleanup, and `watchdog_record_leave()` restores the saved path. After `deep_sleep()` returns, `rtc_pass_mark()` and `pass_t0` also write SRAM. Thus the known “last SRAM write lost at reset” effect is **not a persuasive explanation for site 27 surviving many subsequent normal passes**. There are later writes to drain the restoration.

4. **Entry specifically protects against the lost-write effect.** The sacrificial increment at `sleep.c:436` follows the breadcrumb. Site 27 is not merely an unflushed last store.

5. **The validation is useful but not comprehensive memory integrity.**

   ```c
   /* watchdog_record.c:62, 71–72 */
   bool warm = (magic == RECORD_MAGIC || terminal) && !(rstst & RST_POWER);
   bool valid = warm && count_ok && (rstst & RST_WDT) && path_ok(path) &&
                (uint8_t)path != WDT_SITE_NONE;
   ```

   [Boot validation](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.c:54).

   This rejects bad magic, LVD/POR boots, invalid counts and a broken path complement. It does not checksum uptime, stacks, code in SRAM, or unrelated RAM. Corruption could leave a perfectly valid site-27 record while damaging something else.

6. **Normal fault recording should replace 27.** HardFault, unhandled exception and ChibiOS halt use terminal sites 23/24/25 and a separate magic. `commit_terminal()` includes its own sacrificial write. An ordinary captured fault is therefore disfavoured. Flash/vector-fetch failure, a failure before terminal commit, or an NMI lockup remain exceptions.

7. **RSTST 0x03 is convincing here.** `watchdog_boot_check()` captures the low five bits and then writes zero to clear all sticky flags: [watchdog.c:64–74](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog.c:64). Manual pp. **64–65** confirm write-zero-to-clear and SWRSTF’s reset value. There is no ordinary code path by which a later pure software reset should inherit an old WDT flag after two hours of normal operation. A hardware/ROM anomaly would be an additional unsupported hypothesis.

8. **“Consecutive resets 1” does not mean “first crash ever.”** The retained count ages out after ten minutes of uptime (`watchdog_record.c:112`, `watchdog_record.h:82`). The frozen crash report also intentionally remains visible throughout the following boot; reading it later does not date the crash.

**Other problems and weaknesses worth fixing or measuring**

- **The timer reset and USB/UART loops need bounds.** These are concrete liveness gaps, even if none caused this incident. A main-loop recovery deadline cannot rescue execution stuck inside them.

- **The ten-second recovery bound starts too late to cover early wake failures.** `RC_MAX_MS` is checked by later calls to `recovery_task()`. It does not protect clock restoration, the CT16B3 reset, the first unmask, or a handler that never returns. Calling the *whole wake* bounded would be inaccurate.

- **USB is not fully quiesced before removing its required clock.** NVIC masking prevents handlers; it does not reset the SIE, stop every peripheral state machine, or clear their underlying causes. Periodic RTC wakes run at 12 MHz while USB configuration remains retained. The consequences are undocumented, but this deserves explicit measurement.

- **USB wake restoration is incomplete relative to the USB ISR.** `usb_phy_onI()` restores only PHY_EN. The suspend ISR clears **both PHY_EN and ESD_EN**, while resume/wakeup restores both. See `sleep.c:70–73` against `L/USB/hal_usb_lld.c:240–254`. A cable-pull suspend can therefore leave a different configuration from another sleep-entry path. Whether that affects anything beyond protection/reconnection needs measurement.

- **GPT register writes contain existing hazards.** `gpt_lld_stop_timer()` uses a read-modify-write on the write-only interrupt-clear register and writes MCTRL without explicitly supplying its required key (`hal_gpt_lld.c:517–523`). The board compensates for the stop’s interrupt clear at `indicators.c:208`, and stops CEN, limiting the immediate effect. Start still contains the same IC read-modify-write at line 495. Manual pp. **126–149** require the timer register keys; literal clear writes are the reliable approach.

- **The wake set is assembled with `IE |= mask`, not replacement of the complete port enables.** An existing unrelated enable on P0/P1/P2 would survive and could produce unexplained returns. The dev stray diagnostic explicitly checks this. I found no normal current-board owner that should leave such enables set, so this is a latent assumption, not proof of a present storm.

- **Any enabled GPIO edge can initiate recovery without a person touching the board.** There is no noise qualification before accepting column/knob/CHRG RIS bits. A short electrical glitch can therefore supply the missing first event for candidates 2–4. “Untouched” does not imply “no full-wake attempt.”

- **Cable insertion is not universally covered by CHRG falling.** A full battery/non-charging insertion may not produce that edge. USB IRQ is disabled during the sleep, and periodic RTC wakes do not inspect USB frames to decide to exit. The documented wake path can therefore miss some insertions unless another source wakes it.

- **Radio state can become stale across sleep.** `ch582_sleep_wake()` resets parser/channel state and marks battery data stale, but does not establish a fresh connection state: [ch582f_ajazz.c:1401–1405](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1401). A disconnect or connection transition sent while RX is off can be lost. The wireless notes say there is no reliable state-query command. That explains possible misleading link UI after wake, not this watchdog reset by itself.

- **A UART break disables line-status interrupts without a sleep-time restoration.** `hal_serial_lld.c:304–309` clears `UART_ReceiveLine`; wake restores CTRL, not IE. A break can leave subsequent error reporting changed until reinitialization.

- **The useful wake diagnostics are written after the dangerous boundary.** `ds_secs`, `ds_strays`, and the wake ring are finalized after `chSysUnlock()`. A hang at or before that point loses exactly the distinction needed here; those ordinary RAM diagnostics also do not survive reboot.

**The most informative next diagnostic**

I would first add a small, properly reserved reset-retained record containing:

- sleep phase, counted seconds and stray count;
- accepted wake reason and GPIO RIS masks;
- before/after markers for flash return, PLL restoration, CT16B3 reset and interrupt unmask;
- active ISR and the status value at a bounded-loop failure.

Every terminal breadcrumb needs the existing sacrificial-write treatment. This gives a much sharper answer than collecting more undifferentiated successful sleeps.

Then run long trials varying **physical cable removal versus hub cuts**, and **host available versus unavailable**, on both units, while holding the entry sequence constant. Include the already-expired USB idle ladder and pending-PCF-write case. A 95-second success tests entry well; it provides limited evidence about a failure first observed roughly eight minutes later.