#!/usr/bin/env python3
"""Build a Codex Portable Backup Package 2.0 without modifying the source."""

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
import traceback
import uuid
import urllib.parse
from pathlib import Path
from typing import Any, Iterable


FORMAT_ID = "codex-portable-backup"
FORMAT_VERSION = "2.0"
GENERATOR_VERSION = "2.0.0"
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
    "process_manager",
    "thread-writer-locks",
}
ATTACHMENT_PATTERN = re.compile(
    r"(?i)([a-z]:[\\/][^\x00\r\n\"<>|?*]{1,2048}?\.(?:png|jpe?g|webp|gif|bmp|pdf|docx?|xlsx?|pptx?|csv|zip))"
)


class BackupError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, flush=True)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
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
        raise BackupError(f"Bron-database faalt PRAGMA quick_check: {source_check}")
    target_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(target_connection)
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
            raise BackupError("Snapshot bevat geen tabel 'threads'.")
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
        return {
            "quickCheck": check,
            "schemaMigrationCount": int(migration_count),
            "successfulMigrationCount": int(migrations_successful),
            "tables": sorted(tables),
            "threads": thread_rows,
            "databaseProjects": projects,
            "databaseProjectRoots": roots,
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
            raise BackupError(f"Kan map niet lezen: {current_source}: {exc}") from exc
        for entry in entries:
            entry_source = Path(entry.path)
            entry_destination = current_destination / entry.name
            relative_text = os.path.relpath(entry_source, source).lower()
            if any(fragment and fragment in relative_text for fragment in excluded):
                warnings.append(f"Uitgesloten volgens configuratie: {entry_source}")
                continue
            try:
                if entry.is_symlink():
                    warnings.append(f"Symbolische link/reparsepunt overgeslagen: {entry_source}")
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append((entry_source, entry_destination))
                elif entry.is_file(follow_symlinks=False):
                    copy_file(entry_source, entry_destination)
                    size = entry.stat(follow_symlinks=False).st_size
                    count += 1
                    byte_count += size
                    if count % 1000 == 0:
                        log(f"  ... {count} bestanden gekopieerd uit {source.name}")
            except OSError as exc:
                raise BackupError(f"Kopiëren mislukt voor {entry_source}: {exc}") from exc
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


def parse_session_meta(path: Path) -> tuple[str | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
            first = handle.readline()
        value = json.loads(first)
        if value.get("type") != "session_meta":
            return None, "eerste regel is niet van type session_meta"
        thread_id = (value.get("payload") or {}).get("id")
        if not thread_id:
            return None, "session_meta bevat geen payload.id"
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


def export_portable_state(source_codex: Path, package_root: Path) -> dict[str, Any]:
    source = source_codex / ".codex-global-state.json"
    portable: dict[str, Any] = {}
    if source.exists():
        state = read_json(source)
        portable = {key: state[key] for key in PORTABLE_STATE_KEYS if key in state}
    write_json(package_root / "codex" / "portable-global-state.json", portable)
    return portable


def add_project_candidate(
    candidates: dict[str, dict[str, Any]],
    path_value: str,
    name: str | None,
    origin: str,
    required: bool,
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
        },
    )
    if origin not in candidate["origins"]:
        candidate["origins"].append(origin)
    candidate["required"] = bool(candidate["required"] or required)
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
            )
    return sorted(candidates.values(), key=lambda item: item["sourcePath"].lower())


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
    exclude_fragments: list[str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projects: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for item in candidates:
        source = clean_windows_path(item["sourcePath"])
        project_id = stable_id(source)
        relative = f"projects/project-{project_id}"
        exists = source.is_dir()
        mapping = {
            "mappingKind": "project",
            "id": project_id,
            "originalPath": str(source),
            "backupRelativePath": relative,
            "suggestedTargetPath": f"%USERPROFILE%\\Documents\\Codex-projects\\{source.name}",
            "sourcePresent": exists,
        }
        mappings.append(mapping)
        if not exists:
            message = f"Projectroot bestaat niet meer: {source}"
            if item.get("required"):
                raise BackupError(message + " (verplicht in backup-config.json)")
            warnings.append(message)
            continue
        if broad_or_unsafe_project_path(source, source_profile, codex_home):
            raise BackupError(
                f"Onveilig breed projectpad geweigerd: {source}. Kies een concrete projectmap."
            )
        package_resolved = package_root.resolve(strict=False)
        source_resolved = source.resolve(strict=False)
        if normalized_source_key(package_resolved).startswith(
            normalized_source_key(source_resolved) + os.sep
        ):
            raise BackupError(
                f"De tijdelijke back-upmap ligt binnen projectbron {source}; dit zou recursief kopiëren."
            )
        log(f"Project kopiëren: {source}")
        file_count, byte_count = copy_tree(
            source, package_root / relative, exclude_fragments, warnings
        )
        projects.append(
            {
                "id": project_id,
                "name": item.get("name") or source.name,
                "originalPath": str(source),
                "backupRelativePath": relative,
                "origins": item.get("origins", []),
                "fileCount": file_count,
                "totalBytes": byte_count,
            }
        )
    return projects, mappings


def nested_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)


