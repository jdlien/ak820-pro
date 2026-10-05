# Codex on flash 1b (the trimmed accounting), 2026-10-05 -- verbatim

Model gpt-6-astra, reasoning xhigh, read-only. Prompt: [review-prompt-battery-refine-impl1b.txt](review-prompt-battery-refine-impl1b.txt). Reviewed firmware `7a0f28aa8f` and parent `5035b9c`. Dispositions: the plan, "Gate 3 — failed, and the trim".

---

1. **Fix: pages 3–4 include an unfinished pass.** [loop_acct.c:195](/Users/jdlien/code/ak820-pro/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/loop_acct.c:195) uses `run − fold_base`, while `fold_gap_ms` covers completed passes only. Example: totals `(scope=2, unaccounted=8)` ms become `(8,2)` after 6 scoped ms mid-pass, then revert when disabled. Skipped/aliased time can likewise appear before being dropped. Use **`pass_base − fold_base`** for pending reads; add a mid-pass regression. Otherwise, drop/skip/alias, slow deltas, folding, reset—including Fn+D—and boot settling preserve completed-pass totals without duplication or leakage.

2. **Overflow/stack: right.** Modular u32 differences work across wrap. Maximum fold multiplication is **520,704,000 before division**, safely within u32. The slow-pass array poses no apparent problem on the **2 KB main-thread stack**.

3. **Cost: substantially improved, but understated.** ELF confirms inline counter reads, fixed-address additions, and an inline 48-byte copy. However, inlined `slow_pass()`/`fold()` make every pass-end call save nine registers and allocate a **112-byte frame—even while off**. Keeping those helpers out of line could trim more. Flag/threshold checks and `passes++` also remain. Gate 3 must establish the actual cost.

4. **Dropping those scopes: acceptable for D2.** The user hook is empty; parameter repeat is idle unless adjustment keys are held. Their active time remains visible as UNACCOUNTED; split it if material.

5. **No other new data defect found.** Existing slow-scope u32 totals still wrap after approximately **6.36 accumulated hours per scope**.

No files changed. Inspected source/ELF and checked arithmetic in memory; C/build passes are your supplied evidence.

fix 1 first