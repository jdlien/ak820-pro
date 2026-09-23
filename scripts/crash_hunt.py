#!/usr/bin/env python3
"""Overnight crash hunt (plans/CRASH-HUNT-PLAN.md, Part C). macOS only.

soak.py is a pass/fail gate for a firmware change: five minutes, stop at the
first lost reply. This is the other job -- run for hours against the DAILY
firmware, drive the LCD blit path far harder than production does, and when
the board drops off the bus, wait for the watchdog to bring it back, capture
the retained record, and KEEP GOING. One unexplained reset in several days of
real use is the rate being hunted; a quiet night proves little, a night with a
record tells us where the main loop stopped.

Stressors (one handle, strictly serialised, as soak.py):
  - text pushes on both lines every --text-every s (default 0.2): LCD blits
  - playback-state flips every --playback-every s (default 2): the band
    handoff between the clock and the playback readout, the redraw the S2
    soaks drove to 216 blit timeouts (plans/BACKLOG.md)
  - RGB effect sweep every 20 s WITHOUT saving: new per-frame code paths, no
    flash wear
  - ONE keymap flip and ONE rgb save per --flash-every s (default 30). VIA's
    RGB save is SYNCHRONOUS (via.c -> eeconfig_force_flush_rgb_matrix), a
    flash write inside the raw-HID handler, racing the blits -- not the
    deferred, settle-gated flush soak.py's docstring describes. The
    wear-levelled EEPROM erases both of its sectors every 127 log entries;
    this cadence costs ~23 erases a night against 20k rated.
  - liveness ping every 0.1 s

Measurement never goes through Python: every --health-every s (default 30)
the handle is closed and `ak820 health --rows --isr --crash --json` runs, so
there is one decoder (the Rust one) and the retained record, uptime and ISR
stats are all in the CSV. Replies collide on a shared interface, so the
agent must not be running: pass --pause-agent to boot it out for the run and
restore it afterwards (the clock is unsynced meanwhile, and re-converges).

Settings are protected twice. A FULL backup (ak820keymap.py and
ak820lighting.py dumps: every layer, the encoders, the lighting) is taken
before any stress and never overwritten. After every recovery the record is
captured FIRST, the stress state is put back, and the whole board state is
compared with that backup: a reset during a wear-levelling consolidation can
clear the logical EEPROM. A mismatch restores the backup, verifies it, and
ends the hunt -- a human should look. The kb datablock (BT slot, LCD
brightness, clock format, RTC period) has no backup tool: its loss is not
detected here.

Output: ~/Library/Logs/ak820pro/crash-hunt/<stamp>/ -- hunt.csv, events.log,
run.json, keymap-backup.json, lighting-backup.json, captures/*.json.

Usage: crash_hunt.py [--hours 8] [--pause-agent] [--no-flash]
"""
import argparse, csv, json, os, random, string, subprocess, sys, time

sys.path.insert(0, os.path.dirname(__file__))
from soak import (Soak, report, SET_VALUE, TEXT_CHANNEL,  # noqa: E402
                  RGB_BRIGHTNESS, RGB_EFFECT, KC_NO, KC_TRNS)

TEXT_PLAYBACK = 0x04
AGENT_LABEL = "com.jdlien.ak820pro.agent"
REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
KEYMAP_TOOL = os.path.join(REPO, "hostagent", "ak820keymap.py")
LIGHTING_TOOL = os.path.join(REPO, "hostagent", "ak820lighting.py")
CLI_CANDIDATES = [
    os.path.join(REPO, "ak820-agent/target/release/ak820"),
    os.path.expanduser("~/Library/Application Support/ak820pro/bin/ak820"),
]
# A recovery the watchdog cannot explain within this long means the board hung
# without the watchdog (degraded mode, or a failure it does not cover): stop
# and say so -- the fix is a cold power-off, not more stress.
RETURN_TIMEOUT_S = 120
# Two consecutive watchdog resets and the hunt stops: a third would put the
# firmware in degraded mode (watchdog left off). The count is only cleared by
# a boot that was not a watchdog reset, so it accumulates across nights.
MAX_CONSECUTIVE = 2
# How many leading bytes of each VIA request its reply must echo. A reply
# matching only the command byte could be anybody's (codex finding 13).
# GET_PROTOCOL echoes just the command; the others echo their selectors.
ECHO = {0x01: 1, 0x04: 4, 0x05: 6, 0x07: 3, 0x08: 3, 0x09: 2}
COLUMNS = [
    "at", "elapsed_s", "event", "version", "uptime_ms", "blit_timeouts",
    "tx_sent", "tx_timeouts", "tx_drops", "rx_malformed", "loop_gap_max_ms",
    "loop_gap_max_mark", "scan_rate", "count_ge_10ms", "count_ge_25ms",
    "count_ge_25ms_nonflash", "passes", "flash_writes", "flash_gap_max_ms",
    "blit_gap_max_ms", "i2c_gap_max_ms", "key_presses", "row_gap_max_ms",
    "isr_per_s", "isr_cpu_pct", "isr_max_us", "wdt_consecutive_resets",
    "wdt_fired_last_boot", "wr_valid", "wr_site", "wr_parent",
    "wr_last_pass_uptime_ms", "wr_boot_rstst", "wr_pc", "wr_context",
    # health page 6 (v7 firmware): the `vitals` object
    "v_uptime_ms", "v_build_token", "v_msp_free", "v_psp_free", "v_blits_issued",
    "v_blit_never_started", "v_blit_stalled", "v_blit_irq_lost", "v_blit_unknown",
    "v_blit_busy_waits", "v_blit_retry_successes",
]


