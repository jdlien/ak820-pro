# Hardware verification checklist

Steps that need JD at the keyboard. Software work proceeds ahead of these;
nothing is flashed without you. Run top to bottom when convenient — each
entry says what to do and what "pass" looks like. Build artifacts are in
`ak820pro-builds/out/` (never flash the shared `$QMK_HOME` binary).

## Phase 0 — build provenance

- [ ] Flash the current daily artifact via
      `./flash.sh ak820pro-builds/out/via-daily-<newest>.bin`
      (Fn+Esc first; flash.sh dumps/restores the VIA keymap).
      **Pass:** checksum OK, board back as 0x8009, panel normal, typing
      normal — proves a script-built binary from the committed patches
      branch is flightworthy. Everything later builds on this.

(Phase 1+ entries are appended as their code lands.)
