#!/usr/bin/env python3
"""Windows now-playing producer for the AK820 Pro LCD.  ** UNTESTED **

Written on a Mac against the documented WinRT API; every line below is
reasoned-about but none of it has run on Windows. Treat the enum values and the
async plumbing as the two most likely places for it to be wrong.

Why Windows is the better platform for this:
  GlobalSystemMediaTransportControlsSessionManager is a PUBLIC, supported API
  (Win10 1809+), and browsers register SMTC sessions -- so Chrome/Edge/Firefox
  playing YouTube show up here, which macOS's AppleScript route cannot do.

Setup:
    pip install winsdk hid
  `hid` needs hidapi.dll findable (pip install hidapi, or drop the DLL beside
  this script). That is the most common first-run failure on Windows.

Run:
    python nowplaying-windows.py
"""
import asyncio
import sys
import time

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )
except ImportError:  # older package name
    try:
        from winrt.windows.media.control import (            # type: ignore
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
    except ImportError:
        sys.exit("need `pip install winsdk` (or winrt)")

import ak820text

INTERVAL = 3.0          # seconds; matches the macOS agent


async def read_state():
    """-> (icon_name, title). ('none', '') when nothing is playing."""
    mgr = await MediaManager.request_async()
    session = mgr.get_current_session()
    if session is None:
        return "none", ""

    status = session.get_playback_info().playback_status
    if status == PlaybackStatus.PLAYING:
        icon = "play"
    elif status == PlaybackStatus.PAUSED:
        icon = "pause"
    else:
        # CLOSED / OPENED / CHANGING / STOPPED all mean "nothing to show".
        return "none", ""

    try:
        props = await session.try_get_media_properties_async()
        title = props.title or ""
    except Exception:
        title = ""          # a session can exist before metadata arrives
    return icon, title


async def main():
    last = None
    while True:
        try:
            icon, title = await read_state()
        except Exception as e:
            # Never let a transient WinRT failure kill the agent.
            print(f"[warn] read_state: {e}", file=sys.stderr)
            icon, title = "none", ""

        cur = (icon, title)
        if cur != last:                 # push only on change: each write is a
            last = cur                  # HID round trip plus a panel redraw
            try:
                ak820text.push(icon, title)
            except SystemExit as e:     # raw HID missing (VIA holding it?)
                print(f"[warn] push: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[warn] push: {e}", file=sys.stderr)

        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
