# Regenerating the LCD font atlases

`mkfontatlas.py` needs the source TTF, which is **not committed** (10 MB).

```sh
curl -sLO https://github.com/be5invis/Iosevka/releases/download/v34.8.1/PkgTTF-Iosevka-34.8.1.zip
unzip -o -j PkgTTF-Iosevka-34.8.1.zip "*Iosevka-Medium.ttf" -d assets-src/
rm PkgTTF-Iosevka-34.8.1.zip
```

Then, from `time-util-ak820pro/assets/`:

```sh
V=../../venv/bin/python
$V ../../assets-src/mkfontatlas.py ../../assets-src/Iosevka-Medium.ttf \
    Iosevka-Medium-14.png --size 14 --cell 7x18 --baseline 14
python3 mkraw.py --flash
cp flash_assets.h ../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/graphics/res/
```

Then rebuild the firmware **and** re-provision, together — ids are assigned by
sorted filename, so any added or removed asset shifts them.

## Do not re-derive these

- **The capital P at size 20 is an Iosevka defect**, not a rendering artifact.
  Size 20 is the only size in 16-26 where P's stem collapses to 1px. Size 19
  fixes P but collapses every glyph's *right* stem. The shipped atlas has P
  hand-fixed at 20; leave it.
- **Iosevka Aile (proportional) is WIDER than Iosevka mono** — 10 chars/line
  against 12 at the same ppem. The mono is condensed at 0.5em advance. Going
  proportional loses density here.
- **Render monochrome** with `getmask(mode="1")`. Antialiasing then thresholding
  is a different FreeType path and discards the hinting.
- **Size 12 was built and rejected on the panel** — the counters in a/e/o/g close
  up and word shapes stop reading at a glance.

`font-backup/` holds the pre-font-work atlases and blob. To revert:
`ak820ctl flash write 0xCE0000 font-backup/flash_assets.bin` plus a firmware
build using its `flash_assets.h`.
