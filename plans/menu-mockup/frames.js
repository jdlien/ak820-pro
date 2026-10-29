// The font test's frames for the panel: per face a title card, then six screens; or, with
// `compare`, the top level once in each face, its title naming the face. Writes the upload
// image (the "AKFT" header, then each 128 x 128 frame as RGB565, 0x8000 apart from 0x8000)
// and a contact sheet to check it. The frames are lo byte first: the flash-to-panel DMA swaps
// each pair (mkanim.py's frames are the same; hi first showed the dim grey as dark purple).
// Usage: node frames.js out.bin sheet.png [compare]
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const { createMenu } = require("./core.js");
const d = __dirname, hex = f => fs.readFileSync(path.join(d, f), "utf8").trim();
const FACES = { c6: { hex: hex("font6x14.hex"), cw: 6, ch: 14 }, termb: { hex: hex("f-termb.hex"), cw: 8, ch: 16 } };
const ORDER = [
  ["c6", "Cozette 6x14", "as built", "caps 8, lower 6", "20 columns, 8 rows"],
  ["termb", "Terminus Bold", "8x16", "caps 10, lower 7", "15 columns, 7 rows"],
];
const frames = [], labels = [];
function setup(face) {
  const menu = createMenu({ faces: FACES, face, clock: () => { const t = new Date(); return { h: t.getHours(), m: t.getMinutes(), s: t.getSeconds(), day: t.getDate(), month: t.getMonth() + 1, year: t.getFullYear() }; } });
  const m = menu.m;
  m.rgb = { fx: 1, h: 191, s: 255, v: 115, speed: 213, on: 1 }; m.lcd = 69; m.battView = 2;
  m.profiles[0] = { name: "Purple/Blue", rgb: { ...m.rgb }, lcd: 69, ind: [1, 0], clock: 0, battView: 2 };
  m.profiles[1] = { name: "Rainbow Slow", rgb: { fx: 3, h: 0, s: 255, v: 115, speed: 26, on: 1 }, lcd: 69, ind: [1, 0], clock: 0, battView: 2 };
  m.active = 0;
  m.build = { hash: "ecb10f0e", dirty: false, token: "dc5524d4", flavour: "dev" };
  m.about = { uptime: 98640, battPm: 731, packMv: 3918, left: 9420 };
  m.batt = { pct: 73, on: true, left: 9420, avg: 120 };
  return menu;
}
function card(n, total, name, a, b, c) {
  const menu = setup("c6"), f = menu.face, fb = new Uint32Array(128 * 128);
  const text = (s, x, y, col) => { for (let k = 0; k < s.length; k++) { const g = f.glyph(s.charCodeAt(k));
    for (let r = 0; r < 14; r++) for (let i = 0; i < 6; i++) if (g[r] & (0x80 >> i)) fb[(y + r) * 128 + x + k * 6 + i] = col; } };
  text("\x8f Font test " + n + "/" + total, 4, 0, 0xFFFF);
  for (let x = 4; x <= 123; x++) fb[14 * 128 + x] = 0x632C;
  text(name, 4, 24, 0xFF94); text(a, 4, 38, 0xCE59); text(b, 4, 56, 0xCE59); text(c, 4, 70, 0xCE59);
  text("Turn: next screen", 4, 98, 0xFFFF); text("Click, hold: back", 4, 112, 0xFFFF);
  return fb;
}
let now = 1000;
function screens(face, variants) {
  const out = [];
  for (const v of variants) {
    const menu = setup(face); menu.setVariant(v);
    const fb = () => { const b = new Uint32Array(128 * 128); menu.render(b, now); return b; };
    const act = f => { now += 300; f(now); menu.tick(now); }, quiet = () => { now += 2000; menu.tick(now); };
    const go = row => { const c = menu.cur().cursor; if (row !== c) act(t => menu.turn(row - c, t)); };
    menu.open(now); quiet();
    out.push([v, "top", fb()]);
    if (v !== "iv") continue;
    go(7); quiet(); out.push([v, "top 2", fb()]);
    go(0); act(t => menu.click(t)); quiet(); out.push([v, "Lighting", fb()]);
    act(t => menu.hold(t)); quiet(); go(3); act(t => menu.click(t)); quiet(); out.push([v, "Power", fb()]);
    act(t => menu.hold(t)); quiet(); go(7); act(t => menu.click(t)); act(t => menu.click(t)); quiet(); out.push([v, "profile", fb()]);
    act(t => menu.hold(t)); act(t => menu.hold(t)); quiet(); go(11); act(t => menu.click(t)); go(4); act(t => menu.click(t)); quiet(); out.push([v, "Pro tips", fb()]);
  }
  return out;
}
/* The top level with the face's name for its title, drawn as the title is (white, from x 4 at TITLE_Y). */
function named(face, name) {
  const menu = setup(face), f = menu.face, wide = f.cw === 8, ty = wide ? -1 : 0, sep = wide ? 15 : 14;
  menu.open(now); now += 2000; menu.tick(now);
  const b = new Uint32Array(128 * 128); menu.render(b, now);
  for (let y = 0; y < sep; y++) for (let x = 4; x < 128; x++) b[y * 128 + x] = 0;
  const s = "\x88\x89" + name;
  for (let k = 0; k < s.length; k++) { const g = f.glyph(s.charCodeAt(k));
    for (let r = 0; r < f.ch; r++) for (let i = 0; i < f.cw; i++)
      if (ty + r >= 0 && ty + r < sep && 4 + k * f.cw + i < 128 && g[r] & (0x80 >> i)) b[(ty + r) * 128 + 4 + k * f.cw + i] = 0xFFFF; }
  return b;
}
if (process.argv[4] === "compare") {
  const NAMES = { c6: "Cozette (now)", termb: "Terminus Bold" };
  for (const [face] of ORDER) { frames.push(named(face, NAMES[face])); labels.push(face + " compare"); }
} else {
  const plan = ORDER.map(([face, ...words]) => ({ face, words, shots: screens(face, face === "termb" ? ["iv", "nv", "in"] : ["iv"]) }));
  plan.forEach((p, i) => {
    frames.push(card(i + 1, plan.length, ...p.words)); labels.push(p.face + " card");
    for (const [v, what, b] of p.shots) { frames.push(b); labels.push(p.face + " " + v + " " + what); }
  });
}
if (frames.length > 63) throw new Error("too many frames: " + frames.length);
const STRIDE = 0x8000, img = Buffer.alloc(STRIDE * (1 + frames.length), 0xFF);
img.write("AKFT", 0, "latin1"); img[4] = frames.length;
frames.forEach((f, k) => { const o = STRIDE * (1 + k); for (let i = 0; i < 128 * 128; i++) { const c = f[i] & 0xFFFF; img[o + i * 2] = c & 0xFF; img[o + i * 2 + 1] = c >> 8; } });
fs.writeFileSync(process.argv[2], img);
// the contact sheet, read back from the image as the board will read it
const cols = 8, rows = Math.ceil(frames.length / cols), s = 1, gap = 4;
const Wd = cols * (128 + gap) + gap, Ht = rows * (128 + gap) + gap, raw = Buffer.alloc((Wd * 3 + 1) * Ht, 60);
for (let y = 0; y < Ht; y++) raw[y * (Wd * 3 + 1)] = 0;
for (let k = 0; k < frames.length; k++) {
  const ox = gap + (k % cols) * (128 + gap), oy = gap + Math.floor(k / cols) * (128 + gap), o = STRIDE * (1 + k);
  for (let y = 0; y < 128; y++) for (let x = 0; x < 128; x++) {
    const c = img[o + (y * 128 + x) * 2] | (img[o + (y * 128 + x) * 2 + 1] << 8), p = (oy + y) * (Wd * 3 + 1) + 1 + (ox + x) * 3;
    raw[p] = Math.floor(((c >> 11) & 31) * 255 / 31); raw[p + 1] = Math.floor(((c >> 5) & 63) * 255 / 63); raw[p + 2] = Math.floor((c & 31) * 255 / 31);
  }
}
function crc32(b) { let c, crc = ~0; for (let n = 0; n < b.length; n++) { c = (crc ^ b[n]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; } return ~crc >>> 0; }
const chunk = (t, x) => { const l = Buffer.alloc(4); l.writeUInt32BE(x.length); const td = Buffer.concat([Buffer.from(t), x]); const c = Buffer.alloc(4); c.writeUInt32BE(crc32(td)); return Buffer.concat([l, td, c]); };
const ih = Buffer.alloc(13); ih.writeUInt32BE(Wd, 0); ih.writeUInt32BE(Ht, 4); ih[8] = 8; ih[9] = 2;
fs.writeFileSync(process.argv[3], Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ih), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
console.log(frames.length, "frames,", img.length, "bytes; header", img.slice(0, 5));
console.log(labels.map((l, i) => i + ":" + l).join("  "));
