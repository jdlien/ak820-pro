# The 81-LED fix on JD's board (10:49-10:51 10-21)

`36330d5ec8` (a `dev` build, token `0x57c22634`): `9e52400ec9` plus
ak820-pro-1e's battery.c fix, the RGB model's per-colour slopes over 81 LEDs,
not 82. Codex cleared it (`plans/review-codex-rgb-81-leds-2026-10-21.md`).
The host side and the `deps.lock` pin are on main (`d9b47e5`, `d8f6eee`,
`d8c9480`). `scripts/battery_sim/run.sh` on the checkout: 226 ok.

- Relay 2 went on at 10:49 (JD had the board on its pack) and back off at
  10:51.
- `flash.sh` (`flash.log`): the jump waited through JD's typing ("a key moved
  in the last 2 s") and went in a pause. Flashed; the keymap and lighting
  were restored and read back.
- After (`health-after-flash.txt`): the token matched; msp 640 and psp
  1232 B free; no watchdog resets. The daemon's sync on the return found
  the board -269.3 ms off.
