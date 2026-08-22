# Changelog

## 3.1.4 - 2026-08-23

- Blocks execution directly from Windows Explorer's temporary ZIP preview and
  gives explicit Extract All instructions.
- Makes the transition from 100% hashing to independent verification visible.
- Calculates the hash-manifest digest while writing it, avoiding a redundant
  reopen at the phase boundary.

## 3.1.3 - 2026-08-23

- Added live file, byte and percentage progress during hashing and validation.
- Removed a redundant third full payload hash pass while retaining independent
  full verification before a backup is finalized.
- Detects USB-backed fixed disks in addition to drives marked removable and
  refreshes the drive list automatically.
- Treats an unknown Microsoft Store version as unavailable information instead
  of incorrectly warning that a newer version may exist.

## 3.1.2 - 2026-08-22

- Fixed final validation of real Codex snapshots that use SQLite WAL mode.
- Snapshot databases are now normalized to a single self-contained file.
- The independent validator now opens snapshots as immutable and verifies that
  validation did not modify the backup package.

## 3.1.1 - 2026-08-22

- Fixed backup failure with `WinError 3` when the portable application was
  launched from a transient Windows location.
- The running application now stages a stable copy of itself at startup so the
  restore executable can always be included in the USB backup.

## 3.1.0 - 2026-08-22

- Renamed the public product and executable to Codex Lifeboat.
- Simplified the repository and moved binaries to GitHub Releases.
- Added a prominent, unambiguous Windows download section.
- Added Windows CI, automated release, dependency updates, and repository templates.
- Completed Python package metadata and reorganized translated documentation.

## 3.0.0 - 2026-08-22

- First standalone Windows 10/11 release.
- Bilingual graphical assistant for backup, validation, restore and final verification.
- Functional migration of Codex projects, conversations, settings, skills and local attachments.
- Preservation of destination authentication and machine identity.
- SHA-256 validation, safety copies and automatic rollback.
- Compatibility warning with an explicit option to continue.