def find_attachment_paths(session_files: Iterable[Path]) -> set[str]:
    results: set[str] = set()
    for session_file in session_files:
        with session_file.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                if "codex-" not in line.lower() and "appdata" not in line.lower():
                    continue
                try:
                    value = json.loads(line)
                    strings = nested_strings(value)
                except json.JSONDecodeError:
                    strings = (line,)
                for text in strings:
                    for match in ATTACHMENT_PATTERN.finditer(text):
                        candidate = match.group(1).rstrip(" .")
                        lowered = candidate.lower().replace("/", "\\")
                        if "\\appdata\\local\\temp\\" in lowered or "codex-" in lowered:
                            results.add(candidate)
    return results


def copy_attachments(
    package_root: Path, enabled: bool, warnings: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not enabled:
        return [], []
    session_files = list((package_root / "codex" / "sessions").rglob("*.jsonl"))
    session_files += list(
        (package_root / "codex" / "archived_sessions").rglob("*.jsonl")
    )
    copied: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    log("Lokale chatbijlagen inventariseren...")
    for original in sorted(find_attachment_paths(session_files), key=str.lower):
        source = clean_windows_path(original)
        attachment_id = stable_id(source)
        relative = f"attachments/attachment-{attachment_id}/{source.name}"
        item = {
            "mappingKind": "attachment",
            "id": attachment_id,
            "originalPath": str(source),
            "backupRelativePath": relative,
            "sourcePresent": source.is_file(),
        }
        if source.is_file():
            copy_file(source, package_root / relative)
            item["size"] = source.stat().st_size
            copied.append(item)
        else:
            missing.append(item)
            warnings.append(f"Historische bijlage niet meer aanwezig: {source}")
    return copied, missing


def copy_extras(
    config: dict[str, Any], package_root: Path, warnings: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for index, item in enumerate(config.get("additionalPortablePaths", []), start=1):
        source = clean_windows_path(str(item.get("path", "")))
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(item.get("name") or source.name))
        name = name.strip("-.") or f"extra-{index:03d}"
        if name.lower() in used_names:
            raise BackupError(f"Dubbele naam voor additionalPortablePaths: {name}")
        used_names.add(name.lower())
        relative = f"extra/{name}"
        exists = source.exists()
        mapping = {
            "mappingKind": "extra",
            "id": stable_id(source),
            "originalPath": str(source),
            "backupRelativePath": relative,
            "sourcePresent": exists,
        }
        mappings.append(mapping)
        if not exists:
            if item.get("required", True):
                raise BackupError(f"Verplichte extra bron bestaat niet: {source}")
            warnings.append(f"Optionele extra bron bestaat niet: {source}")
            continue
        if normalized_source_key(package_root).startswith(
            normalized_source_key(source) + os.sep
        ):
            raise BackupError(
                f"De tijdelijke back-upmap ligt binnen extra bron {source}; dit zou recursief kopiëren."
            )
        if source.is_dir():
            count, size = copy_tree(source, package_root / relative, [], warnings)
        elif source.is_file():
            destination = package_root / relative / source.name
            copy_file(source, destination)
            count, size = 1, source.stat().st_size
            mapping["backupRelativePath"] = portable_relative(destination, package_root)
        else:
            warnings.append(f"Niet-reguliere extra bron overgeslagen: {source}")
            continue
        records.append(
            {
                "name": name,
                "originalPath": str(source),
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


def create_hash_manifest(package_root: Path) -> tuple[int, int, str]:
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
    total_bytes = 0
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("relative_path", "size", "sha256"))
        for index, path in enumerate(paths, start=1):
            size = path.stat().st_size
            writer.writerow((portable_relative(path, package_root), size, sha256_file(path)))
            total_bytes += size
            if index % 1000 == 0:
                log(f"  ... {index} bestanden gehasht")
    return len(paths), total_bytes, sha256_file(manifest_path)


def write_package_manifest(package_root: Path, package: dict[str, Any]) -> None:
    package_path = package_root / "manifest" / "package.json"
    write_json(package_path, package)
    sidecar = package_root / "manifest" / "package.json.sha256"
    sidecar.write_text(sha256_file(package_path) + "\n", encoding="ascii")


def run_validator(package_root: Path, validator: Path, allow_building: bool) -> None:
    command = [sys.executable, str(validator), str(package_root)]
    if allow_building:
        command.append("--allow-building")
    completed = subprocess.run(command, text=True, check=False)
    if completed.returncode != 0:
        raise BackupError(
            f"Onafhankelijke pakketcontrole is mislukt (code {completed.returncode})."
        )


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BackupError(f"Configuratiebestand niet gevonden: {path}")
    config = read_json(path)
    if config.get("configVersion") != 1:
        raise BackupError("backup-config.json moet configVersion 1 hebben.")
    if not isinstance(config.get("projects", []), list):
        raise BackupError("config.projects moet een lijst zijn.")
    if not isinstance(config.get("additionalPortablePaths", []), list):
        raise BackupError("config.additionalPortablePaths moet een lijst zijn.")
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
    destination_root = clean_windows_path(
        args.destination or str(config.get("destinationRoot", "D:\\Codex-Backups"))
    ).resolve(strict=False)
    if not source_codex.is_dir():
        raise BackupError(f"Codex-bronmap niet gevonden: {source_codex}")
    source_db = source_codex / "state_5.sqlite"
    if not source_db.is_file():
        raise BackupError(f"Codex-database niet gevonden: {source_db}")
    check_codex_not_running(source_codex, bool(args.allow_running_test))
    destination_root.mkdir(parents=True, exist_ok=True)
    if normalized_source_key(destination_root).startswith(normalized_source_key(source_codex) + os.sep):
        raise BackupError("De doelmap mag niet binnen de Codex-bronmap liggen.")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    final_name = f"Codex-PortableBackup-{stamp}"
    final_path = destination_root / final_name
    if final_path.exists():
        final_path = destination_root / f"{final_name}-{uuid.uuid4().hex[:6]}"
    building = destination_root / f".building-{final_path.name}-{uuid.uuid4().hex[:8]}"
    building.mkdir(parents=True)
    error_path = building / "reports" / "backup-error.txt"
    warnings: list[str] = []

    try:
        log(f"Tijdelijk pakket: {building}")
        database_info = create_snapshot(
            source_db, building / "codex" / "state.snapshot.sqlite"
        )
        log(
            f"SQLite-snapshot is consistent; {len(database_info['threads'])} threads gevonden."
        )
        portable_state = export_portable_state(source_codex, building)
        candidates = collect_project_candidates(config, database_info, portable_state)
        excludes = [str(item) for item in config.get("excludeDirectoryNames", [])]

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
        required_bytes = int(estimated_bytes * 1.05) + 100 * 1024 * 1024
        if free_bytes < required_bytes:
            raise BackupError(
                f"Onvoldoende vrije ruimte. Nodig circa {required_bytes:,} bytes; vrij {free_bytes:,} bytes."
            )

        session_map, invalid_sessions, session_count = copy_sessions(source_codex, building)
        if invalid_sessions:
            write_json(building / "reports" / "invalid-sessions.json", invalid_sessions)
            raise BackupError(
                f"{len(invalid_sessions)} sessiebestand(en) hebben ongeldige metadata."
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
                    "projectId": row.get("project_id"),
                    "originalRolloutPath": row.get("rollout_path"),
                    "backupRelativePath": matches[0] if len(matches) == 1 else None,
                }
            )
        if missing_rollouts or duplicate_rollouts:
            write_json(
                building / "reports" / "rollout-errors.json",
                {"missingThreadIds": missing_rollouts, "duplicateThreadIds": duplicate_rollouts},
            )
            raise BackupError(
                f"Rolloutcontrole mislukt: {len(missing_rollouts)} ontbrekend, "
                f"{len(duplicate_rollouts)} dubbel."
            )

        index_source = source_codex / "session_index.jsonl"
        if index_source.is_file():
            copy_file(index_source, building / "codex" / "session_index.jsonl")

        projects, project_mappings = copy_projects(
            candidates,
            building,
            source_profile,
            source_codex,
            excludes,
            warnings,
        )
        unresolved = unresolved_cwds(database_info["threads"], candidates)
        for cwd in unresolved:
            warnings.append(
                f"Bestaande thread-cwd valt niet onder een geselecteerd project: {cwd}"
            )

        attachment_records, missing_attachments = copy_attachments(
            building, bool(config.get("includeAttachments", True)), warnings
        )
        extras, extra_mappings = copy_extras(config, building, warnings)

        orphan_session_ids = sorted(set(session_map) - {item["id"] for item in thread_manifest})
        if orphan_session_ids:
            warnings.append(
                f"{len(orphan_session_ids)} rollout(s) staan niet in de snapshotdatabase."
            )

        (building / "manifest").mkdir(parents=True, exist_ok=True)
        write_json(building / "manifest" / "projects.json", projects)
        write_json(building / "manifest" / "threads.json", thread_manifest)
        write_json(
            building / "manifest" / "path-mappings.json",
            {
                "mappingVersion": 1,
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
        }
        write_json(building / "reports" / "backup-report.json", report)
        copy_toolkit(building, toolkit_root)

        log("SHA-256-manifest maken...")
        hashed_count, payload_bytes, hash_manifest_sha = create_hash_manifest(building)
        package = {
            "formatId": FORMAT_ID,
            "formatVersion": FORMAT_VERSION,
            "generatorVersion": GENERATOR_VERSION,
            "backupComplete": False,
            "createdAtUtc": utc_now(),
            "source": {
                "computerName": platform.node(),
                "profilePath": str(source_profile),
                "codexHome": str(source_codex),
                "platform": platform.platform(),
                "pythonVersion": platform.python_version(),
            },
            "database": {
                "relativePath": "codex/state.snapshot.sqlite",
                "quickCheck": database_info["quickCheck"],
                "schemaMigrationCount": database_info["schemaMigrationCount"],
                "successfulMigrationCount": database_info["successfulMigrationCount"],
            },
            "counts": {
                "threads": len(thread_manifest),
                "sessionFiles": session_count,
                "projects": len(projects),
                "projectFiles": sum(item["fileCount"] for item in projects),
                "extras": len(extras),
                "attachmentsCopied": len(attachment_records),
                "attachmentsMissing": len(missing_attachments),
                "warnings": len(warnings),
                "hashedFiles": hashed_count,
            },
            "payloadBytes": payload_bytes,
            "hashManifest": {
                "relativePath": "manifest/sha256.csv",
                "sha256": hash_manifest_sha,
            },
        }
        write_package_manifest(building, package)
        validator = toolkit_root / "tools" / "validate_backup.py"
        log("Onafhankelijke voorcontrole uitvoeren...")
        run_validator(building, validator, allow_building=True)
        package["backupComplete"] = True
        package["completedAtUtc"] = utc_now()
        write_package_manifest(building, package)
        log("Definitieve onafhankelijke controle uitvoeren...")
        run_validator(building, validator, allow_building=False)
        os.replace(building, final_path)
        log("")
        log("GESLAAGD")
        log(f"Back-up: {final_path}")
        log(
            f"Threads: {len(thread_manifest)} | Projecten: {len(projects)} | "
            f"Gehashte bestanden: {hashed_count} | Waarschuwingen: {len(warnings)}"
        )
        return final_path
    except Exception:
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
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
        log(f"MISLUKT. Tijdelijke map is bewaard: {building}")
        log(f"Foutlog: {error_path}")
        raise


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maak Codex Portable Backup 2.0")
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
