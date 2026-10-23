# Codex review: the configuration menu's build plan (2026-10-23)

The plan reviewed is [`CONFIG-MENU-BUILD-PLAN.md`](CONFIG-MENU-BUILD-PLAN.md),
revision 1 (`9cb838f`). The model was gpt-6-astra at xhigh, read-only, given
the prompt in [`review-prompt-config-menu-build-plan.txt`](review-prompt-config-menu-build-plan.txt).
Codex's answer follows verbatim, then the dispositions. Revision 2 of the
plan carries the fixes.

---

**I found must-fix issues.** The mono-blit approach is feasible, and the existing dashboard restore is worth reusing. The main blockers are ownership transitions, input-release ownership, RGB persistence, Bluetooth pairing, and dependencies of the EEPROM expansion.

I read only inside the requested directory. I made no changes and ran no hardware operations.

The ten claims in [“What the code says”](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:40) check out as follows:

| Claim | Verdict |
|---|---|
| **1. RAM, lines 44–53** | **Correct measurements; conditional conclusion.** The checked-in dev ELF has a 32-byte heap gap; the corresponding daily build has 2,160 bytes. `log_buf` is 12,960 bytes; both debug text arrays are 198 bytes. Sharing them is safe only after enforcing exclusive ownership, including Fn+D and dev-hook entry. |
| **2. DMA and CPU drawing, lines 54–63** | **Mechanics correct; performance inference incomplete.** This DMA cannot source pixels from SRAM. `lcd_blit_ram()` quiesces, sets the window and sends chunks as described. Flash DMA still has CPU setup cost. The small-tile measurements do not establish that a whole row’s additional cost is mostly fixed. |
| **3. Debug ownership, lines 64–72** | **Wrong about the “single gate”; incomplete about restoration.** Housekeeping is not the only paint entry: the pump, wake paint, logos, animation and restore matter independently. Fourteen stages are not fourteen passes or a guarantee that all queued work has finished. |
| **4. Known ownership gaps, lines 73–83** | **Correct, but incomplete.** Logos and `display_bus_idle()` have the stated gaps. Suppressing `param_status_task()` alone misses direct overlay posts and already-pending overlay state. |
| **5. Knob and hook ordering, lines 84–93** | **Correct at the board hook; incomplete upstream.** Encoder events have both halves, and the hook precedes VIA/RGB processing. However, mapping and action-tapping processing precede it, and encoder.c’s waits remain even when the hook consumes an event. |
| **6. Setters, lines 94–107** | **Mostly correct.** The important omissions are RGB setters that do nothing while RGB is disabled, the existing dev-only `power_set_mode()` that should be promoted, and asynchronous Bluetooth control semantics. |
| **7. RGB dirty/flush behavior, lines 108–116** | **Dirty semantics correct; proposed protection insufficient.** `_noeeprom` does not clear an earlier dirty flag. The board gate protects ordinary deferred flushing, but VIA’s force-flush bypasses it. Concurrent setting changes also make blanket restoration unsafe. |
| **8. Keyboard EEPROM, lines 117–122** | **Partly wrong.** Seven bytes/version 4 and the five-second settling/blocker are correct. A version mismatch zeroes the caller’s RAM buffer on read; it does not physically zero the EEPROM block “once.” Growing the block also affects write attribution and downstream VIA offsets. |
| **9. Activity, lines 123–131** | **Incomplete.** Detents update encoder activity; knob presses update matrix activity. Direct dev-hook injection need not update either. The debug exception lifts the Minimal-mode cap; it does not override a user brightness of zero or `display_powered == false`. Therefore “open menu stays awake” is conditional. |
| **10. Identity and uptime, lines 132–135** | **Correct.** The build token/hash sources exist, and `rtc_seconds_since_boot()` includes accounted sleep time. |

The findings below include the concrete failure and proposed correction.

1. **Must-fix — replace independent ownership flags with explicit transitions.**  
   Plan: [lines 181–198](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:181). Source: [display.c:1174](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1174).

   Adding `menu_active` to paint gates does not prevent Fn+D or its dev hook from setting `debug_active` while the menu is active. The debug composer can then overwrite the shared text arrays. Also, “close that page first” cannot mean calling `display_debug_toggle()`: from Health, that opens Camera.

   Use explicit enter/leave/handoff functions, preferably with one owner enum. Route Fn+D, Diagnostics, dev hooks and animation through them. Specify which owner receives knob input during Diagnostics, reset the shared buffers and paint state on handoff, and cancel or supersede an unfinished dashboard restore when reopening. This belongs in **P1**, even if the Diagnostics menu entries arrive in P2.

