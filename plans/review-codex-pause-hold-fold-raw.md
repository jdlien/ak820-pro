No P1 findings.

- **P2 — Windows holds use the wrong position timestamp.** [media.rs:174](/Users/jdlien/code/ak820-pro/ak820-agent/src/media.rs:174), [agent.rs:442](/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:442). SMTC positions are valid at their observation time, but `PauseHold` records the loop’s retrieval time. Example: position 100 observed at t=0 is read again at t=6 while a paused metadata read is delayed. The pause arrives at t=7; the hold produces **101 instead of 107**, timestamped “now.” Bluetooth detects this six-second backward jump as a seek and can send the incorrect position. Preserve the saved playing snapshot’s position timestamp separately from the pause’s first-sighting deadline.

- **P3 — Accented forms of the newly supported letters still disappear.** [ak820text.py:39](/Users/jdlien/code/ak820-pro/hostagent/ak820text.py:39), [gen_ascii_fold.py:65](/Users/jdlien/code/ak820-pro/scripts/gen_ascii_fold.py:65). Substitutions precede normalization: `Ǿutgrown` becomes `utgrown`, while canonically equivalent `Ǿutgrown` becomes `Outgrown`. Likewise, `Ǽon` becomes `on`, but `Ǽon` becomes `AEon`. Handle substituted letters produced by normalization too.

- **P3 — Common-letter coverage remains incomplete.** [ak820text.py:43](/Users/jdlien/code/ak820-pro/hostagent/ak820text.py:43), [gen_ascii_fold.py:69](/Users/jdlien/code/ak820-pro/scripts/gen_ascii_fold.py:69). `Ə/ə` still vanish: an Azerbaijani artist named `Əli` displays as `li`. This is a remaining omission, not a regression.

Otherwise, the hold’s fixed deadline, expiry scheduling, idle/failed-read clearing, keepalive and radio renewal look sound. Different artist/title metadata clears the hold before publication. `observed` retains source freshness, preserving `STALE_AFTER`. These bounds remain subject to source and transport delays.

Verified: identical `SUBS` copies; exactly 24 changed table mappings; unchanged whitespace handling; all 2,334 fixture cases match the checked-in table. Fixture churn additionally resamples empty cases. Unicode 15.0 → 15.1 adds no other mapping changes. Folding still precedes line truncation, and Python fallbacks share the updated oracle.

No files changed; cargo tests were not rerun.

**NOT READY**