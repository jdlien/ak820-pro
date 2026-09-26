#!/bin/zsh
# Elysium footprint gate for the autorelease-pool leak fix (bf7b7f3).
#
# Samples phys_footprint every 5 minutes alongside the daemon's OWN workload
# counters, so growth can be expressed per media cycle and not against an
# assumed 3 s rate. Records the pid and start time in every row: a restart
# resets the process, and a slope across one is meaningless.
#
# ⚠️ The 0-24 h window contains warm-up and cannot distinguish a fix from a
# plateau. The 24->48 h delta is the one that decides.
set -u
CSV=~/Library/Logs/ak820pro/mem-samples-signed-4e9d5cd.csv
STATUS=~/Library/Application\ Support/ak820pro/ak820-agent.status
[ -f "$CSV" ] || echo "iso,pid,started,uptime_s,footprint_kb,rss_kb,threads,smtc_polls,clock_syncs,cpu_s" > "$CSV"

for _ in $(seq 1 576); do   # 576 x 5 min = 48 h
  PID=$(pgrep -f "ak820pro/bin/ak820-agent" | head -1)
  if [ -n "$PID" ]; then
    /usr/bin/python3 - "$PID" "$STATUS" "$CSV" <<'PY'
import ctypes, sys, time, os, subprocess
pid, status, csv = int(sys.argv[1]), sys.argv[2], sys.argv[3]
buf = (ctypes.c_uint64 * 64)()
libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
if libc.proc_pid_rusage(pid, 4, ctypes.byref(buf)) != 0:
    sys.exit(0)                      # a failed read is not a zero sample
foot, rss = buf[9] / 1024, buf[8] / 1024
cpu = (buf[2] + buf[3]) / 1e9
st = {}
try:
    for line in open(status):
        k, _, v = line.partition("=")
        st[k.strip()] = v.strip()
except OSError:
    pass
ps = subprocess.run(["ps", "-o", "etime=,nlwp=", "-p", str(pid)],
                    capture_output=True, text=True).stdout.split()
started = st.get("started", "")
up = ""
try:
    t0 = time.mktime(time.strptime(started, "%Y-%m-%d %H:%M:%S"))
    up = int(time.time() - t0)
except ValueError:
    pass
row = [time.strftime("%Y-%m-%dT%H:%M:%S"), pid, started, up,
       f"{foot:.0f}", f"{rss:.0f}", ps[1] if len(ps) > 1 else "",
       st.get("smtc_polls", ""), st.get("clock_syncs", ""), f"{cpu:.1f}"]
open(csv, "a").write(",".join(str(c) for c in row) + "\n")
PY
  fi
  sleep 300
done
