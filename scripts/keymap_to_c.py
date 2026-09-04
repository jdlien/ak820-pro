#!/usr/bin/env python3
"""Turn an ak820keymap.py dump into the firmware's default keymap.

    ./venv/bin/python scripts/keymap_to_c.py ~/Documents/ak820pro-keymap.json           # print the C
    ./venv/bin/python scripts/keymap_to_c.py ~/Documents/ak820pro-keymap.json --write   # rewrite keymap.c

Why this exists: VIA's stored keymap overrides the firmware default, so the map
the owner actually types on lives only in the board's EEPROM and in the dump
flash.sh takes. "Make my VIA layout the default" therefore means regenerating
keymaps[] and encoder_map[] in keymaps/via/keymap.c from that dump -- by hand it
is 360 keycodes in matrix order, and the first attempt at doing it by eye got
one modifier wrong. This script is the mechanical version.

Keycode names come from QMK's own data/constants/keycodes/*.hjson (the same
tables `qmk` uses), the board's custom keycodes from the enum in ak820pro.h
(index-matched to via.json, which is why they are read from the source rather
than guessed), and layer names from the same header. Anything it cannot name
is emitted as a hex literal and reported, so a silent mis-translation is not
possible: the C either names every key or the run says which it could not.

Two REQUIREMENTS, not implementation details:

  * The output must be SYMBOLIC (DBG_PAGE, BT1, LGUI(KC_LEFT)), never raw
    values. ak820pro_keycodes is index-matched to via.json's customKeycodes[];
    a literal 0x7E15 baked into keymap.c would silently become a different key
    the moment anyone inserted an enum entry. Symbols survive that, which is
    what makes the generated file safe to regenerate.
  * QK_BOOT must survive. A flash erases the emulated EEPROM, so this array is
    what the board boots with, and a layout that regenerated Fn+Esc away would
    leave no way into the bootloader short of shorting pads. --write refuses a
    keymap with no QK_BOOT on any layer.
"""
import argparse, glob, json, os, re, sys

try:
    import hjson
except ImportError:  # the venv has it (qmk depends on it); system python may not
    sys.exit("needs the repo venv: ./venv/bin/python scripts/keymap_to_c.py ...")

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QMK    = os.path.join(ROOT, "qmk_firmware-ak820pro")
KB     = os.path.join(QMK, "keyboards", "a_jazz", "ak820pro")
KEYMAP = os.path.join(KB, "keymaps", "via", "keymap.c")
LAYOUT = "LAYOUT_82_ansi"
COLW   = 12   # column width in the emitted C, matches the existing file


def load_keycode_names():
    """value -> preferred name, from QMK's keycode specs (later versions win)."""
    names = {}
    files = sorted(glob.glob(os.path.join(QMK, "data/constants/keycodes/keycodes_*.hjson")),
                   key=lambda p: [int(x) if x.isdigit() else x
                                  for x in re.findall(r"\d+|[a-z]+", os.path.basename(p))])
    for f in files:
        with open(f) as fh:
            spec = hjson.load(fh)
        for k, v in spec.get("keycodes", {}).items():
            if not isinstance(v, dict) or "key" not in v:
                continue
            aliases = v.get("aliases") or []
            names[int(k, 16)] = aliases[0] if aliases else v["key"]
    return names


def load_board_enums():
    """Custom keycodes (QK_KB_0 + i) and layer names from ak820pro.h."""
    src = open(os.path.join(KB, "ak820pro.h")).read()
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    m = re.search(r"enum ak820pro_keycodes\s*\{(.*?)\}", src, re.S)
    customs = []
    for ent in m.group(1).split(","):
        ent = ent.strip()
        if not ent:
            continue
        name = ent.split("=")[0].strip()
        if name and name != "AK820PRO_SAFE_RANGE":
            customs.append(name)
    layers = {}
    m = re.search(r"enum\s+\w*\s*\{([^}]*WINBASE[^}]*)\}", src, re.S)
    if m:
        for i, ent in enumerate(x.strip() for x in m.group(1).split(",") if x.strip()):
            name = ent.split("=")[0].strip()
            layers[i] = name
    else:
        for name in ("WINBASE", "WINFN", "MACBASE", "MACFN"):
            d = re.search(r"#define\s+%s\s+(\d+)" % name, src)
            if d:
                layers[int(d.group(1))] = name
    return customs, layers


