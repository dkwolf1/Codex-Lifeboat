# Codex Transfer Assistant

**Complete Codex backup, restore and Windows PC migration — designed for one-click USB transfers.**

[Nederlands](README-NL.md) · [Download for Windows](releases/3.0.0/Codex-Transfer-Assistant-3.0.0-Windows-x64-Portable.zip) · [Build](BUILD.md) · [Security](SECURITY.md)

Codex Transfer Assistant is a standalone, bilingual Windows 10/11 utility for
moving a local Codex workspace from one computer to another. It backs up projects,
Git repositories, local conversations, archived conversations, attachments, skills
and portable settings, validates every file with SHA-256, and restores the workspace
while preserving the destination computer's login and machine identity.

It is intended for people looking for a reliable **Codex backup tool**, **Codex
restore utility**, **Codex PC migration**, **Codex chat backup**, **Codex project
transfer**, or **Codex USB backup**.

> This is an independent community migration utility and is not an official OpenAI product.

## Why this tool exists

Blindly copying the complete `.codex` directory between computers can break local
authentication, installation identity, paths and database state. This assistant
separates portable workspace data from machine-specific data and performs a
schema-aware import into a working Codex installation.

## Features

- One-click graphical workflow for non-technical users
- Windows 10 and Windows 11, 64-bit
- English and Dutch interface
- Complete project copies, including `.git`, `.env` and uncommitted files
- Active and archived local Codex conversations
- Project-to-conversation links and locally available attachments
- Skills and portable Codex configuration
- Consistent SQLite snapshots instead of unsafe live database copies
- SHA-256 integrity manifest and read-only backup validation
- Automatic Windows profile and project path translation
- Local safety copy before restore
- Automatic rollback if restoration fails
- Best-effort Codex version check with a clear warning when unavailable
- No Python installation or administrator rights required for end users

## Quick start

### Back up the source computer

1. Fully close Codex.
2. Insert the USB drive.
3. Run `Codex-Transfer-Assistant.exe`.
4. Choose **Create complete backup**.
5. Choose **Verify backup** when creation is complete.

### Restore on the new computer

1. Install Codex, open it once and sign in.
2. Fully close Codex.
3. Run the assistant from the USB drive or backup directory.
4. Choose **Complete restore**.
5. Review the automatically created local safety copy and confirm.
6. Choose **Verify restore** when restoration is complete.

## What is intentionally excluded

The source computer's `auth.json`, installation ID, machine identity, caches,
locks, sandbox secrets and active runtime files are never restored. The destination
computer keeps its own valid login and identity.

## Download and integrity

The ready-to-run portable release is stored in [`releases/3.0.0`](releases/3.0.0).
Verify the included SHA-256 checksum before running it. Because this community build
is not commercially code-signed, Windows SmartScreen may display a warning.

Backups are intentionally not encrypted and may contain `.env` files, API keys or
other secrets. Keep backup media physically secure.

## Verified behavior

The automated end-to-end suite checks package integrity, source immutability,
authentication exclusion, exact project restoration, portable profile restoration,
path translation, schema compatibility, tamper rejection, safety-copy retention,
rollback and both GUI languages. See [test results](tests/TEST-RESULTS.md).

## Repository layout

- `src/` — current Python source for version 3.0
- `tests/` — recorded end-to-end test results
- `release/` — ready-to-run Windows files
- `releases/3.0.0/` — portable release archive and checksum
- `docs/ROADMAP.md` — English roadmap and design decisions
- `legacy/Codex-Backup-Tools-v2/` — generic phase 0/1 prototype
- `build.ps1` and `test.ps1` — reproducible Windows build and self-test

See [BUILD.md](BUILD.md) to build from source and [CONTRIBUTING.md](CONTRIBUTING.md)
to help improve the project.
