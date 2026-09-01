#!/usr/bin/env python3
"""Clock-sync plan, Phase 0: read the new RTC status blocks and drive the
hardware-fact tests (T0.1 .. T0.8) over raw HID.

    rtc_phase0.py get                 decode RTC_GET_TIME incl. the sub-second tail
    rtc_phase0.py status              HC_RTC pages 1-3 decoded
    rtc_phase0.py t01                 SECCNTV same-value write resets SECCNT?  (+ RTCEN fallback)
    rtc_phase0.py t02 [secs]          tick-ISR latency stats over N s (default 60)
    rtc_phase0.py t03 [secs]          FRMNO delta observation over N s (default 60)
    rtc_phase0.py t04                 PCF 1-byte read / 8-byte write cost in ILRC cycles
    rtc_phase0.py t05 [n]             PCF STOP-bit: release-to-first-increment, n trials
    rtc_phase0.py t06 [n]             rtc_now() cnt vs the old edge-hunting method
    rtc_phase0.py t07 [n]             HID GET round-trip distribution (idle; type during it for 'load')
    rtc_phase0.py t08 [secs]          this Mac's SOF bias from sof_frames_total vs wall clock

Wired slider position required (replies). The test ops (t01, t04, t05) move
the clock phase / PCF registers on purpose: run `ak820ctl clock` afterwards.
Wire layouts mirror keyboards/a_jazz/ak820pro/rtc/rtc.c rtc_status_fill().
"""
import statistics, struct, sys, time
import hid

VID, PID = 0x0C45, 0x8009
SET_VALUE, RTC_CH, HEALTH_CH = 0x07, 0x10, 0x13
RTC_GET, HC_RTC, HC_RTCTEST = 0x02, 0x03, 0x7A


def open_raw():
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == 0xFF60 and d.get("usage") == 0x61:
            return hid.Device(path=d["path"])
    sys.exit("raw HID interface not found (cable in? wired position? VIA open?)")


def xfer(h, payload, timeout=500):
    h.write(bytes([0] + payload + [0] * (32 - len(payload))))
    r = h.read(32, timeout)
    if not r:
        sys.exit("no reply (BT/2.4G position routes replies over the air)")
    return bytes(r)


def u16(b, i): return struct.unpack_from("<H", b, i)[0]
def u32(b, i): return struct.unpack_from("<I", b, i)[0]
def s16(b, i): return struct.unpack_from("<h", b, i)[0]


def decode_tail(b, o):
    """21-byte tail starting at offset o (GET[11] or HC_RTC page1 [4])."""
    return dict(ver=b[o], cnt=u32(b, o + 1), period_active=u16(b, o + 5),
                period_nominal=u16(b, o + 7), flags=b[o + 9],
                last_host_offset_ms=s16(b, o + 10), sof_bias_ppm=s16(b, o + 12),
                ref_state=b[o + 14], sync_age_min=b[o + 15], sof_epoch=b[o + 16],
                sof_frames_total=u32(b, o + 17))


def get(h):
    t_send = time.time()
    r = xfer(h, [SET_VALUE, RTC_CH, RTC_GET])
    t_recv = time.time()
    if r[11] != 2:
        sys.exit(f"firmware RTC_PROTO_VERSION {r[11]} != 2 (old build?)")
    d = decode_tail(r, 11)
    d.update(ok=r[3], hms=(r[8], r[9], r[10]), ymd=(2000 + r[4], r[5], r[6]),
             t_send=t_send, t_recv=t_recv)
    # 1 - remaining/(nominal): correct inside a shortened first period too
    d["frac_ms"] = (1.0 - (d["period_active"] + 1 - d["cnt"]) / (d["period_nominal"] + 1)) * 1000.0
    return d


def board_seconds_of_day(d):
    h, m, s = d["hms"]
    return h * 3600 + m * 60 + s + d["frac_ms"] / 1000.0