2. **Should-fix — retain the restore, but make hidden-state updates and restoration explicit.**  
   Plan: [lines 196–205](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:196). Source: [display.c:1394](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:1394), [display.c:2560](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:2560).

   The 14-stage restore is the right common dashboard restoration path. Its lock stage can repeat, the battery stage paints only one component, and queued glyphs remain afterward. Do not equate `debug_exit_step == 0` with a fully restored panel.

   There are several missing details:

   - Direct LCD/clock/power key paths call `display_set_param_status()` without going through the suppressed poller. An existing overlay and `param_force_kc` can also survive entry. Suppress or classify posts centrally and clear/re-prime the appropriate state.
   - The restore’s text stage does not first call `conn_status_update()`. Refresh status selection and expiry before restoring text, so an expired cached alert or parameter message does not briefly return.
   - Logo setters must retain their RAM updates. If gated during restoration after their stage has passed, mark them dirty or schedule another bounded update; merely dropping the paint leaves an old logo.
   - Gating dashboard self-heal is correct, but failed menu big-glyph DMA also needs menu-local invalidation and retry.

   The other ownership paths are largely compatible: text slots, playback updates, alerts, pairing hints and lock-channel updates store state; the relevant ISR paths update state or GPIO rather than drawing LCD pixels. Keep those updates running while gating their painters, including both glyph queues, wake paint and the second-edge housekeeping call.

3. **Must-fix — define capture ownership through the matching release, including after closing.**  
   Plan: [lines 249–264](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:249). Source: [ak820pro.c:425](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/ak820pro.c:425).

   The opening release is mentioned, but the **closing** release is not covered by the closed-state rule, “Everything else passes.” Fn+knob closing, a root-level long Back, or timeout while held can clear `menu_active` before release. A VIA mapping such as `DBG_PAGE` can then execute a release action whose press the menu swallowed.

   Store whether each relevant press was captured, and consume its matching release regardless of current owner or Fn state. Conversely, forward a release whose press was previously forwarded. Opening release must not become a click in the new menu.

   Also handle release at or beyond 600 ms when the periodic hold task has not fired yet: execute Back exactly once instead of losing the gesture. Ordinary held keys should continue through normally; do not clear the keyboard on ordinary menu entry or exit.

4. **Should-fix — the proposed hook does not fully isolate remapped input or existing repeat state.**  
   Plan: [lines 246–264](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:246). Source: [action.c:95](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/action.c:95), [param_overlay.c:82](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:82).

   Action tapping runs before `process_record_kb`; consumed presses can also affect weak mods and one-shot state. Consequently, position-based handling at this hook does not by itself guarantee identical behavior for arbitrary VIA mod-tap/layer-tap mappings. Capture the physical menu controls before tapping where necessary, or explicitly constrain and test the supported mappings.

   There is also a concrete repeat interaction: opening is swallowed before `param_repeat_process_record()`, so it bypasses the “another press cancels repetition” rule. A held lighting-adjust key can continue changing and saving a value during editing. Cancel that repeat explicitly on entry or apply the settings-conflict policy below.

   Detect Fn through the active `WINFN`/`MACFN` layer bits. The early hook correctly avoids starting new modified-consumer sequences, but keep `modified_consumer_task()` running so a burst begun before opening releases its modifiers.

5. **Must-fix — RGB preview needs a transaction policy covering forced saves and concurrent writers.**  
   Plan: [lines 270–279](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:270). Source: [eeconfig.h:177](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/eeconfig.h:177), [via.c:737](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/via.c:737).

   A VIA Save during preview calls `eeconfig_force_flush_rgb_matrix()` and persists the preview despite `rgb_matrix_eeprom_flush_allowed() == false`. Cancel afterward cannot undo that write.

   Separately, restoring the whole entry snapshot can erase a legitimate Fn/VIA change made during editing. Allowing that writer’s later flush can instead persist the preview. The same conflict exists when LCD hotkeys operate on a previewed brightness.

   A relatively simple policy is: **cancel the active edit before applying any external write to that setting/configuration**, and handle forced saves through that policy too. Alternatively, maintain committed and preview state separately. Preserve pre-existing dirty state; do not “fix” this by clearing QMK’s dirty flag.

   Explicitly define disabled-RGB behavior. In [rgb_matrix.c:605](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:605) and line 657, mode/HSV setters return while disabled. Editing those values can silently do nothing; restoration can fail if it disables RGB before restoring mode/HSV. Use an adapter with a deliberate restore order and restore the original enabled state last.

