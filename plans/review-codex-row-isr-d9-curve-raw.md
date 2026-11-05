**Neither table is ready to ship unchanged.** The generation and rendering arithmetic pass; the release problem is the inconsistent brightness scale and the consumers still calibrated to the old curve.

H = `9157b1599c` (`--hybrid 2`); S = `7221cb6080` (`--stops 4`). Widths below are mean ticks at **K=300**, unless stated otherwise. Comparisons with the old curve use QMK’s actual byte table through the same row ISR. No builds or file changes.

**P1 — must fix**

| Applies | File:line | Finding and concrete failing scenario |
|---|---|---|
| Both | [power.c:191](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:191), [rowisr.c:1754](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1754) | **The global brightness control changes meaning across enabled effects.** At 50%, `v=128`, Solid white drives **41 ticks H / 43 S** per channel. Switch to Rainfall at the same value and saturation: a freshly seeded drop drives **225 ticks**, **5.49× / 5.23×** brighter per channel. The effect picker previews this change without changing brightness. This is a peak-pixel comparison, not a claim that sparse Rainfall draws five times the whole-board power. |

The mode transition itself is correctly handled: the setter restarts rendering, the effect change forces initialization, and the flush detects the changed encoding. The jump is the final intended calculation, not stale chroma interpreted as bytes. See [rgb_matrix.c:330](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/rgb_matrix.c:330) and [rgb_matrix_kb.inc:63](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb_matrix_kb.inc:63).

**P2 — should fix**

| Applies | File:line | Finding and concrete failing scenario |
|---|---|---|
| Both | [power.c:60](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:60), [power.c:77](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:77) | **The automatic caps retain old light assumptions.** Power saver—or battery level ≤15%—caps a bright wide effect at `128`: **225 → 41 / 43 ticks**, approximately **82% / 81% less light than the old ceiling**. Idle dim at `64` becomes **56 → 7.5 / 8 ticks**, approximately **87% / 86% less**. The protection still works, but its intended typing/dim brightness has changed substantially. |
| Both | [profiles.c:429](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/profiles.c:429), [keyboard.json:52](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/keyboard.json:52) | **Resolve the upgrade/default brightness change explicitly.** A pre-D9 purple profile at `v=125` changes from **(61,28,211)** to **(11.5,5.25,38) H / (12,5.5,39) S**. The actual default is **h36/s64/v191**, not the older documented v64: its widths change from **(577,553,427)** to **(219,210,163) / (223,214,166)**, about **62% / 61% less summed drive**. Records remain intact; this is a compatibility change, not profile corruption. |
| Both; particularly S | [config.h:135](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/config.h:135), [rgb_matrix.c:745](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/rgb_matrix/rgb_matrix.c:745) | **The keys do not use the menu’s percent stops.** `RGB_MATRIX_VAL_STEP=2` traverses raw values. With S, successive increases from zero reach `v=2` and `v=4`: the overlay changes **1% → 2%**, but both drive **0.5 tick** on a full channel. `v=10→12` likewise displays **4%→5%** with no width change. H also has raw-step plateaus, e.g. `14→16` remains 2 ticks. Align the keys with percent stepping if that is the release’s control contract. |

For the caps, preserving the former full-channel light would put Saver near **192 H / 191 S**, and dim near **139–140 H / 138–139 S**. With the current split paths, these must be **mode-aware**: raising the shared constants would brighten byte effects substantially.

The idle timings themselves are unchanged: Balanced dims/sleeps at 10/20 minutes; Saver at 1/3 minutes; Lights out sleeps after one minute. Caps still leave saved settings untouched, and changes reinitialize sparse effects. These are brightness-policy regressions, not failures of the ladder machinery. See [power.c:62](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:62).

**P3 — arithmetic and claim corrections**

| Applies | File:line | Scenario checked / result |
|---|---|---|
| Both | [gen_curve12.py:48](/Users/jdlien/code/ak820-pro/scripts/gen_curve12.py:48), [menu.c:2416](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu.c:2416) | **Both generated headers reproduce their commits byte-for-byte.** Checked every percentage 0–100: `pct_of(val_of_pct(p)) == p`. S’s canonical stops 1–15 produce exactly **0.5, 0.75, …, 4 ticks**. The remaining stops follow its generated geometric segment and firmware rounding. |
| S | [gen_curve12.py:27](/Users/jdlien/code/ak820-pro/scripts/gen_curve12.py:27), [curve_steps.py:27](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/curve_steps.py:27) | **“No full-channel repeat” is false, but the tool reports the exception correctly.** **36% (`v92`) and 37% (`v94`) both produce 17 ticks**: their pre-rounding targets are approximately 16.551 and 17.430. Solid white or a saturated primary therefore has a completely flat detent. Purple changes its weaker channels, so its “no channel moves: none” result remains correct. |
| H | [curve_steps.py:22](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/curve_steps.py:22) | The exhaustive percent scan confirms precisely the advertised full-channel/purple flat stops: **6, 8, 13**. No additional reference-scale exception was hidden by the report’s abbreviated printed rows. |
| Both | [curve_steps.py:14](/Users/jdlien/code/ak820-pro/history/rowisr-stage1-20261101/curve_steps.py:14), [rowisr.c:1716](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1716) | **The reciprocal and width arithmetic match exactly.** `curve_steps.py` returns the encoded width’s four-field **mean**, not its packed integer representation; its `q=4` result correctly represents the carry. Checked all **393,216** table/chroma/value/scale combinations across both tables and K=300/640/64. Both exhaustive checkers pass. |
| Both | [color.c:56](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/quantum/color.c:56), [check_curve12.py:46](/Users/jdlien/code/ak820-pro/scripts/check_curve12.py:46) | **(77,35,255) is correct** for h178/s219 at full value. The checker’s **36** is wrong. For example, its devprobe “all purple channels lit” boundary is reported as **v41 H / v39 S**, whereas the actual colour requires **v43 / v40**. The exhaustive arithmetic checks remain valid because they cover every chroma. |
| Both | [ROW-ISR-PLAN.md:1145](/Users/jdlien/code/ak820-pro/plans/ROW-ISR-PLAN.md:1145) | “Differs only below about 16%” is approximate, not literal: at 25%, H/S are **7.5/8 ticks**; at 50%, **41/43**. Both converge to the same top. |

