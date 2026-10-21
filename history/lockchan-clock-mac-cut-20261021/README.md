# The Mac's wireless clock, a 30 min cut (09:43-10:14 10-21)

The first test of type 4 from the Mac. The board ran `9e52400ec9`, and the
daemon ran `a725a8c` with the latency set to -14 ms
([`../lockchan-clock-latency-mac-20261021/`](../lockchan-clock-latency-mac-20261021/README.md)).
`run.sh` waited for a fresh USB sync, then ran `deep_cycles.py --board-only
--awake --dwell 1800 --rtc-gate`: the board on its pack (relay 2 off), the
data cut, the stage forced dark, never asleep, slider on BT. `trace.log`
holds the daemon's status every 10 s. JD used the Mac on another keyboard
throughout, so the hold never stopped a frame.

**The frames worked.** The board's counters (op 17 sub 8) went from all zero
to **applied 2, refused 0, rejected 0, retried 0, dropped 0**:
- the last USB sync was at 09:43:57 (board -17.8 ms), and the cut at 09:44:04;
- frame 1 went at ~09:56:19, 735 s after that sync (`OWNER_FLOOR`), as
  designed;
- frame 2 went at ~10:06:20, 600 s later (`EVERY`).

**The clock between frames did not hold.** The board ran fast, ~0.25%:
- **at frame 2** it was **1616 ms ahead** (`target - board` -1616, stepped,
  being over the 500 ms slew limit): ~2.7 ms/s since frame 1;
- **at the replug** (10:14:21, 481 s after frame 2) the daemon's sync found
  it **+1106.3 ms** (board minus host): ~2.3 ms/s.
- The soak's awake window, the same procedure without type 4, ended at
  +1438.5 ms after 908 s, ~1.6 ms/s.

So at the 10 min cadence the board saws to ~1.6 s ahead before each frame
steps it back, about 0.8 s off on average. The -14 ms latency cannot be
judged from this; the drift buries it.

**Why the drift is so large off USB:** the trim period stayed at 32463
(the SOF loop's at the cut, still moving). The board awake on the pack needs
~0.25% more. Off USB only the legacy PCF discipline can trim. Its
measurement has whole-second resolution and needs `|diff| >= 2` over
`>= 300 s`, so at ~2.5 ms/s it waits ~800 s for a trim. Steps every 600 s
may reset the error before it gets there. "PCF runs +3" here; the soak's
awake window, without type 4, saw 2 PCF-path trims in 908 s. Not checked in
the code.

**What would help** (Gremlin's call; type 4 is Gremlin's): trim the period
from the frames themselves. Each applied offset over its interval is a
millisecond-accurate rate: -1616 ms over 600 s is 0.27%. Or send frames far
more often, at the radio's cost.
