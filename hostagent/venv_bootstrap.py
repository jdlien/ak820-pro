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

No-op when the venv is already active, so LaunchAgents that invoke the venv
python by absolute path are unaffected.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_PY = os.path.join(_ROOT, "venv", "bin", "python3")


def ensure(module="hid"):
    """Import-test `module`; on failure re-exec under the venv, or explain."""
    try:
        __import__(module)
        return
    except ModuleNotFoundError:
        pass

    # Guard against an exec loop: if we ARE the venv python and the module is
    # still missing, the venv is incomplete -- say so rather than spinning.
    already_venv = os.path.realpath(sys.executable) == os.path.realpath(_VENV_PY)

    if os.path.exists(_VENV_PY) and not already_venv:
        script = os.path.abspath(sys.argv[0])
        os.execv(_VENV_PY, [_VENV_PY, script] + sys.argv[1:])  # does not return

    if already_venv:
        sys.exit(
            f"{os.path.basename(sys.argv[0])}: the repo venv is missing '{module}'.\n"
            f"  Rebuild it:  rm -rf {_ROOT}/venv && {_ROOT}/setup.sh"
        )
    sys.exit(
        f"{os.path.basename(sys.argv[0])}: no '{module}', and no repo venv at\n"
        f"  {_VENV_PY}\n"
        f"Run {_ROOT}/setup.sh to create it, or `source {_ROOT}/env.sh` if it\n"
        f"already exists elsewhere."
    )


ensure()
