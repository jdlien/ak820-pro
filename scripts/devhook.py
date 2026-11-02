"""HC_DEVHOOK, dev builds only (hid_protocol.c; build.sh dev): press Fn+D,
read or reset the display probe (graphics/display.c, DPROBE), and set or read
the panel backlight.

    scripts/devhook.py press | reset | read
    scripts/devhook.py lcd [LEVEL | on | off]
    scripts/devhook.py leds [reset | json]
    scripts/devhook.py frames [reset | json]

`lcd` alone reads the backlight; a LEVEL or on/off sets it (a LEVEL above the
maximum is clamped by the firmware, and the reply says what was set). Setting
is RAM only: nothing persists, and a reboot restores the level the keys last
saved. "off" is what Fn+Home does, without its overlay. Needs flash 2f or later
(the older dev builds answer "unhandled").

`leds` reads the inbound 5A trace (flash 2g or later): every checksum-valid
`5A` frame the module sent, i.e. what reached the board of the host's LED
report, as frame number, byte and ms since the previous frame (the ring keeps
the last 52). `leds reset` clears it; `leds json` prints the same as one JSON
object, for scripts/ledchannel_test.py.

`frames` reads the lock-LED channel's receiver (flash 2h or later, lockchan.c):
frames committed, preambles reached, each abort reason's count, and the last
frame (profile, type, seq, payload, its anchor and commit times). `frames
reset` zeroes it; `frames json` prints it as one JSON object.
`rxtap` reads the RX tap (gremlin/rx-tap, ops 15-16): every raw byte from the
CH582F while armed, the last 208 kept (260 before the lock-LED clock). `rxtap arm` clears and starts it,
`rxtap stop` stops it (stop before reading); the read splits the bytes into
5A/5B/5C frames, 61 0D 0A ACKs and anything else, which is what it is for: a
module frame type nobody has documented. `rxtap json` prints it as JSON.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hostagent"))
from ak820health import open_device
SET_VALUE, CH, HC = 0x07, 0x13, 0x76
NAMES = [f"restore clear band {i}" for i in range(1, 9)] + [
    "restore: OS icon", "restore: conn row + clock", "restore: conn digit",
    "restore: battery (outline)", "restore: lock band", "restore: text slot",
    "hk: text slot", "hk: status overlay", "hk: lock band", "hk: clock", "hk: battery",
    "hk: conn digit", "text icon", "band clear", "debug page compose", "debug glyph pump"]
USAGE = ("usage: devhook.py press | reset | read | lcd [LEVEL | on | off] | leds [reset | json]"
         " | frames [reset | json] | rxtap [arm | stop | json]")
def xfer(h, op, arg=0):
    h.write(bytes([0, SET_VALUE, CH, HC, op, arg]) + bytes(27))   # report id + 32 bytes
    for _ in range(5):
        r = h.read(32, 1000)
        # A whole report answering this op: channel, command and the echoed op
        # (codex, flash 2f: an op-2 reply was otherwise taken for LCD state).
        if r and len(r) == 32 and r[1] == CH and r[2] == HC and r[3] == op:
            if r[0] != SET_VALUE: sys.exit(f"unhandled: {bytes(r[:8]).hex()} (flash 2f or later for lcd, 2g for leds)")
            return bytes(r)
    sys.exit("no reply")
args = sys.argv[1:]
ok = (len(args) == 1 and args[0] in ("press", "reset", "read", "lcd", "leds", "frames", "rxtap")) or (
    len(args) == 2 and args[0] == "rxtap" and args[1] in ("arm", "stop", "json")) or (
    len(args) == 2 and args[0] == "lcd" and (args[1] in ("on", "off") or
                                           (args[1].isdigit() and int(args[1]) <= 255))) or (
    len(args) == 2 and args[0] in ("leds", "frames") and args[1] in ("reset", "json"))
if not ok:
    sys.exit(USAGE)
h = open_device()
cmd = args[0]
if cmd == "press": xfer(h, 1)
elif cmd == "reset": xfer(h, 3)
elif cmd == "lcd":
    arg = args[1] if len(args) > 1 else None
    if arg is None: r = xfer(h, 6)
    elif arg in ("on", "off"): r = xfer(h, 5, 1 if arg == "on" else 0)
    else: r = xfer(h, 4, int(arg))
    level, top, on, eff, saved = r[4:9]
    print(f"level {level}/{top} {'on' if on else 'off'}, effective {eff}, "
          f"saved {saved - 1 if saved else 'none'}")
elif cmd == "leds" and args[1:] == ["reset"]: xfer(h, 9)
elif cmd == "leds":
    u32 = lambda b: int.from_bytes(b, "little")
    # Header, pages, header again: consistent only if the count held still
    # between them (codex, flash 2g). Each page echoes its number.
    for _ in range(5):
        r = xfer(h, 7)
        frames, accepted, leds, last, age, size = (u32(r[4:8]), u32(r[8:12]), r[12], r[13],
                                                   u32(r[14:18]), r[18])
        if size != 52: sys.exit(f"unexpected ring size {size} (flash 2g)")
        pages = [xfer(h, 8, pg) for pg in range(4)]
        if any(p[4] != pg or p[5] != 0 for pg, p in enumerate(pages)):
            sys.exit("a ring page did not echo its number")
        if u32(xfer(h, 7)[4:8]) == frames: break
    else:
        sys.exit("the trace kept moving while it was read")
    slots = b"".join(p[6:32] for p in pages)
    seq = [(n, slots[2 * (n % size)], slots[2 * (n % size) + 1])
           for n in range(max(0, frames - size), frames)]
    if args[1:] == ["json"]:
        import json
        print(json.dumps({"frames": frames, "accepted": accepted, "host_leds": leds, "last": last,
                          "age_ms": None if age == 0xFFFFFFFF else age,
                          "seq": [{"n": n, "byte": b, "gap_ms": None if g == 255 else g}
                                  for n, b, g in seq]}))
    else:
        print(f"{frames} frames, {accepted} accepted; host_leds 0x{leds:02x}, last 0x{last:02x}, "
              f"{'none yet' if age == 0xFFFFFFFF else f'{age} ms ago'}")
        for n, b, g in seq:
            print(f"  #{n:<5} 0x{b:02x}  {'>254' if g == 255 else g:>4} ms")
elif cmd == "frames" and args[1:] == ["reset"]: xfer(h, 13)
elif cmd == "frames":
    u32 = lambda b: int.from_bytes(b, "little")
    ABORTS = ["gap", "lifetime", "caps", "header_crc", "header", "range", "crc", "trailer", "reset"]
    for _ in range(5):   # consistent only if no frame landed between the reads
        r = xfer(h, 10)
        ab = xfer(h, 11)
        pages = [xfer(h, 12, pg) for pg in (0, 1)]
        if any(p[4] != pg or p[5] != 0 for pg, p in enumerate(pages)):
            sys.exit("a payload page did not echo its number")
        if xfer(h, 10)[4:8] == r[4:8]: break
    else:
        sys.exit("frames kept arriving while they were read")
    st = {"frames": u32(r[4:8]), "preambles": u32(r[8:12]), "busy": bool(r[12]),
          "aborts": {n: int.from_bytes(ab[4 + 2 * i:6 + 2 * i], "little") for i, n in enumerate(ABORTS)},
          "last": {"profile": r[13], "type": r[14], "seq": r[15], "len": r[16],
                   "payload": (pages[0][6:32] + pages[1][6:28])[:r[16]].hex(),
                   "anchor_ms": u32(r[17:21]), "commit_ms": u32(r[21:25])},
          "board_ms": u32(r[25:29])}
    if args[1:] == ["json"]:
        import json
        print(json.dumps(st))
    else:
        l = st["last"]
        print(f"{st['frames']} frames, {st['preambles']} preambles{', mid-frame' if st['busy'] else ''}; aborts "
              + ", ".join(f"{k} {v}" for k, v in st["aborts"].items() if v))
        if st["frames"]:
            print(f"  last: P{l['profile']} type {l['type']} seq {l['seq']} len {l['len']}, "
                  f"{(st['board_ms'] - l['commit_ms']) & 0xFFFFFFFF} ms ago, "
                  f"{(l['commit_ms'] - l['anchor_ms']) & 0xFFFFFFFF} ms from anchor to commit")
            print(f"  payload {bytes.fromhex(l['payload'])!r}")
elif cmd == "rxtap" and args[1:] in (["arm"], ["stop"]):
    # On a build with the link trace (gremlin/linktrace, 11-01) mode 2 is the
    # trace holding the ring, and a stop drops it to 0 with the trace kept:
    # read that with `ak820 sleep` first (codex's linktrace review, P2).
    if args[1] == "stop" and xfer(h, 15, 0)[4] == 2:
        sys.exit("the link trace holds the tap's ring: read it with `ak820 sleep`, or `rxtap arm` to take the ring")
    r = xfer(h, 15, 1 if args[1] == "arm" else 2)
    print(f"rx tap {'armed' if r[4] else 'stopped'}, {int.from_bytes(r[5:9], 'little')} bytes")
elif cmd == "rxtap":
    # Stop it first (`rxtap stop`) for a consistent read; the header is read
    # before and after the pages as for the 5A trace.
    u32 = lambda b: int.from_bytes(b, "little")
    for _ in range(5):
        r = xfer(h, 15, 0)
        armed, count, size = r[4], u32(r[5:9]), int.from_bytes(r[9:11], "little")
        if armed == 2:   # the link trace's ring: its count is the wake's timer, not bytes
            sys.exit("the link trace holds the tap's ring: read it with `ak820 sleep`, or `rxtap arm` to take the ring")
        if size == 0 or size % 26: sys.exit(f"unexpected tap size {size}")   # 260, or 208 since the lock-LED clock
        pages = [xfer(h, 16, pg) for pg in range(size // 26)]
        if any(p[4] != pg or p[5] != 0 for pg, p in enumerate(pages)):
            sys.exit("a tap page did not echo its number")
        if u32(xfer(h, 15, 0)[5:9]) == count: break
    else:
        sys.exit("the tap kept moving while it was read: `rxtap stop` first")
    ring = b"".join(p[6:32] for p in pages)
    n = min(count, size)
    # Not yet wrapped: slots 0..count-1 in order. Wrapped: the oldest is the
    # next slot to be written, count % size (the firmware's own slot index
    # agrees with it until the count wraps at 2^32).
    data = ring[:n] if count <= size else ring[count % size:] + ring[:count % size]
    # Tokenise as the parser would: 5A/5B/5C with a good sum, the 61 0D 0A ACK,
    # and anything else, which is what the tap is for.
    toks, i = [], 0
    while i < len(data):
        b = data[i:i + 3]
        if len(b) == 3 and b[0] in (0x5A, 0x5B, 0x5C) and b[2] == (b[0] + b[1]) & 0xFF:
            toks.append(("frame", b)); i += 3
        elif b == b"\x61\x0d\x0a":
            toks.append(("ack", b)); i += 3
        else:
            if toks and toks[-1][0] == "other": toks[-1] = ("other", toks[-1][1] + data[i:i + 1])
            else: toks.append(("other", data[i:i + 1]))
            i += 1
    other = sum(len(t) for k, t in toks if k == "other")
    if args[1:] == ["json"]:
        import json
        print(json.dumps({"armed": bool(armed), "count": count, "bytes": data.hex(),
                          "tokens": [[k, t.hex()] for k, t in toks], "unrecognised": other}))
    else:
        print(f"rx tap {'ARMED' if armed else 'stopped'}: {count} bytes since arming, "
              f"{n} held, {other} not part of a known frame"
              + (f" (the first {count - n} have scrolled out)" if count > n else ""))
        for k, t in toks:
            print(f"  {k:5} {t.hex(' ')}")
elif cmd == "read":
    vals = []
    for pg in (0, 1):
        r = xfer(h, 2, pg)
        vals += [r[4 + 2 * k] | (r[5 + 2 * k] << 8) for k in range(14)]
    for n, v in zip(NAMES, vals):
        if v: print(f"{v / 1000:7.2f} ms  {n}")
h.close()
