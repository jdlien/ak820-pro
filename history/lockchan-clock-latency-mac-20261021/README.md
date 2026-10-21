# The Mac's lock-light clock latency (2026-10-21, 09:36)

`ak820 lockchan anchor 40` (debug build of `a725a8c`), with the daemon paused
(`kill -STOP`) and its own writer, `BleLights`, on the board running
`9e52400ec9`. The slider was on BT and the cable in for the readback (devhook
op 10). The Mac was unlocked, and JD typed on another keyboard; nobody
touched the AK820.

**39 of 40 frames committed** (frame 24 abandoned on a deadline). The board's
anchor came **13.9 ms before the Mac reported the write complete** (median;
mean -13.6, sd 2.7, p10 -15.8, p90 -11.5, min -16.8, max -0.6). The sync's
round trips were 2.75 ms at the start and 3.73 at the end, and the board's
timer ran 999.441 ms per host second.

So `BleLights::clock_latency_ms` is **-14**. The sign follows `LockLights`:
how long after a write's completion the board sees it. Windows's is +38
(`history/lockchan-clock-jitter-20261020/`, min 7, p90 54): there the
completion comes before the board has the byte, and the spread is far wider.

Measured with the cable in, so the board ran its USB tasks too. Type 4 goes
only with the cable's data absent; that difference is not measured.
`anchor40.txt` is the run's output.