class HuntSoak(Soak):
    def xfer(self, payload, expect0, tries=3, timeout_ms=1000):
        """soak.py's transaction, but the reply must echo the request's
        selectors, not merely its command byte."""
        k = min(len(payload), ECHO.get(payload[0], 1))
        for _ in range(tries):
            self.h.write(report(payload))
            rep = self.h.read(32, timeout_ms)
            if rep and len(rep) >= 32 and bytes(rep[:k]) == bytes(payload[:k]):
                return bytes(rep)
            self.misses += 1
        return None


def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def find_cli():
    for p in CLI_CANDIDATES:
        if os.access(p, os.X_OK):
            return p
    sys.exit("no ak820 CLI found; build it: (cd ak820-agent && cargo build --release)")


def tool(script, action, path):
    """Run a backup tool with the handle closed. (ok, output)."""
    try:
        r = subprocess.run([sys.executable, script, action, path],
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def agent_loaded():
    return subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{AGENT_LABEL}"],
                          capture_output=True).returncode == 0


def agent_plist():
    return os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")


def pause_agent():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{AGENT_LABEL}"],
                   capture_output=True)
    for _ in range(20):
        if not agent_loaded():
            return
        time.sleep(0.25)
    sys.exit("could not boot the agent out; not starting")


def resume_agent():
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", agent_plist()],
                       capture_output=True, text=True)
    return r.returncode == 0 or agent_loaded()


