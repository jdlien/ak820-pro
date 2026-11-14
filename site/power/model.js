// The power page's maths (plans/POWER-CHARTS-PLAN.md). No DOM: index.html and
// model.test.js run this same code. `fw` is power.json's "firmware" block, read
// by scripts/power_model.py from the commit deps.lock pins, and `ev` its
// "evidence" block; nothing here restates a firmware number but the wide
// path's frame encoding (wideWidth), which the oracle holds to the C exactly.
//
// A setting is { rgb: { on, h, s, v }, screen: { on, level }, radio: "bt" | "g24" };
// a mode is power.c's: "full" (Always on), "normal" (Balanced), "saver"
// (Power saver), "minimal" (Lights out).

export const MODES = [
  ["full", "Always on"],
  ["normal", "Balanced"],
  ["saver", "Power saver"],
  ["minimal", "Lights out"],
];

// power.c's stages, in their order: a larger one is darker.
export const STAGE = { ACTIVE: 0, DIM: 1, LIGHTS_OFF: 2, SCREEN_OFF: 3, SLEEP: 4 };

// QMK's hsv_to_rgb_impl (quantum/color.c) with the CIE curve, which applies to
// the value before the colour is mixed, in its integer arithmetic: remainder
// wraps as a uint8_t and p, q, t shift right by 8.
export function hsvToRgb(fw, h, s, v) {
  const cv = fw.cie1931[v];
  if (s === 0) return [cv, cv, cv];
  const region = Math.floor((h * 6) / 255);
  const remainder = ((h * 2 - region * 85) * 3) & 0xff;
  const p = (cv * (255 - s)) >> 8;
  const q = (cv * (255 - ((s * remainder) >> 8))) >> 8;
  const t = (cv * (255 - ((s * (255 - remainder)) >> 8))) >> 8;
  switch (region) {
    case 6:
    case 0: return [cv, t, p];
    case 1: return [q, cv, p];
    case 2: return [p, cv, t];
    case 3: return [p, q, cv];
    case 4: return [t, p, cv];
    default: return [cv, p, q];
  }
}

// D9's flush (rgb/rowisr.c, since v0.4.0): the curve at the value in Q8
// ticks at full chroma, and its 1/255 in Q8, in the flush's integer arithmetic.
export function wideRecip(fw, v) {
  const fullQ8 = Math.floor((fw.curve_q6[v] * fw.rowisr_k_q6) / 16);
  return Math.floor((fullQ8 * 256 + 127) / 255);
}

// wide_width(): a chroma byte's frame entry. From 16 ticks the width rounded;
// under it the fraction kept to a quarter as a four-field dither, bit 15 set,
// the fields lit a tick more in bits 11-14 and the base in bits 0-10.
export function wideWidth(c, recip) {
  const q8 = Math.floor((c * recip + 128) / 256);
  let w = Math.floor(q8 / 256);
  const frac = q8 % 256;
  if (w >= 16) return w + (frac >= 128 ? 1 : 0);
  let quarters = Math.floor((frac + 32) / 64);
  if (quarters === 4) { w++; quarters = 0; }
  if (quarters === 0) return w;
  return 0x8000 | ([0, 1, 5, 7][quarters] << 11) | w;
}

// An entry's mean width in ticks: the handler drives a dithered entry's base
// plus one tick in each field its pattern names, over the four fields.
export function entryTicks(e) {
  if (!(e & 0x8000)) return e;
  let n = 0;
  for (let p = (e >> 11) & 0xf; p; p >>= 1) n += p & 1;
  return (e & 0x7ff) + n / 4;
}

// The drive the firmware counts from what was emitted
// (sn32f2xx_led_drive_take): ticks x 64 / k_ref, the light in bytes at the
// reference scale, so the model's per-unit costs keep their meaning.
export function wideDrive(fw, chroma, v) {
  const recip = wideRecip(fw, v);
  return chroma.map((c) => (entryTicks(wideWidth(c, recip)) * 64) / fw.rowisr_k_ref_q6);
}

