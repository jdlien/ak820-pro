**P2 closed.** [rtc.c:1533](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:1533) permits writes when USB is inactive despite stale `REF_SOF`; the fast task continues during animation.

**Lock safe:** normal and recovery calls ([rtc.c:2281](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2281), [rtc.c:2261](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc/rtc.c:2261)) run in unlocked thread context; wake releases its lock at [sleep.c:612](C:/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/sleep.c:612). The critical section only reads driver state.

No new findings in `d72bfaf4..ecb10f0e`. Static review; tests not rerun.