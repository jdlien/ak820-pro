#!/usr/bin/env python3
"""The keep-alive's M2 and M3 from the logs alone, no board traffic (README.md,
"The with-run"): white's awake episodes in power.csv since a start time (M3:
each wake's length, its charge above the sleep floor from the INA228's own
charge register, its peak) and white's own link events in bluetoothd (M2: a
keep-alive that holds the link shows no disconnect).

    m23_read.py START_EPOCH [--json]
"""
import json
import statistics as st
import subprocess
import sys
import time

PCSV = "history/power-bench-2026-10-15/power.csv"
WHITE_BT = "EB982520-A7AC-8123-705D-800ADA51BE60"   # since the re-pair ~01:10 11-03
AWAKE_MA = 8.0


def rows_since(t0):
    n = int(time.time() - t0) + 120          # one row a second, and some spare
    out = subprocess.run(["tail", "-n", str(n), PCSV], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        f = line.split(",")
        try:
            ep, ma, mah = float(f[1]), float(f[5]), float(f[6])
        except (IndexError, ValueError):
            continue
        if ep >= t0:
            rows.append((ep, ma, mah))
    return rows


def episodes(rows):
    eps, cur = [], None
    for i, (ep, ma, _) in enumerate(rows):
        if ma > AWAKE_MA:
            if cur is None:
                cur = [i, i]
            else:
                cur[1] = i
        elif cur is not None:
            eps.append(tuple(cur)); cur = None
    if cur is not None:
        eps.append(tuple(cur))
    return eps


def bt_events(t0):
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0))
    out = subprocess.run(["/usr/bin/log", "show", "--start", since, "--style", "compact", "--predicate",
                          f'process == "bluetoothd" AND eventMessage CONTAINS "PowerLogger device \\"{WHITE_BT}\\""'],
                         capture_output=True, text=True).stdout
    ev = []
    for line in out.splitlines():
        if WHITE_BT in line:
            kind = "disconnect" if " disconnect " in line else "connect" if " connect " in line else "?"
            ev.append((line[:23], kind))
    return ev


def main():
    t0 = float(sys.argv[1])
    rows = rows_since(t0)
    if len(rows) < 10:
        raise SystemExit("too few power.csv rows since the start")
    eps = episodes(rows)
    asleep = [ma for _, ma, _ in rows if ma <= AWAKE_MA]
    floor = st.median(asleep) if asleep else float("nan")
    wakes = []
    for a, b in eps:
        i0, i1 = max(a - 1, 0), min(b + 1, len(rows) - 1)
        span = rows[i1][0] - rows[i0][0]
        q = rows[i1][2] - rows[i0][2]                       # the INA's own integral, mAh
        wakes.append({"start": time.strftime("%H:%M:%S", time.localtime(rows[a][0])),
                      "awake_s": int(rows[b][0] - rows[a][0] + 1),
                      "peak_ma": round(max(ma for _, ma, _ in rows[a:b + 1]), 1),
                      "above_floor_mas": round((q - floor * span / 3600) * 3600, 1)})
    gaps_s = [rows[eps[k + 1][0]][0] - rows[eps[k][1]][0] for k in range(len(eps) - 1)]
    hours = (rows[-1][0] - rows[0][0]) / 3600
    total = rows[-1][2] - rows[0][2]
    bt = bt_events(t0)
    d = {"from": time.strftime("%m-%d %H:%M:%S", time.localtime(rows[0][0])),
         "to": time.strftime("%m-%d %H:%M:%S", time.localtime(rows[-1][0])),
         "hours": round(hours, 2), "floor_ma": round(floor, 3), "mean_ma": round(total / hours, 3) if hours else None,
         "wakes": len(wakes), "period_min_median": round(st.median(gaps_s) / 60, 2) if gaps_s else None,
         "wake_awake_s_median": st.median([w["awake_s"] for w in wakes]) if wakes else None,
         "wake_mas_median": round(st.median([w["above_floor_mas"] for w in wakes]), 1) if wakes else None,
         "white_bt": bt, "white_disconnects": sum(1 for _, k in bt if k == "disconnect"), "wake_list": wakes}
    if "--json" in sys.argv:
        print(json.dumps(d))
    else:
        print(f"{d['from']} to {d['to']} ({d['hours']} h): floor {d['floor_ma']} mA, mean {d['mean_ma']} mA; "
              f"{d['wakes']} wakes, period {d['period_min_median']} min, awake {d['wake_awake_s_median']} s, "
              f"{d['wake_mas_median']} mA*s above the floor (medians); white's link: "
              f"{d['white_disconnects']} disconnects, {len(bt)} events")


if __name__ == "__main__":
    main()