// One LED's drive under the stage's value ceiling `vcap`. Since D9 (v0.4.0,
// fw.rgb_path "wide") a Solid colour renders its chroma at full value
// (power.c's rgb_matrix_hsv_to_rgb) and the flush applies the value, capped,
// through the firmware's own curve; before it the cap came first and
// hsv_to_rgb's CIE curve made bytes, each its drive. A state measured on an
// older firmware carries the drive it ran at (`rgb.drive`). Solid colour
// lights every LED alike.
export function rgbDrive(fw, rgb, vcap = 255) {
  if (!rgb.on) return [0, 0, 0];
  if (rgb.drive) return rgb.drive;
  const v = Math.min(rgb.v, vcap);
  if (fw.rgb_path !== "wide") return hsvToRgb(fw, rgb.h, rgb.s, v);
  return wideDrive(fw, hsvToRgb(fw, rgb.h, rgb.s, 255), v);
}

// Where a drive sits on today's curve for a colour: the fractional value whose
// drive matches its channels' sum, linear between whole values.
export function valueForDrive(fw, h, s, drive) {
  const sum = (d) => d[0] + d[1] + d[2];
  const want = sum(drive);
  let dlo = 0;
  for (let v = 1; v <= 255; v++) {
    const d = sum(rgbDrive(fw, { on: true, h, s, v }));
    if (d >= want) return d === dlo ? v : v - 1 + (want - dlo) / (d - dlo);
    dlo = d;
  }
  return 255;
}

// A knobs state's lighting as it ran. The sweep's firmware drew a Solid colour
// on the byte path (ev's rgb_path), QMK's hsv_to_rgb with the CIE curve, each
// byte its drive; on a firmware since D9 the same setting is another light, so
// the state keeps that drive.
export function sweepRgb(fw, sweep, l) {
  if (l.effect === 0) return { on: false };
  const rgb = { on: true, h: l.h, s: l.s, v: l.v };
  if (sweep.rgb_path === "byte" && fw.rgb_path === "wide") rgb.drive = hsvToRgb(fw, l.h, l.s, l.v);
  return rgb;
}

// display.c's effective duty: off is 0, and a stage's ceiling caps the level.
// A measured state carries the duty it ran at (`duty`, in ticks): a sweep on
// the old 24-level Screen ran at duties not every one of today's levels has.
export function backlightDuty(fw, screen, levelCap = Infinity) {
  if (!screen.on) return 0;
  if (screen.duty !== undefined && screen.duty !== null) return screen.duty;
  return fw.backlight_duty[Math.min(screen.level, levelCap)];
}

// The `LCD nn%` readout (param_overlay.c): the level index, rounded.
export function lcdPercent(fw, level) {
  const mx = fw.backlight_duty.length - 1;
  return Math.floor((level * 100 + Math.floor(mx / 2)) / mx);
}

// battery.c's model_nj in its integer arithmetic: the energy over `dt` ms in
// nJ (uW x ms), from each colour's drive x ms, the lit ms, the duty and USB.
export function modelNj(fw, dt, rgbMs, litMs, duty, usb) {
  let uw = fw.p_base_uw + Math.floor((fw.p_bkl_full_uw * duty) / fw.bkl_duty_full);
  if (usb) uw += fw.p_usb_uw;
  const [br, bg, bb] = fw.p_rgb_nw;
  return uw * dt + fw.p_rgb_a_uw * Math.min(litMs, dt) +
    Math.floor((rgbMs[0] * br + rgbMs[1] * bg + rgbMs[2] * bb) / 1000);
}

// The board's modelled draw, mW: one second of model_nj, untethered unless
// `usb`. `vcap` is the value ceiling, `lights` false for a stage that turns
// the RGB off, `levelCap` the backlight's ceiling.
export function boardMw(fw, setting, { vcap = 255, lights = true, levelCap = Infinity, usb = false } = {}) {
  const ch = lights ? rgbDrive(fw, setting.rgb, vcap) : [0, 0, 0];
  const sums = ch.map((c) => c * fw.led_count * 1000);
  const lit = sums.some((x) => x > 0) ? 1000 : 0;
  return modelNj(fw, 1000, sums, lit, backlightDuty(fw, setting.screen, levelCap), usb) / 1e6;
}

// Beyond the board's model, labelled on the page: 2.4G's awake extra and the
// measured sleep per radio (the firmware counts one sleep figure for both).
export function radioExtraMw(ev, radio) {
  return radio === "g24" ? ev.radio_24g_awake_extra_mw.value : 0;
}
export function sleepMw(ev, radio) {
  return ev.sleep_mw[radio];
}

// power.c's stage_for: the stage the idle time asks for under one ladder.
export function stageFor(l, idleMs) {
  if (l.screen_off_ms !== null && idleMs >= l.screen_off_ms) return STAGE.SCREEN_OFF;
  if (l.lights_off_ms !== null && idleMs >= l.lights_off_ms) return STAGE.LIGHTS_OFF;
  if (l.dim_ms !== null && idleMs >= l.dim_ms) return STAGE.DIM;
  return STAGE.ACTIVE;
}

