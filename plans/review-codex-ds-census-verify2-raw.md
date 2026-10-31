**Fixed.** ELF token `0x4de76a30`: `cpsid i` at `0x15c64` precedes `mrs IPSR` at `0x15c66`; `cpsie i` at `0x15c90` follows both final stores, immediately before return.

No new findings. Only the intended ordering/comment changed; other ELF differences are build hash/token values.

**Verdict: PASS — finding 3 closed; OK to keep on black.**