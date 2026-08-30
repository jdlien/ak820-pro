# Shipped atlases and blob

These are the assets **currently provisioned on the board** — copies, kept here
because the originals live in `time-util-ak820pro/assets/`, which is a pristine
upstream clone with uncommitted working-tree changes. A `git checkout` there
silently destroys them, and there is no way to read assets back off the board.

Blob CRC on device: `0x9816A10B` (verify with `ak820ctl flash crc 0xCE0000 179968`).

| File | Cell | Note |
|---|---|---|
| `Iosevka-Medium-13.png` | 7x14 | song text; hand-fixed b/h/p joins and `%` |
| `Iosevka-Medium-20.png` | 10x23 | lock labels, battery %, conn digit; hand-fixed `P` |
| `Iosevka-Regular-30.png` | 15x22 | clock — **CROPPED to its ink**, see below |

## The clock atlas is cropped, and that is load-bearing

It was 15x34, cut for full ASCII with room for ascenders and descenders. The
clock only ever draws `0`-`9` and `:`, which use neither, so 12 of its 34 rows
were blank by construction (5 above the digits, 7 below).

Cropping to the measured ink freed **12 rows of panel** and cut **34 KB** off the
blob (96,900 -> 62,700 B). That is what paid for the even gaps around the lock
row and for keeping the battery percentage at 20px; before it, the panel was
full to the row and every spacing choice was a trade against another.

The glyphs are untouched pixel for pixel — this was a crop of the existing
atlas, not a re-render. Re-rendering would need the Iosevka **Regular** TTF
(only Medium is in `FONTS.md`) and would risk changing the hinting.

**⚠️ Descenders are clipped in this atlas.** `g`/`p`/`q`/`y` lost their tails.
Harmless because nothing but the clock uses `FONT_CLOCK`. If you ever draw
general text at this size, regenerate at the full 15x34 cell and hand the 12
rows back — do not try to fix it by nudging offsets.

To re-crop after regenerating, measure the ink extent of `0123456789:` first,
crop to it, then re-paint one magenta pixel at each cell's top-left: `mkraw.py`
reads markers from **row 0 only**, and marker spacing IS the advance.
