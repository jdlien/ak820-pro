# Phase 0 — Lock down what exists

**Theme:** make the working tree safe to work in. Highest value per unit risk
in the whole plan; everything here is mechanical.

**Exit criterion:** a fresh checkout of the two branches (QMK fork +
chibios-contrib fork) builds a working firmware with no hand-applied steps,
and nothing load-bearing is uncommitted anywhere.

## 0.1 Commit the current working-tree changes

`ak820pro.c` + `config.h` currently carry the uncommitted loop-gap probe
additions (~50 lines). Commit them on `ak820pro-jdlien` as-is.

## 0.2 ChibiOS patches → commits on a forked submodule branch

The six diffs in `keyboards/a_jazz/ak820pro/*.diff` are applied by hand into
`lib/chibios-contrib/` as **uncommitted working-tree edits**. Any
`git submodule update` silently discards them and the build breaks later in
confusing ways. This is the single biggest maintainability hazard in the tree.

Steps:

1. In `lib/chibios-contrib/`, create branch `ak820pro-patches` from the
   currently pinned commit.
2. Commit the applied state as six commits, one per diff, in the documented
   order (`hardware_pwm → i2c_fallback → rtc_lld → spi_fifo_pump →
   spi_flash_dma → efl_ramtext`), each message naming the source diff file.
   Order matters: `spi_flash_dma` follows `spi_fifo_pump` (same LLD file).
3. Verify the committed tree is byte-identical to the current working tree
   (`git status` clean, `git diff` empty against the new branch).
4. Update the superproject's `.gitmodules`/gitlink to pin the new branch tip
   and commit that in the QMK fork.
5. Keep the `.diff` files in `keyboards/a_jazz/ak820pro/` as documentation,
   with a note in each that the submodule branch is now authoritative.
6. Hosting: **push the fork branch to a personal GitHub remote.** A
   local-only branch does not satisfy this phase's fresh-checkout exit
   criterion — a gitlink pinning a commit that exists in one local clone is
   not reproducible anywhere else, and `.gitmodules`' `branch` field does not
   transport the object. If a remote is genuinely unwanted, the fallback is a
   committed `git bundle` of the branch in the workspace repo plus a
   `build.sh` step that fetches from it — but the remote is simpler and
   better. (Same logic applies to the QMK fork branch itself.)

**Verification:** `git -C lib/chibios-contrib status` clean; clean rebuild
produces a binary that passes the structural checks (SP `0x20000400`, reset
`0x191`, USB descriptor `0C45:8009`); flash and confirm normal boot.

**Guardrail:** do NOT run `git checkout`/`stash` in `lib/chibios-contrib`
before step 2 is complete — that is the exact data-loss this phase removes.
Take a tarball of `lib/chibios-contrib` first as cheap insurance.

## 0.3 Build script with provenance

`scripts/build.sh` (in the workspace root, committed to the workspace repo):

1. `source env.sh`.
2. Verify the six patches are present in the submodule (reverse-check, as in
   `ak820pro-mac-setup.sh` step 5) — after 0.2 this becomes "verify the
   submodule is on the pinned commit", which is cheaper and stricter.
3. `qmk compile -kb a_jazz/ak820pro -km via`, with a **flavor switch**: the
   daily build ships `console: false` and instruments compiled out
   (commit 6689927483 — removes a USB interface and the replug stall an
   undrained console queue costs); the *instrumented* flavor re-enables
   console + probes for debugging and soak runs. The script owns the flag
   flip so the two flavors are reproducible and never hand-edited.
4. Copy the output to a per-build name:
   `ak820pro-builds/out/via-<flavor>-<shorthash>[-dirty]-<timestamp>.bin`
   and print the path.

Flashing then uses the per-build file, which kills the shared-binary-path
hazard (two sessions racing on `$QMK_HOME/a_jazz_ak820pro_via.bin`) — the
flashed artifact names the commit it came from.

## 0.4 Inventory sweep for anything else uncommitted

- `git status` in all four upstream clones. Known: `time-util-ak820pro/` has
  uncommitted changes in `assets/` (the shipped atlases/blob — copies exist
  in `assets-src/current/`). Commit those in that clone on a local branch,
  since there is **no way to read assets back off the board**; the repo copy
  is the only durable one.
- Confirm the QMK-core edits (`rgb_matrix.c`, `sn32f2xx.c`,
  `wear_leveling_efl.c`) are all committed on `ak820pro-jdlien` (believed
  yes — verify, don't assume).
- `SonixFlasherC`: confirm still on `fpb/fix_for_macos_tahoe` and the binary
  still links libusb (`nm sonixflasher | grep -c libusb` > 0).

## Deliverables

- [ ] Loop-gap probe committed.
- [ ] `lib/chibios-contrib` on `ak820pro-patches` with six commits; gitlink
      updated and committed.
- [ ] `scripts/build.sh` with provenance naming.
- [ ] All four clones' status documented/clean; asset tree committed locally.
- [ ] CLAUDE.md updated: patches section now points at the submodule branch.
