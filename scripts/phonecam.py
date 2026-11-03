#!/usr/bin/env python3
"""The bench camera: JD's Pixel 8 on its tripod, driven over adb.

    scripts/phonecam.py setup            # awake on power, Camera open, Slow Motion at 1/8x
    scripts/phonecam.py offset           # the phone's clock minus the Mac's
    scripts/phonecam.py record 5         # offset, start, 5 s, stop, pull, probe, delete
    scripts/phonecam.py start | stop     # one key each, stamped on both clocks
    scripts/phonecam.py pull [NAME]      # the newest clip, or NAME, to --out (--delete)
    scripts/phonecam.py teardown         # screen timeout back on
    scripts/phonecam.py status           # who holds the phone, and is it recording

docs/test-bench.md ("The camera") has the measurements behind each step.

Every start and stop appends one JSON line to ~/Documents/ak820pro-phonecam/
stamps.jsonl, with the Mac's time around the command and the phone's on
either side of the key. A clip's frames are 240 a second of real time, so
the record step also prints the gap between the keys' interval and the
frames' span. On 11-03 that gap was 0.710 to 0.773 s across eleven clips.

Rules this follows, each learned on 11-03:
- no UI dump while recording: uiautomator waits for an idle screen, and the
  camera's never idles, so one read held a 3 s clip open for 14.8 s;
- stay awake on AC as well as USB: the hub charges the phone as AC;
- the volume key is the shutter. A start that makes no new file is
  reported, not retried;
- the phone's storage fills, so record deletes its clip from the phone
  once the Mac's copy matches it in size (--keep to keep it). pull leaves
  the phone alone unless --delete;
- one volume key from anyone else stops your recording. So record, setup
  and start take a flock on phone.lock (flock, never a POSIX record lock:
  on macOS the two never see each other), and refuse, naming the holder,
  if it is taken. start leaves phone.hold behind (who, since when) until
  its stop; a hold lives while its process does, or 10 min. And the
  camera's own state decides the key: start and record refuse while it
  is recording, and stop refuses while it is not, since that key would
  start a recording instead.
"""
import argparse
import fcntl
import json
import os
import re
import statistics
import subprocess
import sys
import time

CAM = "/sdcard/DCIM/Camera"
PKG = "com.google.android.GoogleCamera"
LOGDIR = os.path.expanduser("~/Documents/ak820pro-phonecam")
STAMPS = os.path.join(LOGDIR, "stamps.jsonl")
LOCKDIR = os.environ.get("PHONECAM_LOCKDIR", LOGDIR)  # the override is for tests
LOCK = os.path.join(LOCKDIR, "phone.lock")  # flock: one phone command at a time
HOLD = os.path.join(LOCKDIR, "phone.hold")  # a start's claim until its stop
HOLD_MAX_S = 600


def describe(info):
    if not info:
        return "an unknown holder"
    since = info.get("since", 0)
    who = f"pid {info.get('pid', '?')}"
    if info.get("owner"):
        who = f"{info['owner']} ({who})"
    return (f"{who}, `{info.get('cmd', '?')}`, since {time.strftime('%H:%M:%S', time.localtime(since))} "
            f"({time.time() - since:.0f} s ago)")


def take_lock(what):
    """flock phone.lock for the rest of this process, or refuse naming its holder."""
    os.makedirs(LOCKDIR, exist_ok=True)
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            info = json.loads(os.pread(fd, 4096, 0) or b"{}")
        except ValueError:
            info = {}
        sys.exit(f"the phone is busy: {describe(info)} holds {LOCK}")
    os.ftruncate(fd, 0)
    os.pwrite(fd, json.dumps({"pid": os.getpid(), "cmd": what, "since": time.time()}).encode(), 0)
    return fd


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, TypeError, ValueError):
        return False


def read_hold():
    try:
        with open(HOLD) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def hold_live(h):
    return pid_alive(h.get("pid")) or time.time() - h.get("since", 0) < HOLD_MAX_S