def host_seconds_of_day(t):
    lt = time.localtime(t)
    return lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec + (t - int(t))


def offset_ms(d):
    """board - host, NTP with T3 = T2. Positive = board ahead."""
    mid = (d["t_send"] + d["t_recv"]) / 2
    o = board_seconds_of_day(d) - host_seconds_of_day(mid)
    if o > 43200: o -= 86400
    if o < -43200: o += 86400
    return o * 1000.0


def status(h, page):
    r = xfer(h, [SET_VALUE, HEALTH_CH, HC_RTC, page])
    return r


def rtctest(h, op, args=()):
    r = xfer(h, [SET_VALUE, HEALTH_CH, HC_RTCTEST, op] + list(args), timeout=2000)
    if r[0] == 0xFF or r[3] == 0xFF:
        sys.exit("HC_RTCTEST unhandled -- is this the INSTRUMENTED build?")
    return r


# ---------------------------------------------------------------- commands

def cmd_get(h):
    d = get(h)
    print(f"device {d['ymd'][0]}-{d['ymd'][1]:02d}-{d['ymd'][2]:02d} "
          f"{d['hms'][0]:02d}:{d['hms'][1]:02d}:{d['hms'][2]:02d}.{d['frac_ms']:06.1f}  "
          f"cnt={d['cnt']} period={d['period_active']}")
    print(f"offset board-host {offset_ms(d):+.1f} ms  rtt {(d['t_recv']-d['t_send'])*1000:.1f} ms")
    for k in ("flags", "ref_state", "sync_age_min", "sof_epoch", "sof_frames_total",
              "last_host_offset_ms", "sof_bias_ppm"):
        print(f"  {k:20} {d[k]}")


def cmd_status(h):
    p1 = status(h, 1); print("page1:", decode_tail(p1, 4))
    p2 = status(h, 2)
    o = 4
    print("page2:", dict(stale_count=u16(p2, o), i2c_fail=u16(p2, o + 2), deferred=u16(p2, o + 4),
                         i2c_max_cycles=u32(p2, o + 6), window_rejects=u16(p2, o + 10),
                         ref_transitions=u16(p2, o + 12), lat_min=u16(p2, o + 14), lat_max=u16(p2, o + 16),
                         lat_mean=u16(p2, o + 18), lat_n=u16(p2, o + 20), d_zero=u16(p2, o + 22),
                         d_reject=u16(p2, o + 24), sizeof_time_t=p2[o + 26], usb=p2[o + 27]))
    p3 = status(h, 3)
    print("page3 deltas:", [u16(p3, 4 + 2 * i) for i in range(14)])
    p4 = status(h, 4); o = 4
    PS = ["IDLE","STOP_READ","STOP_WRITE","TIME_WRITE","RELEASE_READ","RELEASE_WRITE","VERIFY","RECOVER","BRACKET"]
    ACQ = ["WAIT_SPLASH","COARSE","DONE","ABORTED"]
    print("page4:", dict(pcf_state=PS[p4[o]] if p4[o] < 9 else p4[o], stop_asserted=p4[o+1],
                         release_err_ms=struct.unpack_from("<b", p4, o+2)[0], runs_ok=u16(p4, o+3),
                         restarts=u16(p4, o+5), maybe_stopped=p4[o+7], acq=ACQ[p4[o+8]] if p4[o+8] < 4 else p4[o+8],
                         acq_unc_ms=u16(p4, o+9), acq_step_ms=s16(p4, o+11), attempts=p4[o+13],
                         pcf_pending=p4[o+14], ref_state=p4[o+15], slews=u16(p4, o+16), reload_writes=u16(p4, o+18),
                         boundary_err_ms=s16(p4, o+20), d_first_ms=u16(p4, o+22)))


