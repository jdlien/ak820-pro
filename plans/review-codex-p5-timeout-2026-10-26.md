# Codex: the menu's idle close at 60 s (2026-10-26)

JD (10-26): "like 60 seconds (or more) could be fine for that", then
"Let's increase to 60s." qmk_firmware-ak820pro `553108e5..1f3c79e9` (branch
`gremlin/p5-timeout`): `MI_IDLE_MS` 24000u -> 60000u, comments, and Help's
"Using the menu" regenerated from `plans/MENU-TEXT.md` ("60 seconds idle.").
The prompt: `plans/review-prompt-p5-timeout.txt`; the raw reply:
`plans/review-codex-p5-timeout-raw.md`.

## The reply, verbatim

No new flash blocker in `553108e5..1f3c79e9`.

- [menu_ops.c:167](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:167): 32-bit timeout; fixture/profile preview 60 s; editors/Pairing/Rename retain 180 s.
- [menu_ops.c:189](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:189), [menu.c:2161](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:2161): reported fields and hints introduce no timing hazard.
- [sleep.c:273](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:273), [display.c:3066](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/display.c:3066): menu and unfinished restore block sleep.
- [power.c:66](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/power.c:66): Lights out already sleeps at 60 s.
- [menu_s0_photos.py:10](/C:/Users/jdlien/code/ak820-pro/scripts/menu_s0_photos.py:10): stale “24 s” comment; 15 s keepalive remains safe.

Generated Help matches. Builds/tests weren’t rerun: process execution denied.

## Dispositions

- **No blocker:** flashed (the build `via-dev-1f3c79e9-20261026-172211`,
  token `0xe3fa251b`, heap gap 136 B); the host tests (both builds) and
  `profiles_test` pass, `gen_menu_text.py --check` is current.
- **Lights out sleeps after a 1 min pause** (`power.c`'s ladder), not the
  30 s an old note gives: a menu left open there now closes at about the
  time the board would sleep anyway, so the longer close costs nothing.
- **`menu_s0_photos.py`'s comment:** fixed ("60 s ... (24 s until 10-26)").
