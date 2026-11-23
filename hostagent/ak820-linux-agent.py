#!/usr/bin/env python3
"""ak820-linux-agent.py -- the Linux host agent: now playing and the clock.

Stdlib Python 3 and `busctl` (systemd's), nothing to install or build. The
board is reached through the kernel's own hidraw node, found through sysfs,
so there is no hidapi and no HID enumeration; what is playing comes from
MPRIS on the session D-Bus, which Spotify, Firefox, Chrome, VLC, mpv,
Rhythmbox and most other players publish.

    ak820-linux-agent.py install [--clock]   # a systemd user service, at every login
    ak820-linux-agent.py status              # the service, the board, the last push
    ak820-linux-agent.py uninstall
    ak820-linux-agent.py probe               # what MPRIS says is playing; sends nothing
    ak820-linux-agent.py run [--clock]       # in the foreground (what the service runs)
    ak820-linux-agent.py text "Line 0" "Line 1" [--icon play|pause|stop|none]
    ak820-linux-agent.py clear
    ak820-linux-agent.py clock               # one clock sync

The bytes are the ones hostagent/ak820text.py and ak820-agent send: 32-byte
reports on QMK's raw-HID interface (usage page 0xFF60).

    now playing, line 0   07 12 03 00 <icon> <ascii, 19 max>    beside the icon
    now playing, line 1   07 12 03 01 <icon> <ascii, 21 max>
    playback position     07 12 04 <state> <pos u16 BE> <dur u16 BE>
    clear the slot        07 12 02
    set the clock         07 10 03 <yy mm dd wday hh mi ss> <ms u16 LE> 00 <bias s16 LE>

Scope, today: the USB cable only. 2.4G (the dongle's framed raw81 protocol)
and Bluetooth (the lock-light channel) are not implemented. The clock sends
the unknown-bias sentinel rather than learning the SOF bias as ak820-agent
does, so it lands within tens of ms rather than ~3 ms.

Permissions: /dev/hidraw* is root-only until hostagent/60-ak820pro.rules is
installed (setup.sh does it).

⚠️ Stop the agent while VIA is open (`systemctl --user stop ak820pro-agent`):
two programs on the raw-HID interface read each other's replies. flash.sh
stops and restarts it by itself.
"""
import argparse, fcntl, glob, json, os, select, shutil, signal, subprocess, sys, time
import unicodedata

VID, PID = 0x0C45, 0x8009
SYSFS = os.environ.get("AK820_SYSFS", "/sys/class/hidraw")    # overridable for tests
DEV = os.environ.get("AK820_DEV", "/dev")
REPORT = 32
ICONS = {"none": 0, "play": 1, "pause": 2, "stop": 3}
MAXLEN = {0: 19, 1: 21}          # DISPLAY_TEXT_MAX_L0/L1 in the firmware

UNIT = "ak820pro-agent"
HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local/state"), "ak820pro")
STATUS = os.path.join(STATE_DIR, "ak820-agent.status")      # flash.sh reads `clock=this daemon`
BIN_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share"), "ak820pro", "bin")
UNIT_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "systemd", "user")

POLL_S = 2.0              # MPRIS poll; two busctl calls per player
POSITION_EVERY_S = 5.0    # the firmware runs the position itself; re-assert this often
CLOCK_EVERY_S = 600.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# --- the board: sysfs to find it, hidraw to talk to it -----------------------

class BoardError(Exception):
    pass


def find_hidraw():
    """The board's raw-HID node, from two sysfs reads per hidraw node: its
    HID_ID (bus 0003 = USB, our VID/PID) and whether its report descriptor
    opens with Usage Page 0xFF60 (06 60 FF). The board's other interfaces
    share the VID/PID but not the usage page. Opens nothing."""
    want = "HID_ID=0003:%08X:%08X" % (VID, PID)
    hits = []
    for node in sorted(glob.glob(os.path.join(SYSFS, "hidraw*"))):
        try:
            with open(os.path.join(node, "device", "uevent")) as f:
                if want not in f.read().upper().split("\n"):
                    continue
            with open(os.path.join(node, "device", "report_descriptor"), "rb") as f:
                if f.read(3) != b"\x06\x60\xff":
                    continue
        except OSError:
            continue
        hits.append(os.path.join(DEV, os.path.basename(node)))
    if not hits:
        raise BoardError("board not found on USB (cable in? 2.4G and Bluetooth are not supported yet)")
    if len(hits) > 1:
        raise BoardError("more than one AK820 Pro raw-HID node; refusing to pick: " + ", ".join(hits))
    return hits[0]


