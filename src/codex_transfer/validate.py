#!/usr/bin/env python3
"""Independent, read-only validator for Codex Portable Backup Package 2.x."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import lineage, path_model, project_identity


FORMAT_ID = "codex-portable-backup"
FORMAT_VERSION = "2.4"
SUPPORTED_FORMAT_VERSIONS = {"2.0", "2.1", "2.2", "2.3", FORMAT_VERSION}
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


def supports_format(version: str) -> bool:
    return version in SUPPORTED_FORMAT_VERSIONS


def sha256_file(path: Path, progress: Callable[[int], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            if progress:
                progress(len(chunk))
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


def validate(
    package_root: Path,
    allow_building: bool,
    progress: Callable[[int, int, str], None] | None = None,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    if progress:
        progress(0, 0, "Reading package structure and manifests...")
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
    if not supports_format(str(package.get("formatVersion"))):
        errors.append(f"Niet-ondersteunde formatVersion: {package.get('formatVersion')!r}")
    if package.get("formatVersion") in {"2.2", "2.3", "2.4"} and not (
        package_root / "manifest/project-identities.json"
    ).is_file():
        errors.append("Required file missing: manifest/project-identities.json")
    if package.get("formatVersion") in {"2.3", "2.4"} and not (
        package_root / "manifest/inventory.json"
    ).is_file():
        errors.append("Required file missing: manifest/inventory.json")
    if package.get("formatVersion") == "2.4" and not (
        package_root / "manifest/lineage.json"
    ).is_file():
        errors.append("Required file missing: manifest/lineage.json")
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
    processed_bytes = 0
    total_hash_bytes = sum(size for size, _digest in hash_rows.values())
    last_update = 0.0
    if progress and verify_hashes:
        progress(0, max(total_hash_bytes, 1), f"Validating backup: 0/{len(hash_rows)} files")
    for index, (relative_path, (expected_size, expected_hash)) in enumerate(
        hash_rows.items(), start=1
    ):
        path = package_root / Path(*PurePosixPath(relative_path).parts)
        if not path.is_file():
            continue
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            errors.append(
                f"Grootte wijkt af: {relative_path} ({actual_size} i.p.v. {expected_size})"
            )
            continue
        if verify_hashes:
            file_bytes = 0

            def chunk_progress(chunk_size: int) -> None:
                nonlocal file_bytes, last_update
                file_bytes += chunk_size
                now = time.monotonic()
                if progress and now - last_update >= 0.25:
                    current = processed_bytes + file_bytes
                    percent = (
                        current / total_hash_bytes * 100 if total_hash_bytes else 100
                    )
                    progress(
                        current,
                        max(total_hash_bytes, 1),
                        f"Validating backup: {percent:.1f}% — {index}/{len(hash_rows)} files — "
                        f"{current / 1073741824:.2f}/{total_hash_bytes / 1073741824:.2f} GiB",
                    )
                    last_update = now

            actual_hash = sha256_file(path, chunk_progress)
            checked_hashes += 1
            if actual_hash != expected_hash:
                errors.append(f"Hash wijkt af: {relative_path}")
        processed_bytes += expected_size
        if progress and verify_hashes and index == len(hash_rows):
            progress(
                total_hash_bytes,
                max(total_hash_bytes, 1),
                f"Validating backup: 100.0% — {index}/{len(hash_rows)} files — "
                f"{total_hash_bytes / 1073741824:.2f} GiB",
            )
    checks["hashedFilesChecked"] = checked_hashes
    checks["payloadHashesVerified"] = verify_hashes
    if progress:
        progress(0, 0, "File hashes complete; checking database and manifests...")
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
    database_spawn_edges: set[tuple[str, str, str]] = set()
    database_dynamic_tools: set[tuple[str, int, str, bool]] = set()
    database_sections: set[tuple[str, str, str | None]] = set()
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
            if "thread_spawn_edges" in tables:
                database_spawn_edges = {
                    (str(row[0]), str(row[1]), str(row[2]))
                    for row in connection.execute(
                        "SELECT parent_thread_id,child_thread_id,status FROM thread_spawn_edges"
                    )
                }
            if "thread_dynamic_tools" in tables:
                database_dynamic_tools = {
                    (str(row[0]), int(row[1]), str(row[2]), bool(row[3]))
                    for row in connection.execute(
                        "SELECT thread_id,position,name,defer_loading FROM thread_dynamic_tools"
                    )
                }
            if "thread_sections" in tables:
                section_columns = {
                    str(row[1])
                    for row in connection.execute('PRAGMA table_info("thread_sections")')
                }
                appearance = "appearance" if "appearance" in section_columns else "NULL"
                database_sections = {
                    (str(row[0]), str(row[1]), None if row[2] is None else str(row[2]))
                    for row in connection.execute(
                        f"SELECT id,name,{appearance} FROM thread_sections"
                    )
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

    if package.get("formatVersion") in {"2.2", "2.3", "2.4"}:
        try:
            identity_manifest = read_json(
                package_root / "manifest/project-identities.json"
            )
            for error in project_identity.validate_identity_manifest(identity_manifest):
                errors.append(f"project-identities.json: {error}")
            identity_roots = {
                str(item.get("rootId")): item
                for item in identity_manifest.get("roots", [])
                if isinstance(item, dict)
            }
            project_roots = {str(item.get("id")): item for item in projects}
            if set(identity_roots) != set(project_roots):
                errors.append("Project roots differ between identity and project manifests.")
            for root_id, project in project_roots.items():
                identity = identity_roots.get(root_id, {})
                if project.get("rootIdentityId") != root_id:
                    errors.append(f"Project {root_id} has an inconsistent rootIdentityId.")
                if project.get("projectIdentityId") != identity.get("projectId"):
                    errors.append(f"Project {root_id} has an inconsistent projectIdentityId.")
            counts = package.get("counts", {})
            logical_count = len(
                {str(item.get("projectId")) for item in identity_roots.values()}
            )
            if counts.get("logicalProjects") != logical_count:
                errors.append("counts.logicalProjects differs from project identities.")
            checks["projectIdentitiesChecked"] = len(identity_roots)
        except Exception as exc:
            errors.append(f"project-identities.json is invalid: {exc}")

    project_mappings: list[dict[str, Any]] = []
    attachment_mappings: list[dict[str, Any]] = []
    try:
        mappings = read_json(package_root / "manifest/path-mappings.json")
        mapping_version = mappings.get("mappingVersion")
        if mapping_version not in (1, 2):
            errors.append(f"Unsupported path mapping version: {mapping_version!r}")
        project_mappings = mappings.get("projects", [])
        if not isinstance(project_mappings, list):
            raise ValueError("projects mappings must be a list")
        if mapping_version == 2:
            if mappings.get("locationSchemaVersion") != path_model.LOCATION_SCHEMA_VERSION:
                errors.append("Incorrect locationSchemaVersion in path-mappings.json.")
            for item in project_mappings:
                location_errors = path_model.validate_location(item.get("location"))
                for error in location_errors:
                    errors.append(f"Project mapping {item.get('id')} location: {error}")
        attachment_mappings = mappings.get("attachments", [])
        copied_attachments = [item for item in attachment_mappings if item.get("sourcePresent")]
        missing_attachments = [item for item in attachment_mappings if not item.get("sourcePresent")]
        for item in copied_attachments:
            relative_path = item.get("backupRelativePath", "")
            if not valid_relative_path(relative_path) or not (
                package_root / Path(*PurePosixPath(relative_path).parts)
            ).is_file():
                errors.append(f"Copied attachment is missing: {relative_path}")
        if mapping_version == 2:
            for group_name in ("attachments", "extras"):
                for item in mappings.get(group_name, []):
                    location_errors = path_model.validate_location(item.get("location"))
                    for error in location_errors:
                        errors.append(
                            f"{group_name[:-1].title()} mapping {item.get('id')} location: {error}"
                        )
        counts = package.get("counts", {}) if isinstance(package.get("counts"), dict) else {}
        if counts.get("attachmentsCopied") != len(copied_attachments):
            errors.append("counts.attachmentsCopied differs from path-mappings.json.")
        if counts.get("attachmentsMissing") != len(missing_attachments):
            errors.append("counts.attachmentsMissing differs from path-mappings.json.")
        if missing_attachments:
            warnings.append(
                f"{len(missing_attachments)} historical attachment(s) were missing or unreadable at the source."
            )
        checks["attachmentsCopiedChecked"] = len(copied_attachments)
        checks["portableLocationsChecked"] = (
            len(project_mappings)
            + len(attachment_mappings)
            + len(mappings.get("extras", []))
            if mapping_version == 2
            else 0
        )
    except Exception as exc:
        errors.append(f"path-mappings.json is invalid: {exc}")

    if package.get("formatVersion") in {"2.3", "2.4"}:
        try:
            inventory = read_json(package_root / "manifest/inventory.json")
            if inventory.get("inventoryVersion") != 1:
                errors.append("Unsupported inventoryVersion in inventory.json.")

            conversations = inventory.get("conversations", {})
            conversation_items = conversations.get("items", [])
            if conversation_items != thread_manifest:
                errors.append(
                    "Conversation inventory differs from manifest/threads.json."
                )
            expected_conversation_counts = {
                "total": len(thread_manifest),
                "recent": sum(not bool(item.get("archived")) for item in thread_manifest),
                "archived": sum(bool(item.get("archived")) for item in thread_manifest),
                "pinned": sum(bool(item.get("pinned")) for item in thread_manifest),
                "projectless": sum(
                    bool(item.get("projectless")) for item in thread_manifest
                ),
                "projectLinked": sum(
                    not bool(item.get("projectless")) for item in thread_manifest
                ),
            }
            if conversations.get("counts") != expected_conversation_counts:
                errors.append("Conversation counts in inventory.json are inconsistent.")
            for item in conversation_items:
                archived = bool(item.get("archived"))
                if item.get("state") != ("archived" if archived else "recent"):
                    errors.append(
                        f"Conversation {item.get('id')} has an inconsistent inventory state."
                    )
                expected_collection = (
                    "archived_sessions" if archived else "sessions"
                )
                if item.get("rolloutCollection") != expected_collection:
                    errors.append(
                        f"Conversation {item.get('id')} is stored in the wrong rollout collection."
                    )

            session_inventory = inventory.get("sessions", {})
            inventory_session_items = session_inventory.get("items", [])
            inventory_session_paths = [
                str(item.get("backupRelativePath"))
                for item in inventory_session_items
                if isinstance(item, dict)
            ]
            if len(inventory_session_paths) != len(set(inventory_session_paths)):
                errors.append("Duplicate session path in inventory.json.")
            if set(inventory_session_paths) != session_files:
                errors.append("Session inventory differs from copied rollout files.")
            if session_inventory.get("count") != len(session_files):
                errors.append("Session count in inventory.json is inconsistent.")
            expected_active = sum(
                path.startswith("codex/sessions/") for path in session_files
            )
            expected_archived = sum(
                path.startswith("codex/archived_sessions/") for path in session_files
            )
            if session_inventory.get("active") != expected_active:
                errors.append("Active session count in inventory.json is inconsistent.")
            if session_inventory.get("archived") != expected_archived:
                errors.append("Archived session count in inventory.json is inconsistent.")

            index_inventory = conversations.get("sessionIndex", {})
            index_path = package_root / "codex/session_index.jsonl"
            if bool(index_inventory.get("present")) != index_path.is_file():
                errors.append("session_index presence differs from inventory.json.")
            if index_path.is_file():
                copied_index_ids: list[str] = []
                copied_index_invalid = 0
                with index_path.open(
                    "r", encoding="utf-8-sig", errors="replace"
                ) as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        try:
                            value = json.loads(line)
                            thread_id = value.get("id") or value.get("thread_id")
                            if not thread_id:
                                raise ValueError("missing id/thread_id")
                            copied_index_ids.append(str(thread_id))
                        except Exception:
                            copied_index_invalid += 1
                if sorted(set(copied_index_ids)) != index_inventory.get("threadIds"):
                    errors.append("session_index thread ids differ from inventory.json.")
                if copied_index_invalid != len(index_inventory.get("invalidLines", [])):
                    errors.append("session_index invalid-line count differs from inventory.json.")

            relationships = inventory.get("relationships", {})
            portable_state = read_json(
                package_root / "codex/portable-global-state.json"
            )
            expected_relationship_state = {
                "assignments": portable_state.get("thread-project-assignments", {}),
                "projectlessThreadIds": sorted(
                    str(value)
                    for value in portable_state.get("projectless-thread-ids", [])
                ),
                "workspaceRootHints": portable_state.get(
                    "thread-workspace-root-hints", {}
                ),
                "projectlessOutputDirectories": portable_state.get(
                    "thread-projectless-output-directories", {}
                ),
                "threadWritableRoots": portable_state.get(
                    "thread-writable-roots", {}
                ),
            }
            for key, expected in expected_relationship_state.items():
                if relationships.get(key) != expected:
                    errors.append(
                        f"Portable relationship field {key} differs from the copied state."
                    )
            inventory_edges = {
                (
                    str(item.get("parentThreadId")),
                    str(item.get("childThreadId")),
                    str(item.get("status")),
                )
                for item in relationships.get("spawnEdges", [])
            }
            if inventory_edges != database_spawn_edges:
                errors.append("Spawn-edge inventory differs from the snapshot database.")
            for parent_id, child_id, _status in inventory_edges:
                if parent_id not in manifest_thread_ids or child_id not in manifest_thread_ids:
                    errors.append(
                        f"Spawn edge references an unknown conversation: {parent_id} -> {child_id}"
                    )
            inventory_tools = {
                (
                    str(item.get("threadId")),
                    int(item.get("position")),
                    str(item.get("name")),
                    bool(item.get("deferLoading")),
                )
                for item in relationships.get("dynamicTools", [])
            }
            if inventory_tools != database_dynamic_tools:
                errors.append("Dynamic-tool inventory differs from the snapshot database.")
            if any(item[0] not in manifest_thread_ids for item in inventory_tools):
                errors.append("A dynamic tool references an unknown conversation.")
            inventory_sections = {
                (
                    str(item.get("id")),
                    str(item.get("name")),
                    None if item.get("appearance") is None else str(item.get("appearance")),
                )
                for item in relationships.get("sections", [])
            }
            if inventory_sections != database_sections:
                errors.append("Section inventory differs from the snapshot database.")

            project_inventory = inventory.get("projects", {})
            project_items = project_inventory.get("items", [])
            present_inventory_ids = {
                str(item.get("rootId"))
                for item in project_items
                if item.get("sourcePresent")
            }
            project_ids = {str(item.get("id")) for item in projects}
            if present_inventory_ids != project_ids:
                errors.append("Project inventory differs from copied project payloads.")
            if project_inventory.get("candidateCount") != len(project_items):
                errors.append("Project candidate count in inventory.json is inconsistent.")
            inventory_root_ids = [str(item.get("rootId")) for item in project_items]
            mapping_root_ids = [
                str(item.get("rootIdentityId")) for item in project_mappings
            ]
            if len(inventory_root_ids) != len(set(inventory_root_ids)):
                errors.append("A project root appears more than once in inventory.json.")
            if set(inventory_root_ids) != set(mapping_root_ids):
                errors.append("Project inventory differs from path-mappings.json.")
            expected_missing = sorted(
                [
                    str(item.get("originalPath"))
                    for item in project_items
                    if not item.get("sourcePresent")
                ],
                key=str.lower,
            )
            expected_reparse = sorted(
                [
                    str(item.get("originalPath"))
                    for item in project_items
                    if item.get("reparsePoint")
                ],
                key=str.lower,
            )
            expected_duplicates = sorted(
                [
                    {
                        "path": str(item.get("originalPath")),
                        "origins": item.get("origins", []),
                    }
                    for item in project_items
                    if len(item.get("origins", [])) > 1
                ],
                key=lambda item: item["path"].lower(),
            )
            if project_inventory.get("missingRoots") != expected_missing:
                errors.append("Missing project roots in inventory.json are inconsistent.")
            if project_inventory.get("reparsePointRoots") != expected_reparse:
                errors.append("Reparse-point roots in inventory.json are inconsistent.")
            if project_inventory.get("duplicateRoots") != expected_duplicates:
                errors.append("Duplicate project roots in inventory.json are inconsistent.")
            if project_inventory.get("multiSourceRoots") != expected_duplicates:
                errors.append("Multi-source project roots in inventory.json are inconsistent.")
            if project_inventory.get("overlappingRoots") != project_inventory.get(
                "nestedRoots"
            ):
                errors.append("Overlapping project roots in inventory.json are inconsistent.")
            for item in project_items:
                if item.get("sourcePresent"):
                    relative_path = item.get("backupRelativePath", "")
                    if not valid_relative_path(relative_path) or not (
                        package_root / Path(*PurePosixPath(relative_path).parts)
                    ).is_dir():
                        errors.append(
                            f"Inventoried project payload is missing: {relative_path}"
                        )

            attachment_inventory = inventory.get("attachments", {})
            if attachment_inventory.get("items") != attachment_mappings:
                errors.append("Attachment inventory differs from path-mappings.json.")
            if attachment_inventory.get("copied") != len(
                [item for item in attachment_mappings if item.get("sourcePresent")]
            ):
                errors.append("Copied attachment count in inventory.json is inconsistent.")
            if attachment_inventory.get("missing") != len(
                [item for item in attachment_mappings if not item.get("sourcePresent")]
            ):
                errors.append("Missing attachment count in inventory.json is inconsistent.")
            for attachment in attachment_mappings:
                unknown_threads = set(attachment.get("referencedByThreadIds", [])) - manifest_thread_ids
                if unknown_threads:
                    errors.append(
                        f"Attachment {attachment.get('id')} references unknown conversation(s)."
                    )
            checks["inventoryConversationsChecked"] = len(conversation_items)
            checks["inventoryRelationshipsChecked"] = (
                len(inventory_edges) + len(inventory_tools) + len(inventory_sections)
            )
            checks["inventoryProjectsChecked"] = len(project_items)
        except Exception as exc:
            errors.append(f"inventory.json is invalid: {exc}")

    if package.get("formatVersion") == "2.4":
        try:
            lineage_manifest = read_json(package_root / "manifest/lineage.json")
            for error in lineage.validate_manifest(lineage_manifest):
                errors.append(f"lineage.json: {error}")
            package_lineage = package.get("lineage", {})
            for key in (
                "lineageVersion",
                "backupId",
                "parentBackupId",
                "sourceDeviceId",
                "relation",
            ):
                if package_lineage.get(key) != lineage_manifest.get(key):
                    errors.append(f"package lineage field {key} is inconsistent.")
            if lineage_manifest.get("backupId") == lineage_manifest.get("parentBackupId"):
                errors.append("A backup cannot be its own parent.")
            if bool(lineage_manifest.get("parentBackupId")) != (
                lineage_manifest.get("relation") in {"linear", "diverged"}
            ):
                errors.append("Lineage relation is inconsistent with parentBackupId.")

            replacements = lineage.portable_replacements(package, mappings)
            for item in lineage_manifest.get("items", []):
                if item.get("state") == "removed":
                    continue
                payload_path = item.get("payloadRelativePath")
                payload_kind = item.get("payloadKind")
                selected_rows: list[dict[str, Any]] = []
                empty_tree_exists = False
                if payload_path:
                    if not valid_relative_path(str(payload_path)):
                        errors.append(
                            f"Lineage item {item.get('key')} has an invalid payload path."
                        )
                        continue
                    if payload_kind == "file":
                        if str(payload_path) in hash_rows:
                            size, digest = hash_rows[str(payload_path)]
                            selected_rows.append(
                                {
                                    "relative_path": str(payload_path),
                                    "size": size,
                                    "sha256": digest,
                                }
                            )
                    elif payload_kind == "tree":
                        payload_directory = package_root / Path(
                            *PurePosixPath(str(payload_path)).parts
                        )
                        if payload_directory.is_dir():
                            try:
                                empty_tree_exists = not any(
                                    candidate.is_file()
                                    for candidate in payload_directory.rglob("*")
                                )
                            except OSError:
                                empty_tree_exists = False
                        if str(payload_path) in hash_rows:
                            size, digest = hash_rows[str(payload_path)]
                            selected_rows.append(
                                {
                                    "relative_path": str(payload_path),
                                    "size": size,
                                    "sha256": digest,
                                }
                            )
                        prefix = str(payload_path).rstrip("/") + "/"
                        selected_rows.extend(
                            {
                                "relative_path": relative,
                                "size": size,
                                "sha256": digest,
                            }
                            for relative, (size, digest) in hash_rows.items()
                            if relative.startswith(prefix)
                        )
                    elif payload_kind != "none":
                        errors.append(
                            f"Lineage item {item.get('key')} has an invalid payload kind."
                        )
                    if (
                        payload_kind != "none"
                        and not selected_rows
                        and not (payload_kind == "tree" and empty_tree_exists)
                    ):
                        errors.append(
                            f"Lineage item {item.get('key')} does not resolve to payload data."
                        )
                semantic_item = item.get("kind") in {
                    "conversation", "codex-profile", "codex-state"
                }
                for row in selected_rows:
                    original_relative = str(row["relative_path"])
                    if payload_kind == "file" or original_relative == str(payload_path):
                        row["relative_path"] = PurePosixPath(original_relative).name
                    else:
                        row["relative_path"] = original_relative[
                            len(str(payload_path).rstrip("/") + "/") :
                        ]
                    if semantic_item:
                        row["sha256"] = lineage.semantic_file_digest(
                            package_root
                            / Path(*PurePosixPath(original_relative).parts),
                            replacements,
                        )
                        row["size"] = 0
                actual_fingerprint = lineage.aggregate_fingerprint(
                    selected_rows, item.get("metadata")
                )
                if actual_fingerprint != item.get("currentFingerprint"):
                    errors.append(
                        f"Lineage fingerprint differs for item {item.get('key')}."
                    )
            checks["lineageItemsChecked"] = len(lineage_manifest.get("items", []))
            checks["lineageRelation"] = lineage_manifest.get("relation")
        except Exception as exc:
            errors.append(f"lineage.json is invalid: {exc}")

    if progress:
        progress(0, 0, "Checking backup history and portable relationships...")
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

    if progress:
        progress(1, 1, "Backup validation complete")
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
    parser = argparse.ArgumentParser(description="Validate Codex Portable Backup 2.x")
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