6. **Must-fix — “select, then enter pairing” can pair the wrong slot.**  
   Plan: [line 274](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:274). Source: [ch582f_ajazz.c:1530](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c:1530).

   While already pairing, selection starts the 700 ms cancel-pairing bounce. Immediately calling `ch582_enter_pairing()` replaces `PA_BOUNCE` with `PA_PAIR`; `A6 51` pairs whichever slot the module currently has selected. The return to the intended slot is lost.

   Implement pairing as an asynchronous radio operation that preserves the bounce/select sequence before sending pair commands. Expose requested, selecting, advertising, connected and failed states. `ch582_is_pairing()` alone is insufficient: it is optimistic initially and becomes false on connecting events even while a pair retry remains pending.

   Define cancellation for click, hold, Fn-close, timeout and slider change. `ch582_cancel_connect()` is **not** a pairing-cancel operation: it changes local routing flags without sending the required cancellation sequence or clearing the pending action. Use the documented A6 selection/bounce behavior.

7. **Must-fix — slot changes need an outgoing-report handoff.**  
   Plan: [lines 261–274](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:261). Source: [bt_ui.c:55](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:55), [bt_ui.c:119](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bt_ui.c:119).

   The slider explicitly releases the outgoing host before changing routing. Slot selection does not. Holding a key while selecting another Bluetooth slot can send its press to the old host and release to the new one. The pairing bounce can also briefly connect another bonded host while ordinary typing continues.

   Release and settle outgoing keyboard/consumer reports before issuing the switch, using bounded asynchronous work. Defer switching while other keys are held, or explicitly suspend report forwarding during the transition. Do not promise uninterrupted typing across a host switch.

   Test both A1 keyboard and A3 consumer reports. Bluetooth and 2.4G share this transport; testing USB alone misses these failures.

8. **Must-fix — brightness, sleep and timeout behavior need a single session contract.**  
   Plan: [lines 271–299](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:271). Source: [display.c:238](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:238), [sleep.c:240](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:240).

   A raw brightness floor does not overcome `display_powered == false`, and the Minimal-mode exception only changes the cap. Opening after Screen Off can therefore leave an invisible menu. Clamping the stored editing value to 1 also makes saving zero ambiguous.

   Keep the requested level—including zero—separate from a temporary menu visibility override. Apply that override consistently in the PWM path and effective-brightness reporting, preserve the wake hold, and remove it on every exit.

   Sleep currently has no menu/session blocker. If the menu is dark, Minimal can sleep before the two-minute backstop; `timer_read32()` then stops advancing. Add an explicit session blocker or close/cancel atomically before sleep. Do not overload `display_bus_idle()` with “menu exists,” since wake completion also uses it.

   Two minutes is a reasonable backstop, but use a 32-bit elapsed timer. Specify policy for Help, About, confirmation, pairing and Diagnostics—not just lists and editors. Otherwise a non-edit page can remain lit indefinitely. Hint repainting and host traffic should not count as menu input; actual typing should still count as power activity.

9. **Should-fix — menu entry can strand wake-paint completion.**  
   Plan: [line 185](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:185). Source: [display.c:3315](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3315).

   Gating `wake_paint_step()` while the menu owns the panel leaves `wake_batt_due`/`batt_dirty` outstanding. Adding the menu to `no_clock` in `display_wake_repainted()` does not satisfy the battery conditions. Opening during recovery can therefore keep the backlight held off until sleep.c’s 500 ms fallback.

   Either defer opening until recovery finishes, or make wake completion owner-aware and wait for the visible menu’s required paint instead of a hidden dashboard battery row.

