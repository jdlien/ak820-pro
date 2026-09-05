"""Re-exec the calling script under the repo venv if its deps are missing.

The host scripts need `hid` (and `ak820ctl`'s deps), which live in the repo
venv that setup.sh builds -- not in the system python. `source env.sh` puts
that venv on PATH, but the diagnostic scripts are the ones you reach for in a
hurry, from whatever shell you happen to be in, and a ModuleNotFoundError
traceback is a bad answer to "did I just drop a keystroke".

Import this FIRST, before any third-party import:

    import venv_bootstrap  # noqa: F401  -- must precede `import hid`

Works because Python puts a script's own directory on sys.path[0], and every
caller lives in hostagent/. A caller elsewhere must insert that directory
itself first (see scripts/soak.py).

No-op when the venv already provides the module, so LaunchAgents and Scheduled
Tasks that invoke a venv python by absolute path are unaffected.

A caller needing something other than `hid` asks for it explicitly:

    venv_bootstrap.ensure("winsdk")     # nowplaying-windows.py
"""
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A venv's interpreter path varies by platform AND by which python built it,
# and on Windows there are TWO venvs because no single python can do both jobs:
#
#   macOS / Linux          venv/bin/python3
#   MSYS2 mingw64 python   venv-mingw64/bin/python3.exe  -- builds the firmware;
#                          the name is load-bearing (qmk_cli greps sys.executable
#                          for "mingw64"). No winsdk: it has no mingw wheel and
#                          building it wants MSVC.
#   native Windows python  venv-win/Scripts/python.exe   -- the host agents;
#                          winsdk ships a wheel here. No qmk.
#
# So "the venv" is whichever one actually provides what the caller asked for --
# picking the first that merely EXISTS sent nowplaying to venv-mingw64, which
# can never have winsdk.
_CANDIDATES = (
    os.path.join(_ROOT, "venv", "bin", "python3"),
    os.path.join(_ROOT, "venv", "Scripts", "python.exe"),
    os.path.join(_ROOT, "venv-win", "Scripts", "python.exe"),
    os.path.join(_ROOT, "venv-mingw64", "bin", "python3.exe"),
    os.path.join(_ROOT, "venv-mingw64", "bin", "python.exe"),
)


def _same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.realpath(a).lower() == os.path.realpath(b).lower()


def _provides(py, module):
    """Does interpreter `py` have `module`? One cheap subprocess per candidate.

    CREATE_NO_WINDOW: python.exe is a console program, so probing it from an
    agent running under pythonw.exe would flash a console window and steal
    focus. 0 off Windows, where the flag does not exist.
    """
    try:
        return subprocess.run([py, "-c", f"import {module}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                              ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure(module="hid"):
    """Import-test `module`; on failure re-exec under a venv that has it."""
    try:
        __import__(module)
        return
    except ModuleNotFoundError:
        pass

    present = [p for p in _CANDIDATES if os.path.exists(p)]
    # Guard against an exec loop: never re-exec into the interpreter we already
    # are. If that one lacks the module, the venv is incomplete -- say so
    # rather than spinning.
    others = [p for p in present if not _same(p, sys.executable)]

    for py in others:
        if _provides(py, module):
            script = os.path.abspath(sys.argv[0])
            os.execv(py, [py, script] + sys.argv[1:])  # does not return

    me = os.path.basename(sys.argv[0])
    if present:
        sys.exit(
            f"{me}: no repo venv provides '{module}'.\n"
            f"  looked in: {', '.join(present)}\n"
            f"  Rebuild:   {_ROOT}/setup.sh"
        )
    sys.exit(
        f"{me}: no '{module}', and no repo venv under\n"
        f"  {_ROOT}\n"
        f"Run {_ROOT}/setup.sh to create one, or `source {_ROOT}/env.sh` if it\n"
        f"already exists elsewhere."
    )


ensure()
