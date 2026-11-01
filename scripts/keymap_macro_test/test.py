"""ak820keymap.py's restore when a backup's macros don't fit the firmware's
buffer (codex's verify of the 10-31 audit's Batch 3, P2): the keymap and the
knob are restored all the same, the macros skipped with a warning, and the
exit is 3, which flash.sh takes as a warning and goes on to the profiles. The
backup is codex's: fifteen empty macros, then "AB", its NUL and the validity
byte, 19 bytes from a firmware before the owner byte; this one's buffer is 18.
The device is faked at ak820keymap's own transfer functions."""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hostagent"))
import ak820keymap as km

fails = 0


def check(ok, what):
    global fails
    print(("ok   " if ok else "FAIL ") + what)
    fails += 0 if ok else 1


class Board:
    def __init__(self, msize):
        self.msize = msize
        self.keymap = bytes(km.ROWS * km.COLS * 2 * 4)
        self.encoders = None
        self.macros = bytes(msize)

    def close(self):
        pass


def run(backup_macros, msize):
    b = Board(msize)
    km.open_device = lambda: b
    km.xfer = lambda h, p: bytes([p[0], 4]) + bytes(30)          # GET_LAYER_COUNT: 4
    km.macro_size = lambda h: h.msize
    km.write_keymap = lambda h, data: setattr(h, "keymap", bytes(data))
    km.read_keymap = lambda h, layers: h.keymap
    km.write_encoders = lambda h, e: setattr(h, "encoders", e)
    km.read_encoders = lambda h, layers: h.encoders

    def write_macros(h, used, size):
        h.macros = bytes(used) + bytes(size - len(used))
    km.write_macros = write_macros
    km.read_macros = lambda h: h.macros
    keymap = bytes((i * 7) & 0xFF for i in range(km.ROWS * km.COLS * 2 * 4))
    doc = {"layers": 4, "rows": km.ROWS, "cols": km.COLS, "keymap": keymap.hex(),
           "encoders": [[0x00E9, 0x00EA]] * 4, "macros": backup_macros.hex()}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
    out, err, code = io.StringIO(), io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            km.cmd_restore(f.name)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        if not isinstance(e.code, int):
            err.write(str(e.code))
    os.unlink(f.name)
    return b, keymap, code, err.getvalue()


codex = bytes(15) + b"AB\x00" + b"\x01"   # 19 B: 16 macros' terminators, "AB", the flag
check(len(codex) == 19 and len(km.macros_used(codex)) == 18, "the backup: 19 B, 18 of them macros (codex's case)")

b, keymap, code, err = run(codex, 18)
check(code == 3 and getattr(km, "MACROS_SKIPPED", None) == 3, f"a buffer of 18: exit 3 (got {code})")
check(b.keymap == keymap and b.encoders == [[0x00E9, 0x00EA]] * 4, "the keymap and the knob restored all the same")
check(b.macros == bytes(18), "no macro written (the board keeps none)")
check("NOT restored" in err, "and it says so")

b, keymap, code, err = run(codex, 19)
check(code == 0 and b.macros[:18] == km.macros_used(codex), "a buffer of 19: restored whole, exit 0")

empty = bytes(16) + b"\x00" * 3            # an old 19 B buffer of empty macros
b, keymap, code, err = run(empty, 18)
check(code == 0 and b.keymap == keymap, "empty macros into 18: exit 0, nothing skipped")

print(f"RESULT: {'FAIL' if fails else 'PASS'} ({fails} failed)")
sys.exit(1 if fails else 0)