MODS = {0x01: "LCTL", 0x02: "LSFT", 0x04: "LALT", 0x08: "LGUI",
        0x11: "RCTL", 0x12: "RSFT", 0x14: "RALT", 0x18: "RGUI"}
MOD_COMBOS = {0x06: "LSA", 0x0A: "SGUI", 0x05: "LCA", 0x0C: "LAG", 0x0D: "LCAG",
              0x0E: "HYPR", 0x07: "MEH", 0x16: "RSA", 0x13: "RCS", 0x1C: "RAG"}


class Namer:
    def __init__(self):
        self.names = load_keycode_names()
        self.customs, self.layers = load_board_enums()
        self.unknown = []

    def layer(self, n):
        return self.layers.get(n, str(n))

    def name(self, v):
        if v == 0x0000: return "XXXXXXX"
        if v == 0x0001: return "_______"
        if 0x7E00 <= v < 0x7E00 + len(self.customs):
            return self.customs[v - 0x7E00]
        if 0x0100 <= v <= 0x1FFF:                      # modified basic keycode
            mods, kc = (v >> 8) & 0x1F, v & 0xFF
            inner = self.name(kc)
            if mods in MOD_COMBOS: return f"{MOD_COMBOS[mods]}({inner})"
            if mods in MODS:       return f"{MODS[mods]}({inner})"
            right = mods & 0x10
            out = inner
            for bit, nm in ((0x01, "CTL"), (0x02, "SFT"), (0x04, "ALT"), (0x08, "GUI")):
                if mods & bit:
                    out = f"{'R' if right else 'L'}{nm}({out})"
            return out
        ranges = ((0x5200, 0x5220, "TO"), (0x5220, 0x5240, "MO"), (0x5240, 0x5260, "DF"),
                  (0x5260, 0x5280, "TG"), (0x5280, 0x52A0, "OSL"), (0x52C0, 0x52E0, "TT"))
        for lo, hi, macro in ranges:
            if lo <= v < hi:
                return f"{macro}({self.layer(v - lo)})"
        if v in self.names:
            return self.names[v]
        self.unknown.append(v)
        return f"0x{v:04X}"


def decode(dump):
    L, R, C = dump["layers"], dump["rows"], dump["cols"]
    raw = bytes.fromhex(dump["keymap"])
    return L, R, C, [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw), 2)]


def boot_reachable(dump, namer):
    """QK_BOOT exists AND sits on a layer some base-layer key can reach.

    Existing is not enough: rebind the Fn key itself in VIA, dump, regenerate,
    and QK_BOOT would still be on WINFN with nothing selecting WINFN. Base layers
    are the ones the mode switch installs as default (named *BASE in ak820pro.h,
    else layer 0); from those, follow MO/TG/TT/TO/DF/OSL/LT keys."""
    L, R, C, kc = decode(dump)
    per = [kc[l * R * C:(l + 1) * R * C] for l in range(L)]
    def targets(v):
        for lo, hi in ((0x5200, 0x5220), (0x5220, 0x5240), (0x5240, 0x5260),
                       (0x5260, 0x5280), (0x5280, 0x52A0), (0x52C0, 0x52E0)):
            if lo <= v < hi:
                return [v - lo]
        if 0x4000 <= v <= 0x4FFF:                      # LT(layer, kc)
            return [(v >> 8) & 0x0F]
        return []
    bases = [l for l, nm in namer.layers.items() if nm.endswith("BASE") and l < L] or [0]
    seen, todo = set(bases), list(bases)
    while todo:
        l = todo.pop()
        for v in per[l]:
            for n in targets(v):
                if n < L and n not in seen:
                    seen.add(n); todo.append(n)
    return any(0x7C00 in per[l] for l in seen)          # QK_BOOT = 0x7C00


