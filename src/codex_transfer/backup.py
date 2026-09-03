#!/usr/bin/env python3
"""Build a Codex Portable Backup Package 2.x without modifying the source."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

from . import atomic_io, lineage, path_model, project_identity, windows


FORMAT_ID = "codex-portable-backup"
FORMAT_VERSION = "2.4"
GENERATOR_VERSION = "3.4.4"
PROGRESS_CALLBACK = None
STATUS_CALLBACK = None
_RUNTIME_EXECUTABLE: Path | None = None
_RUNTIME_DIRECTORY: tempfile.TemporaryDirectory[str] | None = None
PORTABLE_STATE_KEYS = (
    "local-projects",
    "project-order",
    "projectless-thread-ids",
    "thread-project-assignments",
    "thread-workspace-root-hints",
    "thread-projectless-output-directories",
    "thread-writable-roots",
    "electron-saved-workspace-roots",
)
BLOCKED_CODEX_NAMES = {
    "auth.json",
    "installation_id",
    "cap_sid",
    "state_5.sqlite-wal",
    "state_5.sqlite-shm",
}
BLOCKED_CODEX_DIRS = {
    ".sandbox",
    ".sandbox-bin",
    ".sandbox-secrets",
    ".tmp",
    "tmp",
    "cache",
    "computer-use",
    "node_repl",
    "plugins",
    "process_manager",
    "thread-writer-locks",
}
ATTACHMENT_PATTERN = re.compile(
    r"(?i)([a-z]:[\\/][^\x00\r\n\"<>|?*]{1,2048}?\.(?:png|jpe?g|webp|gif|bmp|pdf|docx?|xlsx?|pptx?|csv|zip))"
)


class BackupError(RuntimeError):
    pass


def required_backup_space(estimated_bytes: int) -> int:
    """Return the conservative destination-space requirement for a backup."""
    return int(max(estimated_bytes, 0) * 1.05) + 100 * 1024 * 1024


def ensure_backup_space(estimated_bytes: int, free_bytes: int) -> int:
    required_bytes = required_backup_space(estimated_bytes)
    if free_bytes < required_bytes:
        raise BackupError(
            f"Insufficient free space. Approximately {required_bytes:,} bytes required; "
            f"{free_bytes:,} bytes available."
        )
    return required_bytes


def stage_runtime_executable() -> Path | None:
    """Keep a stable copy of the one-file app for inclusion in later backups."""
    global _RUNTIME_DIRECTORY, _RUNTIME_EXECUTABLE
    if not getattr(sys, "frozen", False):
        return None
    if _RUNTIME_EXECUTABLE and _RUNTIME_EXECUTABLE.is_file():
        return _RUNTIME_EXECUTABLE

    source = Path(sys.executable)
    if not source.is_file():
        raise BackupError(
            "Codex Lifeboat cannot access its own executable. Extract the downloaded "
            "ZIP first, then run Codex-Lifeboat.exe from the extracted folder."
        )

    runtime_directory = tempfile.TemporaryDirectory(prefix="Codex-Lifeboat-runtime-")
    staged = Path(runtime_directory.name) / "Codex-Lifeboat.exe"
    try:
        shutil.copy2(source, staged)
        if staged.stat().st_size != source.stat().st_size:
            raise OSError("the staged executable has an unexpected size")
    except OSError as exc:
        runtime_directory.cleanup()
        raise BackupError(
            "Codex Lifeboat could not prepare its executable for the portable backup. "
            "Extract the downloaded ZIP to a normal local folder and start it again. "
            f"Windows reported: {exc}"
        ) from exc

    _RUNTIME_DIRECTORY = runtime_directory
    _RUNTIME_EXECUTABLE = staged
    return staged


def log(message: str) -> None:
    if sys.stdout is not None:
        print(message, flush=True)
    if PROGRESS_CALLBACK:
        try:
            PROGRESS_CALLBACK(message)
        except Exception:
            pass


def set_progress_callback(callback) -> None:
    global PROGRESS_CALLBACK
    PROGRESS_CALLBACK = callback


def set_status_callback(callback) -> None:
    global STATUS_CALLBACK
    STATUS_CALLBACK = callback


def report_status(current: int, total: int, message: str) -> None:
    if STATUS_CALLBACK:
        try:
            STATUS_CALLBACK(current, total, message)
        except Exception:
            pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    atomic_io.write_json(path, value)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path, progress: Callable[[int], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            if progress:
                progress(len(chunk))
    return digest.hexdigest()


def portable_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def clean_windows_path(value: str) -> Path:
    expanded = os.path.expandvars(value).strip().strip('"')
    if expanded.startswith("\\\\?\\"):
        expanded = expanded[4:]
    return Path(expanded).expanduser()


def normalized_source_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False))))


def stable_id(path: Path) -> str:
    return hashlib.sha256(normalized_source_key(path).encode("utf-8")).hexdigest()[:16]


def check_codex_not_running(source_codex_home: Path, allow_running_test: bool) -> None:
    default_home = (Path(os.environ.get("USERPROFILE", "")) / ".codex").resolve(
        strict=False
    )
    if allow_running_test:
        if source_codex_home.resolve(strict=False) == default_home:
            raise BackupError(
                "--allow-running-test mag nooit met de echte gebruikers-.codex worden gebruikt."
            )
        return
    if os.name != "nt":
        return
    completed = subprocess.run(
        ["tasklist.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    running = completed.stdout.lower()
    names = [name for name in ("codex.exe", "chatgpt.exe") if f'"{name}"' in running]
    if names:
        raise BackupError(
            "Codex draait nog ({}). Sluit de app volledig af en start opnieuw.".format(
                ", ".join(names)
            )
        )


def connect_read_only(path: Path) -> sqlite3.Connection:
    uri_path = urllib.parse.quote(path.resolve().as_posix(), safe="/:")
    return sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)


def sqlite_quick_check(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "no result"


def create_snapshot(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = connect_read_only(source)
    source_check = sqlite_quick_check(source_connection)
    if source_check != "ok":
        source_connection.close()
        raise BackupError(f"Source database failed PRAGMA quick_check: {source_check}")
    target_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(target_connection)
        journal_mode = target_connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        if not journal_mode or str(journal_mode[0]).lower() != "delete":
            raise BackupError("Could not normalize the snapshot database journal mode.")
    finally:
        target_connection.close()
        source_connection.close()
    snapshot = sqlite3.connect(destination)
    try:
        check = sqlite_quick_check(snapshot)
        if check != "ok":
            raise BackupError(f"Snapshot faalt PRAGMA quick_check: {check}")
        tables = {
            row[0]
            for row in snapshot.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "threads" not in tables:
            raise BackupError("Snapshot does not contain a 'threads' table.")
        migration_count = (
            snapshot.execute("SELECT count(*) FROM _sqlx_migrations").fetchone()[0]
            if "_sqlx_migrations" in tables
            else 0
        )
        migrations_successful = (
            snapshot.execute(
                "SELECT count(*) FROM _sqlx_migrations WHERE success=1"
            ).fetchone()[0]
            if "_sqlx_migrations" in tables
            else 0
        )
        columns = [
            row[1] for row in snapshot.execute('PRAGMA table_info("threads")')
        ]
        wanted = [
            name
            for name in (
                "id",
                "rollout_path",
                "cwd",
                "title",
                "archived",
                "project_id",
                "created_at",
                "updated_at",
                "cli_version",
                "first_user_message",
                "preview",
                "recency_at",
                "recency_at_ms",
                "history_mode",
                "memory_mode",
                "is_pinned",
            )
            if name in columns
        ]
        quoted = ",".join('"{}"'.format(name.replace('"', '""')) for name in wanted)
        thread_rows = [
            dict(zip(wanted, row))
            for row in snapshot.execute(f"SELECT {quoted} FROM threads ORDER BY id")
        ]
        projects: list[dict[str, Any]] = []
        if "projects" in tables:
            project_columns = [
                row[1] for row in snapshot.execute('PRAGMA table_info("projects")')
            ]
            project_wanted = [
                name for name in ("id", "name", "position") if name in project_columns
            ]
            project_sql = ",".join(f'"{name}"' for name in project_wanted)
            for row in snapshot.execute(f"SELECT {project_sql} FROM projects"):
                projects.append(dict(zip(project_wanted, row)))
        roots: list[dict[str, Any]] = []
        if "project_roots" in tables:
            for row in snapshot.execute(
                "SELECT project_id,position,path FROM project_roots ORDER BY project_id,position"
            ):
                roots.append(
                    {"projectId": row[0], "position": row[1], "path": row[2]}
                )

        def selected_rows(table: str, selected: tuple[str, ...]) -> list[dict[str, Any]]:
            if table not in tables:
                return []
            available = {
                str(row[1]) for row in snapshot.execute(f'PRAGMA table_info("{table}")')
            }
            fields = [name for name in selected if name in available]
            if not fields:
                return []
            selection = ",".join(f'"{name}"' for name in fields)
            return [
                dict(zip(fields, row))
                for row in snapshot.execute(f'SELECT {selection} FROM "{table}"')
            ]

        return {
            "quickCheck": check,
            "schemaMigrationCount": int(migration_count),
            "successfulMigrationCount": int(migrations_successful),
            "tables": sorted(tables),
            "threads": thread_rows,
            "databaseProjects": projects,
            "databaseProjectRoots": roots,
            "threadSections": selected_rows(
                "thread_sections", ("id", "name", "appearance")
            ),
            "threadDynamicTools": selected_rows(
                "thread_dynamic_tools",
                ("thread_id", "position", "name", "defer_loading"),
            ),
            "threadSpawnEdges": selected_rows(
                "thread_spawn_edges",
                ("parent_thread_id", "child_thread_id", "status"),
            ),
        }
    finally:
        snapshot.close()


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(
    source: Path,
    destination: Path,
    exclude_fragments: Iterable[str],
    warnings: list[str],
) -> tuple[int, int]:
    count = 0
    byte_count = 0
    excluded = [value.replace("/", os.sep).lower() for value in exclude_fragments]
    stack: list[tuple[Path, Path]] = [(source, destination)]
    while stack:
        current_source, current_destination = stack.pop()
        current_destination.mkdir(parents=True, exist_ok=True)
        try:
            entries = list(os.scandir(current_source))
        except OSError as exc:
            raise BackupError(f"Cannot read directory: {current_source}: {exc}") from exc
        for entry in entries:
            entry_source = Path(entry.path)
            entry_destination = current_destination / entry.name
            relative_text = os.path.relpath(entry_source, source).lower()
            if any(fragment and fragment in relative_text for fragment in excluded):
                warnings.append(f"Excluded by configuration: {entry_source}")
                continue
            try:
                if entry.is_symlink():
                    warnings.append(f"Symbolic link or reparse point skipped: {entry_source}")
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append((entry_source, entry_destination))
                elif entry.is_file(follow_symlinks=False):
                    copy_file(entry_source, entry_destination)
                    size = entry.stat(follow_symlinks=False).st_size
                    count += 1
                    byte_count += size
                    if count % 1000 == 0:
                        log(f"  ... copied {count} files from {source.name}")
            except OSError as exc:
                raise BackupError(f"Copy failed for {entry_source}: {exc}") from exc
    return count, byte_count


def tree_stats(source: Path, exclude_fragments: Iterable[str]) -> tuple[int, int]:
    count = 0
    byte_count = 0
    excluded = [value.replace("/", os.sep).lower() for value in exclude_fragments]
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        directories[:] = [
            name
            for name in directories
            if not (root_path / name).is_symlink()
            and not any(
                fragment in os.path.relpath(root_path / name, source).lower()
                for fragment in excluded
                if fragment
            )
        ]
        for name in files:
            path = root_path / name
            if path.is_symlink():
                continue
            relative_text = os.path.relpath(path, source).lower()
            if any(fragment in relative_text for fragment in excluded if fragment):
                continue
            try:
                byte_count += path.stat().st_size
                count += 1
            except OSError:
                pass
    return count, byte_count


def tree_stats_with_breakdown(
    source: Path, exclude_fragments: Iterable[str]
) -> tuple[int, int, list[dict[str, Any]]]:
    """Return logical file usage and immediate-child totals without changing data."""
    count = 0
    byte_count = 0
    children: dict[str, dict[str, Any]] = {}
    excluded = [value.replace("/", os.sep).lower() for value in exclude_fragments]
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        directories[:] = [
            name
            for name in directories
            if not (root_path / name).is_symlink()
            and not any(
                fragment in os.path.relpath(root_path / name, source).lower()
                for fragment in excluded
                if fragment
            )
        ]
        for name in files:
            path = root_path / name
            if path.is_symlink():
                continue
            relative = Path(os.path.relpath(path, source))
            relative_text = str(relative).lower()
            if any(fragment in relative_text for fragment in excluded if fragment):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            top = relative.parts[0] if len(relative.parts) > 1 else "(root files)"
            item = children.setdefault(
                top, {"name": top, "fileCount": 0, "totalBytes": 0}
            )
            item["fileCount"] += 1
            item["totalBytes"] += size
            count += 1
            byte_count += size
    return (
        count,
        byte_count,
        sorted(children.values(), key=lambda item: (-item["totalBytes"], item["name"].lower())),
    )


def _portable_profile_stats(source_codex: Path) -> tuple[int, int, list[dict[str, Any]]]:
    handled_names = {
        "sessions",
        "archived_sessions",
        "session_index.jsonl",
        ".codex-global-state.json",
        "state_5.sqlite",
        "state_5.sqlite-wal",
        "state_5.sqlite-shm",
    }
    blocked_names = {value.lower() for value in BLOCKED_CODEX_NAMES}
    blocked_dirs = {value.lower() for value in BLOCKED_CODEX_DIRS}
    total_files = 0
    total_bytes = 0
    details: list[dict[str, Any]] = []
    for entry in sorted(source_codex.iterdir(), key=lambda item: item.name.lower()):
        lowered = entry.name.lower()
        if lowered in {value.lower() for value in handled_names}:
            continue
        if lowered in blocked_names or lowered in blocked_dirs or entry.is_symlink():
            continue
        if entry.is_dir():
            files, size = tree_stats(entry, [])
        elif entry.is_file():
            try:
                files, size = 1, entry.stat().st_size
            except OSError:
                continue
        else:
            continue
        total_files += files
        total_bytes += size
        details.append({"name": entry.name, "fileCount": files, "totalBytes": size})
    details.sort(key=lambda item: (-item["totalBytes"], item["name"].lower()))
    return total_files, total_bytes, details


def build_backup_preview(
    source_profile: Path | None = None,
    source_codex_home: Path | None = None,
    exclude_fragments: Iterable[str] = (),
) -> dict[str, Any]:
    """Inventory selectable backup sources without modifying any source data."""
    profile = (
        source_profile
        or Path(os.environ.get("USERPROFILE", ""))
    ).resolve(strict=False)
    codex_home = (source_codex_home or profile / ".codex").resolve(strict=False)
    source_db = codex_home / "state_5.sqlite"
    if not codex_home.is_dir() or not source_db.is_file():
        raise BackupError(f"Codex source directory is incomplete: {codex_home}")

    excludes = [str(value) for value in exclude_fragments]
    with tempfile.TemporaryDirectory(prefix="Codex-Lifeboat-preview-") as temporary:
        snapshot = Path(temporary) / "state.snapshot.sqlite"
        database_info = create_snapshot(source_db, snapshot)
    portable_state = read_portable_state(codex_home)
    candidates = collect_project_candidates({}, database_info, portable_state)
    from . import portability_audit

    portability = portability_audit.audit(
        profile,
        codex_home,
        extra_project_roots=[str(item["sourcePath"]) for item in candidates],
        include_local_details=True,
    )

    projects: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        source = clean_windows_path(str(item["sourcePath"])).resolve(strict=False)
        report_status(
            index - 1,
            max(len(candidates), 1),
            f"Scanning project {index}/{len(candidates)}: {source.name or source}",
        )
        if source.is_dir() and not broad_or_unsafe_project_path(source, profile, codex_home):
            file_count, total_bytes, folders = tree_stats_with_breakdown(source, excludes)
        else:
            file_count, total_bytes, folders = 0, 0, []
        projects.append(
            {
                "name": str(item.get("name") or source.name or "project"),
                "path": str(source),
                "sourcePresent": source.is_dir(),
                "fileCount": file_count,
                "totalBytes": total_bytes,
                "largestFolders": folders[:8],
                "origins": list(item.get("origins", [])),
                "codexProjectIds": list(item.get("codexProjectIds", [])),
            }
        )

    codex_files = 1
    codex_bytes = source_db.stat().st_size
    codex_details: list[dict[str, Any]] = [
        {"name": "state database", "fileCount": 1, "totalBytes": source_db.stat().st_size}
    ]
    for directory_name in ("sessions", "archived_sessions"):
        directory = codex_home / directory_name
        if not directory.is_dir():
            continue
        files, size = tree_stats(directory, [])
        codex_files += files
        codex_bytes += size
        codex_details.append(
            {"name": directory_name, "fileCount": files, "totalBytes": size}
        )
    profile_files, profile_bytes, profile_details = _portable_profile_stats(codex_home)
    codex_files += profile_files
    codex_bytes += profile_bytes
    codex_details.extend(profile_details)
    index_path = codex_home / "session_index.jsonl"
    if index_path.is_file():
        codex_files += 1
        codex_bytes += index_path.stat().st_size
    state_path = codex_home / ".codex-global-state.json"
    if state_path.is_file():
        codex_files += 1
        codex_bytes += state_path.stat().st_size

    runtime_bytes = 0
    if getattr(sys, "frozen", False):
        executable = stage_runtime_executable()
        if executable and executable.is_file():
            runtime_bytes = executable.stat().st_size
            codex_files += 1
            codex_bytes += runtime_bytes

    codex_details.sort(key=lambda item: (-item["totalBytes"], item["name"].lower()))
    total_project_files = sum(item["fileCount"] for item in projects)
    total_project_bytes = sum(item["totalBytes"] for item in projects)
    report_status(1, 1, "Backup inventory ready")
    return {
        "previewVersion": 1,
        "sourceProfile": str(profile),
        "sourceCodexHome": str(codex_home),
        "conversations": len(database_info.get("threads", [])),
        "codex": {
            "name": "Codex chats, settings and attachments",
            "path": str(codex_home),
            "fileCount": codex_files,
            "totalBytes": codex_bytes,
            "attachmentsMeasured": False,
            "largestFolders": codex_details[:8],
            "locked": True,
        },
        "projects": projects,
        "portabilityAudit": portability,
        "totals": {
            "fileCount": codex_files + total_project_files,
            "totalBytes": codex_bytes + total_project_bytes,
            "projectCount": len(projects),
        },
    }


def parse_session_meta(path: Path) -> tuple[str | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
            first = handle.readline()
        value = json.loads(first)
        if value.get("type") != "session_meta":
            return None, "eerste regel is niet van type session_meta"
        thread_id = (value.get("payload") or {}).get("id")
        if not thread_id:
            return None, "session_meta does not contain payload.id"
        return str(thread_id), None
    except Exception as exc:  # exact error belongs in the report
        return None, str(exc)


def copy_sessions(
    source_codex: Path, package_root: Path
) -> tuple[dict[str, list[str]], list[dict[str, str]], int]:
    by_id: dict[str, list[str]] = {}
    invalid: list[dict[str, str]] = []
    count = 0
    for directory_name in ("sessions", "archived_sessions"):
        source_root = source_codex / directory_name
        if not source_root.exists():
            continue
        for source in sorted(source_root.rglob("*.jsonl")):
            relative = source.relative_to(source_root)
            destination = package_root / "codex" / directory_name / relative
            copy_file(source, destination)
            count += 1
            thread_id, error = parse_session_meta(destination)
            backup_relative = portable_relative(destination, package_root)
            if error:
                invalid.append({"relativePath": backup_relative, "error": error})
            else:
                by_id.setdefault(thread_id or "", []).append(backup_relative)
    return by_id, invalid, count


def read_session_index(source: Path) -> dict[str, Any]:
    """Inventory the optional Recent index without changing or normalizing it."""
    result: dict[str, Any] = {
        "present": source.is_file(),
        "threadIds": [],
        "duplicateThreadIds": [],
        "invalidLines": [],
    }
    if not source.is_file():
        return result
    seen: set[str] = set()
    duplicates: set[str] = set()
    with source.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                thread_id = value.get("id") or value.get("thread_id")
                if not thread_id:
                    raise ValueError("missing id/thread_id")
                thread_id = str(thread_id)
                if thread_id in seen:
                    duplicates.add(thread_id)
                seen.add(thread_id)
            except Exception as exc:
                result["invalidLines"].append(
                    {"line": line_number, "error": str(exc)}
                )
    result["threadIds"] = sorted(seen)
    result["duplicateThreadIds"] = sorted(duplicates)
    return result


def read_portable_state(source_codex: Path) -> dict[str, Any]:
    source = source_codex / ".codex-global-state.json"
    portable: dict[str, Any] = {}
    if source.exists():
        state = read_json(source)
        portable = {key: state[key] for key in PORTABLE_STATE_KEYS if key in state}
    return portable


def export_portable_state(source_codex: Path, package_root: Path) -> dict[str, Any]:
    portable = read_portable_state(source_codex)
    write_json(package_root / "codex" / "portable-global-state.json", portable)
    return portable


def write_portable_state(package_root: Path, portable: dict[str, Any]) -> None:
    write_json(package_root / "codex" / "portable-global-state.json", portable)


def add_project_candidate(
    candidates: dict[str, dict[str, Any]],
    path_value: str,
    name: str | None,
    origin: str,
    required: bool,
    codex_project_id: str | None = None,
) -> None:
    if not path_value:
        return
    path = clean_windows_path(path_value)
    key = normalized_source_key(path)
    candidate = candidates.setdefault(
        key,
        {
            "sourcePath": str(path),
            "name": name or path.name or "project",
            "origins": [],
            "required": False,
            "codexProjectIds": [],
        },
    )
    if origin not in candidate["origins"]:
        candidate["origins"].append(origin)
    candidate["required"] = bool(candidate["required"] or required)
    if codex_project_id and codex_project_id not in candidate["codexProjectIds"]:
        candidate["codexProjectIds"].append(codex_project_id)
    if name and (not candidate.get("name") or candidate["name"] == path.name):
        candidate["name"] = name


def collect_project_candidates(
    config: dict[str, Any], database_info: dict[str, Any], portable_state: dict[str, Any]
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for item in config.get("projects", []):
        add_project_candidate(
            candidates,
            str(item.get("path", "")),
            item.get("name"),
            "config",
            bool(item.get("required", True)),
            str(item.get("codexProjectId")) if item.get("codexProjectId") else None,
        )
    project_names = {
        item.get("id"): item.get("name")
        for item in database_info.get("databaseProjects", [])
    }
    for item in database_info.get("databaseProjectRoots", []):
        add_project_candidate(
            candidates,
            str(item.get("path", "")),
            project_names.get(item.get("projectId")),
            "database.project_roots",
            False,
            str(item.get("projectId")) if item.get("projectId") else None,
        )
    local_projects = portable_state.get("local-projects") or {}
    for project_id, project in local_projects.items():
        if not isinstance(project, dict):
            continue
        for root in project.get("rootPaths") or []:
            add_project_candidate(
                candidates,
                str(root),
                project.get("name") or project_id,
                "global-state.local-projects",
                False,
                str(project_id),
            )
    # Chats zonder formele projectkoppeling kunnen nog steeds in een echte
    # project directory. Prefer the nearest .git root;
    # anders gebruik de concrete cwd. Brede profiel- of schijfroots worden later
    # otherwise be rejected by the safety check.
    existing_roots = list(candidates)
    for thread in database_info.get("threads", []):
        cwd_value = thread.get("cwd")
        if not cwd_value:
            continue
        cwd = clean_windows_path(str(cwd_value))
        if not cwd.is_dir():
            continue
        cwd_key = normalized_source_key(cwd)
        if any(cwd_key == root or cwd_key.startswith(root + os.sep) for root in existing_roots):
            thread_project_id = thread.get("project_id")
            if thread_project_id:
                containing = [
                    root
                    for root in existing_roots
                    if cwd_key == root or cwd_key.startswith(root + os.sep)
                ]
                if containing:
                    closest = max(containing, key=len)
                    candidate = candidates[closest]
                    value = str(thread_project_id)
                    if value not in candidate["codexProjectIds"]:
                        candidate["codexProjectIds"].append(value)
            continue
        anchor = cwd
        for parent in (cwd, *cwd.parents):
            if (parent / ".git").exists():
                anchor = parent
                break
        add_project_candidate(
            candidates,
            str(anchor),
            anchor.name,
            "threads.cwd",
            False,
            str(thread.get("project_id")) if thread.get("project_id") else None,
        )
        existing_roots = list(candidates)
    return sorted(candidates.values(), key=lambda item: item["sourcePath"].lower())


def select_project_candidates(
    candidates: list[dict[str, Any]], excluded_paths: Iterable[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    excluded_keys = {
        normalized_source_key(clean_windows_path(str(value)))
        for value in excluded_paths
        if str(value).strip()
    }
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in candidates:
        key = normalized_source_key(clean_windows_path(str(item["sourcePath"])))
        (excluded if key in excluded_keys else selected).append(item)
    return selected, excluded


def filter_portable_state_for_excluded_projects(
    portable: dict[str, Any], excluded: list[dict[str, Any]]
) -> dict[str, Any]:
    """Keep chats but remove active project registrations intentionally omitted."""
    result = json.loads(json.dumps(portable))
    excluded_project_ids = {
        str(project_id)
        for item in excluded
        for project_id in item.get("codexProjectIds", [])
        if project_id
    }
    if not excluded_project_ids:
        return result
    local_projects = dict(result.get("local-projects") or {})
    for project_id in excluded_project_ids:
        local_projects.pop(project_id, None)
    if "local-projects" in result:
        result["local-projects"] = local_projects
    if "project-order" in result:
        result["project-order"] = [
            value
            for value in (result.get("project-order") or [])
            if str(value) not in excluded_project_ids
        ]
    assignments = dict(result.get("thread-project-assignments") or {})

    def assignment_project_id(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("projectId") or value.get("project_id") or "")
        return str(value)

    affected_threads = {
        str(thread_id)
        for thread_id, assignment in assignments.items()
        if assignment_project_id(assignment) in excluded_project_ids
    }
    for thread_id in affected_threads:
        assignments.pop(thread_id, None)
    if "thread-project-assignments" in result:
        result["thread-project-assignments"] = assignments
    if affected_threads:
        projectless = {
            str(value) for value in (result.get("projectless-thread-ids") or [])
        }
        projectless.update(affected_threads)
        result["projectless-thread-ids"] = sorted(projectless)
    return result


def filter_snapshot_for_excluded_projects(
    snapshot_path: Path,
    database_info: dict[str, Any],
    excluded: list[dict[str, Any]],
) -> set[str]:
    project_ids = {
        str(project_id)
        for item in excluded
        for project_id in item.get("codexProjectIds", [])
        if project_id
    }
    if not project_ids:
        return set()
    connection = sqlite3.connect(snapshot_path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        placeholders = ",".join("?" for _value in project_ids)
        values = tuple(sorted(project_ids))
        with connection:
            if "threads" in tables:
                columns = {
                    str(row[1])
                    for row in connection.execute('PRAGMA table_info("threads")')
                }
                if "project_id" in columns:
                    connection.execute(
                        f'UPDATE "threads" SET "project_id"=NULL '
                        f'WHERE "project_id" IN ({placeholders})',
                        values,
                    )
            if "project_roots" in tables:
                connection.execute(
                    f'DELETE FROM "project_roots" WHERE "project_id" IN ({placeholders})',
                    values,
                )
            if "projects" in tables:
                connection.execute(
                    f'DELETE FROM "projects" WHERE "id" IN ({placeholders})', values
                )
        if sqlite_quick_check(connection) != "ok":
            raise BackupError("Project selection made the snapshot inconsistent.")
    finally:
        connection.close()
    for thread in database_info.get("threads", []):
        if str(thread.get("project_id")) in project_ids:
            thread["project_id"] = None
    database_info["databaseProjects"] = [
        item
        for item in database_info.get("databaseProjects", [])
        if str(item.get("id")) not in project_ids
    ]
    database_info["databaseProjectRoots"] = [
        item
        for item in database_info.get("databaseProjectRoots", [])
        if str(item.get("projectId")) not in project_ids
    ]
    return project_ids


def is_reparse_point(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(
            getattr(os.path, "isjunction", lambda _path: False)(path)
        )
    except OSError:
        return False


def analyze_project_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe root collisions before any payload is copied."""
    roots: list[dict[str, Any]] = []
    nested: list[dict[str, str]] = []
    normalized: list[tuple[str, str]] = []
    for item in candidates:
        source = clean_windows_path(str(item["sourcePath"]))
        key = normalized_source_key(source)
        roots.append(
            {
                "originalPath": str(source),
                "normalizedPath": key,
                "sourcePresent": source.is_dir(),
                "reparsePoint": is_reparse_point(source),
                "origins": list(item.get("origins", [])),
                "codexProjectIds": list(item.get("codexProjectIds", [])),
            }
        )
        normalized.append((key, str(source)))
    for child_key, child_path in normalized:
        parents = [
            (parent_key, parent_path)
            for parent_key, parent_path in normalized
            if child_key != parent_key and child_key.startswith(parent_key + os.sep)
        ]
        if parents:
            _parent_key, parent_path = max(parents, key=lambda value: len(value[0]))
            nested.append({"parentPath": parent_path, "childPath": child_path})
    multi_source = sorted(
        [
            {"path": item["originalPath"], "origins": item["origins"]}
            for item in roots
            if len(item["origins"]) > 1
        ],
        key=lambda item: item["path"].lower(),
    )
    nested = sorted(nested, key=lambda item: item["childPath"].lower())
    return {
        "candidateCount": len(roots),
        "roots": roots,
        "duplicateRoots": multi_source,
        "overlappingRoots": nested,
        "nestedRoots": nested,
        "missingRoots": sorted(
            [item["originalPath"] for item in roots if not item["sourcePresent"]],
            key=str.lower,
        ),
        "reparsePointRoots": sorted(
            [item["originalPath"] for item in roots if item["reparsePoint"]],
            key=str.lower,
        ),
        "multiSourceRoots": multi_source,
    }


