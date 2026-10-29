// An 8 x 16 BDF (Terminus Bold, the Large face) as the menu's table: ASCII from the BDF, the extras from Cozette's 6 x 14
// centred in the bigger cells (a pair's art across 16 px, a single's across 8), one row down.
// The cursor bar is drawn the cell's height. Usage: node mkfont8.js terminus/ter-u16b.bdf out.hex
const fs = require("fs"), { parseBdf } = require("./bdf.js");
const g = parseBdf(process.argv[2], 8, 16, 12);
const coz = fs.readFileSync(__dirname + "/font6x14.hex", "utf8").trim();
const cozRow = (i, r) => parseInt(coz.substr((i * 14 + r) * 2, 2), 16);
const PAIRS = [0x88, 0x8a, 0x8d, 0x90, 0x92, 0x96, 0x98, 0x9a, 0x9c, 0x9e, 0xa0, 0xa4, 0xa6, 0xa9, 0xac];
const ICONS = process.argv[4] === "--cozette-icons" ? {} : require("./icons16.js");   /* the icons redrawn for 8 x 16 */
for (const [c, ic] of Object.entries(ICONS)) {
  const w = ic.art[0].length, pair = PAIRS.includes(+c);
  if (ic.art.some(r => r.length !== w) || w > (pair ? 16 : 8) || ic.top + ic.art.length > 16) throw new Error("icon " + (+c).toString(16));
}
let hex = "";
for (let c = 0x20; c < 0x7f; c++) hex += [...g[c]].map(b => b.toString(16).padStart(2, "0")).join("");
const EXTRAS = coz.length / 28 - 95;   /* Small's extras, whose codes Large shares */
for (let k = 0; k < EXTRAS; k++) {
  const code = 0x80 + k, i = 95 + k, rows = new Uint8Array(16);
  const left = PAIRS.includes(code), right = PAIRS.includes(code - 1);
  const ic = ICONS[left ? code : right ? code - 1 : code];
  if (ic) {   /* redrawn: a pair's columns 0-7 in its first code, 8-15 in its second */
    ic.art.forEach((line, r) => {
      let b = 0;
      for (let x = 0; x < 8; x++) if (line[(right ? 8 : 0) + x] === "#") b |= 0x80 >> x;
      rows[ic.top + r] = b;
    });
  } else for (let r = 0; r < 14; r++) {
    const b = cozRow(i, r) & 0xFC;
    rows[r + 1] = code === 0x87 ? 0 : left ? b >> 2 : right ? b : b >> 1;
  }
  if (code === 0x87) for (let r = 0; r < 15; r++) rows[r] = 0x80;   /* the cursor: the bar, the cell's height less a row */
  hex += [...rows].map(b => b.toString(16).padStart(2, "0")).join("");
}
fs.writeFileSync(process.argv[3], hex);
console.log(process.argv[3], hex.length / 32, "glyphs");
