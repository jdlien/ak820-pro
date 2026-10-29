// Inlines core.js, the font table and the atlases into page.html. Usage: node build.js out.html
const fs = require("fs"), path = require("path"), d = __dirname, r = f => fs.readFileSync(path.join(d, f), "utf8").trim();
let html = r("page.html");
const put = (key, val) => { if (!html.includes(key)) throw new Error("no " + key); html = html.split(key).join(val); };
put("/*CORE*/", r("core.js"));
put("__F_C6__", r("font6x14.hex"));
put("__F_TERMB__", r("f-termb.hex"));
put("__F_TERM__", r("f-term.hex"));
put("__I_COZ16__", r("icons-cozette16.hex"));
put("__I12__", r("icons12.hex"));
put("__F20__", r("f20.uri"));
put("__F30__", r("f30.uri"));
fs.writeFileSync(process.argv[2], html + "\n");
console.log("wrote", process.argv[2], html.length, "bytes");