def refuse_if_held(what, owner=None):
    """A live hold that is not ours refuses; a stale one is cleared with a note."""
    h = read_hold()
    if not h:
        return
    if owner and h.get("owner") == owner:
        return
    if hold_live(h):
        sys.exit(f"the phone is held by {describe(h)}: a start whose stop has not come, so "
                 f"`{what}` could end its recording. Its holder runs stop; stop --force ends it")
    print(f"note: cleared a stale hold by {describe(h)}")
    os.remove(HOLD)


def adb(*args, timeout=30, check=True):
    r = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        sys.exit(f"adb {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def sh(cmd, timeout=30):
    return adb("shell", cmd, timeout=timeout)


def require_device():
    out = adb("devices")
    rows = [l.split() for l in out.splitlines()[1:] if l.strip()]
    if not rows:
        sys.exit("no phone on adb: is the cable in and USB debugging on?")
    if len(rows) > 1:
        sys.exit("more than one adb device: set ANDROID_SERIAL")
    if rows[0][1] == "unauthorized":
        sys.exit("phone says unauthorized: unlock it and tap Allow on the USB debugging prompt")
    if rows[0][1] != "device":
        sys.exit(f"phone is {rows[0][1]}")


def ui_nodes():
    """The camera's UI, one dict a node. Only when NOT recording."""
    xml = sh("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml", timeout=25)
    nodes = []
    for m in re.finditer(r"<node [^>]*>", xml):
        n = m.group(0)
        attr = dict(re.findall(r'([\w-]+)="([^"]*)"', n))
        b = [int(v) for v in re.findall(r"\d+", attr.get("bounds", ""))]
        if len(b) == 4:
            attr["center"] = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
        nodes.append(attr)
    return nodes


def find(nodes, key, value):
    return next((n for n in nodes if n.get(key) == value), None)


def camera_focused():
    return PKG in sh("dumpsys window | grep mCurrentFocus")


def awake_unlocked():
    p = sh("dumpsys power | grep -m1 mWakefulness=")
    k = sh("dumpsys window | grep -m1 isKeyguardShowing")
    return "Awake" in p, "isKeyguardShowing=true" not in k


def clips():
    out = sh(f"ls -t {CAM} | grep -E '^PXL_.*\\.mp4$'")
    return [l.strip() for l in out.splitlines() if l.strip()]


def recording():
    """The camera is recording while a .pending- file in the Camera folder is being written.

    The camera writes .pending-<expiry>-_PXL_<id>.mp4 as it records and
    renames it at the stop (11-03). A crash could leave one behind, so
    only one written in the last 3 s counts.
    """
    ages = sh(f"now=$(date +%s); for f in {CAM}/.pending-*; do "
              f"[ -e \"$f\" ] && echo $((now - $(stat -c %Y \"$f\"))); done; true")
    return any(int(a) <= 3 for a in ages.split() if a.lstrip("-").isdigit())


def offset_ms(n=15):
    """Phone minus Mac, from the sample with the shortest round trip."""
    best = None
    rtts = []
    for _ in range(n):
        a = time.time()
        p = float(sh("date +%s.%N"))
        b = time.time()
        rtt = b - a
        rtts.append(rtt * 1000)
        if best is None or rtt < best[0]:
            best = (rtt, (p - (a + b) / 2) * 1000)
    return best[1], best[0] * 1000, statistics.median(rtts)


def press(label):
    """The volume key, stamped on the Mac around the command and on the phone around the key."""
    a = time.time()
    out = sh("date +%s.%N; cmd input keyevent KEYCODE_VOLUME_DOWN; date +%s.%N")
    b = time.time()
    p0, p1 = (float(x) for x in out.split())
    rec = {"event": label, "mac_before": round(a, 4), "mac_after": round(b, 4),
           "phone_before": round(p0, 4), "phone_after": round(p1, 4)}
    os.makedirs(LOGDIR, exist_ok=True)
    with open(STAMPS, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"{label}: phone {p0:.3f} -> {p1:.3f} ({(p1 - p0) * 1000:.0f} ms on the phone), "
          f"mac {a:.3f} -> {b:.3f}")
    return rec


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets:format_tags=com.android.capture.fps",
         "-of", "default=nw=1", path], capture_output=True, text=True).stdout
    frames = int(re.search(r"nb_read_packets=(\d+)", out).group(1))
    fps = re.search(r"capture.fps=([\d.]+)", out)
    return frames, float(fps.group(1)) if fps else None


