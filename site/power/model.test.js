// model.js against the firmware it describes (node --test site/power/).
//
// Exact: the pinned C (scripts/power_oracle.c via power_model.py --oracle),
// for hsv_to_rgb with the CIE curve over every hue and value at ten
// saturations, and for model_nj over ~1,000 cases. Set POWER_ORACLE_DIR to
// reuse fixtures; otherwise they are built here (needs cc and git).
// Checked: the figures plans/POWER-CHARTS-PLAN.md and docs/power.md state,
// the firmware's rules at the edges, and the model against the bench sweeps.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as M from "./model.js";

const here = dirname(fileURLToPath(import.meta.url));
const doc = JSON.parse(readFileSync(join(here, "power.json"), "utf8"));
const fw = doc.firmware;
const ev = doc.evidence;
const F = doc.assumptions.tail_fraction.value;

let oracleDir = process.env.POWER_ORACLE_DIR;
if (!oracleDir) {
  oracleDir = mkdtempSync(join(tmpdir(), "power-oracle-"));
  execFileSync("python3", [join(here, "..", "..", "scripts", "power_model.py"), "--oracle", oracleDir], { stdio: "inherit" });
}

const SATS = [0, 1, 2, 64, 127, 128, 129, 200, 254, 255]; // power_oracle.c's list
const near = (got, want, tol, what) =>
  assert.ok(Math.abs(got - want) <= tol, `${what}: ${got.toFixed(3)}, expected ${want} +/- ${tol}`);

const setting = (v, level, { h = 0, s = 0, rgbOn = true, screenOn = true, radio = "bt" } = {}) =>
  ({ rgb: { on: rgbOn, h, s, v }, screen: { on: screenOn, level }, radio });

test("the oracle is the pinned firmware's", () => {
  const m = JSON.parse(readFileSync(join(oracleDir, "model.json"), "utf8"));
  assert.equal(m.sha, fw.sha);
});

test("hsv_to_rgb with the CIE curve: every hue and value at ten saturations, exactly", () => {
  const b = readFileSync(join(oracleDir, "hsv.bin"));
  assert.equal(b.length, SATS.length * 256 * 256 * 3);
  let i = 0, bad = 0, first = "";
  for (const s of SATS)
    for (let h = 0; h < 256; h++)
      for (let v = 0; v < 256; v++, i += 3) {
        const [r, g, bl] = M.hsvToRgb(fw, h, s, v);
        if (r !== b[i] || g !== b[i + 1] || bl !== b[i + 2]) {
          if (!bad++) first = `h ${h} s ${s} v ${v}: ${[r, g, bl]} vs ${[b[i], b[i + 1], b[i + 2]]}`;
        }
      }
  assert.equal(bad, 0, `${bad} mismatches, first ${first}`);
});

test("model_nj: every oracle case, exactly", () => {
  const { cases } = JSON.parse(readFileSync(join(oracleDir, "model.json"), "utf8"));
  assert.ok(cases.length > 900);
  for (const c of cases)
    assert.equal(M.modelNj(fw, c.dt, c.rgb_ms, c.lit_ms, c.duty, c.usb), c.nj, JSON.stringify(c));
});

test("the firmware facts the page leans on", () => {
  assert.equal(fw.led_count, 81);
  assert.equal(fw.backlight_duty.length, 24);
  assert.deepEqual([fw.cie1931[64], fw.cie1931[128], fw.cie1931[255]], [12, 48, 255]);
  assert.equal(M.lcdPercent(fw, 5), 22);
  assert.equal(M.lcdPercent(fw, 23), 100);
  assert.equal(fw.ladders.full.sleep_ms, null);
});