def copy_portable_codex_profile(
    source_codex: Path, package_root: Path, warnings: list[str]
) -> list[dict[str, Any]]:
    """Copy all user data not classified as identity/runtime/live database state."""
    destination_root = package_root / "codex" / "portable-profile"
    records: list[dict[str, Any]] = []
    handled_names = {
        "sessions",
        "archived_sessions",
        "session_index.jsonl",
        ".codex-global-state.json",
        "state_5.sqlite",
        "state_5.sqlite-wal",
        "state_5.sqlite-shm",
    }
    for entry in sorted(source_codex.iterdir(), key=lambda item: item.name.lower()):
        lowered = entry.name.lower()
        if lowered in {value.lower() for value in handled_names}:
            continue
        if lowered in {value.lower() for value in BLOCKED_CODEX_NAMES}:
            continue
        if lowered in {value.lower() for value in BLOCKED_CODEX_DIRS}:
            continue
        relative = f"codex/portable-profile/{entry.name}"
        if entry.is_symlink():
            warnings.append(f"Codex symbolic link or reparse point skipped: {entry}")
            continue
        if entry.is_dir():
            count, size = copy_tree(entry, package_root / relative, [], warnings)
        elif entry.is_file():
            copy_file(entry, package_root / relative)
            count, size = 1, entry.stat().st_size
        else:
            continue
        records.append(
            {
                "name": entry.name,
                "backupRelativePath": relative,
                "fileCount": count,
                "totalBytes": size,
            }
        )
    return records


