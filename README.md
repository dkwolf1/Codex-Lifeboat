# Codex Lifeboat

**One-click Codex backup, restore, and Windows PC migration.**

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows)](https://github.com/dkwolf1/Codex-Lifeboat)
[![Public test: 3.4.2](https://img.shields.io/badge/public%20test-v3.4.2-f59e0b)](https://github.com/dkwolf1/Codex-Lifeboat/releases/tag/v3.4.2)
[![CI](https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml/badge.svg)](https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Wiki](https://github.com/dkwolf1/Codex-Lifeboat/wiki) · [Nederlands](docs/nl/README.md) · [Security](SECURITY.md) · [Documentation](docs/IMPLEMENTATION-ROADMAP.md)

> **Public testing release:** version 3.4.2 is a beta release candidate. Its
> automated source, executable, and extracted-ZIP tests pass, but real
> Windows 10 and multi-computer round trips are still being collected. Keep an
> independent copy of irreplaceable data and read the [testing guide](docs/TESTING-GUIDE.md).

## Download for Windows

### [Download Codex Lifeboat 3.4.2 for Windows](https://github.com/dkwolf1/Codex-Lifeboat/releases/tag/v3.4.2)

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
- A read-only diagnostics center with clear pass, notice, and failure results
- An anonymized JSON support report that excludes names, paths, project details,
  conversation content, authentication data, and environment values
- A schema-aware path portability audit that distinguishes translated paths,
  intentionally excluded machine state, unmapped external paths, and new Codex fields
- A local path-review window that explains the schema field, path category,
  current availability, backup handling, translation status, and likely impact;
  full paths remain hidden until the user explicitly reveals them
- Git-aware project conflict explanations that distinguish matching commits,
  forward progress, divergent history, and uncommitted changes without modifying Git
- Durable atomic storage for manifests, reports, registries, mappings, settings,
  lineage, device state, and restore journals
- Strict prefix-only chat synchronization: when every existing local chat record
  and its metadata exactly match the beginning of a longer backup chat, only the
  proven incoming continuation is adopted automatically
- Bounded change-history analysis for very large rollouts and hundreds of
  historical attachment references, with unchanged portable fingerprint meaning

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

Creation reads each payload once to write its SHA-256 and then performs fast
database, manifest, path, size, and lineage-structure checks. **Verify backup** is
the separate independent full reread, so normal creation does not duplicate the
slowest I/O work.

## Restore on the new computer

1. Install Codex, open it once, and sign in.
2. Fully close Codex.
3. Start `Codex-Lifeboat.exe` from the USB drive.
4. Choose **Complete restore**.
5. Review any external project locations when prompted.
6. Review the complete comparison plan. Resolve every chat or project conflict and
   review destination-only projects; they are retained unless you explicitly archive
   or remove them to recovery quarantine. Select a project conflict to see the
   available read-only Git explanation. A chat is extended automatically only when
   its complete local history is a proven unchanged prefix; every other difference
   remains an explicit conflict. File hashes remain authoritative.
7. Review the safety-copy location and confirm.
8. Choose **Verify restore** when restoration is complete.

Use **Manage recovery points** to inspect local recovery storage or safely remove
only older verified points. The two newest valid points, incomplete evidence,
visible project archives, and every USB backup remain untouched.

Recovery points are created on the destination computer immediately before a
restore. They are local rollback copies, not ordinary USB backups, so the list is
empty until this computer has performed a restore.

Use **System check and diagnostics** whenever backup or restore preparation is
unclear. It checks Windows compatibility, Codex data access, SQLite consistency,
the running Codex process, installed version detection, removable storage, free
space, and recovery points without changing any files or settings. Use **Copy
report** or **Save report** to share an anonymized JSON result with a tester or
issue report.

The project-selection screen also shows the path portability result before the
backup starts. **View details** explains what every group represents, whether the
referenced location still exists, whether its data is included, whether it will be
translated, and the likely impact. Unknown references are preserved unchanged: an
attention result does not omit database data and does not block backup or restore.
It means that a preserved link may still point to its previous location. **Verify
restore** reports remaining old-source references separately.

Real schema field names and optional full paths are shown locally only. Every backup
stores a separately hashed `reports/portability-audit.json`, and copied or saved
diagnostic reports contain only counts, classifications, reason codes, and
fingerprints for unknown schema fields—never raw paths, project names, or user identity.

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
[test results](tests/TEST-RESULTS.md). The source, packaged EXE, and freshly
extracted portable ZIP pass 75/75 checks and 12/12 automated Windows compatibility
scenarios. Physical cross-computer testing remains visible in the
[Phase 11 matrix](docs/PHASE-11-TEST-MATRIX.md).

## For developers

- [Build and test](BUILD.md)
- [Product specification](docs/PRODUCT-SPEC.md)
- [Known limitations](docs/KNOWN-LIMITATIONS.md)
- [Public testing guide](docs/TESTING-GUIDE.md)
- [Release checklist](docs/RELEASE-CHECKLIST.md)
- [Implementation phases 0–13](docs/IMPLEMENTATION-ROADMAP.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Third-party notices](THIRD-PARTY-NOTICES.txt)

The repository contains source code and documentation only. Ready-to-run binaries
are distributed through [GitHub Releases](https://github.com/dkwolf1/Codex-Lifeboat/releases).

Codex Lifeboat is an independent community project and is not an official OpenAI product.

Released under the [MIT License](LICENSE).