test("draws the plan states (untethered, BT)", () => {
  near(M.boardMw(fw, setting(255, 5)), 296.584, 0.001, "full white, screen 5");
  near(M.boardMw(fw, setting(128, 5)), 152.93, 0.01, "white 128, screen 5");
  near(M.boardMw(fw, setting(255, 5), { usb: true }), 303.684, 0.001, "full white, screen 5, the bench's USB");
  near(M.boardMw(fw, setting(0, 0, { rgbOn: false, screenOn: false })), 106.9, 1e-9, "every light off");
  // Value 0 lights no LED, so the RGB's fixed cost does not apply; value 1 does.
  near(M.boardMw(fw, setting(0, 0, { screenOn: false })), 106.9, 1e-9, "value 0");
  assert.ok(M.boardMw(fw, setting(1, 0, { screenOn: false })) - 106.9 > fw.p_rgb_a_uw / 1000 - 1e-9, "value 1");
});

test("fixed-state runtimes reproduce the plan's figures", () => {
  const E = fw.e_cap_mwh;
  near(E / M.boardMw(fw, setting(255, 5)), 52.53, 0.01, "full white, screen 5");
  near(E / M.boardMw(fw, setting(128, 5)), 101.87, 0.01, "white 128");
  near(E / M.boardMw(fw, setting(0, 5, { rgbOn: false })), 140.39, 0.01, "RGB off, screen 5");
  near(E / 106.9, 145.73, 0.01, "every light off");
  const max24 = M.boardMw(fw, setting(255, 23)) + M.radioExtraMw(ev, "g24");
  near(E / max24, 46.28, 0.01, "everything at max, 2.4G");
});

test("continuous use: the 15% tail at value 128, by mode", () => {
  const s = setting(255, 5);
  const bal = M.continuousUse(fw, ev, s, "normal", F);
  near(bal.hiHours, 44.65, 0.01, "Balanced, above the cap");
  near(bal.loHours, 15.28, 0.01, "Balanced, the tail");
  near(bal.hours, 59.93, 0.01, "Balanced, in all");
  assert.ok(bal.dims);
  near(M.continuousUse(fw, ev, s, "full", F).hours, bal.hours, 1e-9, "Always on types as Balanced does");
  const saver = M.continuousUse(fw, ev, s, "saver", F);
  near(saver.hiMw, saver.loMw, 1e-9, "Power saver is capped throughout");
  assert.ok(!saver.dims);
  const lo = M.continuousUse(fw, ev, s, "minimal", F);
  near(lo.hiMw, 106.9, 1e-9, "Lights out types dark, the screen too");
  // A setting already under the cap does not dim.
  assert.ok(!M.continuousUse(fw, ev, setting(100, 5), "normal", F).dims);
  // The sensitivity the plan quotes: one point of the tail's share.
  near(M.continuousUse(fw, ev, s, "normal", 0.14).hours - bal.hours, -0.493, 0.002, "one point of f");
  const max24 = M.continuousUse(fw, ev, setting(255, 23, { radio: "g24" }), "normal", F);
  near(max24.hours, 51.45, 0.01, "everything at max, 2.4G, with the tail");
});

test("the ladder: stages, the low cap's rules, sleep", () => {
  const S = M.STAGE;
  assert.equal(M.stateAt(fw, "normal", false, 0).stage, S.ACTIVE);
  assert.equal(M.stateAt(fw, "normal", false, 599999).stage, S.ACTIVE);
  assert.equal(M.stateAt(fw, "normal", false, 600000).stage, S.DIM);
  assert.equal(M.stateAt(fw, "normal", false, 1200000).stage, S.SLEEP);
  assert.equal(M.stateAt(fw, "normal", true, 60000).stage, S.DIM, "low: Power saver's dim at 1 min");
  assert.equal(M.stateAt(fw, "normal", true, 180000).stage, S.SLEEP, "low: Power saver's sleep at 3 min");
  assert.equal(M.stateAt(fw, "normal", true, 0).vcap, fw.saver_val);
  assert.equal(M.stateAt(fw, "full", false, 1e12).stage, S.ACTIVE, "Always on never dims above the cap");
  assert.equal(M.stateAt(fw, "full", true, 1e12).stage, S.SCREEN_OFF, "Always on goes dark below it");
  assert.notEqual(M.stateAt(fw, "full", true, 1e12).stage, S.SLEEP, "and never sleeps");
  assert.equal(M.stateAt(fw, "minimal", false, 0).stage, S.SCREEN_OFF, "Lights out is dark while typing");
  assert.equal(M.stateAt(fw, "minimal", false, 60000).stage, S.SLEEP);
});

