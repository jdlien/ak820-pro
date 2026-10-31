#!/usr/bin/env bash
# Every regression test that came with a fix from the 10-31 audit
# (plans/AUDIT-2026-10-31.md), each against the real sources on the host.
# Prints PASS or FAIL per test; exits 1 if any failed. CC and SAN pass through.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fails=0
for t in "$here"/*_test/run.sh "$here"/wear_leveling_gtest/run.sh; do
  name="$(basename "$(dirname "$t")")"
  [[ "$name" == flash_tidy_test ]] && continue   # older, not the audit's
  if out="$("$t" 2>&1)"; then echo "PASS $name"; else echo "FAIL $name"; echo "$out" | tail -15; fails=1; fi
done
exit $fails