At K=640, neither table repeats a full-channel width between canonical percent stops. Devprobe has additional plateaus; the reference-scale guarantee does not transfer to K=64.

**P3 — low values, sleep, and accounting**

At **1% (`v=3`)**, this applies to **Jellybean and all three Cycles**:

| Scale | H: strongest channel | S: strongest channel | Can an included LED’s entire committed colour round to zero? | Entire dark fields within the four-field pattern |
|---|---:|---:|---|---|
| K=300 | 0.75 | 0.5 | No, either table | H: 1 of 4; S: 2 of 4 |
| K=640 | 1.5 | 1 | No, either table | None |
| K=64 | 0.25 | 0 | H: no; S: **yes, every LED and the entire frame** | H: 3 of 4; S: all |

This is independent of their hue choices: QMK’s full-value HSV conversion always supplies at least one channel equal to 255. Thus, absent flags excluding LEDs or a power-off scale, **no complete HSV-rendered LED rounds permanently dark at any nonzero value on K=300 or K=640**. Individual channels certainly do: purple at 1% is **(¼,0,¾) H / (¼,0,½) S** at K=300.

On devprobe, whole-colour darkness covers **v1–2 H / v1–4 S**. Raw diagnostic patterns retain their byte-to-tick bypass.

| Applies | File:line | Concrete scenario / consequence |
|---|---|---|
| Both | [rowisr.c:1698](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1698), [sleep.c:278](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:278) | **Committed darkness is correct.** A patterned width remains committed-lit during its intentionally dark fields. S at devprobe 1% commits all zeros and is genuinely committed-dark. Neither causes premature sleep: sleep also requires `power_rgb_dark()`, the ladder’s applied off scale, plus its normal sleep conditions. |
| Both | [rowisr.c:1458](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1458), [sleep.c:758](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/sleep.c:758) | **No wake deadlock.** Wake restarts scanning with the retained dark frame; input restarts the ladder and `power_task()` restores caps and reinitializes the effect. Jellybean therefore repaints all included LEDs. Recovery does not wait for RGB light. S/devprobe/1% remains dark after waking because of quantization; increasing brightness restores it. |
| Both | [rowisr.c:1383](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1383), [rowisr.c:1687](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rgb/rowisr.c:1687), [battery.c:678](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/battery.c:678) | **Drive accounting follows emitted ticks, not the old curve.** Dark fields add no drive and no omission; devprobe still divides by the cadence’s reference K=300, correctly retaining its reduced output. An entirely rounded-dark frame accrues no RGB intercept. Patterned frames retain the previously reviewed continuous `lit_ms`/8.64 mW intercept bias. No new accounting defect. |
| Both | [battery.c:1263](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/battery.c:1263), [power.c:137](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/power.c:137) | **The RGB cut is independent of RGB value.** The 3400 mV/30-second condition and three critical-zero reports still force scale zero, repaint, and extinguish both paths. RGB toggles cannot bypass it. The ≤15% threshold concerns battery level, not the lighting value. |
| Both | [flash_tidy.c:45](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/flash_tidy.c:45), [rtc.c:1641](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/rtc/rtc.c:1641) | Rounded-dark devprobe frames permit the existing dark-frame flash-cleanup/clock-write opportunities. Patterned frames do not. Those decisions agree with committed output; no defect found. |
| Both | [menu_edit.c:65](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/menu_edit.c:65), [profiles.c:454](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro-rowisr/keyboards/a_jazz/ak820pro/menu/profiles.c:454) | Menu previews and cancellation preserve numeric settings correctly and therefore inherit the brightness changes above. The hue strip uses full-value colour, not a brightness prediction. There is no separate stale preview curve. |

The battery model needs no replacement lookup table: for sustained full white at `v128`, its RGB contribution changes from approximately **41.95 mW to 14.71 H / 15.01 S**, following the emitted drive. Those are model outputs, not new measurements.

The plan’s **“about 5× at 50%” claim is correct for full-intensity byte-path samples**, with qualifications: Breathing is disabled, and Drift scales its palette linearly after conversion. “Byte path” does not mean every enabled effect uses the same global CIE response.

**“A shared table costs its bottom third” is too imprecise.** For a straightforward rounded byte table, `round(curve_q6[v]/64)`, the first nonzero byte occurs at **v20 H / v23 S**—canonical **8% / 9%**, not 33%. Truncation moves that to **v46 / v44**. However, stops 0–33% collapse to only **four byte outputs: 0,1,2,3**. The resolution and hue loss are real; an entirely dead bottom third is not.

The smallest release fix I would accept while retaining either candidate is **common final brightness scaling**: render Rainfall/Heatmap’s local modulation and Drift’s palette at full global brightness, then apply the selected global curve and cap once in the wide flush. Preserve the raw-pattern bypass. That avoids quantizing global brightness into a byte and does not require another per-LED buffer, although the effects’ fade response must be reviewed. Retune the automatic caps and explicitly settle the default/profile compatibility change alongside it.

NOT READY