def send(*payloads, reply=False):
    """Write reports through ONE open, so a two-line update lands in one
    firmware tick and the band repaints once (ak820text.send has the why).
    Each report is a single 33-byte write(2): report id 0, then 32 bytes."""
    path = find_hidraw()
    try:
        fd = os.open(path, os.O_RDWR)
    except PermissionError:
        raise BoardError(f"no permission on {path}: install hostagent/60-ak820pro.rules (setup.sh does)")
    except OSError as e:
        raise BoardError(f"cannot open {path}: {e}")
    try:
        for p in payloads:
            assert len(p) <= REPORT, p
            os.write(fd, bytes([0]) + bytes(p) + bytes(REPORT - len(p)))
        if reply:
            return _read_reply(fd, bytes(payloads[-1][:3]))
    finally:
        os.close(fd)


def _read_reply(fd, header, timeout=0.5):
    """The firmware answers with the request's first three bytes, or 0xFF and
    the next two for a command it does not handle. Anything else (another
    program's reply, an echo of an earlier write) is skipped."""
    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        if not select.select([fd], [], [], left)[0]:
            break
        r = os.read(fd, 64)
        if r[:3] == header:
            return r
        if r[:1] == b"\xff" and r[1:3] == header[1:3]:
            raise BoardError("the firmware answered 'unhandled' (an older firmware?)")
    return None


# --- the text channel --------------------------------------------------------

# The atlases are printable ASCII. Transliterate what NFKD leaves whole
# (ak820text.SUBS has the history).
SUBS = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
        "—": "-", "…": "...", " ": " ",
        "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d", "Ø": "O", "ø": "o",
        "Þ": "Th", "þ": "th", "ß": "ss", "ẞ": "SS", "Đ": "D", "đ": "d",
        "Ħ": "H", "ħ": "h", "ı": "i", "ĸ": "k", "Ł": "L", "ł": "l",
        "Ŋ": "N", "ŋ": "n", "Œ": "OE", "œ": "oe", "Ŧ": "T", "ŧ": "t"}


def to_ascii(s):
    for k, v in SUBS.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s)
    for k, v in SUBS.items():
        s = s.replace(k, v)
    s = s.encode("ascii", "ignore").decode()
    return "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s)


def line_packet(line, text, icon):
    return [0x07, 0x12, 0x03, line, ICONS[icon]] + list(to_ascii(text)[:MAXLEN[line]].encode())


def playback_packet(playing, pos, dur):
    pos = max(0, min(0xFFFF, int(pos)))
    dur = max(0, min(0xFFFF, int(dur)))
    return [0x07, 0x12, 0x04, 1 if playing else 0, pos >> 8, pos & 0xFF, dur >> 8, dur & 0xFF]


CLEAR = [0x07, 0x12, 0x02]


# --- the clock ---------------------------------------------------------------

def clock_packet(now=None):
    """RTC_SET_TIME_MS: "at receipt, true time was this". Built as late as
    possible and sent at once. 0x7FFF is the unknown-bias sentinel: a 0 would
    tell the firmware its SOF reference is perfect (clock/set.rs)."""
    t = time.time() if now is None else now
    lt = time.localtime(t)
    ms = min(999, int((t - int(t)) * 1000))
    wday = (lt.tm_wday + 1) % 7             # Python: Monday 0; firmware: Sunday 0
    return [0x07, 0x10, 0x03, lt.tm_year - 2000, lt.tm_mon, lt.tm_mday, wday,
            lt.tm_hour, lt.tm_min, lt.tm_sec, ms & 0xFF, ms >> 8, 0, 0xFF, 0x7F]


CLOCK_STATUS = {0: "stepped", 1: "slewing", 0xFE: "busy", 0xFF: "rejected"}


def sync_clock():
    """One SET, retried once on busy, as the C does."""
    for _ in range(2):
        r = send(clock_packet(), reply=True)
        if r is None:
            return "no reply"
        st = CLOCK_STATUS.get(r[3], f"status {r[3]:#x}")
        if r[3] != 0xFE:
            return st
        time.sleep(0.2)
    return st


