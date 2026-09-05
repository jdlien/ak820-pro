#!/usr/bin/env python3
"""Windows now-playing producer for the AK820 Pro LCD.

The Windows counterpart of nowplaying-macos.sh, and a simpler one: Windows has
a real OS-level API for this. GlobalSystemMediaTransportControlsSessionManager
("SMTC", Win10 1809+) is public and supported, and it is what the media flyout
on the volume keys reads. Every app that registers a session -- Spotify, the
Store build of Apple Music, and crucially every BROWSER, so YouTube and web
players too -- is visible through one interface. macOS has no such thing, which
is why the mac agent carries per-app AppleScript for Spotify and Music.

    An app that does not register an SMTC session is invisible here, and no
    amount of work in THIS file can change that -- the fix is a plug-in on the
    app side. `--probe` reports what the API can actually see, per app.

    Measured 2026-09-05: foobar2000 2.24.6 DOES register a session with stock
    components (title and artist both correct), which older advice says it does
    not -- v2 gained this. What it does NOT provide is timeline properties: it
    reports 0s/0s, so the playback progress readout stays blank for foobar and
    the band shows just the icon and text. Apple Music (Store) registers too.

Display contract, matching the mac agent exactly:
    line 0  artist   (19 chars, shares the row with the transport icon)
    line 1  title    (21 chars, full width)
  The artist takes line 0 because it is the less valuable of the two and can
  afford losing ~2 characters to the icon. With no artist the title moves to
  line 0 and line 1 is cleared, so a previous artist cannot linger.

Setup: handled by setup.sh; needs the venv-win venv (winsdk has no mingw wheel).

Run:
    python hostagent/nowplaying-windows.py            # the agent
    python hostagent/nowplaying-windows.py --probe    # what does SMTC see?
    python hostagent/nowplaying-windows.py --once     # one push, then exit
"""
import argparse
import asyncio
import ctypes
import datetime
import os
import sys
import time

import venv_bootstrap
venv_bootstrap.ensure("winsdk")     # re-execs under venv-win if we are elsewhere

from winsdk.windows.media.control import (                       # noqa: E402
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

import ak820text                                                 # noqa: E402

INTERVAL = 3.0     # s between polls; 1 s is wasteful and can make Spotify sluggish
KEEPALIVE = 30.0   # s: re-push unchanged state, because the firmware expires the
                   # host text slot after ~3 min so a dead agent, a sleeping
                   # machine or an unplugged board cannot leave a stale track up


_LOG_PATH = None      # set by --log; None means stdout


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    if _LOG_PATH is None:
        print(line, flush=True)
        return
    # Run from a Scheduled Task the agent is launched with pythonw.exe, which
    # has no console at all -- a print() goes nowhere and a crash would be
    # invisible. Everything worth seeing goes to a file instead.
    try:
        directory = os.path.dirname(_LOG_PATH)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def single_instance(name="ak820pro-nowplaying"):
    """The raw-HID interface is exclusive; two agents fight over it and both
    look broken. A named mutex is the Windows way and, unlike a lock file, is
    released by the kernel if we are killed -- no stale lock to clear by hand."""
    ERROR_ALREADY_EXISTS = 183
    handle = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\" + name)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        sys.exit(f"{name} is already running (named mutex held); "
                 "not starting a second one.")
    return handle          # keep a reference for the process lifetime


def _text(value):
    return (value or "").strip()


def _session_status(session):
    try:
        return session.get_playback_info().playback_status
    except Exception:
        return None


async def read_state():
    """-> (icon, artist, title, playing, pos_s, dur_s).

    Prefers a session that is actually PLAYING over the system's "current" one:
    the current session can be a paused app while something else plays.
    """
    manager = await MediaManager.request_async()

    current = manager.get_current_session()
    try:
        current_id = current.source_app_user_model_id if current else None
    except Exception:
        current_id = None

    # Rank rather than "take the current session": the system's current session
    # is routinely a app that is merely OPEN with nothing loaded (Apple Music
    # does this at launch) while the thing actually holding a track is another
    # session. Taking `current` blindly showed an empty band with foobar2000
    # paused on a track. PLAYING beats PAUSED, and within a status the system's
    # current session wins so a deliberate foreground choice is still honoured.
    def rank(session):
        status = _session_status(session)
        if status == PlaybackStatus.PLAYING:
            base = 0
        elif status == PlaybackStatus.PAUSED:
            base = 1
        else:
            return None                    # CLOSED / OPENED / CHANGING / STOPPED
        try:
            is_current = session.source_app_user_model_id == current_id
        except Exception:
            is_current = False
        return (base, 0 if is_current else 1)

    ranked = []
    for session in list(manager.get_sessions() or []):
        key = rank(session)
        if key is not None:
            ranked.append((key, session))
    if not ranked:
        return "none", "", "", False, 0, 0
    ranked.sort(key=lambda item: item[0])
    chosen = ranked[0][1]
    status = _session_status(chosen)

    if status == PlaybackStatus.PLAYING:
        icon, playing = "play", True
    elif status == PlaybackStatus.PAUSED:
        icon, playing = "pause", False
    else:
        # CLOSED / OPENED / CHANGING / STOPPED all mean "nothing to show".
        return "none", "", "", False, 0, 0

    try:
        props = await chosen.try_get_media_properties_async()
        title, artist = _text(props.title), _text(props.artist)
    except Exception:
        title, artist = "", ""      # a session can exist before metadata arrives

    pos = dur = 0
    try:
        timeline = chosen.get_timeline_properties()
        dur = max(0, int((timeline.end_time - timeline.start_time).total_seconds()))
        pos = max(0, int((timeline.position - timeline.start_time).total_seconds()))
        # SMTC updates position on events, not continuously, so a poll can read
        # a value several seconds old. Extrapolate while playing; the firmware
        # ticks its own timer between pushes and this re-asserts the truth.
        if playing and timeline.last_updated_time:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - timeline.last_updated_time).total_seconds()
            if 0 <= age < 600:
                pos += int(age)
        if dur:
            pos = min(pos, dur)
    except Exception:
        pass

    return icon, artist, title, playing, pos, dur


