#!/usr/bin/env bash
# The Mac's type-4 test (10-21): a 30 min cut, the board on its pack, kept
# awake, after a fresh USB sync; the daemon's status traced every 10 s.
cd /Users/jdlien/code/ak820-pro
D=history/lockchan-clock-mac-cut-20261021
S="$HOME/Library/Application Support/ak820pro/ak820-agent.status"
first=$(grep '^clock_last_sync=' "$S")
until [ "$(grep '^clock_last_sync=' "$S")" != "$first" ]; do sleep 1; done
echo "$(date '+%F %T') fresh sync: $(grep '^clock_last_sync=' "$S")" > $D/trace.log
( while :; do echo "--- $(date +%T)"; grep -E '^(clock_last_sync|clock_last_line|transport|lockchan_)' "$S"; sleep 10; done ) >> $D/trace.log 2>&1 &
T=$!
venv/bin/python scripts/deep_cycles.py --board-only --awake --n 1 --dwell 1800 --rtc-gate --out $D/cut > $D/cut.log 2>&1
echo "deep_cycles exit $?" >> $D/cut.log
sleep 20
kill $T
venv/bin/python scripts/lockchan_clock_counters.py > $D/counters-after.txt 2>&1
echo done >> $D/cut.log
