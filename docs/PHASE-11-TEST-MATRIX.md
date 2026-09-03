# Phase 11 — Universal Windows test matrix

Phase 11 combines reproducible simulated two-computer tests with a small set of
tests that genuinely require physical Windows computers or removable hardware.
This distinction prevents a local simulation from being presented as proof of a
real USB or cross-device hand-off.

Run the automated matrix from PowerShell:

```powershell
.\test-phase11.ps1
```

The command performs the complete end-to-end self-test and writes the detailed
machine-readable matrix to `.build\selftest-*\self-test-result.json` under
`phase11Matrix`.

## Automated scenarios

- Different source and destination usernames.
- Redirected Documents/OneDrive-style known folders and changed drive letters.
- External, USB and UNC location mapping.
- Long and Unicode portable paths.
- Nested, missing and reparse-point project roots.
- Low destination disk space.
- Injected interruptions and transactional rollback.
- Corrupt/incomplete package rejection.
- Source/destination SQLite schema differences.
- Recent, projectless, pinned and archived conversations.
- Independent project and conversation edits.
- Format 2.0 compatibility and repeated A-to-B-to-A round trips.
- Measured and non-measurable progress-bar transitions.

## Physical test status

- **Pending:** packaged executable on a real Windows 10 computer.
- **Passed 2026-09-02:** packaged executable on a second real Windows 11 computer.
- **Pending:** removal of a real USB drive while a backup is being written.
- **Passed 2026-09-02:** a real journey from PC A to PC B and back to PC A,
  including Create backup, Verify backup, Restore, Verify restore, opening Codex,
  and continuing work on both computers.

The machine-readable matrix distinguishes passed physical evidence from remaining
optional coverage. Source tests alone did not close the stable-release gate; the
successful two-computer round trip did.

## Current local packaged evidence

On September 2, 2026, the source build, directly built 3.4.4 executable, and the
executable launched from a freshly extracted portable ZIP each passed all 76
checks and all 12 automated matrix scenarios on Windows 11. The generated EXE
and ZIP also matched their generated SHA-256 values. Together with the successful
physical Windows 11 round trip, this closes the stable-release gate. Windows 10
and interrupted physical USB-write coverage remain useful future additions.