10. **Should-fix — measure a bounded paint operation within the whole pass, not just a row on an idle panel.**  
    Plan: [lines 209–242](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:209). Source: [lcd_bus.c:131](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:131), [lcd_bus.c:689](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:689).

    **The mono primitive is feasible**, including reuse of the 512-byte scratch buffer. Expand pixels in raster order across the whole window, emit panel byte order, and keep interrupts enabled. Move the existing function-local buffer into shared scope rather than allocate another one.

    CPU mono and flash-DMA big glyphs can coexist safely if every CPU transaction quiesces **before** opening its window, and the pump defers an in-flight DMA using the existing bounded recovery. Otherwise the measured “row time” also includes waiting for earlier work. Preserve `pass_deferred` and `clock_ticked_this_pass`.

    The RTC I2C/port-A restriction remains relevant while SPI1 flash DMA runs. Keep the existing RTC busy checks and pass deferral; CPU mono painting on SPI0 does not justify disabling RTC service throughout the menu.

    The 1.12 ms wire calculation is correct. The 2–4 ms total remains unproven because FIFO servicing, chunk calls, expansion and same-priority SPI0/row-ISR contention also matter. Encoder handling still waits twice per detent and drains its queue in one invocation ([encoder.c:30](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/encoder.c:30)); consuming the records removes neither wait.

    Start with independently budgeted chunks—half-rows are a reasonable candidate—and choose full rows only from loaded measurements. Glyphs remain a slower-overall fallback with more windows. Count **row plus shapes plus DMA setup plus other pass work**. Also correct the wall-time estimates: the plan’s own 5 ms baseline plus 2–4 ms gives roughly 63–81 ms for nine passes, before entry clears.

11. **Must-fix — shapes and pixel damage need explicit rendering state.**  
    Plan: [lines 219–242](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:219). Visual source: [mockup:470](/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:470), [mockup:528](/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:528).

    Text comparison against `dbg_shown` cannot detect a selection-color change when the text is unchanged. Nor does it describe changed dots, bars, markers or partially painted big values. Track/invalidate attributes and shapes, and define when a partially painted row becomes “shown.” New navigation must supersede stale pending work.

    Do not allocate the 120×14 hue tile on the stack: RGB565 requires **3,360 bytes**, exceeding the entire 2 KB main stack. The QR’s scaled display footprint is larger still, despite its small packed source. Stream both through bounded scratch-buffer chunks; give shapes their own pass budget rather than appending arbitrary drawing after a text row.

    Match the actual geometry: the mockup’s content starts at y=15, its header separator is y=14, and editor glyphs are 23 pixels high. A generic `row * 14` grid can overwrite the separator or big values. Restoring the old hue marker requires restoring the gradient underneath it. Define single-byte IDs for the extra symbols rather than putting UTF-8 into the fixed character grid.

12. **Should-fix — reserve measured RAM; trimming the log does not enlarge either stack.**  
    Plan: [lines 330–340](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:330). Source: [battery.c:1352](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/battery.c:1352).

    Forty bytes is plausible for a carefully packed navigation model, but not yet a complete allocation: capture state, diagnostic return state, style shadows, partial-paint progress, settings snapshots, new EEPROM fields and write-attribution changes must also fit.

    Three log entries save nominally 54 bytes, subject to final layout. The duration calculation is wrong: entries are **15 minutes**, so 720→717 means **180→179.25 hours**, not 60→59.75.

    The stacks are fixed allocations. Freeing BSS increases the heap gap, not stack capacity, and new call frames/formatting still consume stack even when pixel scratch is static. Check all build maps and exercise worst-case rendering before the overnight test.

    There is a better candidate to investigate first: `tx_pixels()` and `lcd_fill_rect()` each have a separate static 512-byte buffer ([lcd_bus.c:174](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/lcd_bus.c:174)). Sharing those synchronous, non-reentrant buffers could recover substantially more RAM.

13. **Must-fix — EEPROM growth also changes write attribution and its HID protocol.**  
    Plan: [lines 280–282](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:280). Source: [flash_stats.c:29](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_stats.c:29), [flash_stats.c:128](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/flash_stats.c:128).

    Changing the data size to ten immediately breaks the seven-entry `kb_byte_field` static assertion. Adding three independently tracked fields then exceeds the current eight-bit masks.

    There is also a potential memory corruption trap: page 1 already uses all 28 reply bytes—16 bytes of writer totals plus six two-byte field counters. Extending that loop to nine fields writes **six bytes past the reply**.

    Update the attribution table and masks deliberately; put additional counters on another page or use a compatible aggregation scheme, and update the host decoder. Include its RAM cost.

    Correct the version-bump explanation using [nvm_eeconfig.c:225](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/nvm/eeprom/nvm_eeconfig.c:225). The larger block shifts VIA/keymap storage; a version bump alone is not migration. State that the existing erase-and-restore flashing workflow handles this, if that is the intended policy.