def cmd_t01(h):
    for op, name in ((1, "same-value SECCNTV write"), (2, "period+1 then restore"), (10, "RTCEN 1->0->1")):
        r = rtctest(h, op)
        a, b, c = u32(r, 4), u32(r, 8), u32(r, 12)
        if op == 10:
            print(f"{name:28} SECCNT before={a} after={b}  -> {'RESETS' if b < 8 and a > 8 else 'no reset'}")
        else:
            print(f"{name:28} SECCNT before={a} after={b} +100us={c} period={u32(r,16)}"
                  f"  -> {'RESETS (latency ~%d cyc)' % b if b < 8 and a > 8 else 'NO RESET'}")
        time.sleep(0.3)
    print("note: the clock phase moved; run `ak820ctl clock` when done with Phase 0 tests")


def cmd_t02(h, secs=60):
    rtctest(h, 3)
    print(f"collecting ISR latency for {secs} s (do the load you want measured now)...")
    time.sleep(secs)
    p2 = status(h, 2)
    o = 4
    n = u16(p2, o + 20)
    print(f"ticks={n}  latency cycles min={u16(p2,o+14)} max={u16(p2,o+16)} mean={u16(p2,o+18)}"
          f"  (1 cycle ~ {1e6/(u16(status(h,1),9)+1):.1f} us)")


def cmd_t03(h, secs=60):
    rtctest(h, 3)
    t0 = time.time(); f0 = decode_tail(status(h, 1), 4)
    print(f"observing FRMNO deltas for {secs} s ... (epoch {f0['sof_epoch']}, frames {f0['sof_frames_total']})")
    time.sleep(secs)
    f1 = decode_tail(status(h, 1), 4); t1 = time.time()
    p2 = status(h, 2); o = 4
    print("last 14 deltas:", [u16(status(h, 3), 4 + 2 * i) for i in range(14)])
    print(f"d_zero={u16(p2,o+22)} d_reject={u16(p2,o+24)} usb/fn_valid={p2[o+27]:#04x} epoch {f0['sof_epoch']}->{f1['sof_epoch']}")
    F = (f1["sof_frames_total"] - f0["sof_frames_total"]) & 0xFFFFFFFF
    H = t1 - t0
    print(f"frames {F} over {H:.2f} s host  -> {F/H:.3f} frames/s  (coarse; use t08 for the bias)")


def cmd_t04(h):
    for _ in range(5):
        r = rtctest(h, 4); print(f"1-byte read : {u32(r,5)} cycles  ok={r[9]} byte={r[4]:#04x}")
    for _ in range(3):
        r = rtctest(h, 5); print(f"8-byte write: {u32(r,5)} cycles  ok={r[9]}")


def cmd_t05(h, trials=5):
    """STOP; write time S (= board now + 3 s, whole); release; poll the seconds byte
    until it increments; report release->first-increment in board time."""
    per = decode_tail(status(h, 1), 4)["period_active"] + 1
    results = []
    for k in range(trials):
        d = get(h)
        # target S: current board whole second + 3 (avoid rollover drama: keep same minute)
        hh, mm, ss = d["hms"]
        ss2 = ss + 3
        if ss2 >= 57:
            time.sleep(6); continue
        r6 = rtctest(h, 6, [d["ymd"][0] - 2000, d["ymd"][1], d["ymd"][2], 0, hh, mm, ss2])
        if not r6[6]:
            print("STOP/write failed:", r6[4:8]); return
        time.sleep(0.2)
        r7 = rtctest(h, 7)
        sc_rel, c_rel = u32(r7, 12), u32(r7, 16)   # stamp AFTER the release write
        # poll
        first = None; prev = None; deadline = time.time() + 2.5
        while time.time() < deadline:
            r8 = rtctest(h, 8)
            v, sc, c = r8[4], u32(r8, 5), u32(r8, 9)
            sec = ((v >> 4) & 7) * 10 + (v & 0xF)
            if prev is not None and sec != prev:
                first = (sc - sc_rel) * per + (c - c_rel); break
            prev = sec
        if first is None:
            print(f"trial {k+1}: no increment seen (ctl before={r6[4]:#04x})"); continue
        ms = first * 1000.0 / per
        results.append(ms)
        print(f"trial {k+1}: ctl {r6[4]:#04x}->{r6[5]:#04x}, release->first increment {ms:.1f} ms "
              f"(poll granularity ~{2000/per*1:.0f}+ ms per HID trip)")
        time.sleep(1)
    if results:
        print(f"median {statistics.median(results):.1f} ms  (datasheet 507.8; each sample is late by up to one poll)")
    print("NOTE: PCF now holds a test time -- run `ak820ctl clock` to restore.")


