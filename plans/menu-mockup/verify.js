// Replays tour.c's inputs through core.js and diffs each frame against the firmware's
// (frames/*.ppm; Large's, frames-large/; Regular's, frames-regular/). Usage: node verify.js [stepMs] [large|regular]
const fs = require("fs"), path = require("path");
const { createMenu } = require("./core.js");
const dir = __dirname;
const STEP = +(process.argv[2] || 300), LARGE = process.argv[3] === "large", REGULAR = process.argv[3] === "regular";
const hex = f => fs.readFileSync(path.join(dir, f), "utf8").trim();
const menu = createMenu({ faces: { c6: { hex: hex("font6x14.hex"), cw: 6, ch: 14 }, termb: { hex: hex("f-termb.hex"), cw: 8, ch: 16 },
                                   term: { hex: hex("f-term.hex"), cw: 8, ch: 16 } },
  face: REGULAR ? "term" : LARGE ? "termb" : "c6", icons12: hex("icons12.hex"), menuArt: hex("menuart.hex"), clock: () => ({ h: 13, m: 45, s: 1, day: 24, month: 10, year: 2026 }) });
const FRAMES = REGULAR ? "frames-regular" : LARGE ? "frames-large" : "frames";
const T = { LIGHT: 0, SCREEN: 1, CONN: 2, POWER: 3, IND: 4, CLOCK: 5, BATT: 6, PROF: 7, BOOT: 8, FONT: 9, DEFS: 10, DIAG: 11, HELP: 12 };
let now = 1000;
const fb = new Uint32Array(128 * 128);
const act = f => { now += STEP; f(now); menu.tick(now); };
const turn = n => { if (n) act(t => menu.turn(n, t)); };
const click = () => act(t => menu.click(t));
const hold = () => act(t => menu.hold(t));
const unflash = () => { now += 1300; menu.tick(now); };
const go = row => turn(row - menu.cur().cursor);
let bad = 0;
function rgb(c) {
  if (c === menu.BIG_CELL) return [220, 220, 220];
  return [Math.floor(((c >> 11) & 31) * 255 / 31), Math.floor(((c >> 5) & 63) * 255 / 63), Math.floor((c & 31) * 255 / 31)];
}
function shot(name) {
  menu.render(fb, now);
  const b = fs.readFileSync(path.join(dir, FRAMES, name + ".ppm"));
  const m = b.toString("latin1", 0, 32).match(/^P6\s+(\d+)\s+(\d+)\s+255\s/), off = m[0].length;
  let diffs = 0, first = null, rows = new Set();
  for (let y = 0; y < 128; y++) for (let x = 0; x < 128; x++) {
    const p = off + (y * 128 + x) * 3, want = [b[p], b[p + 1], b[p + 2]], got = rgb(fb[y * 128 + x]);
    if (want[0] !== got[0] || want[1] !== got[1] || want[2] !== got[2]) { diffs++; rows.add(y); if (!first) first = { x, y, want, got }; }
  }
  const ys = [...rows].sort((a, b) => a - b);
  console.log((diffs ? "DIFF " : "ok   ") + name.padEnd(16) + (diffs ? diffs + " px, rows " + ys[0] + "-" + ys[ys.length - 1] + ", first " + JSON.stringify(first) : ""));
  if (diffs) bad++;
}
menu.open(now); menu.tick(now);
shot("top-c0");
turn(1); shot("top-c1");
go(T.BOOT); shot("top-p2");
go(T.LIGHT); click(); shot("lighting");
turn(1); click(); shot("lighting-effect"); hold(); unflash();
go(2); click(); shot("edit-range"); hold(); unflash();
go(3); click(); shot("edit-hue"); hold(); unflash();
hold();
go(T.SCREEN); click(); shot("screen"); hold(); unflash();
go(T.CONN); click(); shot("conn"); hold();
go(T.POWER); click(); shot("power"); hold();
go(T.IND); click(); shot("ind"); hold();
go(T.CLOCK); click(); shot("clock"); hold();
go(T.BATT); click(); shot("batt"); hold();
go(T.PROF); click(); shot("prof-empty");
click(); unflash();
turn(-menu.cur().cursor - 1); click(); unflash();
shot("prof-list");
go(1); click(); shot("prof-page");
go(3); click(); shot("prof-rename"); hold(); unflash();
hold(); hold();
go(T.BOOT); click(); shot("boot"); hold();
go(T.FONT); click(); shot("font"); hold(); unflash();
go(T.DEFS); click(); shot("defaults"); hold();
go(T.DIAG); click(); shot("diag"); hold();
go(T.HELP); click(); shot("help");
go(1); click(); shot("help-menu"); hold();
go(2); click(); shot("help-via"); hold();
go(3); click(); shot("help-keys"); hold();
go(4); click(); shot("help-tips"); hold();
go(5); click(); shot("help-more"); turn(1); shot("help-more-qr"); hold();   // P1d: More info's two screens
hold();
go(T.DIAG); click(); click(); shot("about"); hold(); hold();   // 10-28: System info, in Diagnostics
console.log(bad ? bad + " frame(s) differ" : "every frame matches");
