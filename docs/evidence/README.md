# Evidence directory

Commit sanitized reports, commands/exit codes, tool identities, and portable artifact references here. Keep credential-bearing or machine-specific raw logs in ignored `raw/` subdirectories or local runtime storage.

L01 first creates `L01/compatibility-report.md` and the real `toolchain.lock.json`. Later acceptance reports must state which real tools, deterministic fixtures, and live agent profile were exercised. This handoff contains no successful product execution evidence.

- `L01/`: upstream compatibility report (`compatibility-report.md`), sanitized
  probe fixtures (`fixtures/`), and the real toolchain lock recorded at
  `toolchain.lock.json` (repository root).
