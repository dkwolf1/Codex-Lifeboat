# Changelog

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
