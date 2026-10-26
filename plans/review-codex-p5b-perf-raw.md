**No required changes before flashing `b4d29a29` on gremlin.** I found no static blocker in the exact two-file diff.

- **Snapshot/repaint:** [menu.c:1800](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1800) invalidates for input; [menu.c:1903](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1903) invalidates before the pump and consumes host-write invalidation. Key loads, VIA/Fn changes and recovery openings reach this ordering. No persistent signature/paint disagreement found; completing the physical repaint still takes multiple passes.

- **Readers outside tick exist:** input retargets and op 27’s `ms_settled()`/`ms_unsettled()` scans ([menu_ops.c:204](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu_ops.c:204)). These can observe the previous snapshot, but the following tick refreshes it before painting.

- **Raw CRC:** [menu.c:1008](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/menu.c:1008) reads one byte at a bounded slot address, used only as signature bits. Stale validity cannot authorize a load or unsafe payload access. Paint/load paths retain validation; host changes invalidate rows, including CRC collisions.

- **CRC/capture:** [profiles.c:49](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:49) matches all 256 reference entries and 200 strings, independently checked. The matching dev ELF places its 256 bytes in read-only `.rodata` at `0x323cc`. [profiles.c:232](/C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/menu/profiles.c:232) omits only the unused capture CRC.

Artifact hashes match provenance; the heap gap is 136 B. I inspected the C tests but could not rerun them because process execution was denied. The timing improvement still needs board measurement.