// On battery, `idleMs` into a pause (0 while typing): power_task's battery
// branch and power_sleep_wanted. At or below LOW_CAP_PM (`low`) every mode
// takes the darker of its own stage and Power saver's, and the typing ceiling
// drops to SAVER_VAL; Always on never sleeps, at any level.
export function stateAt(fw, mode, low, idleMs) {
  const L = fw.ladders;
  let stage = stageFor(L[mode], idleMs);
  let vcap = L[mode].active_val;
  let sleep = mode === "full" ? null : L[mode].sleep_ms;
  if (low) {
    stage = Math.max(stage, stageFor(L.saver, idleMs));
    vcap = Math.min(vcap, fw.saver_val);
    if (sleep !== null && L.saver.sleep_ms < sleep) sleep = L.saver.sleep_ms;
  }
  if (sleep !== null && idleMs >= sleep) return { stage: STAGE.SLEEP, vcap: 0 };
  return { stage, vcap };
}

// The draw in a state, mW, untethered: power.c's apply() for each stage.
export function stateMw(fw, ev, setting, st) {
  if (st.stage === STAGE.SLEEP) return sleepMw(ev, setting.radio);
  const extra = radioExtraMw(ev, setting.radio);
  switch (st.stage) {
    case STAGE.ACTIVE: return boardMw(fw, setting, { vcap: st.vcap }) + extra;
    case STAGE.DIM: return boardMw(fw, setting, { vcap: fw.dim_val }) + extra;
    case STAGE.LIGHTS_OFF: return boardMw(fw, setting, { lights: false, levelCap: fw.screen_dim_level }) + extra;
    default: return boardMw(fw, setting, { lights: false, levelCap: 0 }) + extra;
  }
}

// Typing nonstop from full: the energy above the low cap at the setting's
// draw, the tail at the capped draw. `f` is the tail's share of the energy, a
// stated assumption (the gauge does not guarantee 150 permille is 15%).
export function continuousUse(fw, ev, setting, mode, f) {
  const E = fw.e_cap_mwh;
  const hiMw = stateMw(fw, ev, setting, stateAt(fw, mode, false, 0));
  const loMw = stateMw(fw, ev, setting, stateAt(fw, mode, true, 0));
  const hiHours = ((1 - f) * E) / hiMw;
  const loHours = (f * E) / loMw;
  return { hiMw, loMw, hiHours, loHours, hours: hiHours + loHours, fixedHours: E / hiMw, dims: loMw < hiMw - 1e-9 };
}

// Left alone from full: asleep at the measured draw, or for Always on, lit
// until the low cap and then awake and dark, since it never sleeps.
export function standby(fw, ev, setting, mode, f) {
  const E = fw.e_cap_mwh;
  if (mode !== "full") return { hours: E / sleepMw(ev, setting.radio), asleep: true };
  const hi = stateMw(fw, ev, setting, stateAt(fw, mode, false, Infinity));
  const lo = stateMw(fw, ev, setting, stateAt(fw, mode, true, Infinity));
  return { hours: ((1 - f) * E) / hi + (f * E) / lo, asleep: false };
}

// One pause of `minutes`, walking the ladder: mWh.
export function pauseMwh(fw, ev, setting, mode, low, minutes) {
  const end = minutes * 60000;
  const cuts = new Set([0, end]);
  const ladders = low ? [fw.ladders[mode], fw.ladders.saver] : [fw.ladders[mode]];
  for (const l of ladders)
    for (const k of ["dim_ms", "lights_off_ms", "screen_off_ms", "sleep_ms"])
      if (l[k] !== null && l[k] > 0 && l[k] < end) cuts.add(l[k]);
  const pts = [...cuts].sort((a, b) => a - b);
  let mwh = 0;
  for (let i = 0; i + 1 < pts.length; i++)
    mwh += (stateMw(fw, ev, setting, stateAt(fw, mode, low, pts[i])) * (pts[i + 1] - pts[i])) / 3.6e6;
  return mwh;
}