def pull(name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    adb("pull", f"{CAM}/{name}", out_dir, timeout=600)
    return os.path.join(out_dir, name)


def delete_from_phone(name, local_path):
    """Remove a clip from the phone once the Mac's copy matches its size.

    Through the media index, so the gallery keeps no ghost and nothing goes
    to a trash; `rm` only if the index has no row for it.
    """
    if not re.fullmatch(r"PXL_[0-9_]+(\.[A-Z]+)?\.mp4", name):
        sys.exit(f"refusing to delete {name!r}: not a camera clip's name")
    on_phone = int(sh(f"stat -c %s {CAM}/{name}").strip())
    if os.path.getsize(local_path) != on_phone:
        sys.exit(f"kept {name} on the phone: the Mac's copy is not its size")
    uri = "content://media/external/video/media"
    rows = sh(f"content query --uri {uri} --projection _id --where \"_display_name='{name}'\"")
    ids = re.findall(r"_id=(\d+)", rows)
    if len(ids) == 1:
        sh(f"content delete --uri {uri}/{ids[0]}")
    else:
        sh(f"rm {CAM}/{name}")
    if name in clips():
        sys.exit(f"{name} is still on the phone")
    print(f"deleted {name} from the phone ({on_phone / 1e6:.1f} MB; the Mac's copy is {local_path})")


def cmd_setup(args):
    _lock = take_lock("setup")
    refuse_if_held("setup")
    require_device()
    if recording():
        sys.exit("the camera is recording: setup's UI reads would stretch the clip; stop it first")
    sh("settings put global stay_on_while_plugged_in 3")  # AC | USB
    sh("input keyevent KEYCODE_WAKEUP")
    awake, unlocked = awake_unlocked()
    if not unlocked:
        sys.exit("the phone is locked: unlock it once (it then stays awake on power)")
    if not camera_focused():
        sh("am start -a android.media.action.VIDEO_CAMERA >/dev/null")
        time.sleep(2.5)
    nodes = ui_nodes()
    chip = find(nodes, "content-desc", "Switch to Slow Motion Mode")
    if chip:
        sh("input tap %d %d" % chip["center"])
        time.sleep(1.5)
        nodes = ui_nodes()
    shutter = find(nodes, "resource-id", "ComposeShutter")
    speed = find(nodes, "text", "1/8×")
    ok = shutter is not None and shutter.get("content-desc") == "Start slow motion"
    print("stay awake on power: on (AC|USB)")
    print("camera:", "Slow Motion, ready" if ok else f"NOT ready (shutter: {shutter and shutter.get('content-desc')})")
    print("speed:", "1/8x (240 fps)" if speed else "not 1/8x: tap the speed button (bottom right) to 1/8x")
    sys.exit(0 if ok and speed else 1)


def cmd_teardown(args):
    require_device()
    sh("settings put global stay_on_while_plugged_in 0")
    print("stay awake on power: off (the screen times out as usual)")


def cmd_offset(args):
    require_device()
    off, rtt, med = offset_ms()
    print(f"phone - mac: {off:+.1f} ms (best round trip {rtt:.0f} ms, median {med:.0f} ms)")


def check_ready():
    require_device()
    awake, unlocked = awake_unlocked()
    if not (awake and unlocked and camera_focused()):
        sys.exit("the camera is not in front, awake and unlocked: run setup first")


def owner_of(args):
    return args.owner or os.environ.get("PHONECAM_OWNER")


def cmd_start(args):
    _lock = take_lock("start")
    refuse_if_held("start")
    check_ready()
    if recording():
        sys.exit("the camera is already recording: a start key would stop it")
    hold = {"pid": os.getppid(), "owner": owner_of(args), "cmd": "start", "since": time.time()}
    with open(HOLD, "w") as f:
        json.dump(hold, f)
    print(f"holding the phone for {describe(hold)} until stop")
    press("start")


def cmd_stop(args):
    _lock = take_lock("stop")
    h = read_hold()
    if h and h.get("owner") and h.get("owner") != owner_of(args) and not args.force:
        sys.exit(f"the hold belongs to {describe(h)}, not to you: stop --force ends it anyway")
    require_device()
    if not h and not args.force:
        if recording():
            sys.exit("the camera is recording, but not from a phonecam start (by hand?): "
                     "stop --force stops it")
        sys.exit("nothing to stop: no hold, and a stop key could start a recording")
    if not recording():
        if h:
            os.remove(HOLD)
        sys.exit("the camera is not recording: a stop key would start a recording, so none was sent"
                 + (f" (cleared {describe(h)}'s hold)" if h else ""))
    press("stop")
    if h:
        os.remove(HOLD)


def cmd_pull(args):
    require_device()
    name = args.name or clips()[0]
    path = pull(name, args.out)
    frames, fps = probe(path)
    print(f"{path}: {frames} frames at {fps or '?'} fps capture = {frames / (fps or 30):.3f} s real")
    if args.delete:
        delete_from_phone(name, path)


def cmd_status(args):
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o644) if os.path.isdir(LOCKDIR) else None
    if fd is None:
        print("lock: free (no lock directory yet)")
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)  # a look only: never hold it past this line
            print("lock: free")
        except BlockingIOError:
            try:
                info = json.loads(os.pread(fd, 4096, 0) or b"{}")
            except ValueError:
                info = {}
            print(f"lock: held by {describe(info)}")
    h = read_hold()
    print("hold: none" if not h else f"hold: {describe(h)}{'' if hold_live(h) else ' (stale)'}")
    require_device()
    print("camera:", "recording" if recording() else "not recording",
          "| in front" if camera_focused() else "| NOT in front")


