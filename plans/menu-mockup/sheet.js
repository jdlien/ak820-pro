// Every page in one face as a contact sheet PNG. Usage: node sheet.js face variant out.png [scale]
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const { createMenu } = require("./core.js");
const d = __dirname, hex = f => fs.readFileSync(path.join(d, f), "utf8").trim();
const FACES = { c6: { hex: hex("font6x14.hex"), cw: 6, ch: 14 }, termb: { hex: hex("f-termb.hex"), cw: 8, ch: 16 } };
const [face, variant, out, scale = 2] = process.argv.slice(2);
const menu = createMenu({ faces: FACES, face, clock: () => ({ h: 13, m: 45, s: 1, day: 24, month: 10, year: 2026 }) });
menu.setVariant(variant);
const m = menu.m;
m.rgb = { fx: 1, h: 191, s: 255, v: 115, speed: 213, on: 1 }; m.lcd = 69; m.battView = 2;
m.profiles[0] = { name: "Purple/Blue", rgb: { ...m.rgb }, lcd: 69, ind: [1, 0], clock: 0, battView: 2 };
m.profiles[1] = { name: "Rainbow Slow", rgb: { fx: 3, h: 0, s: 255, v: 115, speed: 26, on: 1 }, lcd: 69, ind: [1, 0], clock: 0, battView: 2 };
m.active = 0;
let now = 1000;
const frames = [], fb = new Uint32Array(128 * 128);
const act = f => { now += 300; f(now); menu.tick(now); };
const turn = n => { if (n) act(t => menu.turn(n, t)); }, click = () => act(t => menu.click(t)), hold = () => act(t => menu.hold(t));
const unflash = () => { now += 1300; menu.tick(now); };
const go = row => turn(row - menu.cur().cursor);
const shot = () => { menu.render(fb, now); frames.push(Uint32Array.from(fb)); };
menu.open(now);
shot(); go(7); shot(); go(0);
click(); shot(); turn(1); click(); shot(); hold(); unflash(); go(2); click(); turn(-3); shot(); hold(); unflash(); go(3); click(); shot(); hold(); unflash(); hold();
go(1); click(); shot(); hold(); unflash();
go(2); click(); shot(); hold();
go(3); click(); shot(); hold();
go(4); click(); shot(); hold();
go(5); click(); shot(); hold();
go(6); click(); shot(); m.batt.avg = 20; now += 10; shot(); m.batt.avg = 120; hold();
go(7); click(); shot(); go(1); click(); shot(); go(3); click(); shot(); hold(); unflash(); go(2); click(); shot(); hold(); unflash(); hold(); hold();
go(8); click(); shot(); hold();
go(9); click(); shot(); hold();
go(10); click(); shot(); hold();
go(11); click(); shot(); go(1); click(); shot(); hold(); go(3); click(); shot(); turn(1); shot(); hold(); hold();
go(12); click(); shot(); turn(1); shot(); hold();
const cols = 6, rows = Math.ceil(frames.length / cols), s = +scale, gap = 6;
const Wd = cols * (128 * s + gap) + gap, Ht = rows * (128 * s + gap) + gap, raw = Buffer.alloc((Wd * 3 + 1) * Ht, 60);
for (let y = 0; y < Ht; y++) raw[y * (Wd * 3 + 1)] = 0;
frames.forEach((f, k) => {
  const ox = gap + (k % cols) * (128 * s + gap), oy = gap + Math.floor(k / cols) * (128 * s + gap);
  for (let y = 0; y < 128 * s; y++) for (let x = 0; x < 128 * s; x++) {
    let c = f[Math.floor(y / s) * 128 + Math.floor(x / s)];
    const rgb = c === menu.BIG_CELL ? [90, 90, 90] : [Math.floor(((c >> 11) & 31) * 255 / 31), Math.floor(((c >> 5) & 63) * 255 / 63), Math.floor((c & 31) * 255 / 31)];
    const p = (oy + y) * (Wd * 3 + 1) + 1 + (ox + x) * 3; raw[p] = rgb[0]; raw[p + 1] = rgb[1]; raw[p + 2] = rgb[2];
  }
});
function crc32(buf) { let c, crc = ~0; for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; } return ~crc >>> 0; }
const chunk = (t, data) => { const l = Buffer.alloc(4); l.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(t), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc32(td)); return Buffer.concat([l, td, c]); };
const ih = Buffer.alloc(13); ih.writeUInt32BE(Wd, 0); ih.writeUInt32BE(Ht, 4); ih[8] = 8; ih[9] = 2;
fs.writeFileSync(out, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ih), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
console.log(out, frames.length, "frames");
