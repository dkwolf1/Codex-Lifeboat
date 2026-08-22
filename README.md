# Codex Lifeboat

**One-click Codex backup, restore, and Windows PC migration.**

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows)](https://github.com/dkwolf1/Codex-Lifeboat)
[![Latest release](https://img.shields.io/github/v/release/dkwolf1/Codex-Lifeboat?label=release)](https://github.com/dkwolf1/Codex-Lifeboat/releases/latest)
[![CI](https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml/badge.svg)](https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml)

[Nederlands](docs/nl/README.md) · [Security](SECURITY.md) · [Documentation](docs/ROADMAP.md)

## Download for Windows

### [Download Codex Lifeboat for Windows](https://github.com/dkwolf1/Codex-Lifeboat/releases/latest)

On the release page, download only:

```text
Codex-Lifeboat-Windows-x64-Portable.zip
```

Extract the ZIP and start `Codex-Lifeboat.exe`. No installation, Python, or
administrator rights are required.

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
- A destination safety copy and automatic rollback on failure

It deliberately excludes source authentication, installation IDs, machine identity,
caches, locks, sandbox secrets, and active runtime files.

## Back up the source computer

1. Fully close Codex.
2. Insert the USB drive.
3. Start `Codex-Lifeboat.exe`.
4. Choose **Create complete backup**.
5. Choose **Verify backup** when creation is complete.

## Restore on the new computer

1. Install Codex, open it once, and sign in.
2. Fully close Codex.
3. Start `Codex-Lifeboat.exe` from the USB drive.
4. Choose **Complete restore**.
5. Review the safety-copy location and confirm.
6. Choose **Verify restore** when restoration is complete.

## Important security note

Backups are intentionally not encrypted and may contain source code, `.env` files,
API keys, and other confidential project data. Keep the USB drive physically secure.
See the [security policy](SECURITY.md) for reporting vulnerabilities.

## Verified behavior

The end-to-end suite checks package integrity, source immutability, authentication
exclusion, exact project restoration, portable profile restoration, path translation,
schema compatibility, tamper rejection, safety-copy retention, rollback, and both
GUI languages. See the [test results](tests/TEST-RESULTS.md).

## For developers

- [Build and test](BUILD.md)
- [Product specification](docs/PRODUCT-SPEC.md)
- [Known limitations](docs/KNOWN-LIMITATIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Third-party notices](THIRD-PARTY-NOTICES.txt)

The repository contains source code and documentation only. Ready-to-run binaries
are distributed through [GitHub Releases](https://github.com/dkwolf1/Codex-Lifeboat/releases).

Codex Lifeboat is an independent community project and is not an official OpenAI product.
