// The icons, Cozette's beside the redrawn, each in a row of text, as a PNG. Usage: node iconsheet.js face.hex out.png
const fs = require("fs"), zlib = require("zlib"), { createMenu } = require("./core.js");
const hex = f => fs.readFileSync(__dirname + "/" + f, "utf8").trim();
const faces = { c6: { hex: hex("font6x14.hex"), cw: 6, ch: 14 }, w: { hex: hex(process.argv[2]), cw: 8, ch: 16 } };
const items = [["\x95 ", "Lighting"], ["\x96\x97", "Screen"], ["\x9c\x9d", "Connection"], ["\x8c ", "Power"], ["\x9a\x9b", "Indicators"],
  ["\x8d\x8e", "Clock"], ["\xa2 ", "Battery"], ["\xa3 ", "Profiles"], ["\x98\x99", "Bootloader"], ["\xab ", "Defaults"],
  ["\x8f ", "Diagnostics"], ["\x90\x91", "Help"], ["\x92\x93", "About"], ["\x94 ", "Exit"], ["\xa4\xa5", "Load"], ["\xa6\xa7", "Save"],
  ["\xa8 ", "Rename"], ["\xa9\xaa", "Delete"], ["\x8a\x8b", "Saved"], ["\x9e\x9f", "Trying"], ["\xa0\xa1", "Failed"], ["\x88\x89", "Title"],
  ["\x85 ", "Back"], ["  ", "Open \x86"]];
const S = 3, W = 2 * 128 + 8, H = items.length * 18 + 4, fb = new Uint32Array(W * H);
function draw(face, cw, ch, s, x0, y0) {
  for (let k = 0; k < s.length; k++) { const g = face.glyph(s.charCodeAt(k));
    for (let r = 0; r < ch; r++) for (let i = 0; i < cw; i++) if (g[r] & (0x80 >> i)) fb[(y0 + r) * W + x0 + k * cw + i] = 1; }
}
const m6 = createMenu({ faces, face: "c6" }), mw = createMenu({ faces, face: "w" });
items.forEach(([ic, label], i) => { draw(m6.face, 6, 14, ic + label, 4, 2 + i * 18 + 1); mw.setFace("w"); draw(mw.face, 8, 16, ic + label, 136, 2 + i * 18); });
const WW = W * S, HH = H * S, raw = Buffer.alloc((WW * 3 + 1) * HH);
for (let y = 0; y < HH; y++) { raw[y * (WW * 3 + 1)] = 0; for (let x = 0; x < WW; x++) { const v = fb[Math.floor(y / S) * W + Math.floor(x / S)] ? 235 : (x % S === 0 || y % S === 0 ? 22 : 8); const p = y * (WW * 3 + 1) + 1 + x * 3; raw[p] = raw[p + 1] = raw[p + 2] = v; } }
function crc32(b) { let c, crc = ~0; for (let n = 0; n < b.length; n++) { c = (crc ^ b[n]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; } return ~crc >>> 0; }
const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc32(td)); return Buffer.concat([l, td, c]); };
const ih = Buffer.alloc(13); ih.writeUInt32BE(WW, 0); ih.writeUInt32BE(HH, 4); ih[8] = 8; ih[9] = 2;
fs.writeFileSync(process.argv[3], Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ih), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
