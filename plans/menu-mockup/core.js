/* The configuration menu as built (firmware menu/menu.c, 10-27), drawn into a
   128 x 128 RGB565 frame. A port of the firmware's rows, titles, pages and
   navigation, checked against frames the firmware's own code draws on the host
   test's fake panel. Pure: no DOM, so Node runs it too.
   The 6 x 14 face is the board's. An 8 x 16 face is a proposal: its own geometry
   (15 columns, 7 rows) and a text pass for the narrower rows, marked "wide" below. */
(function (root) {
"use strict";
const W = 128, H = 128;

/* The palette (menu.h) and the bulbs' (graphics/power_bulb.c), RGB565. */
const C = { LIT: 0xFF94, DIM: 0xCE59, LEAVE: 0xFCD3, WHITE: 0xFFFF, GREY: 0x632C, TRACK: 0x4228, CURSOR: 0xA514,
            SAVED: 0x468C, ICON_LIT: 0xFFB8 };
const LINK_COLOUR = [C.SAVED, 0x9492, 0x3CFF, C.SAVED, 0xFACB];
const BIG_CELL = 0x10000;   /* a big-face cell in a frame with no big face loaded (the host test's grey) */

/* The face's extras (menu_text.h's MT_*): a two-cell icon is two codes. */
const X = { TRI_L: "\x85", TRI_R: "\x86", CURSOR: "\x87", WRENCH: "\x88\x89", CHECK_BOX: "\x8a\x8b",
  I_POWER: "\x8c", I_CLOCK: "\x8d\x8e", I_DIAG: "\x8f", I_HELP: "\x90\x91", I_ABOUT: "\x92\x93", I_EXIT: "\x94",
  I_LIGHT: "\x95", I_SCREEN: "\x96\x97", I_BOOT: "\x98\x99", I_IND: "\x9a\x9b", I_CONN: "\x9c\x9d",
  I_WAIT: "\x9e\x9f", I_FAIL: "\xa0\xa1", I_BATT: "\xa2", I_PROF: "\xa3", I_LOAD: "\xa4\xa5", I_SAVE: "\xa6\xa7",
  I_RENAME: "\xa8", I_DELETE: "\xa9\xaa", I_RESET: "\xab", I_FONT: "\xac\xad" };

/* A 1-bit face: a byte a pixel row (column 0 in bit 7) for faces up to 8 wide,
   glyphs 0x20-0x7E then the extras from 0x80, as font_small_mono.h. */
function makeFace(hex, cw, ch) {
  const n = hex.length / 2 / ch, glyphs = [];
  for (let g = 0; g < n; g++) {
    const a = new Uint8Array(ch);
    for (let r = 0; r < ch; r++) a[r] = parseInt(hex.substr((g * ch + r) * 2, 2), 16);
    glyphs.push(a);
  }
  return { cw, ch, glyphs, mask: (0xFF << (8 - cw)) & 0xFF,
    glyph(code) {
      if (code >= 0x20 && code < 0x7F) return glyphs[code - 0x20];
      if (code >= 0x80 && code - 0x80 + 95 < glyphs.length) return glyphs[95 + code - 0x80];
      return glyphs[0x3F - 0x20];
    } };
}

/* The bulbs (power_bulb.c), 13 x 14. */
const BULB_ART = [
  ["......#......", ".#.........#.", "..#.......#..", ".....###.....", "...#######...", "##.#######.##", "..#########..",
   "..#########..", "..#########..", "...#######...", "....#####....", "....=====....", "....+++++....", ".....+++....."],
  [".............", ".............", ".............", ".....###.....", "...#######...", "...#######...", "..#########..",
   "..#########..", "..#########..", "...#######...", "....#####....", "....=====....", "....+++++....", ".....+++....."],
  [".............", ".............", ".............", ".....###.....", "...##***##...", "...#*****#...", "..#*******#..",
   "..#*******#..", "..#*******#..", "...#*****#...", "....#***#....", "....=====....", "....+++++....", ".....+++....."],
  [".............", ".............", ".//..........", "..//..##.....", "...//...##...", "....//...#...", "..#..//...#..",
   "..#...//..#..", "..#....//....", "...#....//...", "....#....//..", "....====..//.", "....+++++....", ".....+++....."],
];
const BULB_COLS = [[0xFFFF, 0, 0xB5B6, 0x632C, 0], [0xFFFF, 0, 0xB5B6, 0x632C, 0], [0xFFFF, 0x8410, 0xB5B6, 0x632C, 0],
                   [0x8D18, 0, 0x6BD2, 0x4AAD, 0xDEFB]];
function bulbPx(mode, x, y) {
  const c = BULB_ART[mode][y][x];
  return c === "." ? 0 : BULB_COLS[mode]["#*+=/".indexOf(c)];
}

/* The tables (menu.c, rgb_effects.c). */
const EFFECTS = ["Solid", "Alphas/Mods", "Cycle All", "Cycle L-R", "Cycle U-D", "Jellybean", "Heatmap", "Rainfall", "Drift"];
const TWO_TONE = 1;   /* Alphas/Mods: its speed is the second colour */
const POWER_FULL = ["Always on", "Balanced", "Power saver", "Lights out"];
const POWER_SHORT = ["Always on", "Balanced", "Saver", "Lights out"];
const CLOCK_FULL = ["24h:ss", "24h", "12h:ss", "12h", "Date", "Off"];
const CLOCK_ENUM = [0, 4, 1, 5, 3, 2];
const CLOCK_SHORT_BY_ENUM = ["24h:ss", "12h:ss", "Off", "Date", "24h", "12h"];
const BATT_FULL = ["Percent", "Hours of use", "Both"], BATT_SHORT = ["Percent", "Hours", "Both"];
const LINK_NAMES = ["USB", "2.4G", "BT 1", "BT 2", "BT 3"];
const LINK_WORDS = ["", "Trying", "Pair", "Linked", "Failed"];
const LINK_ICONS = [X.CHECK_BOX, X.I_WAIT, X.I_CONN, X.CHECK_BOX, X.I_FAIL];
const HELP_TITLES = ["Using the menu", "Customizing", "Shortcuts", "Pro tips"];
const HELP_LINES = [
  ["Turn: move", "Click: choose, save", "Hold: back, cancel", "Fn+click: close", "", "Auto-closes after", "60 seconds idle."],
  ["Remap keys & knob at", "usevia.app over USB", "", "Load via.json from", "the repo: Settings,", "Show Design tab,", "Load Draft", "Definition."],
  ["Fn+Q/W/E  BT slot", "  hold 2 s: pair", "Slider: BT 2.4G USB", "Fn+Lt/Rt  hue", "Fn+Up/Dn  brightness", "Fn+6/7    saturation",
   "Fn+X      lights", "Fn+\\      effect", "Fn+B      power mode", "Fn+C      clock", "Fn+PgUp/Dn screen", "Fn+Esc    bootloader"],
  ["Balanced sleeps", "after 20 min idle.", "A key wakes it, and", "the key still types.", "", "The lights are the",
   "battery's big cost.", "Asleep, a night is", "about 1%.", "", "2.4G answers faster;", "Bluetooth has three", "slots."],
];
/* wide: Help for 15 columns. */
const HELP_TITLES_W = ["Menu basics", "Customizing", "Shortcuts", "Pro tips"];
const HELP_LINES_W = [
  ["Turn: move", "Click: choose", "Hold: back", "Fn+click: close", "", "Closes after 60", "seconds idle."],
  ["Remap keys and", "the knob at", "usevia.app over", "USB.", "", "Load via.json", "from the repo:", "Settings, Show", "Design tab,", "Load Draft", "Definition."],
  ["Fn+QWE  BT 1-3", " hold 2 s: pair", "Slider  BT 2.4G", "        or USB", "Fn+Lt/Rt  hue", "Fn+Up/Dn bright", "Fn+6/7 saturate",
   "Fn+X    lights", "Fn+\\    effect", "Fn+B    power", "Fn+C    clock", "Fn+PgUp/Dn", "        screen", "Fn+Esc", "    bootloader"],
  ["Balanced sleeps", "after 20 min", "idle. A key", "wakes it and", "still types.", "", "The lights are", "the battery's", "big cost.",
   "Asleep, a night", "is about 1%.", "", "2.4G answers", "faster; BT has", "three slots."],
];
/* wide: the words that change for 15 columns, always (labels; titles), or only when a row won't fit. */
const W_LABEL = { "Reset settings": "Defaults", "Reset counters": "Reset counts", "Lock lights": "Lock LEDs", "Second color": "2nd color",
  "Percent": "%",   /* the Battery choice's: "Percent" and "18% <1h" don't fit (codex, the build's review) */
  "Effect": "FX", "Save current here": "Save here", "Using the menu": "Menu basics", "Hours of use": "Hours",
  "Bluetooth 1": "BT 1", "Bluetooth 2": "BT 2", "Bluetooth 3": "BT 3",
  "Pair device to BT 1": "Pair to BT 1", "Pair device to BT 2": "Pair to BT 2", "Pair device to BT 3": "Pair to BT 3" };
const W_TITLE = { "Charging light": "Charging", "Rename profile": "Rename", "Delete profile": "Delete", "Reset settings": "Defaults",
  "Reset counters": "Reset counts", "Using the menu": "Menu basics", "Turn + Click Knob": "Turn + Click",
  "Loaded w/o effect": "Loaded, no FX", "Full: delete one": "Full: delete 1" };
const W_NEEDED = { "Connection": "Link" };
const W_VALUE = { "Percent": "%" };
const PROF_USER = 7, PROF_NAME = 12;
const FLASH_MS = 1300, HINT_FROM = 4000, HINT_EVERY = 6000, PREVIEW_MS = 300, IDLE_MS = 60000, BACKSTOP_MS = 180000;

const ROWS = {
  top: ["light", "screen", "conn", "power", "ind", "clock", "batt", "prof", "boot", "font", "defaults", "diag", "help", "exit"],
  font: ["back", "fopt0", "fopt1", "fopt2"],   /* 10-28: 8px (c6), 10px (term), 10px bold (termb) */
  light: ["back", "effect", "bright", "hue", "sat", "speed", "lights"],
  ind: ["back", "locks", "chgl"],
  conn: ["back", "bt0", "bt1", "bt2", "pairnow"],
  diag: ["back", "about", "health", "reset"],   /* 10-28: About as System info; no Camera page. A dev build adds Write test */
  help: ["back", "topic0", "topic1", "topic2", "topic3", "more"],   /* P1d: More info last */
  power: ["back", "pow0", "pow1", "pow2", "pow3"],
  clock: ["back", "clk0", "clk1", "clk2", "clk3", "clk4", "clk5"],
  batt: ["back", "bv0", "bv1", "bv2"],
  pslot: ["back", "pload", "psave", "prename", "pdelete"],
};
const LABEL = { power: "Power", clock: "Clock", batt: "Battery", diag: "Diagnostics", help: "Help", about: "System info", exit: "Exit",
  health: "Health page", reset: "Reset counters", back: X.TRI_L + " Back", light: "Lighting",
  screen: "Screen", effect: "Effect", bright: "Brightness", hue: "Hue", sat: "Saturation", lights: "Lights", boot: "Bootloader",
  defaults: "Reset settings", ind: "Indicators", conn: "Connection", locks: "Lock lights", chgl: "Charging", prof: "Profiles",
  pload: "Load", psave: "Save current here", pdelete: "Delete", prename: "Rename", pnew: "+ Save new", font: "Font", more: "More info" };
const ICON = { power: X.I_POWER + " ", clock: X.I_CLOCK, diag: X.I_DIAG + " ", help: X.I_HELP, exit: X.I_EXIT + " ",
  light: X.I_LIGHT + " ", screen: X.I_SCREEN, boot: X.I_BOOT, defaults: X.I_RESET + " ", ind: X.I_IND, conn: X.I_CONN,
  batt: X.I_BATT + " ", prof: X.I_PROF + " ", pload: X.I_LOAD, psave: X.I_SAVE, prename: X.I_RENAME + " ", pdelete: X.I_DELETE,
  font: X.I_FONT };
const VALUE_ROWS = new Set(["effect", "bright", "hue", "sat", "speed", "lights", "screen", "locks", "chgl"]);
const OPENS = new Set(["diag", "help", "about", "health", "reset", "light", "boot", "ind", "defaults", "more"]);
const EDITORS = new Set(["screen", "bright", "hue", "sat", "speed", "locks", "chgl"]);
const CONFIRMS = new Set(["reset", "boot", "conninfo", "pairing", "psave", "pdelete", "prename", "defaults"]);
const LISTS = new Set(["top", "diag", "help", "light", "ind", "conn", "profiles", "pslot"]);
const CHOICES = new Set(["power", "clock", "batt", "effect", "lights", "font"]);
const PREVIEWS = new Set(["effect", "lights"]);
/* 10-28: the Font page's options' faces, their names, Large's top-level short, and its note (font_note[]). */
const FONT_OPT = ["c6", "term", "termb"];
const FONT_NAME = { c6: "8px", term: "10px", termb: "10px bold" }, FONT_SHORT = { c6: "8px", term: "10px", termb: "Bold" };
const FONT_NOTE = [["For the menus and", "now playing"], ["For the menus", "and now playing"]];
const isTopic = n => /^topic\d$/.test(n);
/* P1d: Help's More info, two screens (menu.c's "More info"): the credits beside the bunny, then the QR code. The
   credits by face, a line a row, the bunny's three from cell 5 (wide: 4); the link's lines in blue. */
const MORE_TEXT = [["AJAZZ", "Jackrabbit", "by JD Lien", "", "github.com/jdlien", "  /ak820-pro", "", "QMK Port by fpb"],
                   ["AJAZZ", "Jackrabbit", "by JD Lien", "github.com", "  /jdlien", "  /ak820-pro", "QMK Port by fpb"]];
const MORE_LINK = [[4, 5], [3, 4, 5]];
const BUNNY_W = 27, BUNNY_H = 42, QR_N = 29;
const isOption = n => /^(pow|clk|bv|fopt)\d$/.test(n) || /^(effopt|ltsopt)$/.test(n) || /^bt\d$/.test(n) || n === "pslotrow";

/* Geometry: the 6 x 14 face's is menu.c's constants. An 8 x 16 face's (wide): 15 columns from
   x 4, 7 rows of 16 from y 16, the title's blank top pixel row cut so the title, the rule
   and the rows fill the 128 rows exactly; the editors and pages moved to suit. */
/* 10-28: an icon's first code -> its index in the 12 px set (ICON12_* in icons12_2bpp.h); Back's and a page's triangles
   stay the face's glyphs. */
const ICON12 = { 0x95: 0, 0x96: 1, 0x9c: 2, 0x8c: 3, 0x9a: 4, 0x8d: 5, 0xa2: 6, 0xa3: 7, 0x98: 8, 0xab: 9, 0x8f: 10, 0x90: 11,
  0x92: 12, 0x94: 13, 0xa4: 14, 0xa6: 15, 0xa8: 16, 0xa9: 17, 0x8a: 18, 0x9e: 19, 0xa0: 20, 0x88: 21, 0xac: 24 };
/* Level n of an RGB565 colour: each channel at n/3, to the nearest (lv_scale()). */
function level565(c, n) {
  const k = v => Math.floor((v * n + 1) / 3);
  return (k(c >> 11) << 11) | (k((c >> 5) & 63) << 5) | k(c & 31);
}
function geometry(face) {
  if (face.cw === 6) return { wide: false, CW: 6, CH: 14, COLS: 20, ROWS: 8, TITLE_Y: 0, SEP_Y: 14, ROW0: 15, ROW_H: 14,
    TEXT_X: 4, BAR_X: 125, C_Y: [22, 36, 72, 86], INFO_Y: [22, 36, 50, 86], BAR: { X0: 13, X1: 114, YT: 51, YB: 60 },
    STRIP: { X0: 4, X1: 123, YT: 22, YB: 35 }, ENV: { Y0: 20, Y1: 40 }, VAL_X: 14, VAL_Y: [22, 44], HINT_Y0: 72, HINT_DY: 14,
    BULB_X: 111, BULB_DY: 0, PSUM_ROW0: 5, PSUM_LINES: 3, NOTE_ROW0: 5 };
  return { wide: true, CW: 8, CH: 16, COLS: 15, ROWS: 7, TITLE_Y: -1, SEP_Y: 15, ROW0: 16, ROW_H: 16,
    TEXT_X: 4, BAR_X: 125, C_Y: [24, 40, 80, 96], INFO_Y: [24, 40, 56, 96], BAR: { X0: 13, X1: 114, YT: 56, YB: 65 },
    STRIP: { X0: 4, X1: 123, YT: 24, YB: 37 }, ENV: { Y0: 22, Y1: 42 }, VAL_X: 14, VAL_Y: [24, 48], HINT_Y0: 80, HINT_DY: 16,
    BULB_X: 111, BULB_DY: 1, PSUM_ROW0: 5, PSUM_LINES: 2, NOTE_ROW0: 4 };
}

function createMenu(opts) {
  const faces = {};
  for (const [k, f] of Object.entries(opts.faces || { c6: { hex: opts.fontHex, cw: 6, ch: 14 } })) faces[k] = makeFace(f.hex, f.cw, f.ch);
  /* An 8 x 16 face's icons: its own (redrawn), or another set of the 44 extras (opts.icons16, by name). */
  const icons16 = {};
  for (const [k, h] of Object.entries(opts.icons16 || {})) icons16[k] = makeFace(h, 8, 16);
  let iconSet = null;
  /* 10-28: the 12 px set in four greys (opts.icons12: 25 icons x 64 bytes, hex, as graphics/res/icons12_2bpp.h), which
     the 8 x 16 face draws for an icon in cells 0-1 of a row with an icon colour, and of a title: the firmware's. */
  const icons12 = [];
  if (opts.icons12) for (let i = 0; i < opts.icons12.length / 128; i++)
    icons12.push(Uint8Array.from({ length: 64 }, (_, b) => parseInt(opts.icons12.substr(i * 128 + b * 2, 2), 16)));
  /* P1d: More info's art (opts.menuArt: menuart.hex, scripts/gen_menu_art.py): the bunny's 27 x 42 levels, then the
     QR's 29 rows of 4 bytes (module 0 in bit 7, 1 dark). Without it the page draws its text only. */
  const art = opts.menuArt ? Uint8Array.from({ length: opts.menuArt.length / 2 }, (_, i) => parseInt(opts.menuArt.substr(i * 2, 2), 16)) : null;
  let faceName = opts.face || Object.keys(faces)[0];
  let face = faces[faceName], G = geometry(face);
  /* The face as drawn: an 8 x 16 face's extras from the chosen icon set. */
  const drawFace = () => {
    if (face.cw !== 8 || !iconSet || !icons16[iconSet]) return face;
    const ic = icons16[iconSet];
    return { ...face, glyph: code => code >= 0x80 && code < 0xAC ? ic.glyphs[code - 0x80] : face.glyph(code) };
  };
  const big = opts.big || null;   /* { glyph(code) -> Uint8Array(230) } for the 10 x 23 face, if loaded */
  const clockNow = opts.clock || (() => { const d = new Date(); return { h: d.getHours(), m: d.getMinutes(), s: d.getSeconds(), day: d.getDate(), month: d.getMonth() + 1, year: d.getFullYear() }; });

  /* ---- The model: what the board holds ---- */
  const m = {
    rgb: { fx: 1, h: 240, s: 215, v: 86, speed: 127, on: 1 },
    lcd: 52, ind: [1, 0], power: 1, clock: 0, battView: 1, font: null,   /* font: the saved face (null: the one created with) */
    link: { tr: 1, slot: 0, st: 3 },          /* tr: 0 USB, 1 BT, 2 2.4G; st: idle, linking, pairing, connected, rejected */
    batt: { pct: 85, on: true, left: 9600, avg: 120 },
    about: { uptime: 93240, battPm: 767, packMv: 4017, left: 3840 },
    build: { hash: "36afff30", dirty: false, token: "ef38330e", flavour: "dev" },
    profiles: new Array(8).fill(null),      /* seven users' and the switch's last record */
    active: 0xFF, reserve: false,
  };
  const S = {   /* the menu's state */
    open: false, stack: [], flashText: null, flashAt: 0, lastInput: 0, confirmPage: 0, edit: null, pslot: 0,
    pv: "live", about: null, name: "", pairing: null, ftLast: -1e9, ftHave: false, mode: "menu", diagPage: 0,
    variant: "iv",   /* wide, the top level: icons + values, "nv" values without row icons, "in" icons without values */
  };
  const cur = () => S.stack[S.stack.length - 1];
  const twoTone = () => m.rgb.fx === TWO_TONE;
  const wl = s => (G.wide && W_LABEL[s]) || s;
  const helpLines = t => (G.wide ? HELP_LINES_W : HELP_LINES)[t];
  const helpTitle = t => (G.wide ? HELP_TITLES_W : HELP_TITLES)[t];
  /* wide: a label and a value into `room` cells, shortening only what doesn't fit. */
  function fitPair(room, label, value) {
    const fits = (l, v) => l.length + (v ? v.length + 1 : 0) <= room;
    if (!G.wide || fits(label, value)) return [label, value];
    const l2 = W_NEEDED[label] || label, v2 = W_VALUE[value] || value;
    for (const [l, v] of [[l2, value], [label, v2], [l2, v2]]) if (fits(l, v)) return [l, v];
    return [l2.slice(0, Math.max(0, room - (v2 ? v2.length + 1 : 0))), v2];
  }

  /* ---- Profiles ---- */
  const valid = s => !!m.profiles[s];
  const saved = () => m.profiles.slice(0, PROF_USER).filter(Boolean).length;
  const nth = k => { for (let s = 0, i = 0; s < PROF_USER; s++) if (valid(s) && i++ === k) return s; return 0xFF; };
  const rank = slot => { let i = 0; for (let s = 0; s < slot; s++) if (valid(s)) i++; return i; };
  const profName = s => (m.profiles[s] && m.profiles[s].name) || "Profile " + (s + 1);
  function snapshot(name) { return { name, rgb: { ...m.rgb }, lcd: m.lcd, ind: [...m.ind], clock: m.clock, battView: m.battView }; }
  function star() {
    const p = m.active < PROF_USER && m.profiles[m.active];
    if (!p) return false;
    const r = p.rgb, l = m.rgb;
    return r.fx !== l.fx || r.h !== l.h || r.s !== l.s || r.v !== l.v || r.speed !== l.speed || r.on !== l.on ||
           p.lcd !== m.lcd || p.ind[0] !== m.ind[0] || p.ind[1] !== m.ind[1] || p.clock !== m.clock || p.battView !== m.battView;
  }
  /* What the keys and the screen show: a profile's lighting and screen while it's previewed. */
  function shown() {
    const p = typeof S.pv === "number" && m.profiles[S.pv];
    return p ? { rgb: p.rgb, lcd: p.lcd } : { rgb: m.rgb, lcd: m.lcd };
  }

  /* ---- Formatting (fmt_value, the Fn readout's) ---- */
  const pct255 = v => Math.floor((v * 100 + 127) / 255);
  const valOfPct = p => Math.floor((p * 255 + 50) / 100);
  function fmtValue(node, v) {
    switch (node) {
      case "effect": return EFFECTS[v] || "Mode " + v;
      case "hue": return String(Math.floor(v * 360 / 256));
      case "lights": return v ? "On" : "Off";
      case "screen": return v ? Math.floor((v * 100 + 50) / 100) + "%" : "Off";
      case "locks": case "chgl": return v ? v + "%" : "Off";
      case "speed": return twoTone() ? "+" + Math.floor(v * 360 / 256) : pct255(v) + "%";
      default: return pct255(v) + "%";
    }
  }
  function liveValue(node) {
    if (node === "screen") return m.lcd;
    if (node === "locks") return m.ind[0];
    if (node === "chgl") return m.ind[1];
    const c = m.rgb;
    return { effect: c.fx, bright: c.v, hue: c.h, sat: c.s, speed: c.speed, lights: c.on }[node];
  }
  function setLive(node, v) {
    if (node === "screen") m.lcd = v;
    else if (node === "locks") m.ind[0] = v;
    else if (node === "chgl") m.ind[1] = v;
    else m.rgb[{ effect: "fx", bright: "v", hue: "h", sat: "s", speed: "speed", lights: "on" }[node]] = v;
  }
  const battReady = () => m.batt.on && m.batt.avg >= 60 && m.batt.left !== 0xFFFF;
  function battLevelText(view) {
    const b = m.batt, ready = b.on && b.avg >= 60 && b.left !== 0xFFFF;
    const hrs = b.left < 60 ? "<1h" : Math.min(999, Math.floor(b.left / 60)) + "h";
    let s;
    if (ready && view === 2) s = hrs;
    else if (ready && (view === 3 || b.left < 600)) { s = b.pct + "% " + hrs; if (s.length > 8) s = b.pct + "%"; }
    else s = b.pct + "%";
    return s.slice(0, 8);
  }
  function battPreview(view) {
    const b = m.batt;
    if (b.pct > 100) return "--";
    if (b.pct === 0 && b.on) return "Low";
    if (view === 2 && !battReady()) return "--";
    if (view === 3 && !battReady()) return b.pct + "% --";
    return battLevelText(view);
  }
  function battNote(line) {
    const b = m.batt;
    if (battReady() || line > 2) return "";
    if (b.on && (b.pct === 0 || b.pct > 100)) return "";
    if (b.avg < 60) {
      if (G.wide) return line < 2 ? ["Hours show once", "on battery 1 h:"][line] : (60 - b.avg) + " min to go.";
      return line < 2 ? ["Hours show after an", "hour on battery:"][line] : (60 - b.avg) + " min to go.";
    }
    if (!b.on && line < 2) return ["Hours show only", "on battery."][line];
    return "";
  }
  const z2 = n => String(n).padStart(2, "0");
  function clockExample(row) {
    const t = clockNow(), mode = CLOCK_ENUM[row], twelve = mode === 1 || mode === 5, secs = mode === 0 || mode === 1;
    let hh = t.h;
    if (twelve) { hh %= 12; if (!hh) hh = 12; }
    const ap = t.h >= 12 ? "PM" : "AM";
    if (row === 4) return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][t.month - 1] + " " + t.day + ", " + t.year;
    if (secs && twelve) return hh + ":" + z2(t.m) + ":" + z2(t.s) + " " + ap;
    if (secs) return z2(hh) + ":" + z2(t.m) + ":" + z2(t.s);
    if (twelve) return hh + ":" + z2(t.m) + " " + ap;
    return z2(hh) + ":" + z2(t.m);
  }
  const onBt = () => m.link.tr === 1;
  const linkCode = () => m.link.tr === 0 ? 0 : m.link.tr === 2 ? 1 : 2 + Math.min(2, m.link.slot);
  /* The top level's value: the active profile's name in `room` cells (9 on the board), or room - 1 and its `*`. */
  function profValue(room) {
    if (m.active >= PROF_USER || !valid(m.active)) return "None";
    const st = star(), p = m.profiles[m.active];
    if (st && !p.name) return room >= 8 ? "Prof. " + (m.active + 1) + "*" : "P" + (m.active + 1) + "*";
    const n = profName(m.active).slice(0, st ? room - 1 : room);
    return st ? n + "*" : n;
  }
  function profSummary(slot, line) {
    const N = G.COLS, out = new Array(N).fill(" "), put = (at, s) => { for (let i = 0; i < s.length && at + i < N; i++) out[at + i] = s[i]; };
    const p = m.profiles[slot];
    if (!p) return out.join("");
    if (line === 0) {
      if (!p.rgb.on) { put(G.wide ? 0 : 2, "Lights off"); return out.join(""); }
      const v = p.rgb.fx === TWO_TONE ? "+" + Math.floor(p.rgb.speed * 360 / 256) : pct255(p.rgb.speed) + "%";
      const at = G.wide ? 0 : 2;   /* wide: in one column with the line under it */
      put(N - v.length, v);
      put(at, (EFFECTS[p.rgb.fx] || "Unknown").slice(0, N - at - v.length - 1));
    } else if (line === 1 && G.wide) {   /* wide: the hue, saturation and brightness in one line, no bulb */
      put(0, "H" + Math.floor(p.rgb.h * 360 / 256) + " S" + pct255(p.rgb.s) + " B" + pct255(p.rgb.v));
    } else if (line === 1) {
      put(0, ICON.light);
      const b = "H:" + Math.floor(p.rgb.h * 360 / 256) + " S:" + pct255(p.rgb.s) + "% B:" + pct255(p.rgb.v) + "%";
      put(b.length <= 18 ? 2 : 20 - b.length, b);
    } else {
      put(0, ICON.screen); put(2, fmtValue("screen", p.lcd)); put(8, X.I_CLOCK); put(10, CLOCK_SHORT_BY_ENUM[p.clock % 6]);
    }
    return out.join("");
  }

  /* ---- Rows (row_count, row_node, row_at) ---- */
  function rowCount(node) {
    if (node === "effect") return 1 + EFFECTS.length;
    if (node === "lights") return 3;
    if (node === "profiles") return 2 + saved();
    return (ROWS[node] || []).length;
  }
  function rowNode(node, i) {
    if (node === "effect" || node === "lights") return i ? { node: node === "effect" ? "effopt" : "ltsopt", val: i - 1 } : { node: "back", val: 0 };
    if (node === "profiles") {
      if (!i) return { node: "back", val: 0 };
      const s = nth(i - 1);
      if (s < PROF_USER) return { node: "pslotrow", val: s };
      return { node: i === 1 + saved() ? "pnew" : null, val: 0 };
    }
    const r = ROWS[node];
    return { node: r && i < r.length ? r[i] : null, val: 0 };
  }
  function savedRow(node) {
    if (node === "power") return 1 + m.power;
    if (node === "effect") return 1 + (S.edit ? S.edit.before : m.rgb.fx);
    if (node === "lights") return (S.edit ? S.edit.before : m.rgb.on) ? 2 : 1;
    if (node === "batt") return m.battView;
    if (node === "font") return 1 + FONT_OPT.indexOf(savedFace());
    return 1 + CLOCK_ENUM.indexOf(m.clock);
  }
  function rowAt(r) {
    const f = cur(), blank = { kind: "blank" };
    if (isTopic(f.node)) {
      const t = +f.node.slice(5), i = f.top + r, L = helpLines(t);
      return i < L.length ? { kind: "text", text: L[i] } : blank;
    }
    if (f.node === "about") { const i = f.top + r; return i < 8 ? { kind: "text", text: aboutLine(i) } : blank; }
    if (f.node === "more") { const i = f.top + r; return i < 2 * G.ROWS ? { kind: "more", line: i } : blank; }
    if (f.node === "batt" && r >= G.NOTE_ROW0 && r < G.NOTE_ROW0 + 3) return { kind: "text", text: battNote(r - G.NOTE_ROW0) };
    if (f.node === "font" && r >= G.NOTE_ROW0 && r < G.NOTE_ROW0 + 2) return { kind: "text", text: FONT_NOTE[G.wide ? 1 : 0][r - G.NOTE_ROW0] };
    if (f.node === "pslot" && r >= G.PSUM_ROW0 && r < G.PSUM_ROW0 + G.PSUM_LINES) return { kind: "pnote", text: profSummary(S.pslot, r - G.PSUM_ROW0), rule: r === G.PSUM_ROW0 };
    const i = f.top + r;
    if (i >= rowCount(f.node)) return blank;
    const { node, val } = rowNode(f.node, i);
    if (!node) return blank;
    const x = { kind: "item", node, val, lit: i === f.cursor, bullet: false, top: f.node === "top" };
    if (/^bt\d$/.test(node)) { x.bullet = onBt() && +node[2] === m.link.slot; x.val = x.bullet ? m.link.st : 0; }
    else if (node === "pslotrow") x.bullet = m.active === val;
    else if (node === "pnew") x.val = saved() >= PROF_USER ? 1 : 0;
    else if (VALUE_ROWS.has(node)) x.kind = "value";
    if (CHOICES.has(f.node) && i && i === savedRow(f.node)) x.bullet = true;
    return x;
  }
  /* wide: whether a top-level row shows its icon (not in the variant without row icons). */
  const rowIcon = x => ICON[x.node] && !(G.wide && x.top && S.variant === "nv") ? ICON[x.node] : null;
  /* A row's cells, as row_text() composes them. */
  function rowText(x) {
    const N = G.COLS, out = new Array(N).fill(" "), put = (at, s) => { for (let i = 0; i < s.length && at + i < N; i++) out[at + i] = s[i]; };
    if (x.kind === "text" || x.kind === "pnote") { put(0, x.text); return out.join(""); }
    if (x.kind === "value") {
      let at = 0;
      const icon = rowIcon(x);
      if (icon) { put(0, icon); at = 2; }
      let label = wl(x.node === "speed" ? (twoTone() ? "Second color" : "Speed") : LABEL[x.node]);
      let v = G.wide && x.top && S.variant === "in" ? X.TRI_R : fmtValue(x.node, liveValue(x.node));
      [label, v] = fitPair(N - at, label, v);
      put(at, label);
      const room = at + label.length + 1 < N ? N - at - label.length - 1 : 0;
      v = v.slice(0, room);
      put(N - v.length, v);
      return out.join("");
    }
    if (x.kind !== "item") return out.join("");
    const n = x.node;
    let label = n === "effopt" ? EFFECTS[x.val] : n === "ltsopt" ? (x.val ? "On" : "Off")
                : n === "pairnow" ? "Pair device to BT " + (Math.min(2, m.link.slot) + 1)
                : n === "pslotrow" ? profName(x.val)
                : /^bt\d$/.test(n) ? "Bluetooth " + (+n[2] + 1)
                : /^pow\d$/.test(n) ? POWER_FULL[+n[3]]
                : /^clk\d$/.test(n) ? CLOCK_FULL[+n[3]]
                : /^bv\d$/.test(n) ? BATT_FULL[+n[2]]
                : /^fopt\d$/.test(n) ? FONT_NAME[FONT_OPT[+n[4]]]
                : isTopic(n) ? helpTitle(+n[5]) : LABEL[n];
    label = wl(label);
    let value = "";
    if (n === "power") value = POWER_SHORT[m.power];
    else if (n === "clock") value = CLOCK_SHORT_BY_ENUM[m.clock];
    else if (/^clk[0-4]$/.test(n)) value = clockExample(+n[3]);
    else if (n === "batt") value = BATT_SHORT[m.battView - 1];
    else if (n === "font") value = (G.wide ? FONT_SHORT : FONT_NAME)[savedFace()];
    else if (n === "conn") value = LINK_NAMES[linkCode()];
    else if (/^bt\d$/.test(n)) value = LINK_WORDS[x.val];
    else if (/^bv\d$/.test(n)) value = battPreview(+n[2] + 1);
    else if (n === "prof") value = profValue(9);
    else if (n === "pslotrow") value = X.TRI_R;
    else if (n === "pnew") value = x.val ? "Full" : "";
    else if (OPENS.has(n) || isTopic(n)) value = X.TRI_R;
    if (G.wide) {
      if (/^clk\d$/.test(n)) { label = n === "clk5" ? "Off" : clockExample(+n[3]); value = ""; }   /* the format by its example */
      if (n === "pslotrow") label = label.slice(0, N - 4);
      if (x.top) {
        if (S.variant === "in") value = n === "exit" ? "" : X.TRI_R;
        else if (n === "power") value = "";   /* its bulb (drawList) */
        else if (n === "prof" && S.variant === "iv") {   /* the folder and the profile's name, or "Profiles" */
          const a = m.active < PROF_USER && valid(m.active);
          label = a ? profName(m.active).slice(0, star() ? N - 5 : N - 4) + (star() ? "*" : "") : "Profiles";
          value = X.TRI_R;
        } else if (n === "prof") value = profValue(N - 9);
      }
    }
    let at = 0;
    const icon = rowIcon(x);
    if (icon) { put(0, icon); at = 2; }
    else if (isOption(n)) {
      if (x.bullet) put(0, /^bt\d$/.test(n) ? LINK_ICONS[x.val] : X.CHECK_BOX);
      at = 2;
    }
    [label, value] = fitPair(N - at, label, value);
    put(at, label.slice(0, N - at));
    if (value) put(N - value.length, value);
    return out.join("");
  }
  function rowColours(x) {
    let fg = C.DIM;
    if (x.kind !== "item" && x.kind !== "value") fg = C.WHITE;
    else if (x.lit) fg = C.LIT;
    else if (x.node === "back" || x.node === "exit") fg = C.LEAVE;
    else if (x.node === "pnew" && x.val) fg = C.GREY;
    let icon = 0;
    if (x.kind === "item" || x.kind === "value") {
      if (rowIcon(x)) icon = x.lit ? C.ICON_LIT : C.WHITE;
      else if (x.kind === "item" && x.bullet && isOption(x.node)) icon = /^bt\d$/.test(x.node) ? LINK_COLOUR[x.val] : C.SAVED;
    }
    return { fg, icon };
  }
  function aboutLine(r) {
    const a = S.about || m.about, L = ["idle", "linking", "pairing", "connected", "rejected"], w = G.wide;
    switch (r) {
      case 0: return (w ? "FW " : "Firmware ") + m.build.hash + (m.build.dirty ? "+" : "");
      case 1: return m.build.flavour + ", 0x" + m.build.token;
      case 2: { const mm = Math.floor(a.uptime / 60), d = Math.floor(mm / 1440), h = Math.floor(mm / 60) % 24;
        return d ? "Up " + d + "d " + h + "h " + (mm % 60) + "m" : "Up " + h + "h " + (mm % 60) + "m"; }
      case 3: return "Battery " + Math.floor(a.battPm / 10) + "." + (a.battPm % 10) + "%";
      case 4: return "Pack " + a.packMv + " mV";
      case 5: return w ? "Left: " + Math.floor(a.left / 60) + "h" : "Left " + Math.floor(a.left / 60) + "h of use";
      case 6: return "Mode " + (w ? POWER_SHORT : POWER_FULL)[m.power];
      default: {
        const t = m.link.tr === 0 ? "USB" : m.link.tr === 2 ? "2.4G " + L[m.link.st] : "BT " + (m.link.slot + 1) + " " + L[m.link.st];
        return w && m.link.tr !== 0 ? t : "Link " + t;
      }
    }
  }

  /* ---- Titles (screen_title, title_text, title_icon, want_title) ---- */
  const TITLE = { top: "Configuration", power: "Power", clock: "Clock", diag: "Diagnostics", help: "Help", about: "System info",
    reset: "Reset counters", light: "Lighting", screen: "Screen", effect: "Effect", bright: "Brightness", hue: "Hue",
    sat: "Saturation", lights: "Lights", boot: "Bootloader", defaults: "Reset settings", ind: "Indicators",
    conn: "Connection", conninfo: "Connection", locks: "Lock lights", chgl: "Charging light", pairing: "Pairing",
    batt: "Battery", profiles: "Profiles", psave: "Save profile", pdelete: "Delete profile", prename: "Rename profile",
    font: "Font", more: "More info" };
  const TICON = { top: X.WRENCH + " ", power: ICON.power, clock: ICON.clock, diag: ICON.diag, reset: ICON.diag, help: ICON.help,
    about: ICON.diag, screen: ICON.screen, boot: ICON.boot, defaults: ICON.defaults, ind: ICON.ind, locks: ICON.ind,
    chgl: ICON.ind, conn: ICON.conn, conninfo: ICON.conn, pairing: ICON.conn, batt: ICON.batt, light: ICON.light,
    effect: ICON.light, bright: ICON.light, hue: ICON.light, sat: ICON.light, speed: ICON.light, lights: ICON.light,
    profiles: ICON.prof, pslot: ICON.prof, psave: ICON.prof, pdelete: ICON.prof, prename: ICON.prof, font: ICON.font,
    more: ICON.help };
  /* wide: the shorter words, and an icon's space dropped where the title needs it. */
  function compose(icon, text) {
    if (!G.wide) return icon + text;
    text = W_TITLE[text] || text;
    if ((icon + text).length > G.COLS && icon.endsWith(" ")) icon = icon.slice(0, -1);
    return icon + text;
  }
  function titleNow(now) {
    if (S.flashText && now - S.flashAt < FLASH_MS) return compose("", S.flashText);
    S.flashText = null;
    const n = cur().node, idle = now - S.lastInput;
    if (LISTS.has(n) && idle >= HINT_FROM) {
      const ph = idle % HINT_EVERY;
      if (ph >= HINT_FROM) return compose("", ph < HINT_FROM + 1000 ? "Turn + Click Knob" : "Hold to Go Back");
    }
    if (isTopic(n)) return compose(ICON.help, helpTitle(+n[5]));
    if (n === "pslot") return compose(ICON.prof, profName(S.pslot));
    if (n === "speed") return compose(ICON.light, twoTone() ? "Second color" : "Speed");
    return compose(TICON[n] || "", TITLE[n] || "");
  }
  function flash(text, now) { S.flashText = text; S.flashAt = now; }

  /* ---- Navigation (activate, pop, menu_input) ---- */
  function push(node, cursor) { S.stack.push({ node, cursor, top: Math.floor(cursor / G.ROWS) * G.ROWS }); }
  function fitList(f) {   /* prof_list_fit: in range */
    const n = rowCount(f.node);
    if (f.cursor >= n) f.cursor = n - 1;
    f.top = Math.floor(f.cursor / G.ROWS) * G.ROWS;
  }
  function editOpen(node) { S.edit = { node, before: liveValue(node) }; }
  function editCancel() { if (S.edit) { setLive(S.edit.node, S.edit.before); S.edit = null; } }
  function editSave() { S.edit = null; }
  function pop(now) {
    if (S.stack.length <= 1) return close(now);
    const from = cur().node;
    if (EDITORS.has(from) || PREVIEWS.has(from)) editCancel();
    if (from === "profiles") S.pv = "live";
    if (from === "font") setFace(savedFace());   /* 10-28: the preview's face back to the saved */
    S.stack.pop();
    if (cur().node === "pslot") S.pv = S.pslot;
    if (from === "pslot" && valid(S.pslot)) cur().cursor = 1 + rank(S.pslot);
    fitList(cur());
  }
  function open(now) {
    S.open = true; S.mode = "menu"; S.stack = []; S.flashText = null; S.confirmPage = 0; S.edit = null; S.pv = "live";
    S.lastInput = now; push("top", 0);
  }
  function close(now) {
    editCancel(); S.pv = "live"; S.open = false; S.stack = []; S.mode = "menu";
    setFace(savedFace());   /* 10-28: a preview never outlives the menu */
  }
  function savedFace() { return m.font || faceName; }
  function applyDefaults() {
    m.rgb = { fx: 0, h: 50, s: valOfPct(25), v: valOfPct(75), speed: valOfPct(40), on: 1 };
    m.lcd = 80; m.ind = [5, 5];   /* 10-28: the screen's default 80 */ m.clock = 0; m.battView = 1; m.power = 1; m.active = 0xFF;
    m.font = "termb"; setFace("termb");   /* 10-28: Large, the default face */
  }
  function activate(now) {
    const f = cur(), { node, val } = rowNode(f.node, f.cursor);
    if (!node) return;
    if (node === "back") { if (CHOICES.has(f.node)) flash("Cancelled", now); return pop(now); }
    if (PREVIEWS.has(f.node)) { setLive(f.node, val); editSave(); flash("Saved", now); return pop(now); }
    if (CHOICES.has(f.node)) {
      const i = f.cursor - 1;
      if (f.node === "power") m.power = i; else if (f.node === "batt") m.battView = i + 1;
      else if (f.node === "font") { m.font = FONT_OPT[i]; setFace(m.font); }   /* the menu re-lays out in it, as the firmware's */
      else m.clock = CLOCK_ENUM[i];
      flash("Saved", now); return pop(now);
    }
    switch (node) {
      case "power": case "clock": case "batt": case "font": push(node, savedRow(node)); return;
      case "effect": case "lights": editOpen(node); push(node, savedRow(node)); return;
      case "screen": case "bright": case "hue": case "sat": case "speed": case "locks": case "chgl":
        editOpen(node); S.ftHave = false; push(node, 0); return;
      case "diag": case "help": case "light": case "ind": push(node, 1); return;
      case "conn":
        if (onBt()) push("conn", 1 + Math.min(2, m.link.slot)); else push("conninfo", 0);
        return;
      case "bt0": case "bt1": case "bt2": {
        const slot = +node[2];
        if (slot === m.link.slot && (m.link.st === 3 || m.link.st === 1)) flash("Already on BT " + (slot + 1), now);
        else { m.link = { tr: 1, slot, st: 1 }; S.linkAt = now; flash("Now on BT " + (slot + 1), now); }
        return;
      }
      case "pairnow": {
        const slot = Math.min(2, m.link.slot);
        m.link.st = 2; S.pairing = { slot, at: now, phase: 0 };
        f.cursor = 1 + slot; push("pairing", slot); return;
      }
      case "about": S.about = { ...m.about }; push("about", 0); return;
      case "prof": push("profiles", 1 + (m.active < PROF_USER ? rank(m.active) : 0)); return;
      case "pslotrow": S.pslot = val; S.pv = val; push("pslot", 1); return;
      case "pnew": {
        S.pv = "live";
        let s = 0; while (s < PROF_USER && valid(s)) s++;
        if (s >= PROF_USER) { flash("Full: delete one", now); return; }
        m.profiles[s] = snapshot(""); m.active = s; flash("Saved", now);
        f.cursor = 1 + rank(s); f.top = Math.floor(f.cursor / G.ROWS) * G.ROWS; return;
      }
      case "pload": {
        S.pv = "live";
        const p = m.profiles[S.pslot];
        m.rgb = { ...p.rgb }; m.lcd = p.lcd; m.ind = [...p.ind]; m.clock = p.clock; m.battView = p.battView;
        m.active = S.pslot; S.pv = S.pslot; flash("Loaded", now); return pop(now);
      }
      case "prename": S.name = (m.profiles[S.pslot].name || ""); push("prename", S.pslot); return;
      case "psave": S.pv = "live"; push("psave", S.pslot); return;
      case "pdelete": push("pdelete", S.pslot); return;
      case "exit": return close(now);
      case "health": S.mode = "diag"; S.diagPage = 0; return;
      case "reset": case "boot": case "defaults": S.confirmPage = 0; push(node, 0); return;
      default: if (isTopic(node) || node === "more") { push(node, 0); cur().top = 0; }
    }
  }
  function turn(turns, now) {
    input(now);
    if (!S.open) return;
    if (S.mode === "diag") return;
    const f = cur();
    if (EDITORS.has(f.node)) return editTurn(turns, now);
    if (LISTS.has(f.node) || CHOICES.has(f.node)) {
      const n = rowCount(f.node);
      f.cursor = (((f.cursor + turns) % n) + n) % n;
      f.top = Math.floor(f.cursor / G.ROWS) * G.ROWS;
      if (PREVIEWS.has(f.node)) { const { node, val } = rowNode(f.node, f.cursor); setLive(f.node, node === "back" ? S.edit.before : val); }
    } else if (isTopic(f.node) || f.node === "about" || f.node === "more") {   /* pages scroll a screen at a time */
      const lines = pageLines(f.node), maxtop = Math.max(0, lines - G.ROWS);
      f.top = Math.max(0, Math.min(maxtop, f.top + (turns > 0 ? G.ROWS : -G.ROWS)));
    }
  }
  const pageLines = n => n === "about" ? 8 : n === "more" ? 2 * G.ROWS : helpLines(+n[5]).length;
  function editTurn(turns, now) {
    const fast = Math.abs(turns) >= 2 || (S.ftHave && now - S.ftLast < 90);
    S.ftHave = true; S.ftLast = now;
    const node = cur().node;
    let v = liveValue(node);
    if (node === "hue" || (node === "speed" && twoTone())) v = (v + turns * (fast ? 12 : 1)) & 255;
    else if (node === "screen" || node === "locks" || node === "chgl") v = Math.max(0, Math.min(100, v + turns * (fast ? 8 : 1)));
    else v = valOfPct(Math.max(0, Math.min(100, pct255(v) + turns * (fast ? 8 : 1))));
    setLive(node, v);
  }
  function click(now) {
    input(now);
    if (!S.open) return;
    if (S.mode === "diag") { S.mode = "menu"; cur().cursor = 2; return; }   /* back on Health's row */
    if (S.mode === "boot") return;
    const f = cur();
    if (EDITORS.has(f.node)) { editSave(); flash("Saved", now); return pop(now); }
    if (LISTS.has(f.node) || CHOICES.has(f.node)) return activate(now);
    if (f.node === "boot") {
      if (S.confirmPage === 0) { if (!m.reserve) { S.mode = "boot"; return; } S.confirmPage = 1; return; }
      return pop(now);
    }
    if (f.node === "reset") { if (S.confirmPage === 0) { S.confirmPage = 1; flash("Counters reset", now); return; } return pop(now); }
    if (f.node === "defaults") {
      if (S.confirmPage === 0) { applyDefaults(); S.confirmPage = 1; flash("Settings reset", now); return; }
      return pop(now);
    }
    if (f.node === "pairing") return pairLeave(now);
    if (f.node === "psave") { m.profiles[S.pslot] = snapshot(m.profiles[S.pslot].name); m.active = S.pslot; flash("Saved", now); return pop(now); }
    if (f.node === "pdelete") {
      m.profiles[S.pslot] = null; if (m.active === S.pslot) m.active = 0xFF;
      flash("Deleted", now); S.pv = "live"; S.stack.length -= 2; fitList(cur()); return;
    }
    if (f.node === "prename") return renameCommit(now);
    return pop(now);
  }
  function hold(now) {
    input(now);
    if (!S.open) return;
    if (S.mode === "diag") { S.mode = "menu"; cur().cursor = 2; return; }   /* back on Health's row */
    if (S.mode === "boot") return;
    const f = cur();
    if (f.node === "pairing") return pairLeave(now);
    if (CHOICES.has(f.node) || EDITORS.has(f.node) || (["reset", "boot", "defaults"].includes(f.node) && S.confirmPage === 0) ||
        ["psave", "pdelete", "prename"].includes(f.node)) flash("Cancelled", now);
    pop(now);
  }
  function pairLeave(now) {
    if (S.pairing && S.pairing.phase < 2) { m.link.st = 3; flash("Pairing stopped", now); }
    S.pairing = null; pop(now);
  }
  function renameCommit(now) {
    const n = S.name.replace(/ +$/, "");
    m.profiles[S.pslot].name = n; flash("Renamed", now); pop(now);
  }
  /* Rename's keys: the board's own keymap, US QWERTY. */
  function key(k, now) {
    if (!S.open || S.mode !== "menu" || cur().node !== "prename") return false;
    input(now);
    if (k === "Enter") renameCommit(now);
    else if (k === "Escape") { flash("Cancelled", now); pop(now); }
    else if (k === "Backspace") S.name = S.name.slice(0, -1);
    else if (k.length === 1 && k >= " " && k <= "~") { if (S.name.length < PROF_NAME) S.name += k; }
    else return false;
    return true;
  }
  function input(now) { S.lastInput = now; }
  function fnClick(now) { input(now); if (S.mode === "boot") { S.mode = "menu"; S.open = false; S.stack = []; return; } if (S.open) close(now); else open(now); }
  function setSlider(tr, now) {
    m.link = tr === 1 ? { tr: 1, slot: m.link.slot, st: 1 } : { tr, slot: m.link.slot, st: tr === 2 ? 1 : 3 };
    S.linkAt = now;
    if (S.open && S.mode === "menu") {
      const n = cur().node;
      if ((["conn", "pairing"].includes(n) && tr !== 1) || (n === "conninfo" && tr === 1)) {
        S.pairing = null; S.stack.length = 1; cur().cursor = ROWS.top.indexOf("conn"); fitList(cur());
      }
    }
  }
  /* A face of a different size: the pages refit, each list on its cursor's screen, a page of text
     from its first line (Help and About wrap differently per face): menu_refont()'s rule. */
  function setFace(name) {
    if (!faces[name] || faces[name] === face) return;
    faceName = name; face = faces[name]; G = geometry(face);
    for (const f of S.stack) f.top = isTopic(f.node) || f.node === "about" || f.node === "more" ? 0 : Math.floor(f.cursor / G.ROWS) * G.ROWS;
  }
  function setVariant(v) { S.variant = v; }
  function setIcons(name) { iconSet = name; }
  /* The passage of time: links settle, pairing advances, the preview rests, the menu closes when idle. */
  function tick(now) {
    if (m.link.st === 1 && now - (S.linkAt || 0) > 1500) m.link.st = 3;
    if (S.pairing && S.pairing.phase === 0 && now - S.pairing.at > 1200) S.pairing.phase = 1;
    if (!S.open) return;
    const n = cur().node;
    if (n === "profiles" && now - S.lastInput >= PREVIEW_MS) { const r = rowNode("profiles", cur().cursor); S.pv = r.node === "pslotrow" ? r.val : "live"; }
    if (n === "font" && S.mode === "menu" && now - S.lastInput >= PREVIEW_MS) {   /* 10-28: the face under the cursor, unsaved */
      const r = rowNode("font", cur().cursor);
      setFace(/^fopt\d$/.test(r.node || "") ? FONT_OPT[+r.node[4]] : savedFace());
    }
    const editing = S.mode === "menu" && (EDITORS.has(n) || PREVIEWS.has(n));
    const limit = editing || (S.mode === "menu" && (n === "pairing" || n === "prename")) ? BACKSTOP_MS : IDLE_MS;
    if (S.mode !== "boot" && now - S.lastInput > limit) close(now);
  }
  function idleLeft(now) {
    if (!S.open) return null;
    const n = cur().node, editing = S.mode === "menu" && (EDITORS.has(n) || PREVIEWS.has(n));
    const limit = editing || (S.mode === "menu" && (n === "pairing" || n === "prename")) ? BACKSTOP_MS : IDLE_MS;
    return { left: Math.max(0, limit - (now - S.lastInput)), backstop: limit === BACKSTOP_MS };
  }

  /* ---- Drawing into the frame ---- */
  let fb = null;
  function px(x, y, c) { if (x >= 0 && x < W && y >= 0 && y < H) fb[y * W + x] = c; }
  function fill(x0, y0, x1, y1, c) { for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) px(x, y, c); }
  /* A text slot (text_piece): a lead (4 px for a row, its cursor in it; 1 px for a title or a page's line), the cells,
     a 1 px trail. icon: cells 0-1's colour; bulb: a mode's bulb over x 111-124. */
  function slot(y, cells, o) {
    /* 10-28: in Terminus regular a title keeps Bold's glyphs (text_piece()'s `title`) */
    const lead = o.row ? 4 : 1, x0 = G.TEXT_X - lead, face = o.bold && faceName === "term" && faces.termb ? faces.termb : drawFace();
    const cg = face.glyph(0x87);
    for (let r = 0; r < G.CH; r++) {
      for (let i = 0; i < lead; i++) px(x0 + i, y + r, o.cursor && (cg[r] & (0x80 >> i)) ? C.CURSOR : 0);
      for (let c = 0; c < G.COLS; c++) {
        const g = face.glyph(c < cells.length ? cells.charCodeAt(c) : 32), col = o.icon && c < 2 ? o.icon : o.fg;
        for (let i = 0; i < G.CW; i++) {
          const x = G.TEXT_X + c * G.CW + i;
          if (o.bulb != null && x >= G.BULB_X) continue;
          px(x, y + r, (g[r] & face.mask & (0x80 >> i)) ? col : 0);
        }
      }
      const tx = G.TEXT_X + G.COLS * G.CW;
      if (o.bulb == null) px(tx, y + r, 0);
    }
    const i12 = G.wide && (o.row ? o.icon : o.title) ? ICON12[cells.charCodeAt(0)] : undefined;
    if (i12 != null && icons12[i12])   /* the set's icon over cells 0-1, every pixel of its 16 x 16 cell */
      for (let r = 0; r < G.CH; r++) for (let i = 0; i < 16; i++) {
        const lv = (icons12[i12][r * 4 + (i >> 2)] >> (6 - 2 * (i & 3))) & 3;
        px(G.TEXT_X + i, y + r, lv ? level565(o.row ? o.icon : o.fg, lv) : 0);
      }
    if (o.bulb != null)
      for (let r = 0; r < G.CH; r++) for (let i = 0; i < 14; i++) {
        const ar = r - G.BULB_DY;
        px(G.BULB_X + i, y + r, i < 13 && ar >= 0 && ar < 14 ? bulbPx(o.bulb, i, ar) : 0);
      }
  }
  function title(now) { slot(G.TITLE_Y, titleNow(now).padEnd(G.COLS).slice(0, G.COLS), { fg: C.WHITE, title: true, bold: true }); fill(4, G.SEP_Y, 123, G.SEP_Y, C.GREY); }
  function scrollbar(count, top) {
    const BAR_H = G.ROWS * G.ROW_H;
    if (count <= G.ROWS) { fill(G.BAR_X, G.ROW0, G.BAR_X, G.ROW0 + BAR_H - 1, 0); return; }
    if (top > count - G.ROWS) top = count - G.ROWS;
    let th = Math.floor((BAR_H * G.ROWS + Math.floor(count / 2)) / count); if (th < 6) th = 6;
    const ty = G.ROW0 + Math.floor(((BAR_H - th) * top + Math.floor((count - G.ROWS) / 2)) / (count - G.ROWS));
    fill(G.BAR_X, G.ROW0, G.BAR_X, G.ROW0 + BAR_H - 1, C.TRACK);
    fill(G.BAR_X, ty, G.BAR_X, ty + th - 1, C.WHITE);
  }
  function drawList(now) {
    title(now);
    const f = cur();
    for (let r = 0; r < G.ROWS; r++) {
      const x = rowAt(r), y = G.ROW0 + r * G.ROW_H;
      if (x.kind === "more") { moreRow(x.line, y); continue; }
      const { fg, icon } = rowColours(x);
      let bulb = x.kind === "item" && /^pow\d$/.test(x.node) ? +x.node[3] : null;
      if (G.wide && x.top && x.node === "power" && S.variant !== "in") bulb = m.power;   /* wide: the mode as its bulb */
      slot(y, rowText(x), { row: true, fg, icon, cursor: !!x.lit, bulb });
      if (x.rule) fill(4, y, 123, y, C.GREY);
    }
    const count = isTopic(f.node) || f.node === "about" || f.node === "more" ? pageLines(f.node) : rowCount(f.node);
    scrollbar(count, f.top);
  }
  /* P1d: a More info row, its band x 0-124 (more_paint()). The bunny at x 4, a pixel under the rule (wide: 3 into
     its three rows), its ink a level of white; the QR's 3 px modules and 2-module quiet zone white, 99 x 99, centred. */
  function moreRow(line, y) {
    if (line >= G.ROWS) {
      const qx = (W - 99) >> 1, qy = G.ROW0 + ((G.ROWS * G.ROW_H - 99) >> 1);
      for (let r = 0; r < G.ROW_H; r++) for (let x = 0; x <= 124; x++) {
        const dx = x - qx, dy = y + r - qy;
        let c = 0;
        if (dx >= 0 && dx < 99 && dy >= 0 && dy < 99) {
          const mx = Math.floor(dx / 3) - 2, my = Math.floor(dy / 3) - 2;
          const dark = art && mx >= 0 && my >= 0 && mx < QR_N && my < QR_N && (art[BUNNY_W * BUNNY_H + my * 4 + (mx >> 3)] >> (7 - (mx & 7))) & 1;
          c = dark ? 0 : 0xFFFF;
        }
        px(x, y + r, c);
      }
      return;
    }
    const by = G.ROW0 + (G.wide ? 3 : 1), meets = y < by + BUNNY_H && y + G.ROW_H > by, at = meets ? (G.wide ? 4 : 5) : 0;
    const t = MORE_TEXT[G.wide ? 1 : 0][line] || "";
    slot(y, (" ".repeat(at) + t).padEnd(G.COLS).slice(0, G.COLS), { row: true, fg: MORE_LINK[G.wide ? 1 : 0].includes(line) ? LINK_COLOUR[2] : C.WHITE });
    if (!meets || !art) return;
    for (let r = 0; r < G.ROW_H; r++) for (let i = 0; i < BUNNY_W; i++) {
      const b = y + r - by;
      if (b < 0 || b >= BUNNY_H) continue;
      const g = art[b * BUNNY_W + i], k = n => Math.floor((g * n + 127) / 255);
      px(G.TEXT_X + i, y + r, (k(31) << 11) | (k(63) << 5) | k(31));
    }
  }
  function confirmLines() {
    const n = cur().node, p = S.confirmPage & 1, nm = profName(cur().cursor), w = G.wide;
    if (n === "conninfo") return w ? ["Slide to BT to", "change these", "settings.", "Click: back"] : ["Switch to BT mode to", "change Bluetooth", "settings.", "Click: back"];
    if (n === "pairing") {
      const s = S.pairing ? S.pairing.slot : 0, ph = S.pairing ? S.pairing.phase : 3, stop = w ? "Click: stop" : "Click or hold: stop";
      return ph === 0 ? ["Bluetooth " + (s + 1), w ? "Getting ready" : "Getting ready...", stop, ""]
           : ph === 1 ? (w ? ["On the device,", "add AK820 5.1-" + (s + 1), stop, ""] : ["On the device, add", "AK820 5.1-" + (s + 1), stop, ""])
           : ["Pairing ended.", "", "Click: back", ""];
    }
    if (n === "psave") return w ? ["Save over", nm + "?", "Click: save", "Hold: cancel"] : ["Replace " + nm, "with these settings?", "Click: replace", "Hold: cancel"];
    if (n === "pdelete") return w ? ["Delete", nm + "?", "Click: delete", "Hold: cancel"] : ["Delete " + nm + "?", "", "Click: delete", "Hold: cancel"];
    if (n === "prename") return [S.name + "_", "Type a name", w ? "Enter: save" : "Enter, click: save", w ? "Esc: cancel" : "Esc, hold: cancel"];
    if (n === "boot") return w ? [["For a firmware", "update via USB.", "Click: enter", "Hold: cancel"], ["Plug in first:", "battery is low.", "Click: back", ""]][p]
                              : [["For a firmware", "update over USB.", "Click: enter", "Hold: cancel"], ["Plug in first:", "the battery is low.", "Click: back", ""]][p];
    if (n === "defaults") return w ? [["Use defaults?", "Profiles stay.", "Click: reset", "Hold: cancel"], ["Settings reset.", "", "Click: back", ""]][p]
                                  : [["Back to defaults?", "Profiles are kept.", "Click: reset", "Hold: cancel"], ["Settings reset.", "", "Click: back", ""]][p];
    return w ? [["Clear health", "counters?", "Click: reset", "Hold: cancel"], ["Counters reset.", "", "Click: back", ""]][p]
             : [["Clear the health", "counters?", "Click: reset", "Hold: cancel"], ["Counters reset.", "", "Click: back", ""]][p];
  }
  function drawConfirm(now) {
    title(now);
    const ys = cur().node === "conninfo" ? G.INFO_Y : G.C_Y;
    confirmLines().forEach((l, i) => slot(ys[i], l.padEnd(G.COLS).slice(0, G.COLS), { fg: C.WHITE }));
  }
  function bigText(s, x, y) {
    for (let k = 0; k < s.length; k++) {
      const cx = x + k * 10;
      if (!big) { fill(cx, y, cx + 9, y + 22, BIG_CELL); continue; }
      const g = big.glyph(s.charCodeAt(k));
      for (let j = 0; j < 23; j++) for (let i = 0; i < 10; i++) px(cx + i, y + j, g && g[j * 10 + i] ? C.WHITE : 0);
    }
  }
  function hue565(h) {   /* QMK's hsv_to_rgb at full saturation and value, as the strip's */
    const region = Math.floor(h * 6 / 255), rem = ((h * 2 - region * 85) * 3) & 255;
    const q = (255 * (255 - ((255 * rem) >> 8))) >> 8, t = (255 * (255 - ((255 * (255 - rem)) >> 8))) >> 8;
    let r, g, b;
    switch (region) { case 6: case 0: r = 255; g = t; b = 0; break; case 1: r = q; g = 255; b = 0; break;
      case 2: r = 0; g = 255; b = t; break; case 3: r = 0; g = q; b = 255; break; case 4: r = t; g = 0; b = 255; break;
      default: r = 255; g = 0; b = q; }
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
  }
  function drawEditor(now) {
    title(now);
    const n = cur().node, v = liveValue(n), hueEd = n === "hue" || (n === "speed" && twoTone());
    if (!hueEd) {
      const B = G.BAR, max = n === "screen" || n === "locks" || n === "chgl" ? 100 : 255;
      const edge = B.X0 + 1 + Math.floor((v * 100 + Math.floor(max / 2)) / max);
      for (let y = B.YT; y <= B.YB; y++) for (let x = B.X0; x <= B.X1; x++)
        px(x, y, (y === B.YT || y === B.YB || x === B.X0 || x === B.X1) ? C.GREY : x < edge ? C.WHITE : 0);
    } else {
      const a = n === "speed" ? (m.rgb.h + v) & 255 : v, mx = G.STRIP.X0 + Math.floor((a * 120 + 128) / 256), ty = G.ENV.Y1 - 2;
      for (let y = G.ENV.Y0; y <= G.ENV.Y1; y++) for (let x = 0; x < 128; x++) {
        let c = 0;
        if (y >= G.STRIP.YT && y <= G.STRIP.YB && x >= G.STRIP.X0 && x <= G.STRIP.X1) c = hue565(Math.floor(((x - G.STRIP.X0) * 256 + 60) / 120));
        if (y >= ty) { const half = 2 - (y - ty); if (Math.abs(x - mx) <= half) c = C.LIT; }
        else if (x === mx) c = C.WHITE;
        px(x, y, c);
      }
    }
    const s = fmtValue(n, v), at = s.length < 10 ? Math.floor((10 - s.length) / 2) : 0;
    bigText((" ".repeat(at) + s).padEnd(10).slice(0, 10), G.VAL_X, G.VAL_Y[hueEd ? 1 : 0]);
    ["Turn: change", "Click: save", "Hold: cancel"].forEach((l, i) => slot(G.HINT_Y0 + i * G.HINT_DY, l.padEnd(G.COLS).slice(0, G.COLS), { fg: C.WHITE }));
  }
  function render(target, now) {
    fb = target; fb.fill(0);
    if (!S.open || S.mode !== "menu") return false;   /* the page draws the dashboard and Fn+D's pages */
    const n = cur().node;
    if (CONFIRMS.has(n)) drawConfirm(now);
    else if (EDITORS.has(n)) drawEditor(now);
    else drawList(now);
    return true;
  }

  return { m, S, C, X, EFFECTS, POWER_FULL, CLOCK_SHORT_BY_ENUM, BATT_SHORT, LINK_NAMES, TWO_TONE, BIG_CELL,
    get G() { return G; }, get face() { return face; }, get faceName() { return faceName; },
    open, close, turn, click, hold, key, fnClick, tick, setSlider, setFace, setVariant, setIcons, render, idleLeft, shown, star,
    profName, battLevelText, fmtValue, bulbPx, cur: () => (S.stack.length ? cur() : null), valid, saved };
}

root.createMenu = createMenu;
if (typeof module !== "undefined") module.exports = { createMenu };
})(typeof window !== "undefined" ? window : globalThis);