def render(dump, namer):
    kb = json.load(open(os.path.join(KB, "keyboard.json")))
    order = [tuple(e["matrix"]) for e in kb["layouts"][LAYOUT]["layout"]]
    L, R, C = dump["layers"], dump["rows"], dump["cols"]
    raw = bytes.fromhex(dump["keymap"])
    kc = [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw), 2)]
    assert len(kc) == L * R * C, "dump size does not match layers*rows*cols"
    in_layout = set(order)
    stray = [(l, r, c) for l in range(L) for r in range(R) for c in range(C)
             if (r, c) not in in_layout and kc[(l * R + r) * C + c] != 0]
    if stray:
        print("WARNING: non-zero keycodes at matrix positions outside the layout:", stray, file=sys.stderr)

    out = []
    out.append("const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {")
    for l in range(L):
        out.append(f"    [{namer.layer(l)}] = {LAYOUT}(")
        rows = {}
        for (r, c) in order:
            rows.setdefault(r, []).append(namer.name(kc[(l * R + r) * C + c]))
        row_lines = []
        for r in sorted(rows):
            cells = [f"{n + ',':<{COLW}}" for n in rows[r]]
            row_lines.append("        " + "".join(cells).rstrip())
        # the last key of the layer has no trailing comma
        row_lines[-1] = row_lines[-1].rstrip(",")
        out.extend(row_lines)
        out.append("    )" + ("," if l < L - 1 else ""))
    out.append("};")
    keymaps_c = "\n".join(out)

    enc = dump.get("encoders") or []
    eout = ["const uint16_t PROGMEM encoder_map[][NUM_ENCODERS][NUM_DIRECTIONS] = {"]
    for l, per_layer in enumerate(enc):
        cells = ", ".join(f"ENCODER_CCW_CW({namer.name(ccw)}, {namer.name(cw)})" for ccw, cw in per_layer)
        eout.append(f"    [{namer.layer(l)}]{' ' * (8 - len(namer.layer(l)))}= {{{cells} }}" + ("," if l < len(enc) - 1 else ""))
    eout.append("};")
    return keymaps_c, "\n".join(eout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", help="JSON from `ak820keymap.py dump`")
    ap.add_argument("--write", action="store_true", help="rewrite keymaps[] and encoder_map[] in keymap.c")
    a = ap.parse_args()
    dump = json.load(open(a.dump))
    namer = Namer()
    keymaps_c, enc_c = render(dump, namer)
    if namer.unknown:
        print("WARNING: could not name:", ", ".join(f"0x{v:04X}" for v in sorted(set(namer.unknown))), file=sys.stderr)
    if not boot_reachable(dump, namer):
        print("ERROR: QK_BOOT is missing or unreachable -- a flash erases EEPROM and this array "
              "is the fallback, so the generated default would have no usable way into the "
              "bootloader (recoverable via usevia.app, but confusing right after a flash). Bind "
              "QK_BOOT on a layer a base-layer key can reach, dump again.", file=sys.stderr)
        if a.write:
            sys.exit(2)

    if not a.write:
        print(keymaps_c); print(); print(enc_c)
        return

    src = open(KEYMAP).read()
    k0 = src.index("const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {")
    k1 = src.index("\n};", k0) + len("\n};")
    src = src[:k0] + keymaps_c + src[k1:]
    e0 = src.index("const uint16_t PROGMEM encoder_map[][NUM_ENCODERS][NUM_DIRECTIONS] = {")
    e1 = src.index("\n};", e0) + len("\n};")
    src = src[:e0] + enc_c + src[e1:]
    open(KEYMAP, "w").write(src)
    print(f"rewrote {os.path.relpath(KEYMAP, ROOT)} from {a.dump} (saved {dump.get('saved')})")


if __name__ == "__main__":
    main()
