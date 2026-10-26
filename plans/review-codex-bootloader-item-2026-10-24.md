# Codex on the bootloader item (`077ab77c`), 10-24 night

Prompt: `plans/review-prompt-bootloader-item.txt`.

## Dispositions

1. **[P1] The releases before the reset:** taken in the next commit: the raw-HID jump's preparation (clear_keyboard, fresh releases, the drain), refused with "Try again" on failure; its 2 s idle guard not copied (the knob's click is input). Fn+Esc keeps the gap, as HC_BOOTLOADER's comment says (the hands are on the keys).
2. **[P2] The scrollbar on Exit's page:** taken: the position clamps to count - 8; a host check of the thumb at y 27-126 on page two (it fails without the clamp: the fake clips silently).
- **The reserve predicate:** taken: `battery_on_battery() && power_lights_cut()`, flash.sh's exactly.

## The review, verbatim

**Yes—I would fix two issues before flashing `077ab77c`.**

1. **[P1] Send and drain radio releases before entering the bootloader.**  
   [env_bootloader()](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_glue.c:95) immediately paints, waits, and resets. `reset_keyboard()` eventually calls `clear_keyboard()`, but wireless releases are queued; neither the wait nor shutdown pumps `ch582_task()`. A held key or consumer usage can therefore remain down at the wireless host throughout flashing—even when the menu is driven through USB op 27.

   Fn+Esc already has this gap. [HC_BOOTLOADER](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/hid_protocol.c:1324) explicitly compensates with `clear_keyboard()`, fresh `ch582_send_releases()`, and `ch582_tx_drain(500)`, refusing on failure. Reuse that preparation before the splash, with a failure result that leaves the menu usable. Its two-second idle guard also deserves preservation for synthetic entry; copying it unconditionally would reject physical knob confirmations because those are input activity.

2. **[P2] Clamp the scrollbar position on Exit’s page.**  
   Nine rows make the second page’s `top` equal **8**, but [the thumb formula](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:600) assumes `top <= count - MENU_ROWS`, which is **1** here. It computes a 100-pixel thumb at **y=111–210**, outside the track at y=15–126 and the panel itself.

   Clamp the position used by the scrollbar to `count - MENU_ROWS`, while retaining page-aligned list navigation. That gives y=27–126. Add assertions for both pages and drawing bounds: the [fake framebuffer silently clips](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_test.c:62), and the current test checks the scrollbar only on page one, explaining why this passes.

The remaining checks look sound, with one minor policy difference:

- **Main-loop/display handoff:** Calling the splash here is valid. The initial clear enters `lcd_blit_flash()`, whose `bus_quiesce()` waits out an existing glyph DMA; the splash also drains its final transfer. Menu painting cannot resume before reset. The row/backlight interrupts continue during `wait_ms()`, which sleeps the main thread. The nominal 12-second watchdog accommodates the normal sequence, and `bootloader_jump()` stops it before the magic-flag system reset. I found no additional menu-owner or DMA blocker.
- **Synthetic click:** Acceptable as the explicitly designed development interface once the release handling above is fixed. Op 27 is guarded by `AK820_DEV_HOOKS`; the radio command allowlist does not admit it. Daily/fpb do not expose it.
- **Reserve:** `power_lights_cut()` implements the design literally, but is slightly stricter than [flash.sh’s predicate](/C:/Users/jdlien/code/ak820-pro/flash.sh:183), which requires **battery supply AND lights cut**. The cut remains latched for five seconds of external-power evidence, so the menu can briefly refuse after power is connected. This is conservative, not a flash-safety hole; exact parity would use `battery_on_battery() && power_lights_cut()`.
- **Shared confirmation:** The node-specific signatures, page bit, selected text table, layout changes on entry/exit, restored parent cursor, refusal-page return, and question-page `Cancelled` flash are consistent. Reset counters retains its behavior.
- **Rows/icons/tooling:** Nine-row wraps, Exit activation, blank trailing rows, and restored cursors are correct apart from the scrollbar. `0x98–0x99` map to glyph indices 119–120 within `FONT_MONO_N=121`; header definitions, renderer checks, generator, and host assertions agree. The current board-script row constants are updated.

I verified the changed working files match the commit objects. No files changed. I could not rerun tests because process spawning is denied in this session; the findings above come from source inspection and reproducing the scrollbar arithmetic.