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

## Physical tests still required for the Phase 11 gate

- Packaged executable on a real Windows 10 computer.
- Packaged executable on a second real Windows 11 computer.
- Removal of a real USB drive while a backup is being written.
- One release-candidate journey from PC A to PC B and back to PC A.

These tests remain explicitly `pending` in the JSON matrix until they are
performed and documented. Source tests alone do not close the Phase 11 gate.

## Current local packaged evidence

On August 24, 2026, the source build, directly built 3.4.0 executable, and the
executable launched from a freshly extracted portable ZIP each passed all 75
checks and all 12 automated matrix scenarios on Windows 11. The generated EXE
and ZIP also matched their published SHA-256 values. This is strong local
evidence, but it does not replace the four physical cross-device tests above.