def push_text(icon, artist, title):
    """One device open for both lines: two opens can straddle the firmware's
    ~10 Hz repaint tick and produce a visible double flash on a track change."""
    if not title and not artist and icon == "none":
        ak820text.push()                      # empty text + icon none = TEXT_CLEAR
    elif artist:
        ak820text.push_both(artist, title, icon)
    else:
        ak820text.push_both(title, "", icon)  # clear line 1 explicitly


async def probe():
    """Print every SMTC session. The answer to 'why doesn't <app> show up?'."""
    manager = await MediaManager.request_async()
    sessions = list(manager.get_sessions() or [])
    current = manager.get_current_session()
    current_id = current.source_app_user_model_id if current else None

    if not sessions:
        print("No SMTC sessions at all. Start playback in an app and re-run.")
        print("An app that never appears here does not register with SMTC, which")
        print("is an app-side plug-in question, not something this agent can fix.")
        return

    print(f"{len(sessions)} SMTC session(s):\n")
    for session in sessions:
        try:
            app_id = session.source_app_user_model_id
            status = session.get_playback_info().playback_status
            props = await session.try_get_media_properties_async()
            timeline = session.get_timeline_properties()
            dur = int((timeline.end_time - timeline.start_time).total_seconds())
            pos = int((timeline.position - timeline.start_time).total_seconds())
            mark = "   <- current session" if app_id == current_id else ""
            print(f"  app      : {app_id}{mark}")
            print(f"  status   : {status.name}")
            print(f"  title    : {_text(props.title)!r}")
            print(f"  artist   : {_text(props.artist)!r}")
            print(f"  album    : {_text(props.album_title)!r}")
            print(f"  timeline : {pos}s / {dur}s\n")
        except Exception as exc:
            print(f"  (session unreadable: {type(exc).__name__}: {exc})\n")


async def run(once=False, interval=INTERVAL):
    last, keepalive_at = None, 0.0
    if not once:
        log(f"polling SMTC every {interval:g}s (keepalive {KEEPALIVE:g}s)")
    while True:
        try:
            icon, artist, title, playing, pos, dur = await read_state()
        except Exception as exc:
            log(f"[warn] read_state: {type(exc).__name__}: {exc}")
            icon, artist, title, playing, pos, dur = "none", "", "", False, 0, 0

        current = (icon, artist, title)
        now = time.monotonic()
        if current != last or (now - keepalive_at) >= KEEPALIVE:
            changed = current != last
            try:
                push_text(icon, artist, title)
                last, keepalive_at = current, now
                if changed:
                    log(f"{icon:5} {artist} - {title}" if artist
                        else f"{icon:5} {title}")
            except SystemExit as exc:        # raw HID missing / VIA holding it
                log(f"[warn] push: {exc}")
            except Exception as exc:
                log(f"[warn] push: {type(exc).__name__}: {exc}")

        # Pushed every poll while playing, separately from the text: it is the
        # readout that has to stay honest, and it is cheap.
        try:
            if playing and dur:
                ak820text.push_playback(1, pos, dur)
            else:
                ak820text.push_playback(0, 0, 0)
        except SystemExit:
            pass
        except Exception as exc:
            log(f"[warn] playback: {type(exc).__name__}: {exc}")

        if once:
            return
        await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="AK820 Pro now-playing agent")
    parser.add_argument("--probe", action="store_true",
                        help="list every SMTC session and exit (no board needed)")
    parser.add_argument("--once", action="store_true",
                        help="one push, then exit")
    parser.add_argument("--interval", type=float, default=INTERVAL,
                        help=f"seconds between polls (default {INTERVAL:g})")
    parser.add_argument("--log", metavar="PATH",
                        help="append to PATH instead of stdout (the Scheduled "
                             "Task uses this; pythonw.exe has no console)")
    args = parser.parse_args()

    if args.log:
        global _LOG_PATH
        _LOG_PATH = os.path.abspath(args.log)

    if args.probe:
        asyncio.run(probe())
        return
    if not args.once:
        single_instance()
    try:
        asyncio.run(run(once=args.once, interval=args.interval))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