def broad_or_unsafe_project_path(path: Path, source_profile: Path, codex_home: Path) -> bool:
    resolved = path.resolve(strict=False)
    anchors = {
        Path(resolved.anchor).resolve(strict=False),
        source_profile.resolve(strict=False),
        codex_home.resolve(strict=False),
    }
    environment_roots = [
        os.environ.get("WINDIR"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ]
    anchors.update(Path(value).resolve(strict=False) for value in environment_roots if value)
    return resolved in anchors


def copy_projects(
    candidates: list[dict[str, Any]],
    package_root: Path,
    source_profile: Path,
    codex_home: Path,
    known_folders: dict[str, str],
    identity_registry: dict[str, Any],
    exclude_fragments: list[str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    projects: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    for item in candidates:
        source = clean_windows_path(item["sourcePath"])
        legacy_path_id = stable_id(source)
        exists = source.is_dir()
        identity = (
            project_identity.assign_identity(
                identity_registry,
                source,
                str(item.get("name") or source.name or "project"),
                item.get("codexProjectIds", []),
            )
            if exists
            else None
        )
        root_id = str(identity["rootId"]) if identity else f"missing-{legacy_path_id}"
        project_identity_id = str(identity["projectId"]) if identity else None
        relative = f"projects/root-{root_id}"
        location = path_model.describe_location(
            str(source), str(source_profile), known_folders
        )
        mapping = {
            "mappingKind": "project",
            "id": root_id,
            "projectIdentityId": project_identity_id,
            "rootIdentityId": root_id,
            "legacyPathId": legacy_path_id,
            "originalPath": str(source),
            "backupRelativePath": relative,
            "suggestedTargetPath": path_model.suggested_target_expression(location),
            "sourcePresent": exists,
            "location": location,
        }
        mappings.append(mapping)
        if identity:
            identities.append({
                "projectId": project_identity_id,
                "rootId": root_id,
                "legacyPathId": legacy_path_id,
                "name": item.get("name") or source.name or "project",
                "codexProjectIds": identity.get("codexProjectIds", []),
                "matchBasis": identity.get("matchBasis"),
                "gitEvidence": identity.get("gitEvidence", {}),
                "originalPath": str(source),
                "location": location,
                "backupRelativePath": relative,
                "sourcePresent": exists,
            })
        if not exists:
            message = f"Project root no longer exists: {source}"
            if item.get("required"):
                raise BackupError(message + " (required in backup-config.json)")
            warnings.append(message)
            continue
        if broad_or_unsafe_project_path(source, source_profile, codex_home):
            raise BackupError(
                f"Unsafe broad project path rejected: {source}. Select a specific project directory."
            )
        package_resolved = package_root.resolve(strict=False)
        source_resolved = source.resolve(strict=False)
        if normalized_source_key(package_resolved).startswith(
            normalized_source_key(source_resolved) + os.sep
        ):
            raise BackupError(
                f"The temporary backup directory is inside project source {source}; this would recurse."
            )
        log(f"Copying project: {source}")
        file_count, byte_count = copy_tree(
            source, package_root / relative, exclude_fragments, warnings
        )
        projects.append(
            {
                "id": root_id,
                "projectIdentityId": project_identity_id,
                "rootIdentityId": root_id,
                "legacyPathId": legacy_path_id,
                "name": item.get("name") or source.name,
                "originalPath": str(source),
                "location": mapping["location"],
                "backupRelativePath": relative,
                "origins": item.get("origins", []),
                "fileCount": file_count,
                "totalBytes": byte_count,
            }
        )
    return projects, mappings, identities


def nested_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)


def explicit_local_attachment_strings(value: Any) -> Iterable[str]:
    """Yield paths from typed local-file/image message objects only.

    Tool calls and their output frequently mention arbitrary paths. Treating every
    string in a rollout as a conversation attachment creates false positives and
    can make a backup depend on private sandbox files.
    """

    if isinstance(value, list):
        for item in value:
            yield from explicit_local_attachment_strings(item)
        return
    if not isinstance(value, dict):
        return
    item_type = str(value.get("type", "")).casefold()
    if item_type in {
        "local_image",
        "local_file",
        "input_file",
        "input_image",
    }:
        for key in ("path", "local_path", "file_path"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                yield candidate
    for item in value.values():
        if isinstance(item, (dict, list)):
            yield from explicit_local_attachment_strings(item)


def attachment_strings_from_rollout_event(value: Any) -> Iterable[str]:
    """Return only user-supplied attachment candidates from a rollout event."""

    if not isinstance(value, dict):
        return
    event_type = str(value.get("type", ""))
    payload = value.get("payload")
    if not isinstance(payload, dict):
        return
    if event_type == "event_msg" and payload.get("type") == "user_message":
        yield from nested_strings(payload.get("message"))
        yield from explicit_local_attachment_strings(payload)
        return
    if event_type == "event_msg" and payload.get("type") == "item_completed":
        item = payload.get("item")
        if isinstance(item, dict) and item.get("type") == "UserMessage":
            yield from explicit_local_attachment_strings(item.get("content"))
        return
    if (
        event_type == "response_item"
        and payload.get("type") == "message"
        and payload.get("role") == "user"
    ):
        # Modern desktop rollouts also contain a typed UserMessage event. Only
        # accept explicit local-file objects here, because internal review tasks
        # can place complete tool transcripts inside an input_text block.
        yield from explicit_local_attachment_strings(payload.get("content"))


def find_attachment_paths(session_files: Iterable[Path]) -> dict[str, set[str]]:
    results: dict[str, set[str]] = {}
    for session_file in session_files:
        thread_id, _error = parse_session_meta(session_file)
        with session_file.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                if "codex-" not in line.lower() and "appdata" not in line.lower():
                    continue
                try:
                    value = json.loads(line)
                    strings = attachment_strings_from_rollout_event(value)
                except json.JSONDecodeError:
                    continue
                for text in strings:
                    for match in ATTACHMENT_PATTERN.finditer(text):
                        candidate = match.group(1).rstrip(" .")
                        lowered = candidate.lower().replace("/", "\\")
                        if "\\appdata\\local\\temp\\" in lowered or "codex-" in lowered:
                            results.setdefault(candidate, set())
                            if thread_id:
                                results[candidate].add(thread_id)
    return results


def attachment_source_is_file(source: Path) -> bool:
    """Probe an attachment through a testable boundary for Windows access errors."""
    return source.is_file()


def copy_attachments(
    package_root: Path,
    enabled: bool,
    warnings: list[str],
    source_profile: Path,
    known_folders: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not enabled:
        return [], []
    session_files = list((package_root / "codex" / "sessions").rglob("*.jsonl"))
    session_files += list(
        (package_root / "codex" / "archived_sessions").rglob("*.jsonl")
    )
    copied: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    log("Inventorying local conversation attachments...")
    references = find_attachment_paths(session_files)
    for original in sorted(references, key=str.lower):
        source = clean_windows_path(original)
        attachment_id = stable_id(source)
        relative = f"attachments/attachment-{attachment_id}/{source.name}"
        probe_error: OSError | None = None
        try:
            source_exists = attachment_source_is_file(source)
        except OSError as exc:
            source_exists = False
            probe_error = exc
        item = {
            "mappingKind": "attachment",
            "id": attachment_id,
            "originalPath": str(source),
            "backupRelativePath": relative,
            "sourcePresent": source_exists,
            "sourceStatus": (
                "unreadable" if probe_error else ("copied" if source_exists else "missing")
            ),
            "referencedByThreadIds": sorted(references[original]),
            "location": path_model.describe_location(
                str(source), str(source_profile), known_folders
            ),
        }
        if probe_error is not None:
            item["copyError"] = f"{type(probe_error).__name__}: {probe_error}"
            missing.append(item)
            warnings.append(
                f"Historical attachment exists but is unreadable: {source}: {probe_error}"
            )
        elif source_exists:
            destination = package_root / relative
            try:
                copy_file(source, destination)
                item["size"] = source.stat().st_size
                copied.append(item)
            except OSError as exc:
                if destination.exists():
                    try:
                        destination.unlink()
                    except OSError:
                        pass
                item["sourcePresent"] = False
                item["sourceStatus"] = "unreadable"
                item["copyError"] = f"{type(exc).__name__}: {exc}"
                missing.append(item)
                warnings.append(
                    f"Historical attachment exists but is unreadable: {source}: {exc}"
                )
        else:
            missing.append(item)
            warnings.append(f"Historical attachment is no longer available: {source}")
    return copied, missing


def copy_extras(
    config: dict[str, Any],
    package_root: Path,
    warnings: list[str],
    source_profile: Path,
    known_folders: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for index, item in enumerate(config.get("additionalPortablePaths", []), start=1):
        source = clean_windows_path(str(item.get("path", "")))
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(item.get("name") or source.name))
        name = name.strip("-.") or f"extra-{index:03d}"
        if name.lower() in used_names:
            raise BackupError(f"Duplicate additionalPortablePaths name: {name}")
        used_names.add(name.lower())
        relative = f"extra/{name}"
        exists = source.exists()
        mapping = {
            "mappingKind": "extra",
            "id": stable_id(source),
            "originalPath": str(source),
            "backupRelativePath": relative,
            "sourcePresent": exists,
            "location": path_model.describe_location(
                str(source), str(source_profile), known_folders
            ),
        }
        mappings.append(mapping)
        if not exists:
            if item.get("required", True):
                raise BackupError(f"Required extra source does not exist: {source}")
            warnings.append(f"Optional extra source does not exist: {source}")
            continue
        if normalized_source_key(package_root).startswith(
            normalized_source_key(source) + os.sep
        ):
            raise BackupError(
                f"The temporary backup directory is inside extra source {source}; this would recurse."
            )
        if source.is_dir():
            count, size = copy_tree(source, package_root / relative, [], warnings)
        elif source.is_file():
            destination = package_root / relative / source.name
            copy_file(source, destination)
            count, size = 1, source.stat().st_size
            mapping["backupRelativePath"] = portable_relative(destination, package_root)
        else:
            warnings.append(f"Skipped non-regular extra source: {source}")
            continue
        records.append(
            {
                "name": name,
                "originalPath": str(source),
                "location": mapping["location"],
                "backupRelativePath": mapping["backupRelativePath"],
                "fileCount": count,
                "totalBytes": size,
                "reason": item.get("reason", "expliciet geselecteerd"),
            }
        )
    return records, mappings


def unresolved_cwds(
    threads: list[dict[str, Any]], project_candidates: list[dict[str, Any]]
) -> list[str]:
    roots = [
        normalized_source_key(clean_windows_path(item["sourcePath"]))
        for item in project_candidates
        if clean_windows_path(item["sourcePath"]).exists()
    ]
    unresolved: set[str] = set()
    for thread in threads:
        cwd = thread.get("cwd")
        if not cwd:
            continue
        path = clean_windows_path(str(cwd))
        if not path.is_dir():
            continue
        key = normalized_source_key(path)
        if not any(key == root or key.startswith(root + os.sep) for root in roots):
            unresolved.add(str(path))
    return sorted(unresolved, key=str.lower)


def copy_toolkit(package_root: Path, toolkit_root: Path) -> None:
    package_tools = package_root / "tools"
    package_spec = package_root / "spec"
    package_tools.mkdir(parents=True, exist_ok=True)
    package_spec.mkdir(parents=True, exist_ok=True)
    flat_source = (
        toolkit_root
        if (toolkit_root / "Backup-Codex.ps1").is_file()
        else toolkit_root / "tools"
    )
    for name in (
        "Backup-Codex.ps1",
        "Controleer-CodexBackup.ps1",
        "MAAK-Codex-backup.cmd",
        "CONTROLEER-Codex-backup.cmd",
        "backup-config.json",
        "README.md",
    ):
        source = flat_source / name
        if source.is_file():
            copy_file(source, package_tools / name)
    for name in ("backup_codex.py", "validate_backup.py"):
        source = toolkit_root / "tools" / name
        if not source.is_file():
            source = flat_source / name
        if source.is_file():
            copy_file(source, package_tools / name)
    for source in (toolkit_root / "spec").glob("*"):
        if source.is_file():
            copy_file(source, package_spec / source.name)
    # Een PyInstaller-build neemt zichzelf mee, zodat dezelfde USB direct op de
    # destination computer for validation and restoration.
    if getattr(sys, "frozen", False):
        executable = stage_runtime_executable()
        if executable is None:
            raise BackupError("The portable Codex Lifeboat executable is unavailable.")
        copy_file(executable, package_tools / "Codex-Lifeboat.exe")


def find_peer_lineage(
    destination_root: Path, parent_backup_id: str | None, backup_id: str
) -> dict[str, Any] | None:
    if not parent_backup_id:
        return None
    candidates: list[dict[str, Any]] = []
    for directory in destination_root.glob("Codex-PortableBackup-*"):
        package_path = directory / "manifest" / "package.json"
        lineage_path = directory / "manifest" / "lineage.json"
        if not package_path.is_file() or not lineage_path.is_file():
            continue
        try:
            package = read_json(package_path)
            value = read_json(lineage_path)
        except Exception:
            continue
        if package.get("backupComplete") is not True:
            continue
        if (
            value.get("backupId") != backup_id
            and value.get("backupId") != parent_backup_id
            and value.get("parentBackupId") == parent_backup_id
            and not lineage.validate_manifest(value)
        ):
            candidates.append(value)
    return max(candidates, key=lambda item: str(item.get("createdAtUtc", ""))) if candidates else None


def build_lineage_items(
    package_root: Path,
    hash_rows: list[dict[str, Any]],
    threads: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    attachment_mappings: list[dict[str, Any]],
    extras: list[dict[str, Any]],
    portable_profile: list[dict[str, Any]],
    replacements: list[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    by_path = {str(item["relative_path"]): item for item in hash_rows}
    last_semantic_update = 0.0
    log("Analyzing backup change history with bounded memory...")

    def selected(
        path: str, payload_kind: str, semantic: bool
    ) -> list[dict[str, Any]]:
        nonlocal last_semantic_update
        if payload_kind == "file":
            rows = [by_path[path]] if path in by_path else []
        elif path in by_path:
            rows = [by_path[path]]
        else:
            prefix = path.rstrip("/") + "/"
            rows = [item for relative, item in by_path.items() if relative.startswith(prefix)]
        normalized: list[dict[str, Any]] = []
        for item in rows:
            value = dict(item)
            original_relative = str(item["relative_path"])
            if payload_kind == "file" or original_relative == path:
                value["relative_path"] = PurePosixPath(original_relative).name
            else:
                value["relative_path"] = original_relative[len(path.rstrip("/") + "/") :]
            if semantic:
                source_path = package_root / Path(
                    *PurePosixPath(original_relative).parts
                )
                file_size = max(int(item.get("size", 0)), 1)
                processed = 0

                def semantic_progress(chunk_size: int) -> None:
                    nonlocal processed, last_semantic_update
                    processed += chunk_size
                    now = time.monotonic()
                    if now - last_semantic_update >= 0.25 or processed >= file_size:
                        percent = min(processed / file_size * 100, 100)
                        report_status(
                            min(processed, file_size),
                            file_size,
                            f"Analyzing change history: {percent:.1f}% — "
                            f"{PurePosixPath(original_relative).name} — "
                            f"{processed / 1048576:.1f}/{file_size / 1048576:.1f} MiB",
                        )
                        last_semantic_update = now

                value["sha256"] = lineage.semantic_file_digest(
                    source_path,
                    replacements,
                    semantic_progress,
                )
                value["size"] = 0
            normalized.append(value)
        return normalized

    result: dict[str, dict[str, Any]] = {}

    def add(
        key: str,
        kind: str,
        item_id: str,
        payload_path: str | None,
        payload_kind: str,
        metadata: Any,
        semantic: bool = False,
    ) -> None:
        rows = selected(payload_path, payload_kind, semantic) if payload_path else []
        result[key] = {
            "key": key,
            "kind": kind,
            "id": item_id,
            "payloadRelativePath": payload_path,
            "payloadKind": payload_kind,
            "metadata": metadata,
            "fingerprint": lineage.aggregate_fingerprint(rows, metadata),
        }

    for item in threads:
        add(
            f"conversation/{item['id']}",
            "conversation",
            str(item["id"]),
            str(item["backupRelativePath"]),
            "file",
            {
                key: item.get(key)
                for key in (
                    "title", "archived", "pinned", "projectless", "projectId",
                    "historyMode", "memoryMode",
                )
            },
            True,
        )
    for item in projects:
        add(
            f"project/{item['id']}", "project", str(item["id"]),
            str(item["backupRelativePath"]), "tree",
            {"projectIdentityId": item.get("projectIdentityId"), "name": item.get("name")},
        )
    for item in attachment_mappings:
        attachment_path = (
            str(item["backupRelativePath"]) if item.get("sourcePresent") else None
        )
        attachment_hash = (
            str(by_path.get(attachment_path, {}).get("sha256", ""))
            if attachment_path
            else ""
        )
        attachment_identity = hashlib.sha256(
            json.dumps(
                {
                    "name": Path(str(item.get("originalPath", "attachment"))).name.casefold(),
                    "content": attachment_hash,
                    "threads": item.get("referencedByThreadIds", []),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        add(
            f"attachment/{attachment_identity}", "attachment", attachment_identity,
            attachment_path,
            "file" if item.get("sourcePresent") else "none",
            {
                "sourcePresent": bool(item.get("sourcePresent")),
                "name": Path(str(item.get("originalPath", "attachment"))).name,
                "referencedByThreadIds": item.get("referencedByThreadIds", []),
            },
        )
    for index, item in enumerate(extras):
        item_id = str(item.get("name") or index)
        path = str(item["backupRelativePath"])
        add(f"extra/{item_id}", "extra", item_id, path, "tree", {"name": item_id})
    for item in portable_profile:
        item_id = str(item["name"])
        path = str(item["backupRelativePath"])
        add(
            f"codex-profile/{item_id}", "codex-profile", item_id, path,
            "file" if int(item.get("fileCount", 0)) == 1 and (Path(path).suffix) else "tree",
            {"name": item_id}, True,
        )
    for item_id, path in (
        ("portable-global-state", "codex/portable-global-state.json"),
        ("session-index", "codex/session_index.jsonl"),
    ):
        if path in by_path:
            add(
                f"codex-state/{item_id}", "codex-state", item_id, path,
                "file", None, True,
            )
    log("Backup change-history analysis completed.")
    return result


def create_hash_manifest(
    package_root: Path,
    finalize: Callable[[list[dict[str, Any]]], Path | None] | None = None,
) -> tuple[int, int, str]:
    excluded = {
        "manifest/package.json",
        "manifest/package.json.sha256",
        "manifest/sha256.csv",
    }
    paths = [
        path
        for path in package_root.rglob("*")
        if path.is_file() and portable_relative(path, package_root) not in excluded
    ]
    paths.sort(key=lambda path: portable_relative(path, package_root).lower())
    manifest_path = package_root / "manifest" / "sha256.csv"
    total_file_bytes = sum(path.stat().st_size for path in paths)
    total_bytes = 0
    hash_rows: list[dict[str, Any]] = []
    last_update = 0.0
    manifest_digest = hashlib.sha256()
    report_status(0, max(total_file_bytes, 1), f"Hashing backup: 0/{len(paths)} files")
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        class DigestingWriter:
            def write(self, value: str) -> int:
                manifest_digest.update(value.encode("utf-8"))
                return handle.write(value)

        writer = csv.writer(DigestingWriter(), lineterminator="\n")
        writer.writerow(("relative_path", "size", "sha256"))
        for index, path in enumerate(paths, start=1):
            size = path.stat().st_size
            file_bytes = 0

            def chunk_progress(chunk_size: int) -> None:
                nonlocal file_bytes, last_update
                file_bytes += chunk_size
                now = time.monotonic()
                if now - last_update >= 0.25:
                    current = total_bytes + file_bytes
                    percent = (
                        current / total_file_bytes * 100 if total_file_bytes else 100
                    )
                    report_status(
                        current,
                        max(total_file_bytes, 1),
                        f"Hashing backup: {percent:.1f}% — {index}/{len(paths)} files — "
                        f"{current / 1073741824:.2f}/{total_file_bytes / 1073741824:.2f} GiB",
                    )
                    last_update = now

            relative_path = portable_relative(path, package_root)
            digest = sha256_file(path, chunk_progress)
            writer.writerow((relative_path, size, digest))
            hash_rows.append(
                {"relative_path": relative_path, "size": size, "sha256": digest}
            )
            total_bytes += size
            now = time.monotonic()
            if now - last_update >= 0.25 or index == len(paths):
                percent = (total_bytes / total_file_bytes * 100) if total_file_bytes else 100
                message = (
                    f"Hashing backup: {percent:.1f}% — {index}/{len(paths)} files — "
                    f"{total_bytes / 1073741824:.2f}/{total_file_bytes / 1073741824:.2f} GiB"
                )
                report_status(total_bytes, max(total_file_bytes, 1), message)
                last_update = now
            if index % 1000 == 0 or index == len(paths):
                log(f"  ... hashed {index}/{len(paths)} files ({total_bytes / 1073741824:.2f} GiB)")
        if finalize:
            report_status(
                0,
                0,
                "File hashing complete; analyzing backup change history...",
            )
            generated = finalize(hash_rows)
            if generated is not None:
                relative_path = portable_relative(generated, package_root)
                size = generated.stat().st_size
                digest = sha256_file(generated)
                writer.writerow((relative_path, size, digest))
                hash_rows.append(
                    {"relative_path": relative_path, "size": size, "sha256": digest}
                )
                total_bytes += size
        log("Hash manifest finalized; preparing fast structural checks...")
    report_status(0, 0, "Hash manifest complete; preparing structural checks...")
    return len(hash_rows), total_bytes, manifest_digest.hexdigest()


def write_package_manifest(package_root: Path, package: dict[str, Any]) -> None:
    package_path = package_root / "manifest" / "package.json"
    write_json(package_path, package)
    sidecar = package_root / "manifest" / "package.json.sha256"
    atomic_io.write_text(sidecar, sha256_file(package_path) + "\n", encoding="ascii")


def run_validator(
    package_root: Path,
    validator: Path,
    allow_building: bool,
    verify_hashes: bool = True,
) -> None:
    try:
        from .validate import validate
    except ImportError:
        try:
            from validate import validate
        except ImportError:
            validate = None
    if validate is not None:
        result = validate(
            package_root,
            allow_building,
            progress=lambda current, total, message: report_status(
                current, total, message
            ),
            verify_hashes=verify_hashes,
        )
        if not result.get("valid"):
            for error in result.get("errors", []):
                log(f"FOUT: {error}")
            raise BackupError("Independent package validation failed.")
        log("Independent package validation passed.")
        return
    command = [sys.executable, str(validator), str(package_root)]
    if allow_building:
        command.append("--allow-building")
    if not verify_hashes:
        command.append("--skip-hashes")
    completed = subprocess.run(command, text=True, check=False)
    if completed.returncode != 0:
        raise BackupError(
            f"Independent package validation failed (code {completed.returncode})."
        )


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BackupError(f"Configuration file not found: {path}")
    config = read_json(path)
    if config.get("configVersion") != 1:
        raise BackupError("backup-config.json moet configVersion 1 hebben.")
    if not isinstance(config.get("projects", []), list):
        raise BackupError("config.projects moet een lijst zijn.")
    if not isinstance(config.get("additionalPortablePaths", []), list):
        raise BackupError("config.additionalPortablePaths moet een lijst zijn.")
    if not isinstance(config.get("excludedProjectPaths", []), list):
        raise BackupError("config.excludedProjectPaths must be a list.")
    return config


def build_backup(args: argparse.Namespace) -> Path:
    script_path = Path(__file__).resolve()
    toolkit_root = script_path.parent.parent
    config_path = Path(args.config).resolve() if args.config else toolkit_root / "backup-config.json"
    config = load_config(config_path)
    source_profile = (
        clean_windows_path(args.source_profile)
        if args.source_profile
        else Path(os.environ.get("USERPROFILE", "")).resolve()
    ).resolve(strict=False)
    source_codex = (
        clean_windows_path(args.source_codex_home)
        if args.source_codex_home
        else source_profile / ".codex"
    ).resolve(strict=False)
    source_known_folders = windows.known_folders(source_profile)
    configured_known_folders = config.get("knownFolders")
    if isinstance(configured_known_folders, dict):
        source_known_folders.update(
            {
                str(key).casefold(): str(value)
                for key, value in configured_known_folders.items()
                if value
            }
        )
    configured_registry = config.get("projectRegistryPath")
    identity_registry_path = (
        clean_windows_path(str(configured_registry)).resolve(strict=False)
        if configured_registry
        else windows.project_registry_path(source_profile).resolve(strict=False)
    )
    identity_registry = project_identity.load_registry(identity_registry_path)
    configured_lineage_state = config.get("lineageStatePath")
    lineage_state_path = (
        clean_windows_path(str(configured_lineage_state)).resolve(strict=False)
        if configured_lineage_state
        else windows.lineage_state_path(source_profile).resolve(strict=False)
    )
    configured_device_state = config.get("deviceStatePath")
    device_state_path = (
        clean_windows_path(str(configured_device_state)).resolve(strict=False)
        if configured_device_state
        else windows.device_state_path(source_profile).resolve(strict=False)
    )
    lineage_state = lineage.load_state(lineage_state_path)
    source_device_id = lineage.load_or_create_device_id(device_state_path)
    backup_id = str(uuid.uuid4())
    created_at_utc = utc_now()
    destination_root = clean_windows_path(
        args.destination or str(config.get("destinationRoot", "D:\\Codex-Backups"))
    ).resolve(strict=False)
    if not source_codex.is_dir():
        raise BackupError(f"Codex source directory not found: {source_codex}")
    source_db = source_codex / "state_5.sqlite"
    if not source_db.is_file():
        raise BackupError(f"Codex database not found: {source_db}")
    check_codex_not_running(source_codex, bool(args.allow_running_test))
    destination_root.mkdir(parents=True, exist_ok=True)
    if normalized_source_key(destination_root).startswith(normalized_source_key(source_codex) + os.sep):
        raise BackupError("The destination directory cannot be inside the Codex source directory.")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    final_name = f"Codex-PortableBackup-{stamp}"
    final_path = destination_root / final_name
    if final_path.exists():
        final_path = destination_root / f"{final_name}-{uuid.uuid4().hex[:6]}"
    building = destination_root / f".building-{final_path.name}-{uuid.uuid4().hex[:8]}"
    building.mkdir(parents=True)
    error_path = building / "reports" / "backup-error.txt"
    warnings: list[str] = []
    lineage_manifest: dict[str, Any] | None = None

    try:
        log(f"Temporary package: {building}")
        report_status(0, 0, "Step 1/6 — Creating a consistent Codex snapshot...")
        database_info = create_snapshot(
            source_db, building / "codex" / "state.snapshot.sqlite"
        )
        log(
            f"SQLite snapshot is consistent; found {len(database_info['threads'])} conversations."
        )
        portable_state = read_portable_state(source_codex)
        portable_profile = copy_portable_codex_profile(source_codex, building, warnings)
        all_candidates = collect_project_candidates(config, database_info, portable_state)
        from . import portability_audit

        portability = portability_audit.audit(
            source_profile,
            source_codex,
            extra_project_roots=[str(item["sourcePath"]) for item in all_candidates],
        )
        write_json(building / "reports" / "portability-audit.json", portability)
        portability_summary = portability.get("summary") or {}
        portability_needs_review = int(
            portability_summary.get("needsReviewReferences", 0)
        )
        portability_review_fields = int(
            portability_summary.get("fieldsNeedingReview", 0)
        )
        if portability_needs_review or portability_summary.get("scanErrors"):
            warnings.append(
                "Portability audit found "
                f"{portability_needs_review} path reference(s) in "
                f"{portability_review_fields} field(s) that need review; "
                "no source path values were written to the audit report."
            )
        candidates, excluded_candidates = select_project_candidates(
            all_candidates, config.get("excludedProjectPaths", [])
        )
        excluded_project_ids = filter_snapshot_for_excluded_projects(
            building / "codex" / "state.snapshot.sqlite",
            database_info,
            excluded_candidates,
        )
        portable_state = filter_portable_state_for_excluded_projects(
            portable_state, excluded_candidates
        )
        write_portable_state(building, portable_state)
        if excluded_candidates:
            warnings.append(
                f"{len(excluded_candidates)} project(s) intentionally excluded from project-file backup; "
                "their conversations remain included as projectless history."
            )
        project_analysis = analyze_project_candidates(candidates)
        if project_analysis["nestedRoots"]:
            warnings.append(
                f"{len(project_analysis['nestedRoots'])} nested project root(s) detected and inventoried."
            )
        if project_analysis["reparsePointRoots"]:
            warnings.append(
                f"{len(project_analysis['reparsePointRoots'])} project root reparse point(s) detected and inventoried."
            )
        excludes = [str(item) for item in config.get("excludeDirectoryNames", [])]

        report_status(0, 0, "Step 2/6 — Calculating required backup space...")
        estimated_bytes = source_db.stat().st_size
        for directory_name in ("sessions", "archived_sessions"):
            directory = source_codex / directory_name
            if directory.is_dir():
                estimated_bytes += tree_stats(directory, [])[1]
        for item in candidates:
            path = clean_windows_path(item["sourcePath"])
            if path.is_dir() and not broad_or_unsafe_project_path(path, source_profile, source_codex):
                estimated_bytes += tree_stats(path, excludes)[1]
        free_bytes = shutil.disk_usage(destination_root).free
        ensure_backup_space(estimated_bytes, free_bytes)

        report_status(0, 0, "Step 3/6 — Copying conversations and selected projects...")
        session_map, invalid_sessions, session_count = copy_sessions(source_codex, building)
        if invalid_sessions:
            write_json(building / "reports" / "invalid-sessions.json", invalid_sessions)
            raise BackupError(
                f"{len(invalid_sessions)} session file(s) contain invalid metadata."
            )
        index_source = source_codex / "session_index.jsonl"
        session_index = read_session_index(index_source)
        index_thread_ids = set(session_index["threadIds"])
        if session_index["invalidLines"]:
            warnings.append(
                f"session_index.jsonl contains {len(session_index['invalidLines'])} invalid line(s); the original file is preserved."
            )
        if session_index["duplicateThreadIds"]:
            warnings.append(
                f"session_index.jsonl contains {len(session_index['duplicateThreadIds'])} duplicate thread id(s)."
            )

        thread_manifest: list[dict[str, Any]] = []
        missing_rollouts: list[str] = []
        duplicate_rollouts: list[str] = []
        for row in database_info["threads"]:
            thread_id = str(row.get("id", ""))
            matches = session_map.get(thread_id, [])
            if not matches:
                missing_rollouts.append(thread_id)
            if len(matches) > 1:
                duplicate_rollouts.append(thread_id)
            thread_manifest.append(
                {
                    "id": thread_id,
                    "title": row.get("title"),
                    "cwd": row.get("cwd"),
                    "archived": bool(row.get("archived")),
                    "state": "archived" if bool(row.get("archived")) else "recent",
                    "pinned": bool(row.get("is_pinned")),
                    "projectless": not bool(row.get("project_id")),
                    "projectId": row.get("project_id"),
                    "createdAt": row.get("created_at"),
                    "updatedAt": row.get("updated_at"),
                    "recencyAt": row.get("recency_at"),
                    "recencyAtMs": row.get("recency_at_ms"),
                    "historyMode": row.get("history_mode"),
                    "memoryMode": row.get("memory_mode"),
                    "indexPresent": thread_id in index_thread_ids,
                    "originalRolloutPath": row.get("rollout_path"),
                    "backupRelativePath": matches[0] if len(matches) == 1 else None,
                    "rolloutCollection": (
                        matches[0].split("/")[1]
                        if len(matches) == 1 and matches[0].startswith("codex/")
                        else None
                    ),
                }
            )
        if missing_rollouts or duplicate_rollouts:
            write_json(
                building / "reports" / "rollout-errors.json",
                {"missingThreadIds": missing_rollouts, "duplicateThreadIds": duplicate_rollouts},
            )
            raise BackupError(
                f"Rollout validation failed: {len(missing_rollouts)} missing, "
                f"{len(duplicate_rollouts)} duplicate."
            )

        if index_source.is_file():
            copy_file(index_source, building / "codex" / "session_index.jsonl")

        projects, project_mappings, project_identities = copy_projects(
            candidates,
            building,
            source_profile,
            source_codex,
            source_known_folders,
            identity_registry,
            excludes,
            warnings,
        )
        unresolved = unresolved_cwds(database_info["threads"], candidates)
        for cwd in unresolved:
            warnings.append(
                f"Existing conversation working directory is outside selected projects: {cwd}"
            )

        attachment_records, missing_attachments = copy_attachments(
            building,
            bool(config.get("includeAttachments", True)),
            warnings,
            source_profile,
            source_known_folders,
        )
        extras, extra_mappings = copy_extras(
            config, building, warnings, source_profile, source_known_folders
        )

        orphan_session_ids = sorted(set(session_map) - {item["id"] for item in thread_manifest})
        if orphan_session_ids:
            warnings.append(
                f"{len(orphan_session_ids)} rollout(s) are absent from the snapshot database."
            )

        inventory_thread_ids = {item["id"] for item in thread_manifest}
        session_index["missingThreadIds"] = sorted(
            inventory_thread_ids - index_thread_ids
        )
        session_index["extraThreadIds"] = sorted(
            index_thread_ids - inventory_thread_ids
        )
        session_records = [
            {
                "threadId": thread_id,
                "backupRelativePath": relative,
                "collection": relative.split("/")[1],
                "orphan": thread_id not in inventory_thread_ids,
            }
            for thread_id, relatives in sorted(session_map.items())
            for relative in relatives
        ]
        project_mapping_by_path = {
            normalized_source_key(clean_windows_path(item["originalPath"])): item
            for item in project_mappings
        }
        project_inventory = []
        for root in project_analysis["roots"]:
            mapping = project_mapping_by_path.get(root["normalizedPath"], {})
            project_inventory.append(
                {
                    **root,
                    "rootId": mapping.get("rootIdentityId"),
                    "projectIdentityId": mapping.get("projectIdentityId"),
                    "backupRelativePath": mapping.get("backupRelativePath"),
                    "location": mapping.get("location"),
                }
            )
        inventory = {
            "inventoryVersion": 1,
            "conversations": {
                "items": thread_manifest,
                "counts": {
                    "total": len(thread_manifest),
                    "recent": sum(not item["archived"] for item in thread_manifest),
                    "archived": sum(item["archived"] for item in thread_manifest),
                    "pinned": sum(item["pinned"] for item in thread_manifest),
                    "projectless": sum(item["projectless"] for item in thread_manifest),
                    "projectLinked": sum(not item["projectless"] for item in thread_manifest),
                },
                "sessionIndex": session_index,
            },
            "relationships": {
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
                "spawnEdges": [
                    {
                        "parentThreadId": item.get("parent_thread_id"),
                        "childThreadId": item.get("child_thread_id"),
                        "status": item.get("status"),
                    }
                    for item in database_info.get("threadSpawnEdges", [])
                ],
                "dynamicTools": [
                    {
                        "threadId": item.get("thread_id"),
                        "position": item.get("position"),
                        "name": item.get("name"),
                        "deferLoading": bool(item.get("defer_loading")),
                    }
                    for item in database_info.get("threadDynamicTools", [])
                ],
                "sections": database_info.get("threadSections", []),
            },
            "sessions": {
                "items": session_records,
                "count": len(session_records),
                "active": sum(item["collection"] == "sessions" for item in session_records),
                "archived": sum(
                    item["collection"] == "archived_sessions" for item in session_records
                ),
                "orphanThreadIds": orphan_session_ids,
            },
            "projects": {
                "items": project_inventory,
                **{key: value for key, value in project_analysis.items() if key != "roots"},
            },
            "attachments": {
                "items": attachment_records + missing_attachments,
                "copied": len(attachment_records),
                "missing": len(missing_attachments),
            },
        }

        (building / "manifest").mkdir(parents=True, exist_ok=True)
        write_json(building / "manifest" / "projects.json", projects)
        write_json(
            building / "manifest" / "project-identities.json",
            {
                "identityVersion": project_identity.IDENTITY_MANIFEST_VERSION,
                "registryVersion": project_identity.REGISTRY_VERSION,
                "roots": [item for item in project_identities if item["sourcePresent"]],
            },
        )
        write_json(building / "manifest" / "threads.json", thread_manifest)
        write_json(building / "manifest" / "inventory.json", inventory)
        write_json(
            building / "manifest" / "path-mappings.json",
            {
                "mappingVersion": 2,
                "locationSchemaVersion": path_model.LOCATION_SCHEMA_VERSION,
                "projects": project_mappings,
                "attachments": attachment_records + missing_attachments,
                "extras": extra_mappings,
            },
        )
        write_json(
            building / "manifest" / "database-info.json",
            {key: value for key, value in database_info.items() if key != "threads"},
        )
        report = {
            "reportVersion": 1,
            "status": "ready-for-independent-validation",
            "createdAtUtc": utc_now(),
            "warnings": warnings,
            "unresolvedExistingThreadCwds": unresolved,
            "orphanSessionIds": orphan_session_ids,
            "extras": extras,
            "portableCodexProfile": portable_profile,
            "portabilityAudit": portability,
            "selection": {
                "includedProjectPaths": [str(item["sourcePath"]) for item in candidates],
                "excludedProjectPaths": [
                    str(item["sourcePath"]) for item in excluded_candidates
                ],
                "excludedCodexProjectIds": sorted(excluded_project_ids),
                "conversationsAlwaysIncluded": True,
            },
        }
        write_json(building / "reports" / "backup-report.json", report)
        copy_toolkit(building, toolkit_root)

        peer_lineage = find_peer_lineage(
            destination_root,
            str(lineage_state.get("baseBackupId"))
            if lineage_state.get("baseBackupId")
            else None,
            backup_id,
        )

        def finalize_lineage(hash_rows: list[dict[str, Any]]) -> Path:
            nonlocal lineage_manifest
            replacements = lineage.portable_replacements(
                {
                    "source": {
                        "profilePath": str(source_profile),
                        "codexHome": str(source_codex),
                    }
                },
                {
                    "projects": project_mappings,
                    "attachments": attachment_records + missing_attachments,
                },
            )
            current_items = build_lineage_items(
                building,
                hash_rows,
                thread_manifest,
                projects,
                attachment_records + missing_attachments,
                extras,
                portable_profile,
                replacements,
            )
            lineage_manifest = lineage.build_manifest(
                backup_id,
                source_device_id,
                created_at_utc,
                current_items,
                lineage_state,
                peer_lineage,
            )
            path = building / "manifest" / "lineage.json"
            write_json(path, lineage_manifest)
            return path

        log("Creating SHA-256 manifest...")
        report_status(0, 0, "Step 4/6 — Preparing file-integrity verification...")
        hashed_count, payload_bytes, hash_manifest_sha = create_hash_manifest(
            building, finalize_lineage
        )
        if lineage_manifest is None:
            raise BackupError("Lineage manifest was not created.")
        package = {
            "formatId": FORMAT_ID,
            "formatVersion": FORMAT_VERSION,
            "generatorVersion": GENERATOR_VERSION,
            "backupComplete": False,
            "createdAtUtc": created_at_utc,
            "source": {
                "computerName": platform.node(),
                "profilePath": str(source_profile),
                "codexHome": str(source_codex),
                "platform": platform.platform(),
                "pythonVersion": platform.python_version(),
                "codexVersion": config.get("versionCheck", {}).get("installed", {}).get("version"),
                "versionCheck": config.get("versionCheck"),
                "knownFolders": source_known_folders,
            },
            "database": {
                "relativePath": "codex/state.snapshot.sqlite",
                "quickCheck": database_info["quickCheck"],
                "schemaMigrationCount": database_info["schemaMigrationCount"],
                "successfulMigrationCount": database_info["successfulMigrationCount"],
            },
            "projectIdentity": {
                "manifestRelativePath": "manifest/project-identities.json",
                "identityVersion": project_identity.IDENTITY_MANIFEST_VERSION,
                "registryVersion": project_identity.REGISTRY_VERSION,
            },
            "inventory": {
                "manifestRelativePath": "manifest/inventory.json",
                "inventoryVersion": 1,
            },
            "portabilityAudit": {
                "reportRelativePath": "reports/portability-audit.json",
                "auditVersion": portability.get("portabilityAuditVersion"),
                "status": portability.get("status"),
                "needsReviewReferences": portability_summary.get(
                    "needsReviewReferences", 0
                ),
                "unrecognizedSchemaFields": portability_summary.get(
                    "unrecognizedSchemaFields", 0
                ),
                "fieldsNeedingReview": portability_summary.get(
                    "fieldsNeedingReview", 0
                ),
            },
            "lineage": {
                "manifestRelativePath": "manifest/lineage.json",
                "lineageVersion": lineage.LINEAGE_VERSION,
                "backupId": backup_id,
                "parentBackupId": lineage_manifest.get("parentBackupId"),
                "sourceDeviceId": source_device_id,
                "relation": lineage_manifest.get("relation"),
            },
            "counts": {
                "threads": len(thread_manifest),
                "sessionFiles": session_count,
                "projects": len(projects),
                "logicalProjects": len(
                    {item["projectId"] for item in project_identities if item["sourcePresent"]}
                ),
                "projectFiles": sum(item["fileCount"] for item in projects),
                "extras": len(extras),
                "portableCodexEntries": len(portable_profile),
                "attachmentsCopied": len(attachment_records),
                "attachmentsMissing": len(missing_attachments),
                "warnings": len(warnings),
                "hashedFiles": hashed_count,
            },
            "selection": {
                "includedProjects": len(candidates),
                "excludedProjects": len(excluded_candidates),
                "conversationsAlwaysIncluded": True,
            },
            "payloadBytes": payload_bytes,
            "hashManifest": {
                "relativePath": "manifest/sha256.csv",
                "sha256": hash_manifest_sha,
            },
        }
        write_package_manifest(building, package)
        validator = toolkit_root / "tools" / "validate_backup.py"
        log("Running fast structural preflight validation...")
        report_status(0, 0, "Step 5/6 — Checking database, manifests and package structure...")
        # Every payload byte was already read while creating sha256.csv. Re-reading
        # the complete package here made Create backup roughly twice as slow.
        # The separate Verify backup action remains the independent full reread.
        run_validator(
            building, validator, allow_building=True, verify_hashes=False
        )
        package["backupComplete"] = True
        package["completedAtUtc"] = utc_now()
        write_package_manifest(building, package)
        log("Running final structural validation...")
        report_status(0, 0, "Step 6/6 — Performing final structural validation...")
        # Final validation checks completion metadata, paths and file sizes.
        run_validator(
            building, validator, allow_building=False, verify_hashes=False
        )
        report_status(0, 0, "All checks passed; completing the backup safely...")
        project_identity.save_registry(identity_registry_path, identity_registry)
        os.replace(building, final_path)
        lineage.save_state(lineage_state_path, lineage.state_from_manifest(lineage_manifest))
        log("")
        log("PASSED")
        log(f"Backup: {final_path}")
        log(
            f"Conversations: {len(thread_manifest)} | Projects: {len(projects)} | "
            f"Hashed files: {hashed_count} | Warnings: {len(warnings)}"
        )
        report_status(1, 1, "Backup complete")
        return final_path
    except Exception:
        error_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_io.write_text(error_path, traceback.format_exc())
        try:
            package_path = building / "manifest" / "package.json"
            if package_path.is_file():
                package = read_json(package_path)
                package["backupComplete"] = False
                package["failedAtUtc"] = utc_now()
                write_package_manifest(building, package)
        except Exception:
            pass
        log("")
        log(f"FAILED. Temporary directory retained: {building}")
        log(f"Foutlog: {error_path}")
        raise


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Codex Portable Backup 2.x")
    parser.add_argument("--config")
    parser.add_argument("--destination")
    parser.add_argument("--source-profile")
    parser.add_argument("--source-codex-home")
    parser.add_argument("--allow-running-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    try:
        build_backup(parse_arguments())
        return 0
    except BackupError as exc:
        log(f"FOUT: {exc}")
        return 1
    except Exception as exc:
        log(f"ONVERWACHTE FOUT: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
