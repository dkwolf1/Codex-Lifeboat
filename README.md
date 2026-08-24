# Codex Lifeboat

**One-click Codex backup, restore, and Windows PC migration.**

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows)](https://github.com/dkwolf1/Codex-Lifeboat)
[![Public test: 3.4.0](https://img.shields.io/badge/public%20test-v3.4.0-f59e0b)](https://github.com/dkwolf1/Codex-Lifeboat/releases/tag/v3.4.0)
[![CI](https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml/badge.svg)](https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Nederlands](docs/nl/README.md) · [Security](SECURITY.md) · [Documentation](docs/IMPLEMENTATION-ROADMAP.md)

> **Public testing release:** version 3.4.0 is a beta release candidate. Its
> automated source, executable, and extracted-ZIP tests pass, but real
> Windows 10 and multi-computer round trips are still being collected. Keep an
> independent copy of irreplaceable data and read the [testing guide](docs/TESTING-GUIDE.md).

## Download for Windows

### [Download Codex Lifeboat 3.4.0 for Windows](https://github.com/dkwolf1/Codex-Lifeboat/releases/tag/v3.4.0)

On the release page, download only:

```text
Codex-Lifeboat-Windows-x64-Portable.zip
```

Extract the ZIP and start `Codex-Lifeboat.exe`. No installation, Python, or
administrator rights are required. Windows 10/11 x64 is supported.

> Do not download GitHub's automatically generated **Source code (zip)** or
> **Source code (tar.gz)** files unless you want to develop the application.

Windows SmartScreen may warn because the community build is not commercially
code-signed. Verify the included `SHA256.txt` before running the application.

## What it does

Codex Lifeboat moves a local Codex workspace from one Windows computer to another.
It creates and validates a portable backup, restores it into a working Codex
installation, and preserves the destination computer's login and machine identity.

It includes:

- Complete project directories, including `.git`, `.env`, and uncommitted files
- Active and archived local conversations
- Project-to-conversation links and locally available attachments
- Skills and portable Codex configuration
- Consistent SQLite snapshots and SHA-256 integrity validation
- Automatic Windows profile and project-path translation
- A reviewed Project Location Mapper for external-drive, USB, and network roots
- A read-only comparison plan with conflicts, selected actions, and free-space checks
- Per-chat keep-backup, keep-computer, keep-both, skip, and cancel decisions
- Destination-only projects retained by default, with explicit archive or
  recoverable-delete choices
- Per-project keep-backup, keep-computer, archive-and-replace, skip, and cancel decisions
- Transactional, hash-verified project replacement without stale overlay files
- A destination safety copy and automatic rollback on failure
- A visual backup summary showing exactly what was protected and verified
- A pre-backup inventory with every project selected by default, showing its path,
  file count, size, and largest folders before anything is copied
- Optional whole-project exclusion while conversations and Codex settings remain protected
- Managed recovery points with disk usage and a two-valid-point retention policy

It deliberately excludes source authentication, installation IDs, machine identity,
caches, locks, sandbox secrets, and active runtime files.

## Back up the source computer

1. Fully close Codex.
2. Insert the USB drive.
3. Start `Codex-Lifeboat.exe`.
4. Choose **Create complete backup**.
5. Review the inventory. Everything is selected by default; exclude a project only
   when its files do not need to be recoverable from this backup.
6. Choose **Verify backup** when creation is complete.

## Restore on the new computer

1. Install Codex, open it once, and sign in.
2. Fully close Codex.
3. Start `Codex-Lifeboat.exe` from the USB drive.
4. Choose **Complete restore**.
5. Review any external project locations when prompted.
6. Review the complete comparison plan. Resolve every chat or project conflict and
   review destination-only projects; they are retained unless you explicitly archive
   or remove them to recovery quarantine.
7. Review the safety-copy location and confirm.
8. Choose **Verify restore** when restoration is complete.

Use **Manage recovery points** to inspect local recovery storage or safely remove
only older verified points. The two newest valid points, incomplete evidence,
visible project archives, and every USB backup remain untouched.

Recovery points are created on the destination computer immediately before a
restore. They are local rollback copies, not ordinary USB backups, so the list is
empty until this computer has performed a restore.

## Important security note

Backups are intentionally not encrypted and may contain source code, `.env` files,
API keys, and other confidential project data. Keep the USB drive physically secure.
See the [security policy](SECURITY.md) for reporting vulnerabilities.

## Verified behavior

The end-to-end suite checks package integrity, source immutability, authentication
exclusion, exact project restoration, portable profile restoration, path translation,
schema compatibility, tamper rejection, transactional replacement, exact conversation
mirroring, per-chat and per-project decisions, destination-only project retention,
archive and recoverable removal, idempotent repeat restore, injected-failure rollback,
and both GUI languages. See the
[test results](tests/TEST-RESULTS.md). Version 3.4.0 passes 66/66 checks and 12/12
automated Windows compatibility scenarios in source, packaged-EXE, and extracted-ZIP
runs. Physical cross-computer testing remains visible in the
[Phase 11 matrix](docs/PHASE-11-TEST-MATRIX.md).

## For developers

- [Build and test](BUILD.md)
- [Product specification](docs/PRODUCT-SPEC.md)
- [Known limitations](docs/KNOWN-LIMITATIONS.md)
- [Public testing guide](docs/TESTING-GUIDE.md)
- [Release checklist](docs/RELEASE-CHECKLIST.md)
- [Implementation phases 0–12](docs/IMPLEMENTATION-ROADMAP.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Third-party notices](THIRD-PARTY-NOTICES.txt)

The repository contains source code and documentation only. Ready-to-run binaries
are distributed through [GitHub Releases](https://github.com/dkwolf1/Codex-Lifeboat/releases).

Codex Lifeboat is an independent community project and is not an official OpenAI product.

Released under the [MIT License](LICENSE).
