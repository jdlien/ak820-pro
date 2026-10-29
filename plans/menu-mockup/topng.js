// PPM (P6) to PNG, scaled up by an integer, for viewing. Usage: node topng.js scale file.ppm...
const fs = require("fs"), zlib = require("zlib");
const scale = +process.argv[2];
function crc32(buf) {
  let c, crc = ~0;
  for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; }
  return ~crc >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
for (const f of process.argv.slice(3)) {
  const b = fs.readFileSync(f);
  const m = b.toString("latin1", 0, 32).match(/^P6\s+(\d+)\s+(\d+)\s+255\s/);
  const w = +m[1], h = +m[2], off = m[0].length;
  const W = w * scale, H = h * scale, raw = Buffer.alloc((W * 3 + 1) * H);
  for (let y = 0; y < H; y++) {
    raw[y * (W * 3 + 1)] = 0;
    for (let x = 0; x < W; x++) {
      const s = off + ((Math.floor(y / scale) * w + Math.floor(x / scale)) * 3), d = y * (W * 3 + 1) + 1 + x * 3;
      raw[d] = b[s]; raw[d + 1] = b[s + 1]; raw[d + 2] = b[s + 2];
    }
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4); ihdr[8] = 8; ihdr[9] = 2;
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
  fs.writeFileSync(f.replace(/\.ppm$/, ".png"), png);
}
