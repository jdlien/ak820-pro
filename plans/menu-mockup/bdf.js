// A BDF face into a cw x ch cell, a byte a row (column 0 in bit 7), glyphs 0x20-0x7E.
const fs = require("fs");
function parseBdf(file, cw, ch, ascent) {
  const lines = fs.readFileSync(file, "latin1").split(/\r?\n/), out = {};
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].startsWith("STARTCHAR")) continue;
    let enc = -1, bbx = null, j = i;
    for (; !lines[j].startsWith("BITMAP"); j++) {
      if (lines[j].startsWith("ENCODING")) enc = +lines[j].split(/\s+/)[1];
      if (lines[j].startsWith("BBX")) bbx = lines[j].split(/\s+/).slice(1).map(Number);
    }
    const [w, h, xo, yo] = bbx, rows = new Uint8Array(ch);
    for (let r = 0; r < h; r++) {
      const v = parseInt(lines[j + 1 + r], 16), bits = lines[j + 1 + r].length * 4;
      const y = ascent - (yo + h) + r;   /* top of the bitmap: ascent - (yoff + h) */
      for (let c = 0; c < w; c++) if ((v >> (bits - 1 - c)) & 1) { const x = xo + c; if (x >= 0 && x < cw && y >= 0 && y < ch) rows[y] |= 0x80 >> x; }
    }
    out[enc] = rows;
  }
  return out;
}
module.exports = { parseBdf };
if (require.main === module) {
  const g = parseBdf(process.argv[2], 8, 16, 12);
  let top = 0, bottom = 0;
  for (let c = 0x20; c < 0x7f; c++) { if (g[c][0]) top++; if (g[c][15]) bottom++; }
  const ink = ch => { const r = g[ch.charCodeAt(0)]; const ys = [...r].map((b, i) => b ? i : -1).filter(i => i >= 0); const w = r.reduce((a, b) => a | b, 0).toString(2).replace(/0+$/, "").length; return ch + ": rows " + ys[0] + "-" + ys[ys.length - 1] + " (" + ys.length + "), width " + w; };
  console.log("glyphs inking row 0:", top, " row 15:", bottom);
  ["H", "x", "g", "|", "M", "%"].forEach(c => console.log(ink(c)));
  for (const c of "Rg") { console.log(c); g[c.charCodeAt(0)].forEach(b => console.log("  " + b.toString(2).padStart(8, "0").replace(/0/g, ".").replace(/1/g, "#"))); }
}
