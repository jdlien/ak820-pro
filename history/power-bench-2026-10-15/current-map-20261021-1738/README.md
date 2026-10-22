# Every knob from one floor (17:38-20:28 10-21)

`scripts/current_map.py --set knobs` on `36afff30e8` (dev, token
`0xef38330e`), BT, relay 2 off (the pack, VCELL 4.04 falling to 4.02 V), USB
data attached, in Balanced with the active stage held (op 14 sub 2, nothing
persisted). 56 states, each held 90 s with the first 15 skipped, run forward
and then backward:

- five dark references (RGB off, screen off), at the start, between the
  families and at the end;
- value 0 (solid colour, nothing lit);
- white at 11 values from 1 to 255; red, green and blue alone at 8 each;
- the screen alone at 7 levels;
- three held-out colours (purple, hue 0 at saturation 128, hue 43);
- three with the RGB and the screen on together;
- Cycle All at 255 and 128.

The RGB states have the screen off and the screen states the RGB off, so
every knob is measured from the same floor. Raw: `steps.csv`, `summary.txt`,
and `results.json` (full precision: each hold's setting as read back, its
charge-register current and VCELL, the LED drive and the board's own
modelled draw). `scripts/power_model.py` reads `results.json` for the power
page.

**Every lit state is within 1% of the board's model** (each state the mean
of its two passes). Red, green, blue, the held-out colours and the combined
states are within 0.53%. White reads up to 0.99% above the model at values
16-128 and about 0.2% above at 192-255 (300.2 mW at 255 against 299.6).

**With nothing lit the board reads above the model.** The five dark states
drew 115.0 to 116.1 mW against 114.0 (`P_BASE` 106.9 + `P_USB` 7.1), a mean
of 115.6, +1.4%. On the same floor, the screen states read up to 1.4% over
in total, but each level's own cost is within 0.31 mW of the model's. Value
0 draws what dark does, so `P_RGB_A` applies only to a lit LED, as modelled.

Measured from the dark mean, the first lit drive (value 1) costs about 7 mW
against the model's ~8.9 (`P_RGB_A` 8.64). So the base is ~1.5 mW light and
the lit step ~1.5-2 mW heavy, and the two cancel in every lit state.
`rgb_fit.py` fitted A against the model's base on purpose for that reason
(`../rgb-curve-20261019/`). The offset has moved between maps:
- 10-15: within 0.03% (older firmware);
- 10-19: +0.9 mW;
- today: +1.6 mW.

**Cycle All matches the model averaged over every hue** at saturation 255:
211.0 and 139.5 mW against 211.1 and 139.2, within 0.2%.

**Noise:** red at 192-255 and Cycle All at 255 have per-second SDs of
1.7-3.6 mA, against 0.1-0.7 elsewhere. Their two passes still agree within
0.3 mA. Two other things showed up only in single passes:
- The screen family's backward pass (19:15-19:30) read ~0.4 mA above its
  forward one at every level (0.25-0.6 mA), with the SD up from ~0.1 to
  ~0.7 mA. That is background load; the two-pass mean carries half of it.
- The run's first hold (dark 1, forward) read 117.5 mW, against 114.6 on its
  return.
