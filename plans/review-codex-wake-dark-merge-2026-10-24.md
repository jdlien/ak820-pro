# Codex on the wake-dark-frame merge (`88057ba7`, JD's `52acdffe99`), 10-24 night

Prompt: `plans/review-prompt-wake-dark-merge.txt`.

## Dispositions

- **No must-fix.** Flashed to the keyboard on gremlin with P1b.
- **The dev sleep arm masks `DSB_RGB`**, so a forced dev sleep can't test the fix: the ordinary ladder can (noted for any test of it on gremlin).

## The review, verbatim

**No must-fix issue found before flashing the test board.** I verified the exact fix against both merge parents and the current source. HEAD is `bca53a49`; its only change after `88057ba7` is menu help text.

- **`drive_now[]` means the committed frame.** Only `sn32f2xx_flush()` updates it, summing `led_state[]` after the protected buffer copy. Battery accounting clears the accumulators, not these sums. Both the frame and sums start zero. Physical blanking alone does not clear them—which is appropriate for detecting a stale frame that would return on wake. [Driver](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/drivers/led/sn32f2xx.c:928)

- **No normal-state permanent RGB blocker found.** Scale zero produces exact zero channel values. RGB cut and the ladder’s dark stages force effect reinitialization, including sparse effects. User-disabled RGB renders and flushes `NONE`; suspension does likewise when enabled. Subsequent skipped black-frame flushes are safe because the committed frame is already black. Before any frame renders, it is also zero. If rendering genuinely stops forever after a lit frame, the guard will block forever; I found no such path caused by disabling RGB, suspension, or the menu. [Power application](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:119), [RGB state machine](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/quantum/rgb_matrix/rgb_matrix.c:319)

- **The menu remains compatible.** `menu_visibility` overrides only the LCD backlight; it cannot bypass the RGB cut or Lights out. `DSB_MENU` deliberately blocks throughout PENDING and OPEN, including menu Diagnostics. Closing clears the session blocker; remaining display work or the next power tick may briefly delay sleep. The wake hold still overrides menu visibility. [Backlight](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:262), [Session policy](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/panel_owner.c:50)

- **The immediate `power_task()` call is safe here.** Clocks and interrupts are restored first; both calls run serially on the main loop—the 10 Hz call is not an interrupt. Key/knob activity is reset before restaging, and `display_sleep_wake()` establishes the backlight hold first. Power processing updates caps, render state and notification flags; even its configuration setter only schedules a deferred write. There is no new bus I/O or recursive sleep call. The documented brief use of the pre-sleep battery level remains. [Recovery](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:660)

**Test caveat:** the explicit dev sleep arm masks out `DSB_RGB`, including this new condition. Exercise the ordinary ladder to validate the dark-frame fix; forced dev sleep can still retain a lit frame. [Dev arm](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:909)

Read-only source/Git-object review; no build or hardware test performed.