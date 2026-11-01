# The CH582F link model

The 10-31 audit's model of the radio module's UART, its peer and the board's
clocks (`plans/AUDIT-2026-10-31.md`, its fuzz-ch582-rx harness): `sim.c` and
`sim.h`, and the stubs the real `bluetooth/ch582f_ajazz.c` compiles against.
Shared by `scripts/sleep_relink_test` (F-023) and `scripts/rx_window_test`
(F-019), each of which compiles the real driver by path. (`scripts/ch582_sim`
is an older, separate model.)