14. **Should-fix — specify adapters between mockup choices and firmware values.**  
    Plan: [settings table](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:268). Source: [mockup:303](/Users/jdlien/code/ak820-pro/plans/config-menu-mockup.html:303), [display.h:59](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.h:59).

    The mockup lists Clock as `24h, 12h, Date, Off`; the firmware enum is `24h, 12h, Off, Date`. Passing choice indices directly selects the wrong mode. The mockup effect list also omits firmware effects such as Rainfall and Drift.

    Use explicit label→enum tables. Treat Second color as the ALPHAS_MODS speed/hue-offset field, not an independent RGB value. Promote the existing dev-only `power_set_mode()` instead of creating a second implementation. For indicators, add a charging getter as well as setter, validate persisted levels, and retain the distinction between unset and explicitly saved zero.

15. **Should-fix — expand the tests and make op 27 asynchronous and observable.**  
    Plan: [lines 349–410](/Users/jdlien/code/ak820-pro/plans/CONFIG-MENU-BUILD-PLAN.md:349). Source: [hid_protocol.c:1288](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1288).

    Op 27 is available, but its contract needs packet-length/subcommand validation, bounded counts and coordinates, dev-only compilation, and readable completion/state results. Queue the S1 paint through the pump; painting synchronously in the HID handler could add a second paint to that pass. Use the existing high-resolution accounting counter for the short timing measurement; `timer_read32()` is millisecond-granularity. A synthetic hold must be scheduled, never `wait_ms(600)`.

    Direct menu-event injection tests the model, not QMK’s mapping/tapping/release path, encoder delays or real activity. Add physical/integration cases for closing-release capture, Fn released first, held keys/modifiers, 600 ms boundaries, modified-consumer bursts, repeat cancellation and VIA tap-hold/one-shot mappings.

    The persistence proof needs replacement. An unchanged flash counter is neither necessary nor sufficient, and VIA reads live RAM. Test rebooted values after settled Save and Cancel, including a pre-existing dirty change, forced VIA Save during editing and RGB initially disabled.

    Add pixel-level checks for selection-only changes and interrupted paints; ownership tests during wake, startup restore, debug handoff and DMA recovery; and full-pass measurements during QR/hue painting and dashboard restoration with playback active. Check key **releases and modifier state**, not only F19 press counts. Keep counter-reset testing separate from the measured session.

    The bench sequence should isolate pairing from the “edit every value” sweep: use a designated test slot/host, since pairing and cancellation can affect bonds or briefly route input elsewhere. Deep-sleep tests need USB data disconnected as well as VBUS removed; otherwise `DSB_USB` invalidates the result. Follow the bench’s supply procedure—slider changes can brownout/reset and erase the session’s diagnostic evidence.

I would reorder the work to establish RAM headroom, ownership transitions, release capture and the bounded paint scheduler first; then validate mono painting under load; then add ordinary settings. Bluetooth should follow as its own asynchronous integration stage. That keeps the useful parts of this design while resolving the contracts on which its safety claims depend.
---

## Dispositions (ak820-pro-32, 10-23), fixed in revision 2

Three of codex's facts were checked in the source before agreeing:
- the log's period is 15 minutes (`battery.c:1353`, `LOG_PERIOD_MS 900000u`);
- `kb_byte_field` is pinned to 7 bytes by a static assert (`flash_stats.c:29-35`);
- Rainfall and Drift are the board's own effects (`rgb_matrix_kb.inc:20,89`).

And one fix was checked before relying on it: `pre_process_record_kb` runs
from `action_exec` before `action_tapping_process` (`action.c:133-134`).

**The facts table:** all corrections agreed and made in revision 2:
- claim 3: housekeeping isn't the single gate, and the restore isn't 14
  passes;
- claim 8: a version mismatch zeroes the RAM copy on read, and the bigger
  block moves VIA's storage;
- claim 9: activity and visibility are conditional;
- claim 2: the row's cost is unmeasured, not mostly fixed.