// A day as [kind, minutes] segments, every minute counted once: the
// scenario's typing and pauses, then the rest of the 24 hours away.
export function dayPlan(sc) {
  const segs = [];
  if (sc.repeat)
    for (let i = 0; i < sc.repeat.count; i++) segs.push(["type", sc.repeat.type], ["pause", sc.repeat.pause]);
  for (const [k, m] of sc.blocks) if (m > 0) segs.push([k, m]);
  const used = segs.reduce((a, [, m]) => a + m, 0);
  if (used > 1440) throw new Error(`${sc.id}: ${used} minutes is more than a day`);
  if (used < 1440) segs.push(["pause", 1440 - used]);
  return segs;
}

export function dayMwh(fw, ev, setting, mode, low, segs) {
  let mwh = 0;
  for (const [k, m] of segs)
    mwh += k === "type"
      ? (stateMw(fw, ev, setting, stateAt(fw, mode, low, 0)) * m) / 60
      : pauseMwh(fw, ev, setting, mode, low, m);
  return mwh;
}

export function daysPerCharge(fw, ev, setting, mode, segs, f) {
  const E = fw.e_cap_mwh;
  const hi = dayMwh(fw, ev, setting, mode, false, segs);
  const lo = dayMwh(fw, ev, setting, mode, true, segs);
  return { days: ((1 - f) * E) / hi + (f * E) / lo, hiMwh: hi, loMwh: lo };
}

// The chart's curves, each knob alone ("other lighting off"), awake and
// active, untethered: every RGB value for a colour, every screen level.
export function rgbCurve(fw, ev, h, s, radio = "bt") {
  const pts = [];
  for (let v = 0; v <= 255; v++) {
    const setting = { rgb: { on: true, h, s, v }, screen: { on: false, level: 0 }, radio };
    pts.push({ v, x: (v * 100) / 255, mw: boardMw(fw, setting) + radioExtraMw(ev, radio) });
  }
  return pts;
}

export function screenCurve(fw, ev, radio = "bt") {
  return fw.backlight_duty.map((_, level) => {
    const setting = { rgb: { on: false, h: 0, s: 0, v: 0 }, screen: { on: true, level }, radio };
    return { level, x: lcdPercent(fw, level), mw: boardMw(fw, setting) + radioExtraMw(ev, radio) };
  });
}

// The knobs sweep's measured points, as each knob's increment over the dark
// states' mean (RGB off, screen off), drawn on the model's floor: the bench's
// USB data and the reversal's drift cancel in the difference. A lit state's
// `x` is where today's curve gives the light it ran at, its `v` the value read
// back then.
export function measuredPoints(fw, ev, radio = "bt") {
  const floor = boardMw(fw, { rgb: { on: false }, screen: { on: false, level: 0 } }) + radioExtraMw(ev, radio);
  const rows = ev.knobs_sweep.rows;
  const darks = rows.filter((r) => r.family === "dark");
  const dark = darks.reduce((a, r) => a + r.mw, 0) / darks.length;
  // Each lit state at the light it ran at, placed where today's curve gives it.
  const rgb = rows.filter((r) => ["white", "red", "green", "blue"].includes(r.family)).map((r) => {
    const l = r.lighting, sr = sweepRgb(fw, ev.knobs_sweep, l);
    const v = sr.drive ? valueForDrive(fw, l.h, l.s, sr.drive) : l.v;
    return { colour: r.family, v: l.v, drive: sr.drive ?? null, x: (v * 100) / 255, mw: floor + r.mw - dark, name: r.name };
  });
  const screen = rows.filter((r) => r.family === "screen").map((r) => ({
    level: r.screen_level, duty: r.screen_duty, x: r.screen_x ?? lcdPercent(fw, r.screen_level),
    mw: floor + r.mw - dark, name: r.name,
  }));
  return { rgb, screen, floor };
}

// The model against each knobs state as it was measured (on the pack, USB
// data attached), from the setting the hold read back: the fractional error
// per state. Animated effects are not modelled, so they are left out.
export function sweepAgreement(fw, ev) {
  return ev.knobs_sweep.rows.filter((r) => r.family !== "animated").map((r) => {
    const l = r.lighting;
    const setting = {
      rgb: sweepRgb(fw, ev.knobs_sweep, l),
      screen: r.screen_level === null ? { on: false, level: 0 } : { on: true, level: r.screen_level, duty: r.screen_duty },
    };
    const model = boardMw(fw, setting, { usb: true });
    const passErr = Math.max(...r.passes.map((x) => Math.abs(model / x - 1)));
    return { name: r.name, family: r.family, lighting: l, measured: r.mw, model, err: model / r.mw - 1, passErr };
  });
}
