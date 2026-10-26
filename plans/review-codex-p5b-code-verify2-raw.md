**No remaining must-fix blocker found in `28fac431..9ca4ed6a` before a development flash on gremlin.**

- [profiles.c:498](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:498) checks the failure latch independently of `pend`, closing the P2. [profiles_test.c:559](/C:/Users/jdlien/code/ak820-pro/scripts/profiles_test.c:559) covers flushes after a failed tick and repeated flushes.
- The immediate RGB baseline refresh preserves `last_nkro`, fixing the swallowed NKRO notification and allowing subsequent RGB adjustments to surface.

**One nonblocking feedback edge:** [param_overlay.c:175](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/param_overlay.c:175) leaves `param_force_kc` pending. Tap an RGB adjustment, then a profile key before the next poll: the forced-readout branch can still replace the profile name. Clearing `param_force_kc` in the rebase, before its early return, would close that edge without touching NKRO.

Static review only: process execution was denied, so I inspected the tests but did not rerun them or independently verify the reported build.