| # | Severity | Disposition |
|---|---|---|
| 1 | must-fix | **Agreed.** One owner enum (`PANEL_DASH`, `PANEL_DEBUG`, `PANEL_MENU`, `PANEL_ANIM`), with enter, leave and handoff functions. `Fn`+`D`, dev hook op 1, Diagnostics and the animation all go through them. In P1 (stage S0). |
| 2 | should-fix | **Agreed.** "Restored" means the restore has ended *and* both queues are drained. Overlay posts are classified centrally. `conn_status_update()` runs before the text stage. Gated logos keep their RAM state and are repainted from it. The menu's big-glyph DMA gets its own retry. |
| 3 | must-fix | **Agreed.** A capture table records, per matrix position, whether the press was consumed. The matching release follows that record, whatever the owner or `Fn` is now. A release at or past 600 ms, before the hold has fired, is Back, exactly once. |
| 4 | should-fix | **Agreed.** The capture moves to `pre_process_record_kb`, ahead of action tapping, so a VIA tap-hold or one-shot on the knob can't see the menu's events. Opening cancels the param repeat. `modified_consumer_task()` keeps running. |
| 5 | must-fix | **Agreed.** The edit transaction rule: any external write to the setting being edited (`Fn` keys, the param repeat, VIA's set or save, the LCD keys) cancels the edit first, then applies. Pre-existing dirty state is kept. With RGB off, the adapter sets and restores in a fixed order, with the enabled state last. |
| 6 | must-fix | **Agreed.** Pairing is an asynchronous operation that keeps the select and bounce sequence before `A6 51`, with explicit states. Cancelling uses the documented A6 path, never `ch582_cancel_connect()`. It's a stage of its own. |
| 7 | must-fix | **Agreed.** A slot change first releases and settles the outgoing keyboard and consumer reports, as the slider does with `clear_keyboard()`. It waits while other keys are held. Tested with A1 and A3 reports. |
| 8 | must-fix | **Agreed.** A menu visibility override, separate from the requested level: it powers the panel, lifts the cap and the zero, and comes off on every exit. A session sleep blocker (`DSB_MENU`). A 32-bit backstop with a policy for every screen kind. Only knob input counts as menu activity; typing still counts for the ladder. |
| 9 | should-fix | **Agreed.** Opening waits until a wake's repaint has been released. |
| 10 | should-fix | **Agreed.** S1 measures the whole pass under load, with HC_ACCT's tick counter. Half-rows are the default unit, and full rows are used only if the loaded numbers allow. The wall-time estimates are corrected. |
| 11 | must-fix | **Agreed.** A damage model of regions, each with a signature: text plus style for rows, and the shapes, values, bar, strip and marker. A row counts as shown only when it's finished, and navigating supersedes pending work. The strip and the QR code stream through the shared scratch buffer in bounded chunks. The layout is per screen kind. Symbols get single-byte codes. |
| 12 | should-fix | **Agreed.** The log arithmetic is corrected: 15-minute entries, so 720 to 717 is 180 h to 179.25 h. Stacks are fixed. First, try sharing `tx_pixels`' and `lcd_fill_rect`'s static 512 B buffers. |
| 13 | must-fix | **Agreed.** `flash_stats.c`'s table and masks are updated, the new counters go on a page of their own, and the host decoders follow. The flash policy is stated: the build that grows the block goes on with `flash.sh`, which backs up and restores the keymap and lighting around the erase. |
| 14 | should-fix | **Agreed.** Label-to-enum tables. The clock in the firmware's order. The effects are the firmware's nine, named as the `Fn` readout names them (the mockup now shows them). The second colour is the `ALPHAS_MODS` speed field. The dev-only `power_set_mode()` is promoted. The indicators get a getter and validation. |
| 15 | should-fix | **Agreed.** Op 27 is dev-only, validated, bounded, asynchronous and readable. Physical tests sit beside injection: one short hands-on session for the knob, since the wake rig can't turn it. Persistence is proved by a reboot after a settled save and after a cancel. Pairing uses a designated slot. Sleep tests cut the data too. The sequence follows the bench's supply procedure. |

**The order of work:** agreed, with ownership, release capture, RAM and the
paint scheduler first (S0). Then the mono paint measured under load (S1).
Then the ordinary settings (P1). Then the indicators and EEPROM (P2). Then
Bluetooth as its own asynchronous stage (P3). Then the battery view (P4).
