No remaining or new P1/P2/P3 findings.

- **Timestamp fix verified:** [agent.rs:389](/Users/jdlien/code/ak820-pro/ak820-agent/src/agent.rs:389) preserves source freshness and platform position timing. Failed reads still publish idle, clear the hold, and use `observed = now`. [media.rs:182](/Users/jdlien/code/ak820-pro/ak820-agent/src/media.rs:182) saves the original position instant and advances from it without double-counting. USB/radio receive the corrected held position; the lock-light channel correctly timestamps it at `now`.
- **Folding fix verified:** post-NFKD substitutions handle both accented examples and their decomposed equivalents. Exactly **43 mappings changed**: 24 new letters, six accented forms, and 13 compatibility characters decomposing to `SUBS` keys. No unrelated changes; whitespace handling is unchanged.
- **Ə/ə:** unchanged under the accepted disposition.

All **2,353 fixture cases** match the decoded table and Python oracle. Comparing all **1,112,064 scalars** confirms exactly the intended behavioral changes. Local Python uses Unicode 17; its 37 differences from the checked-in Unicode tables are identical before and after this patch.

`git diff --check` passes. Cargo tests were not rerun. No files changed.

**READY**