# --- now playing, from MPRIS -------------------------------------------------

def busctl(*args):
    out = subprocess.run(["busctl", "--user", "--json=short", *args],
                         capture_output=True, text=True, timeout=3)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or f"busctl exited {out.returncode}")
    return json.loads(out.stdout)["data"]


def _v(x):                       # busctl's {"type": .., "data": ..} -> data
    return x["data"] if isinstance(x, dict) and "data" in x else x


def players():
    names = busctl("call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                   "org.freedesktop.DBus", "ListNames")[0]
    return sorted(n for n in names if n.startswith("org.mpris.MediaPlayer2."))


def player_state(name):
    props = busctl("call", name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties",
                   "GetAll", "s", "org.mpris.MediaPlayer2.Player")[0]
    meta = {k: _v(v) for k, v in (_v(props.get("Metadata")) or {}).items()}
    artist = meta.get("xesam:artist") or []
    return {
        "player": name.split(".", 3)[3],
        "status": _v(props.get("PlaybackStatus")) or "Stopped",
        "artist": ", ".join(artist) if isinstance(artist, list) else str(artist),
        "title": str(meta.get("xesam:title") or ""),
        "length_s": int(meta.get("mpris:length") or 0) / 1e6,
        "position_s": int(_v(props.get("Position")) or 0) / 1e6,
    }


def now_playing():
    """The first Playing player with a title or artist, else the first Paused one."""
    states = []
    for n in players():
        try:
            states.append(player_state(n))
        except Exception:
            continue                  # quit mid-call, or no Player interface
    for want in ("Playing", "Paused"):
        for s in states:
            if s["status"] == want and (s["title"] or s["artist"]):
                return s
    return None


# --- the daemon ----------------------------------------------------------------

def write_status(**kv):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")
    os.replace(tmp, STATUS)


def single_instance():
    run_dir = os.environ.get("XDG_RUNTIME_DIR") or STATE_DIR
    os.makedirs(run_dir, exist_ok=True)
    f = open(os.path.join(run_dir, "ak820pro-agent.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another ak820-linux-agent is already running")
    return f


class Stop(Exception):
    pass


def run(clock=False, poll=POLL_S):
    lock = single_instance()          # noqa: F841 -- held for the process's life
    def on_term(*_):
        raise Stop()
    signal.signal(signal.SIGTERM, on_term)
    log(f"started (pid {os.getpid()}, clock {'on' if clock else 'off'})")
    shown = None                      # what the slot shows: (artist, title, icon)
    board = None                      # the hidraw path last seen, to notice a replug
    last_pos = last_clock = -1e9
    clock_result = last_push = "-"
    last_err = None
    try:
        while True:
            try:
                path = find_hidraw()
                if path != board:     # arrived, or re-enumerated: resend everything
                    log(f"board at {path}")
                    board, shown, last_pos, last_clock = path, None, -1e9, -1e9
                if clock and time.monotonic() - last_clock > CLOCK_EVERY_S:
                    clock_result = sync_clock()
                    last_clock = time.monotonic()
                    log(f"clock sync: {clock_result}")
                try:
                    s = now_playing()
                except Exception as e:
                    raise RuntimeError(f"MPRIS: {e}")
                pkts = []
                if s is None:
                    if shown is not None:
                        pkts = [playback_packet(False, 0, 0), CLEAR]
                        shown = None
                        last_push = time.strftime("%H:%M:%S") + " cleared"
                        log("nothing playing: slot handed back to the clock")
                else:
                    playing = s["status"] == "Playing"
                    icon = "play" if playing else "pause"
                    key = (s["artist"], s["title"], icon)
                    if key != shown:
                        pkts += [line_packet(0, s["artist"], icon), line_packet(1, s["title"], icon)]
                        shown = key
                        last_push = f"{time.strftime('%H:%M:%S')} {s['player']}: {s['artist']} - {s['title']}"
                        log(f"now playing ({s['player']}, {s['status']}): {s['artist']} - {s['title']}")
                    if pkts or time.monotonic() - last_pos > POSITION_EVERY_S:
                        pkts.append(playback_packet(playing and s["length_s"] > 0,
                                                    s["position_s"], s["length_s"]))
                        last_pos = time.monotonic()
                if pkts:
                    send(*pkts)
                last_err = None
            except (BoardError, RuntimeError, OSError) as e:
                if str(e) != last_err:      # log a condition once, not every poll
                    log(e)
                if isinstance(e, BoardError):
                    board = None
                last_err = str(e)
            write_status(pid=os.getpid(), board=board or "absent",
                         clock="this daemon" if clock else "off",
                         last_clock_sync=clock_result, last_push=last_push,
                         error=last_err or "none")
            time.sleep(poll)
    except (Stop, KeyboardInterrupt):
        log("stopping: handing the slot back to the clock")
        try:
            send(playback_packet(False, 0, 0), CLEAR)
        except Exception:
            pass
        try:
            os.remove(STATUS)
        except OSError:
            pass


# --- install as a systemd user service ----------------------------------------

def systemctl(*a, check=True):
    return subprocess.run(["systemctl", "--user", *a], check=check, capture_output=True, text=True)


def install(clock):
    if not shutil.which("busctl"):
        raise SystemExit("busctl not found (it comes with systemd)")
    if not shutil.which("systemctl"):
        raise SystemExit("systemctl not found: run `ak820-linux-agent.py run` from your session's autostart instead")
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(UNIT_DIR, exist_ok=True)
    dest = os.path.join(BIN_DIR, "ak820-linux-agent.py")
    # A copy, so moving or re-checking-out the repo cannot break the service.
    shutil.copyfile(os.path.abspath(__file__), dest)
    os.chmod(dest, 0o755)
    args = "run --clock" if clock else "run"
    unit = f"""[Unit]
Description=AK820 Pro host agent (now playing{' and the clock' if clock else ''} on the keyboard's screen)
After=dbus.socket

[Service]
ExecStart={sys.executable} {dest} {args}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
    with open(os.path.join(UNIT_DIR, UNIT + ".service"), "w") as f:
        f.write(unit)
    systemctl("daemon-reload")
    systemctl("enable", UNIT)
    systemctl("restart", UNIT)
    print(f"installed: {dest}\nservice:   {UNIT} (systemctl --user status {UNIT}; journalctl --user -u {UNIT})")
    try:
        print("board:    ", find_hidraw())
    except BoardError as e:
        print("board:    ", e)


def uninstall():
    systemctl("disable", "--now", UNIT, check=False)
    for p in (os.path.join(UNIT_DIR, UNIT + ".service"), os.path.join(BIN_DIR, "ak820-linux-agent.py"), STATUS):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    systemctl("daemon-reload", check=False)
    print("removed")


def status():
    r = systemctl("is-active", UNIT, check=False)
    print("service:", r.stdout.strip() or "not installed")
    try:
        print("board:  ", find_hidraw())
    except BoardError as e:
        print("board:  ", e)
    if os.path.exists(STATUS):
        age = time.time() - os.path.getmtime(STATUS)
        print(f"status ({age:.0f} s old):")
        with open(STATUS) as f:
            print("  " + f.read().strip().replace("\n", "\n  "))


def main():
    ap = argparse.ArgumentParser(description="AK820 Pro host agent for Linux (now playing + clock over USB)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("find", "probe", "clear", "clock", "status", "uninstall"):
        sub.add_parser(name)
    t = sub.add_parser("text")
    t.add_argument("line0")
    t.add_argument("line1", nargs="?", default="")
    t.add_argument("--icon", default="none", choices=list(ICONS))
    for name in ("run", "install"):
        p = sub.add_parser(name)
        p.add_argument("--clock", action="store_true", help="keep the keyboard's clock synced too")
    a = ap.parse_args()
    try:
        if a.cmd == "find":
            print(find_hidraw())
        elif a.cmd == "probe":
            for n in players():
                try:
                    print(json.dumps(player_state(n)))
                except Exception as e:
                    print(n, "error:", e)
            print("chosen:", json.dumps(now_playing()))
        elif a.cmd == "text":
            send(line_packet(0, a.line0, a.icon), line_packet(1, a.line1, a.icon))
        elif a.cmd == "clear":
            send(playback_packet(False, 0, 0), CLEAR)
        elif a.cmd == "clock":
            print("clock:", sync_clock())
        elif a.cmd == "run":
            run(a.clock)
        elif a.cmd == "install":
            install(a.clock)
        elif a.cmd == "uninstall":
            uninstall()
        elif a.cmd == "status":
            status()
    except BoardError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
