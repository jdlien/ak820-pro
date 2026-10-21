#!/usr/bin/env bash
# The Mac's type-4 test with the frame trim (10-21, 36afff30e8, daemon
# 21e8fe8): a 30 min cut, the board on its pack, kept awake, after a USB
# sync whose offset has settled (|before| <= 25 ms: the flash left the board
# 460 ms off, and a slew in progress would spoil the frames' first window);
# the daemon's status traced every 10 s. As ../lockchan-clock-mac-cut-20261021/.
cd /Users/jdlien/code/ak820-pro
D=history/lockchan-clock-mac-cut-trim-20261021
S="$HOME/Library/Application Support/ak820pro/ak820-agent.status"
settled() {
  b=$(grep '^clock_last_line=' "$S" | sed -nE 's/.*before (-?[0-9.]+) ms.*/\1/p')
  [ -n "$b" ] && awk -v b="$b" 'BEGIN { exit !(b <= 25 && b >= -25) }'
}
last=$(grep '^clock_last_sync=' "$S")
until [ "$(grep '^clock_last_sync=' "$S")" != "$last" ] && settled; do
  [ "$(grep '^clock_last_sync=' "$S")" != "$last" ] && echo "$(date +%T) not settled: $(grep '^clock_last_line=' "$S")" >> $D/wait.log
  last=$(grep '^clock_last_sync=' "$S"); sleep 1
done
echo "$(date '+%F %T') settled sync: $(grep -E '^clock_last_(sync|line)=' "$S" | tr '\n' ' ')" > $D/trace.log
venv/bin/python scripts/lockchan_clock_counters.py > $D/counters-before.txt 2>&1
( while :; do echo "--- $(date +%T)"; grep -E '^(clock_last_sync|clock_last_line|transport|lockchan_)' "$S"; sleep 10; done ) >> $D/trace.log 2>&1 &
T=$!
# deep_cycles starts from relay 2 on (the charging state) and puts it back on;
# JD runs on the pack, so relay 2 goes off again at the end.
scripts/relay on power >> $D/cut.log 2>&1
venv/bin/python scripts/deep_cycles.py --board-only --awake --n 1 --dwell 1800 --rtc-gate --out $D/cut >> $D/cut.log 2>&1
echo "deep_cycles exit $?" >> $D/cut.log
sleep 20
kill $T
venv/bin/python scripts/lockchan_clock_counters.py > $D/counters-after.txt 2>&1
scripts/relay off power >> $D/cut.log 2>&1
echo done >> $D/cut.log