def cmd_record(args):
    _lock = take_lock(f"record {args.seconds:g}")
    refuse_if_held("record")
    check_ready()
    if recording():
        sys.exit("the camera is already recording (not through phonecam): a start key would stop it")
    before = set(clips())
    off, rtt, _ = offset_ms()
    print(f"phone - mac: {off:+.1f} ms (round trip {rtt:.0f} ms)")
    s = press("start")
    time.sleep(args.seconds)
    e = press("stop")
    time.sleep(2.5)  # the file is finalized after the stop
    new = [c for c in clips() if c not in before]
    if not new:
        sys.exit("no new clip: is the volume key the shutter (Camera settings, Gestures)?")
    path = pull(new[0], args.out)
    frames, fps = probe(path)
    span = frames / (fps or 30)
    keys = e["phone_before"] - s["phone_before"]
    print(f"{path}: {frames} frames at {fps or '?'} fps = {span:.3f} s real")
    print(f"keys {keys:.3f} s apart on the phone; the frames span {span:.3f}; gap {keys - span:.3f} s")
    print(f"start key on the Mac's clock: {s['phone_before'] - off / 1000:.3f} "
          f"(the file name's stamp is the phone's clock, {off / 1000:+.3f} s from the Mac's)")
    if not args.keep:
        delete_from_phone(new[0], path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    sub.add_parser("teardown").set_defaults(fn=cmd_teardown)
    sub.add_parser("offset").set_defaults(fn=cmd_offset)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("start")
    p.add_argument("--owner", help="name the hold (or PHONECAM_OWNER); stop then needs the same")
    p.set_defaults(fn=cmd_start)
    p = sub.add_parser("stop")
    p.add_argument("--owner")
    p.add_argument("--force", action="store_true", help="end another owner's hold")
    p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("pull")
    p.add_argument("name", nargs="?")
    p.add_argument("--out", default=os.path.expanduser("~/Downloads"))
    p.add_argument("--delete", action="store_true", help="remove it from the phone once the copy checks out")
    p.set_defaults(fn=cmd_pull)
    p = sub.add_parser("record")
    p.add_argument("seconds", type=float)
    p.add_argument("--out", default=os.path.expanduser("~/Downloads"))
    p.add_argument("--keep", action="store_true", help="leave the clip on the phone too")
    p.set_defaults(fn=cmd_record)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