class Hunt:
    def __init__(self, out, no_flash=False):
        self.out = out
        self.no_flash = no_flash
        self.cli = find_cli()
        self.s = None
        self.t0 = time.time()
        self.events = open(os.path.join(out, "events.log"), "a", buffering=1)
        self.csvf = open(os.path.join(out, "hunt.csv"), "a", newline="", buffering=1)
        self.csv = csv.writer(self.csvf)
        self.csv.writerow(COLUMNS)
        self.recoveries = 0
        self.first = None
        self.last = None
        self.last_at = None
        self.km_backup = os.path.join(out, "keymap-backup.json")
        self.lt_backup = os.path.join(out, "lighting-backup.json")
        # Stimulus actually delivered, for the exposure the summary reports.
        self.sent = dict(text=0, playback=0, fx=0, keymap=0, rgb_save=0)

    def log(self, msg):
        line = f"{stamp()} {msg}"
        print(line, flush=True)
        self.events.write(line + "\n")

    # -- the handle ---------------------------------------------------------
    def open(self):
        self.s = HuntSoak()

    def close(self):
        if self.s is not None:
            try:
                self.s.close()
            except Exception:
                pass
            self.s = None

    # -- measurement, all through the Rust CLI --------------------------------
    def health(self):
        """Close our handle and read everything. None if the board did not
        answer."""
        self.close()
        try:
            r = subprocess.run([self.cli, "health", "--rows", "--isr", "--crash", "--json"],
                               capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return None

    def rebooted(self, h):
        """Did the board reboot since the last sample? Uptime must keep pace
        with wall time: anything more than 5 s short of the last sample's
        uptime plus the time since is a reboot. A plain "went backwards" test
        misses a reboot when the last sample itself came just after one
        (implementation review, second pass, finding 4)."""
        up = h.get("uptime_ms")
        if up is None or self.last is None or self.last.get("uptime_ms") is None:
            return up is not None and up < 120_000
        expected = self.last["uptime_ms"] + (time.time() - self.last_at) * 1000
        return up < expected - 5000

    def record(self, h, event=""):
        wr = h.get("watchdog_record") or {}
        vitals = h.get("vitals") or {}
        row = {k: h.get(k, "") for k in COLUMNS}
        row.update(at=stamp(), elapsed_s=int(time.time() - self.t0), event=event,
                   wr_valid=wr.get("valid", ""), wr_site=wr.get("site", ""),
                   wr_parent=wr.get("parent", ""),
                   wr_last_pass_uptime_ms=wr.get("last_pass_uptime_ms", ""),
                   wr_boot_rstst=wr.get("boot_rstst", ""),
                   wr_pc=wr.get("pc", ""), wr_context=wr.get("context", ""))
        row.update({f"v_{k}": v for k, v in vitals.items() if f"v_{k}" in row})
        self.csv.writerow([row[k] for k in COLUMNS])
        if self.first is None:
            self.first = h
        self.last = h
        self.last_at = time.time()

    def capture(self, h, why):
        self.recoveries += 1
        path = os.path.join(self.out, "captures", f"{self.recoveries:02d}-{time.strftime('%H%M%S')}.json")
        with open(path, "w") as f:
            json.dump({"at": stamp(), "why": why, "health": h}, f, indent=1)
        return path

    # -- settings -------------------------------------------------------------
    def backup(self):
        self.close()
        for script, path in ((KEYMAP_TOOL, self.km_backup), (LIGHTING_TOOL, self.lt_backup)):
            ok, msg = tool(script, "dump", path)
            if not ok:
                sys.exit(f"backup failed, not starting ({os.path.basename(script)}): {msg}")

    def state_differs(self):
        """The whole keymap, encoders and lighting against the backup. A list
        of what differs; empty when it all matches."""
        self.close()
        km_now = os.path.join(self.out, "keymap-now.json")
        lt_now = os.path.join(self.out, "lighting-now.json")
        diffs = []
        ok, msg = tool(KEYMAP_TOOL, "dump", km_now)
        if not ok:
            return [f"keymap unreadable: {msg}"]
        ok, msg = tool(LIGHTING_TOOL, "dump", lt_now)
        if not ok:
            return [f"lighting unreadable: {msg}"]
        with open(self.km_backup) as f:
            want_km = json.load(f)
        with open(km_now) as f:
            got_km = json.load(f)
        for k in ("layers", "keymap", "encoders"):
            if got_km.get(k) != want_km.get(k):
                diffs.append(f"keymap.{k}")
        with open(self.lt_backup) as f:
            want_lt = json.load(f)
        with open(lt_now) as f:
            got_lt = json.load(f)
        diffs += [f"lighting.{k}" for k in sorted(set(want_lt) | set(got_lt))
                  if want_lt.get(k) != got_lt.get(k)]
        return diffs

    def restore_backup(self):
        """Put the whole backup back and verify it. True when it matches."""
        self.close()
        for script, path in ((KEYMAP_TOOL, self.km_backup), (LIGHTING_TOOL, self.lt_backup)):
            ok, msg = tool(script, "restore", path)
            if not ok:
                self.log(f"restore via {os.path.basename(script)} failed: {msg}")
        diffs = self.state_differs()
        if diffs:
            self.log(f"RESTORE DID NOT VERIFY: {', '.join(diffs)} -- backups in {self.out}")
            return False
        self.log("backup restored and verified")
        return True

    def undo_stress(self, orig):
        """The three values the stress moves, back to their originals, with
        acknowledgments checked. A list of failures. With --no-flash nothing
        was persisted, so nothing is written back to flash either: the effect
        is restored in RAM and the keymap is left alone (second pass,
        finding 6)."""
        fails = []
        try:
            if self.s is None:
                self.open()
            s = self.s
            if not self.no_flash:
                if not s.set_keycode(orig["keycode"]) or s.get_keycode() != orig["keycode"]:
                    fails.append("keycode")
            ok = (s.rgb_set(RGB_EFFECT, orig["effect"])
                  and s.rgb_set(RGB_BRIGHTNESS, orig["brightness"])
                  and (self.no_flash or s.rgb_save()))
            if (not ok or s.rgb_get(RGB_EFFECT) != orig["effect"]
                    or s.rgb_get(RGB_BRIGHTNESS) != orig["brightness"]):
                fails.append("rgb")
        except (Exception, SystemExit) as e:
            fails.append(f"board unreachable ({e})")
        return fails

    def verify_settings(self, orig, when):
        """After a recovery or at the end: stress undone, then the whole state
        against the backup. False means stop -- a human should look."""
        fails = self.undo_stress(orig)
        if fails:
            self.log(f"{when}: could not undo the stress ({', '.join(fails)})")
        diffs = self.state_differs()
        if not diffs and not fails:
            self.log(f"{when}: keymap, encoders and lighting match the backup")
            return True
        self.log(f"{when}: SETTINGS DIFFER from the backup ({', '.join(diffs) or 'see above'}) "
                 "-- restoring it; the hunt stops")
        self.restore_backup()
        return False

    # -- the event --------------------------------------------------------------
    def recover(self, why):
        """The board stopped answering. Wait for it, capture, decide."""
        lost = time.time()
        prev_up = (self.last or {}).get("uptime_ms")   # the last sample BEFORE the loss
        self.log(f"LOST: {why} -- waiting up to {RETURN_TIMEOUT_S} s for the board")
        self.close()
        h = None
        while time.time() - lost < RETURN_TIMEOUT_S:
            time.sleep(2)
            h = self.health()
            if h is not None:
                break
        if h is None:
            self.log("board did NOT come back: hung without the watchdog, or the "
                     "watchdog is degraded. Leave it connected, read `ak820 health "
                     "--crash` once it answers; if it never does, cold power-off "
                     "(cable + unplug ~10 s) loses the record.")
            return False
        gone = time.time() - lost
        wr = h.get("watchdog_record") or {}
        # Did it REBOOT? Only uptime says so: wdt_fired_last_boot stays set for
        # the whole boot after one watchdog reset, so a later transport hiccup
        # would otherwise be reported -- and captured -- as a fresh reset of
        # the same frozen record (implementation review, finding 6).
        up = h.get("uptime_ms")
        if not self.rebooted(h):
            self.log(f"back after {gone:.0f} s WITHOUT rebooting (uptime {up} ms, was {prev_up}): "
                     "a transport hiccup, not a crash")
            self.record(h, event="lost and back, no reboot")
            return self.within_limits(h)
        path = self.capture(h, why)   # evidence first, before anything else
        if h.get("wdt_fired_last_boot"):
            if not wr.get("valid"):
                what = "record unavailable"
            elif "pc" in wr:   # a terminal record: fault, unhandled vector, halt
                token = (h.get("vitals") or {}).get("build_token", "?")
                what = (f"{wr.get('site')} at pc {wr.get('pc')} in {wr.get('context')} within "
                        f"{wr.get('parent')} -- scripts/symbolize.sh {wr.get('pc')} {token}")
            else:
                what = (f"{wr.get('site')} within {wr.get('parent')}, last pass uptime "
                        f"{wr.get('last_pass_uptime_ms')} ms")
            self.log(f"WATCHDOG RESET after {gone:.0f} s: {what}; consecutive "
                     f"{h.get('wdt_consecutive_resets')}; saved {path}")
            self.record(h, event=f"watchdog: {wr.get('site')} within {wr.get('parent')}")
        else:
            # Rebooted, but not by the watchdog: a brownout, a power blip, a
            # software reset. Still evidence; still captured.
            self.log(f"REBOOTED after {gone:.0f} s, not by the watchdog "
                     f"(reset flags {wr.get('boot_rstst')}, uptime {up} ms); saved {path}")
            self.record(h, event="rebooted, not by the watchdog")
        return self.within_limits(h)

    def within_limits(self, h):
        """Checked on EVERY recovered sample, rebooted or not."""
        if h.get("wdt_degraded"):
            self.log("the watchdog is DEGRADED (off): stopping")
            return False
        if (h.get("wdt_consecutive_resets") or 0) >= MAX_CONSECUTIVE:
            self.log(f"{h.get('wdt_consecutive_resets')} consecutive watchdog resets: "
                     "stopping before a third puts the firmware in degraded mode")
            return False
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--text-every", type=float, default=0.2)
    ap.add_argument("--playback-every", type=float, default=2.0)
    ap.add_argument("--flash-every", type=float, default=30.0)
    ap.add_argument("--health-every", type=float, default=30.0)
    ap.add_argument("--no-flash", action="store_true",
                    help="no keymap writes or rgb saves at all (zero wear)")
    ap.add_argument("--pause-agent", action="store_true",
                    help=f"boot {AGENT_LABEL} out for the run and restore it after")
    ap.add_argument("--out", default=os.path.expanduser("~/Library/Logs/ak820pro/crash-hunt"))
    a = ap.parse_args()

    if sys.platform != "darwin":
        # Opening the board enumerates HID, which is harmless on macOS and
        # wedged a UPS on Windows (CLAUDE.md). Refuse rather than port blind.
        sys.exit("macOS only")

    # Everything from the bootout to the agent's return is inside this try,
    # and responsibility for restoring it is taken BEFORE the bootout: an
    # interrupt after a successful bootout, or a failure making the output
    # directory, finding the CLI or restoring settings, must not leave the
    # agent paused (implementation review, finding 3 and second pass).
    paused = False
    rc = 1
    try:
        if agent_loaded():
            if not a.pause_agent:
                sys.exit(f"{AGENT_LABEL} is running; its replies would collide with ours. "
                         "Re-run with --pause-agent (it is restored at exit).")
            paused = True
            pause_agent()
        rc = run(a)
    finally:
        if paused:
            print(stamp(), "agent restored" if resume_agent() else
                  f"AGENT NOT RESTORED: launchctl bootstrap gui/{os.getuid()} {agent_plist()}",
                  flush=True)
    sys.exit(rc)


def run(a):
    out = os.path.join(a.out, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(out, "captures"), exist_ok=True)
    hunt = Hunt(out, no_flash=a.no_flash)
    hunt.log(f"crash hunt: {a.hours} h, output {out}")
    print("  (VIA must be closed: it would steal replies and lose its own sync)")
    rc = 1
    orig = None
    try:
        h = hunt.health()
        if h is None:
            sys.exit("board did not answer `ak820 health` -- connected, cable mode?")
        if h.get("wdt_degraded"):
            sys.exit("watchdog is DEGRADED -- power-cycle before hunting")
        if (h.get("wdt_consecutive_resets") or 0) >= MAX_CONSECUTIVE:
            sys.exit(f"{h.get('wdt_consecutive_resets')} consecutive watchdog resets already: "
                     "capture the record, then clear the count with a cold power-off")
        hunt.record(h, event="start")
        hunt.backup()
        hunt.open()
        s = hunt.s
        o = {"keycode": s.get_keycode(), "brightness": s.rgb_get(RGB_BRIGHTNESS),
             "effect": s.rgb_get(RGB_EFFECT)}
        if None in o.values():
            sys.exit("could not read the keymap/RGB state to restore later")
        if o["effect"] == 0:
            # VIA reads effect 0 when RGB is OFF, which hides the remembered
            # mode: the sweep would replace it and the restore could not bring
            # it back (implementation review, finding 4).
            sys.exit("RGB is off: turn it on (Fn+X) before hunting, so its effect can be restored")
        orig = o   # only now does the exit path have something to restore
        with open(os.path.join(out, "run.json"), "w") as f:
            json.dump({"started": stamp(), "args": vars(a), "originals": orig,
                       "cli": hunt.cli}, f, indent=1)
        hunt.log(f"backed up; originals: keycode 0x{orig['keycode']:04X}, brightness "
                 f"{orig['brightness']}, effect {orig['effect']}")
        effects = s.discover_effects()
        s.rgb_set(RGB_EFFECT, orig["effect"])
        hunt.log(f"effects: {effects}")

        end = time.time() + a.hours * 3600
        nxt = dict(ping=0.0, text=0.0, playback=0.0, fx=0.0, keymap=0.0,
                   rgb=time.time() + a.flash_every / 2, health=time.time() + a.health_every)
        kc_flip, b_dir, fx_i, playing = False, 1, 0, False
        stopped = False
        while time.time() < end:
            now = time.time()
            try:
                s = hunt.s
                if now >= nxt["ping"]:
                    nxt["ping"] = now + 0.1
                    if not s.ping():
                        raise IOError("liveness ping unanswered")
                if now >= nxt["text"]:
                    nxt["text"] = now + a.text_every
                    n = random.randint(3, 21)
                    s.text(random.randint(0, 1),
                           "".join(random.choices(string.ascii_letters + " ", k=n)))
                    hunt.sent["text"] += 1
                if now >= nxt["playback"]:
                    nxt["playback"] = now + a.playback_every
                    playing = not playing
                    pos, dur = random.randint(0, 200), random.randint(200, 400)
                    s.send([SET_VALUE, TEXT_CHANNEL, TEXT_PLAYBACK, 1 if playing else 0,
                            pos >> 8, pos & 0xFF, dur >> 8, dur & 0xFF])
                    hunt.sent["playback"] += 1
                if now >= nxt["fx"] and effects:
                    nxt["fx"] = now + 20.0
                    fx_i += 1
                    if not s.rgb_set(RGB_EFFECT, effects[fx_i % len(effects)]):  # no save
                        raise IOError("effect set unanswered")
                    hunt.sent["fx"] += 1
                if not a.no_flash and now >= nxt["keymap"]:
                    nxt["keymap"] = now + a.flash_every
                    kc_flip = not kc_flip
                    if not s.set_keycode(KC_TRNS if kc_flip else KC_NO):
                        raise IOError("keymap write unanswered")
                    hunt.sent["keymap"] += 1
                if not a.no_flash and now >= nxt["rgb"]:
                    nxt["rgb"] = now + a.flash_every
                    b_dir = -b_dir
                    if not (s.rgb_set(RGB_BRIGHTNESS, max(1, min(255, orig["brightness"] + b_dir)))
                            and s.rgb_save()):   # a synchronous flash write
                        raise IOError("rgb save unanswered")
                    hunt.sent["rgb_save"] += 1
                if now >= nxt["health"]:
                    nxt["health"] = time.time() + a.health_every
                    h = hunt.health()
                    if h is None:
                        raise IOError("health read failed")
                    # A reset between our pings, judged by uptime against wall
                    # time (Hunt.rebooted). Not "the fired flag is set and
                    # uptime is small" -- that flag stays set all boot, and the
                    # first reading after a recovery we DID catch re-captured
                    # the same frozen record (first hunt, 21:19:36). Checked
                    # before recording, so recover() compares against the
                    # pre-reboot sample.
                    if hunt.rebooted(h):
                        raise IOError("the board rebooted between readings")
                    hunt.record(h)
                    hunt.open()
            # SystemExit too: ak820health raises it for a garbled or missing
            # reply. KeyboardInterrupt is neither, so ^C still reaches the
            # restore below.
            except (Exception, SystemExit) as e:
                if (not hunt.recover(f"{type(e).__name__}: {e}")
                        or not hunt.verify_settings(orig, "after recovery")):
                    stopped = True
                    break
                hunt.open()
                nxt["health"] = time.time() + a.health_every
            time.sleep(0.01)
        rc = 1 if stopped else 0
    except KeyboardInterrupt:
        hunt.log("interrupted")
        rc = 0
    finally:
        if orig is not None:
            if not hunt.verify_settings(orig, "at exit"):
                rc = 1
            try:
                if hunt.s is None:
                    hunt.open()
                hunt.s.send([SET_VALUE, TEXT_CHANNEL, TEXT_PLAYBACK, 0, 0, 0, 0, 0])
                hunt.s.text(0, "hunt done")
            except (Exception, SystemExit):
                pass
            end_h = hunt.health()
            if end_h is not None:
                hunt.record(end_h, event="end")
        hunt.close()
        summarize(hunt)
    return rc


def summarize(hunt):
    hours = (time.time() - hunt.t0) / 3600
    hunt.log(f"ran {hours:.2f} h; {hunt.recoveries} recover{'y' if hunt.recoveries == 1 else 'ies'}; "
             "sent " + ", ".join(f"{v} {k}" for k, v in hunt.sent.items()))
    f, l = hunt.first, hunt.last
    if f and l and hunt.recoveries == 0 and l.get("uptime_ms", 0) > f.get("uptime_ms", 0):
        # One boot throughout: the deltas mean something.
        d = lambda k: (l.get(k) or 0) - (f.get(k) or 0)  # noqa: E731
        hunt.log(f"this boot: blit_timeouts +{d('blit_timeouts')} "
                 f"({d('blit_timeouts') / max(hours, 1e-9):.1f}/h), nonflash stalls >=25 ms "
                 f"+{d('count_ge_25ms_nonflash')}, flash writes +{d('flash_writes')}, "
                 f"worst loop gap {l.get('loop_gap_max_ms')} ms ({l.get('loop_gap_max_mark')})")


if __name__ == "__main__":
    main()