test("pauses and days", () => {
  const s = setting(255, 5);
  const sleep = M.sleepMw(ev, "bt");
  near(M.pauseMwh(fw, ev, s, "normal", false, 20) - (sleep * 20) / 60, 66.3, 0.1, "a Balanced pause, above sleep");
  near(M.pauseMwh(fw, ev, s, "saver", false, 3) - (sleep * 3) / 60, 6.15, 0.02, "a Power saver pause, above sleep");
  for (const sc of doc.scenarios) {
    const segs = M.dayPlan(sc);
    assert.equal(segs.reduce((a, [, m]) => a + m, 0), 1440, `${sc.id} covers the day once`);
    const d = M.daysPerCharge(fw, ev, s, "normal", segs, F);
    assert.ok(d.days > 2 && d.days < 60, `${sc.id}: ${d.days} days`);
  }
  // The office day: 8 h at the draw, then 16 h that walk Balanced's ladder to sleep.
  const draw = M.boardMw(fw, s);
  const office = M.dayMwh(fw, ev, s, "normal", false, M.dayPlan(doc.scenarios.find((x) => x.id === "office")));
  near(office, draw * 8 + M.pauseMwh(fw, ev, s, "normal", false, 960), 1e-6, "office day");
  // Always on's day never sleeps: 24 h at the draw above the cap.
  near(M.dayMwh(fw, ev, s, "full", false, [["type", 480], ["pause", 960]]), draw * 24, 1e-6, "Always on");
});

test("standby", () => {
  const s = setting(255, 5);
  near(M.standby(fw, ev, s, "normal", F).hours / 24, 48.99, 0.01, "asleep on BT");
  near(M.standby(fw, ev, { ...s, radio: "g24" }, "normal", F).hours / 24, 47.04, 0.01, "asleep on 2.4G");
  assert.equal(M.standby(fw, ev, s, "full", F).asleep, false, "Always on stays awake");
});

// The measurement gate, apart from the exact ones above: each knobs state's
// mean over its two passes (2026-10-21). A miss means investigate, not change
// the firmware. The lit states within 1.0% (worst 0.99%, white 32); with no
// LED lit the board reads above the model, the dark floor by up to 1.8%
// (115.0-116.1 mW against 114.0) and the screen alone by up to 1.4%.
test("the model against the bench sweep", () => {
  const rows = M.sweepAgreement(fw, ev);
  assert.ok(rows.length >= 54);
  const tol = { dark: 0.018, screen: 0.014 };
  for (const r of rows) {
    const t = tol[r.family] ?? 0.010;
    assert.ok(Math.abs(r.err) <= t, `${r.name}: model ${r.model.toFixed(1)} vs measured ${r.measured} (${(100 * r.err).toFixed(2)}%)`);
  }
});

// Each knob's increment over the dark states' mean, on the model's curve: the
// screen's within 0.5 mW (worst 0.31), the LEDs' within 3 mW (red at 240-255
// sits 2.5 below, and the first lit drive ~1.9 below: the floor reads high).
test("the measured points sit on the curves", () => {
  const pts = M.measuredPoints(fw, ev);
  const curves = {
    white: M.rgbCurve(fw, ev, 0, 0), red: M.rgbCurve(fw, ev, 0, 255),
    green: M.rgbCurve(fw, ev, 85, 255), blue: M.rgbCurve(fw, ev, 170, 255),
  };
  assert.equal(pts.rgb.length, 36);
  assert.equal(pts.screen.length, 7);
  for (const p of pts.rgb) near(p.mw, curves[p.colour][p.v].mw, 3.0, p.name);
  const sc = M.screenCurve(fw, ev);
  for (const p of pts.screen) near(p.mw, sc[p.level].mw, 0.5, p.name);
});
