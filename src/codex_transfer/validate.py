#!/usr/bin/env python3
"""Independent, read-only validator for Codex Portable Backup Package 2.0."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any


FORMAT_ID = "codex-portable-backup"
FORMAT_VERSION = "2.0"
MANIFEST_EXCLUSIONS = {
    "manifest/package.json",
    "manifest/package.json.sha256",
    "manifest/sha256.csv",
}
FORBIDDEN_CODEX_PATHS = {
    "codex/auth.json",
    "codex/installation_id",
    "codex/cap_sid",
    "codex/state_5.sqlite-wal",
    "codex/state_5.sqlite-shm",
}
FORBIDDEN_CODEX_DIRECTORIES = {
    "codex/.sandbox",
    "codex/.sandbox-bin",
    "codex/.sandbox-secrets",
    "codex/.tmp",
    "codex/tmp",
    "codex/cache",
    "codex/computer-use",
    "codex/node_repl",
    "codex/process_manager",
    "codex/thread-writer-locks",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def valid_relative_path(value: str) -> bool:
    candidate = PurePosixPath(value)
    return (
        bool(value)
        and "\\" not in value
        and not candidate.is_absolute()
        and ".." not in candidate.parts
        and candidate.parts[0] not in ("", ".")
    )


def parse_session_id(path: Path) -> tuple[str | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
            first_line = handle.readline()
        value = json.loads(first_line)
        if value.get("type") != "session_meta":
            return None, "eerste regel is niet session_meta"
        thread_id = (value.get("payload") or {}).get("id")
        if not thread_id:
            return None, "payload.id ontbreekt"
        return str(thread_id), None
    except Exception as exc:
        return None, str(exc)


def validate(package_root: Path, allow_building: bool) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    package_root = package_root.resolve()
    required = [
        "manifest/package.json",
        "manifest/package.json.sha256",
        "manifest/sha256.csv",
        "manifest/projects.json",
        "manifest/threads.json",
        "manifest/path-mappings.json",
        "codex/state.snapshot.sqlite",
        "codex/portable-global-state.json",
        "reports/backup-report.json",
    ]
    if not package_root.is_dir():
        return {
            "valid": False,
            "errors": [f"Package directory does not exist: {package_root}"],
            "warnings": [],
            "checks": {},
        }
    for value in required:
        if not (package_root / value).is_file():
            errors.append(f"Required file missing: {value}")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "checks": checks}

    try:
        package = read_json(package_root / "manifest/package.json")
    except Exception as exc:
        package = {}
        errors.append(f"package.json is invalid: {exc}")
    if package.get("formatId") != FORMAT_ID:
        errors.append(f"Onjuist formatId: {package.get('formatId')!r}")
    if package.get("formatVersion") != FORMAT_VERSION:
        errors.append(f"Niet-ondersteunde formatVersion: {package.get('formatVersion')!r}")
    complete = package.get("backupComplete")
    if allow_building:
        if complete not in (False, True):
            errors.append("backupComplete moet een boolean zijn.")
    elif complete is not True:
        errors.append("Pakket heeft niet backupComplete: true.")
    for key in ("generatorVersion", "createdAtUtc", "source", "database", "counts", "hashManifest"):
        if key not in package:
            errors.append(f"Verplicht package.json-veld ontbreekt: {key}")

    package_path = package_root / "manifest/package.json"
    expected_package_hash = (package_root / "manifest/package.json.sha256").read_text(
        encoding="ascii", errors="replace"
    ).strip().lower()
    actual_package_hash = sha256_file(package_path)
    if expected_package_hash != actual_package_hash:
        errors.append("package.json.sha256 komt niet overeen met package.json.")
    checks["packageManifestHash"] = expected_package_hash == actual_package_hash

    hash_manifest_path = package_root / "manifest/sha256.csv"
    actual_hash_manifest_hash = sha256_file(hash_manifest_path)
    declared_hash_manifest_hash = (
        package.get("hashManifest", {}).get("sha256", "")
        if isinstance(package.get("hashManifest"), dict)
        else ""
    )
    if declared_hash_manifest_hash != actual_hash_manifest_hash:
        errors.append("SHA-256 van manifest/sha256.csv komt niet overeen met package.json.")
    checks["hashManifestHash"] = declared_hash_manifest_hash == actual_hash_manifest_hash

    hash_rows: dict[str, tuple[int, str]] = {}
    try:
        with hash_manifest_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["relative_path", "size", "sha256"]:
                errors.append("sha256.csv heeft niet exact de verwachte kolommen.")
            for row_number, row in enumerate(reader, start=2):
                relative_path = row.get("relative_path", "")
                if not valid_relative_path(relative_path):
                    errors.append(f"Invalid relative path in sha256.csv row {row_number}: {relative_path!r}")
                    continue
                if relative_path in MANIFEST_EXCLUSIONS:
                    errors.append(f"Zelfrefererend manifestpad is niet toegestaan: {relative_path}")
                if relative_path in hash_rows:
                    errors.append(f"Dubbel pad in sha256.csv: {relative_path}")
                    continue
                try:
                    size = int(row.get("size", ""))
                except ValueError:
                    errors.append(f"Invalid file size for {relative_path}")
                    continue
                digest = row.get("sha256", "").lower()
                if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                    errors.append(f"Invalid SHA-256 for {relative_path}")
                    continue
                hash_rows[relative_path] = (size, digest)
    except Exception as exc:
        errors.append(f"sha256.csv kan niet worden gelezen: {exc}")

    actual_files = {
        rel(path, package_root)
        for path in package_root.rglob("*")
        if path.is_file() and rel(path, package_root) not in MANIFEST_EXCLUSIONS
    }
    listed_files = set(hash_rows)
    for value in sorted(actual_files - listed_files):
        errors.append(f"Unexpected/unhashed file: {value}")
    for value in sorted(listed_files - actual_files):
        errors.append(f"Hashed file is missing: {value}")
    checked_hashes = 0
    for relative_path, (expected_size, expected_hash) in hash_rows.items():
        path = package_root / Path(*PurePosixPath(relative_path).parts)
        if not path.is_file():
            continue
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            errors.append(
                f"Grootte wijkt af: {relative_path} ({actual_size} i.p.v. {expected_size})"
            )
            continue
        actual_hash = sha256_file(path)
        checked_hashes += 1
        if actual_hash != expected_hash:
            errors.append(f"Hash wijkt af: {relative_path}")
    checks["hashedFilesChecked"] = checked_hashes
    declared_hashed = package.get("counts", {}).get("hashedFiles") if isinstance(package.get("counts"), dict) else None
    if declared_hashed != len(hash_rows):
        errors.append(
            f"counts.hashedFiles ({declared_hashed}) wijkt af van sha256.csv ({len(hash_rows)})."
        )

    actual_all = {rel(path, package_root).lower() for path in package_root.rglob("*")}
    for forbidden in FORBIDDEN_CODEX_PATHS:
        if forbidden.lower() in actual_all:
            errors.append(f"Machine-specific Codex file found: {forbidden}")
    for forbidden_directory in FORBIDDEN_CODEX_DIRECTORIES:
        prefix = forbidden_directory.lower() + "/"
        if any(value == forbidden_directory.lower() or value.startswith(prefix) for value in actual_all):
            errors.append(f"Machine-specific Codex directory found: {forbidden_directory}")

    database_path = package_root / "codex/state.snapshot.sqlite"
    database_threads: set[str] = set()
    try:
        uri_path = urllib.parse.quote(database_path.as_posix(), safe="/:")
        # A plain read-only connection to a WAL-mode database can still create
        # sibling -wal/-shm files. A validator must never mutate the package it
        # is checking, so treat the completed snapshot as immutable.
        connection = sqlite3.connect(
            f"file:{uri_path}?mode=ro&immutable=1", uri=True
        )
        try:
            quick_check_row = connection.execute("PRAGMA quick_check").fetchone()
            quick_check = str(quick_check_row[0]) if quick_check_row else "no result"
            checks["sqliteQuickCheck"] = quick_check
            if quick_check != "ok":
                errors.append(f"SQLite quick_check is niet ok: {quick_check}")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "threads" not in tables:
                errors.append("Snapshot database does not contain a threads table.")
            else:
                database_threads = {
                    str(row[0]) for row in connection.execute("SELECT id FROM threads")
                }
        finally:
            connection.close()
    except Exception as exc:
        errors.append(f"Snapshotdatabase kan niet worden gecontroleerd: {exc}")

    try:
        thread_manifest = read_json(package_root / "manifest/threads.json")
        if not isinstance(thread_manifest, list):
            raise ValueError("root moet een lijst zijn")
    except Exception as exc:
        thread_manifest = []
        errors.append(f"threads.json is invalid: {exc}")
    manifest_thread_ids: set[str] = set()
    referenced_rollouts: set[str] = set()
    for item in thread_manifest:
        if not isinstance(item, dict) or not item.get("id"):
            errors.append("threads.json bevat een item zonder id.")
            continue
        thread_id = str(item["id"])
        if thread_id in manifest_thread_ids:
            errors.append(f"Dubbele thread-id in threads.json: {thread_id}")
        manifest_thread_ids.add(thread_id)
        relative_path = item.get("backupRelativePath")
        if not isinstance(relative_path, str) or not valid_relative_path(relative_path):
            errors.append(f"Conversation {thread_id} has no valid backupRelativePath.")
            continue
        if relative_path in referenced_rollouts:
            errors.append(f"Rollout file is used by more than one conversation: {relative_path}")
        referenced_rollouts.add(relative_path)
        rollout = package_root / Path(*PurePosixPath(relative_path).parts)
        if not rollout.is_file():
            errors.append(f"Rollout file missing for conversation {thread_id}: {relative_path}")
            continue
        rollout_id, rollout_error = parse_session_id(rollout)
        if rollout_error:
            errors.append(f"Invalid rollout {relative_path}: {rollout_error}")
        elif rollout_id != thread_id:
            errors.append(
                f"Thread-id wijkt af in {relative_path}: {rollout_id} i.p.v. {thread_id}"
            )
    if database_threads != manifest_thread_ids:
        for thread_id in sorted(database_threads - manifest_thread_ids):
            errors.append(f"Database-thread ontbreekt in threads.json: {thread_id}")
        for thread_id in sorted(manifest_thread_ids - database_threads):
            errors.append(f"Manifest-thread ontbreekt in database: {thread_id}")
    session_files = {
        rel(path, package_root)
        for directory in ("sessions", "archived_sessions")
        for path in (package_root / "codex" / directory).rglob("*.jsonl")
    }
    orphan_files = session_files - referenced_rollouts
    if orphan_files:
        warnings.append(f"Found {len(orphan_files)} orphan rollout file(s).")
    declared_threads = package.get("counts", {}).get("threads") if isinstance(package.get("counts"), dict) else None
    declared_sessions = package.get("counts", {}).get("sessionFiles") if isinstance(package.get("counts"), dict) else None
    if declared_threads != len(database_threads):
        errors.append(
            f"counts.threads ({declared_threads}) wijkt af van database ({len(database_threads)})."
        )
    if declared_sessions != len(session_files):
        errors.append(
            f"counts.sessionFiles ({declared_sessions}) differs from files ({len(session_files)})."
        )
    checks["threadsChecked"] = len(manifest_thread_ids)
    checks["sessionFilesFound"] = len(session_files)

    try:
        projects = read_json(package_root / "manifest/projects.json")
        if not isinstance(projects, list):
            raise ValueError("root moet een lijst zijn")
    except Exception as exc:
        projects = []
        errors.append(f"projects.json is invalid: {exc}")
    for item in projects:
        if not isinstance(item, dict):
            errors.append("projects.json bevat een niet-object.")
            continue
        relative_path = item.get("backupRelativePath")
        if not isinstance(relative_path, str) or not valid_relative_path(relative_path):
            errors.append(f"Project {item.get('id')} has an invalid backupRelativePath.")
            continue
        project_root = package_root / Path(*PurePosixPath(relative_path).parts)
        if not project_root.is_dir():
            errors.append(f"Project directory missing: {relative_path}")
            continue
        files = [path for path in project_root.rglob("*") if path.is_file()]
        actual_count = len(files)
        actual_size = sum(path.stat().st_size for path in files)
        if item.get("fileCount") != actual_count:
            errors.append(
                f"Project {item.get('id')} file count differs: {actual_count} instead of {item.get('fileCount')}"
            )
        if item.get("totalBytes") != actual_size:
            errors.append(
                f"Byteaantal project {item.get('id')} wijkt af: {actual_size} i.p.v. {item.get('totalBytes')}"
            )
    declared_projects = package.get("counts", {}).get("projects") if isinstance(package.get("counts"), dict) else None
    if declared_projects != len(projects):
        errors.append(
            f"counts.projects ({declared_projects}) wijkt af van projects.json ({len(projects)})."
        )
    checks["projectsChecked"] = len(projects)

    try:
        mappings = read_json(package_root / "manifest/path-mappings.json")
        attachment_mappings = mappings.get("attachments", [])
        copied_attachments = [item for item in attachment_mappings if item.get("sourcePresent")]
        missing_attachments = [item for item in attachment_mappings if not item.get("sourcePresent")]
        for item in copied_attachments:
            relative_path = item.get("backupRelativePath", "")
            if not valid_relative_path(relative_path) or not (
                package_root / Path(*PurePosixPath(relative_path).parts)
            ).is_file():
                errors.append(f"Copied attachment is missing: {relative_path}")
        counts = package.get("counts", {}) if isinstance(package.get("counts"), dict) else {}
        if counts.get("attachmentsCopied") != len(copied_attachments):
            errors.append("counts.attachmentsCopied differs from path-mappings.json.")
        if counts.get("attachmentsMissing") != len(missing_attachments):
            errors.append("counts.attachmentsMissing differs from path-mappings.json.")
        if missing_attachments:
            warnings.append(
                f"{len(missing_attachments)} historical attachment(s) were already missing at the source."
            )
        checks["attachmentsCopiedChecked"] = len(copied_attachments)
    except Exception as exc:
        errors.append(f"path-mappings.json is invalid: {exc}")

    actual_files_after = {
        rel(path, package_root)
        for path in package_root.rglob("*")
        if path.is_file() and rel(path, package_root) not in MANIFEST_EXCLUSIONS
    }
    package_unchanged = actual_files_after == actual_files
    checks["packageUnchangedDuringValidation"] = package_unchanged
    if not package_unchanged:
        for value in sorted(actual_files_after - actual_files):
            errors.append(f"Validator created an unexpected file: {value}")
        for value in sorted(actual_files - actual_files_after):
            errors.append(f"File disappeared during validation: {value}")

    return {
        "valid": not errors,
        "package": str(package_root),
        "formatVersion": package.get("formatVersion"),
        "backupComplete": complete,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Controleer Codex Portable Backup 2.0")
    parser.add_argument("package")
    parser.add_argument("--allow-building", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    result = validate(Path(args.package), args.allow_building)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("")
        print("PASSED" if result["valid"] else "FAILED")
        print(f"Pakket: {result.get('package', args.package)}")
        checks = result.get("checks", {})
        print(
            "Conversations: {} | Projects: {} | Hashes: {}".format(
                checks.get("threadsChecked", 0),
                checks.get("projectsChecked", 0),
                checks.get("hashedFilesChecked", 0),
            )
        )
        for warning in result.get("warnings", []):
            print(f"WARNING: {warning}")
        for error in result.get("errors", []):
            print(f"FOUT: {error}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