def cmd_t06(h, n=5):
    """Compare the cnt-based offset against the edge-hunting method using the
    SAME packet (the GET that first shows the new second), so the board's
    current drift cannot separate the two readings."""
    errs = []
    for i in range(n):
        prev = None; dl = time.time() + 3
        while time.time() < dl:
            e = get(h); t = (e["t_send"] + e["t_recv"]) / 2
            if prev is not None and e["hms"][2] != prev:
                frac = t - int(t)
                err = frac if frac < 0.5 else frac - 1.0
                o_edge = -err * 1000.0     # device ticked at host .frac -> device behind by frac
                o_cnt = offset_ms(e)       # same packet: cnt says how long ago the tick was
                rtt = (e["t_recv"] - e["t_send"]) * 1000
                errs.append(o_cnt - o_edge)
                print(f"sample {i+1}: cnt-method {o_cnt:+7.1f} ms   edge-method {o_edge:+7.1f} ms   "
                      f"diff {o_cnt-o_edge:+5.1f}  (cnt={e['cnt']}, rtt {rtt:.1f} ms; edge is late by 0..rtt)")
                break
            prev = e["hms"][2]
    if errs:
        print(f"mean diff {statistics.mean(errs):+.1f} ms, spread {max(errs)-min(errs):.1f} ms "
              f"(expect mean ~ +rtt/2 from edge-poll lateness; spread < 3 ms is the coherence check)")
    p2 = status(h, 2); print(f"stale_count={u16(p2,4)}")


def cmd_t07(h, n=100):
    rtts = []
    for _ in range(n):
        d = get(h); rtts.append((d["t_recv"] - d["t_send"]) * 1000)
    rtts.sort()
    print(f"n={n} rtt ms: min {rtts[0]:.2f} median {rtts[n//2]:.2f} p90 {rtts[int(n*.9)]:.2f} "
          f"p99 {rtts[int(n*.99)]:.2f} max {rtts[-1]:.2f}")
    print("(the SET-lead half of T0.7 needs the Phase 1 0x03 command)")


def cmd_t08(h, secs=600):
    f0 = decode_tail(status(h, 1), 4); t0 = time.time()
    print(f"measuring SOF bias over {secs} s; keep the cable in and the Mac awake ...")
    time.sleep(secs)
    f1 = decode_tail(status(h, 1), 4); t1 = time.time()
    if f0["sof_epoch"] != f1["sof_epoch"]:
        sys.exit(f"continuity broke (epoch {f0['sof_epoch']}->{f1['sof_epoch']}); rerun")
    F = (f1["sof_frames_total"] - f0["sof_frames_total"]) & 0xFFFFFFFF
    H = t1 - t0
    b = F / (1000.0 * H) - 1.0
    print(f"F={F} frames  H={H:.3f} s  b = {b*1e6:+.1f} ppm  (+/- {2000/H:.1f} ppm from 1 ms quantisation)")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    cmd = sys.argv[1]; arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    h = open_raw()
    try:
        fn = globals().get("cmd_" + cmd)
        if not fn:
            print(__doc__); sys.exit(2)
        fn(h) if arg is None else fn(h, arg)
    finally:
        h.close()


if __name__ == "__main__":
    main()
