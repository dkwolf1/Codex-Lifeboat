from __future__ import annotations

import csv
import datetime as dt
import json
import os
import shutil
import sqlite3
import traceback
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

try:
    from . import backup, windows
    from .validate import validate
except ImportError:
    import backup
    import windows
    from validate import validate


RESTORE_VERSION = "3.0.0"
PROTECTED_NAMES = {"auth.json", "installation_id", "cap_sid"}
RUNTIME_NAMES = {
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
PORTABLE_STATE_KEYS = backup.PORTABLE_STATE_KEYS


class RestoreError(RuntimeError):
    pass


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _safe_target(path: Path, profile: Path) -> None:
    resolved = path.resolve(strict=False)
    profile_resolved = profile.resolve(strict=False)
    allowed_roots = {
        profile_resolved,
        windows.documents_folder(profile).resolve(strict=False),
        windows.desktop_folder(profile).resolve(strict=False),
    }
    if resolved in allowed_roots or resolved == Path(resolved.anchor):
        raise RestoreError(f"Onveilig breed doelpad geweigerd: {resolved}")
    for allowed in allowed_roots:
        try:
            resolved.relative_to(allowed)
            return
        except ValueError:
            continue
    raise RestoreError(f"Doelpad valt buiten het doelprofiel: {resolved}")


def _copy_all(source: Path, destination: Path) -> tuple[int, int]:
    warnings: list[str] = []
    return backup.copy_tree(source, destination, [], warnings)


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = backup.connect_read_only(source)
    target_connection = sqlite3.connect(destination)
    try:
        if backup.sqlite_quick_check(source_connection) != "ok":
            raise RestoreError(f"Database is beschadigd: {source}")
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


def _copy_codex_safety(source_codex: Path, safety_codex: Path) -> None:
    safety_codex.mkdir(parents=True, exist_ok=True)
    for entry in source_codex.iterdir():
        lowered = entry.name.lower()
        if lowered in {"state_5.sqlite", "state_5.sqlite-wal", "state_5.sqlite-shm"}:
            continue
        if lowered in {value.lower() for value in RUNTIME_NAMES}:
            continue
        destination = safety_codex / entry.name
        if entry.is_symlink():
            continue
        if entry.is_dir():
            _copy_all(entry, destination)
        elif entry.is_file():
            backup.copy_file(entry, destination)
    database = source_codex / "state_5.sqlite"
    if database.is_file():
        _sqlite_snapshot(database, safety_codex / "state_5.sqlite")


def prepare_restore(
    package_root: Path,
    target_profile: Path,
    progress: Callable[[str], None] | None = None,
    allow_running_test: bool = False,
) -> dict[str, Any]:
    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    target_codex = target_profile / ".codex"
    result = validate(package_root, False)
    if not result.get("valid"):
        raise RestoreError("De gekozen back-up is ongeldig: " + "; ".join(result["errors"][:5]))
    if not target_codex.is_dir() or not (target_codex / "state_5.sqlite").is_file():
        raise RestoreError(
            "Codex is nog niet eenmaal gestart op deze computer. Installeer, open en sluit Codex eerst."
        )
    if not (target_codex / "auth.json").is_file():
        raise RestoreError(
            "Geen lokale Codex-aanmelding gevonden. Open Codex, meld aan en sluit de app volledig."
        )
    backup.check_codex_not_running(target_codex, allow_running_test)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safety_root = windows.documents_folder(target_profile) / "Codex Restore Safety" / stamp
    if safety_root.exists():
        safety_root = safety_root.with_name(safety_root.name + "-" + uuid.uuid4().hex[:6])
    if progress:
        progress(f"Veiligheidskopie maken: {safety_root}")
    _copy_codex_safety(target_codex, safety_root / "codex-before-restore")
    target_connection = sqlite3.connect(target_codex / "state_5.sqlite")
    try:
        target_threads = target_connection.execute(
            "SELECT count(*) FROM threads"
        ).fetchone()[0]
        target_projects = (
            target_connection.execute("SELECT count(*) FROM projects").fetchone()[0]
            if target_connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='projects'"
            ).fetchone()[0]
            else 0
        )
    finally:
        target_connection.close()
    metadata = {
        "preparedAtUtc": backup.utc_now(),
        "package": str(package_root),
        "targetProfile": str(target_profile),
        "targetThreadsBefore": int(target_threads),
        "targetProjectsBefore": int(target_projects),
        "safetyRoot": str(safety_root),
        "status": "prepared",
    }
    backup.write_json(safety_root / "restore-journal.json", metadata)
    return metadata


class PathTranslator:
    def __init__(self, package_root: Path, target_profile: Path):
        self.package_root = package_root
        self.target_profile = target_profile.resolve(strict=False)
        self.package = backup.read_json(package_root / "manifest/package.json")
        self.mappings = backup.read_json(package_root / "manifest/path-mappings.json")
        self.source_profile = Path(self.package["source"]["profilePath"])
        self.source_known_folders = self.package.get("source", {}).get("knownFolders") or {}
        self.project_targets: dict[str, Path] = {}
        self.attachment_targets: dict[str, Path] = {}
        self.replacements: list[tuple[str, str]] = []
        for item in self.mappings.get("projects", []):
            original = Path(item["originalPath"])
            project_id = str(item["id"])
            target = self._project_target(original, project_id)
            self.project_targets[project_id] = target
            self._add_replacement(str(original), str(target))
        for item in self.mappings.get("attachments", []):
            attachment_id = str(item["id"])
            name = Path(item.get("originalPath", "attachment.bin")).name
            target = windows.documents_folder(self.target_profile) / "Codex Attachments" / attachment_id / name
            self.attachment_targets[attachment_id] = target
            self._add_replacement(str(item.get("originalPath", "")), str(target))
        self._add_replacement(str(self.source_profile), str(self.target_profile))
        self.replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

    def _project_target(self, original: Path, project_id: str) -> Path:
        for kind, target_known in (
            ("documents", windows.documents_folder(self.target_profile)),
            ("desktop", windows.desktop_folder(self.target_profile)),
        ):
            source_known_value = self.source_known_folders.get(kind)
            if source_known_value:
                try:
                    relative = original.resolve(strict=False).relative_to(
                        Path(source_known_value).resolve(strict=False)
                    )
                    target = target_known / relative
                    _safe_target(target, self.target_profile)
                    return target
                except ValueError:
                    pass
        try:
            relative = original.resolve(strict=False).relative_to(
                self.source_profile.resolve(strict=False)
            )
            if relative.parts and relative.parts[0].lower() == "documents":
                target = windows.documents_folder(self.target_profile) / Path(*relative.parts[1:])
            elif relative.parts and relative.parts[0].lower() == "desktop":
                target = windows.desktop_folder(self.target_profile) / Path(*relative.parts[1:])
            else:
                target = self.target_profile / relative
        except ValueError:
            safe_name = original.name or f"project-{project_id}"
            target = windows.documents_folder(self.target_profile) / "Codex Restored Projects" / safe_name
            if target in self.project_targets.values():
                target = target.with_name(f"{target.name}-{project_id[:6]}")
        _safe_target(target, self.target_profile)
        return target

    def _add_replacement(self, source: str, target: str) -> None:
        if not source:
            return
        variants = {
            source: target,
            source.replace("\\", "/"): target.replace("\\", "/"),
            source.replace("\\", "\\\\"): target.replace("\\", "\\\\"),
        }
        for old, new in variants.items():
            if old and (old, new) not in self.replacements:
                self.replacements.append((old, new))

    def text(self, value: str) -> str:
        result = value
        for old, new in self.replacements:
            result = result.replace(old, new)
        return result

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            return {key: self.value(item) for key, item in value.items()}
        return value


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_exists(connection: sqlite3.Connection, schema: str, table: str) -> bool:
    return bool(
        connection.execute(
            f"SELECT count(*) FROM {schema}.sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
    )


def _columns(connection: sqlite3.Connection, schema: str, table: str) -> list[dict[str, Any]]:
    return [
        {
            "name": row[1],
            "type": str(row[2] or ""),
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": int(row[5]),
        }
        for row in connection.execute(f"PRAGMA {schema}.table_info({_quote(table)})")
    ]


def _fallback_expression(column: dict[str, Any], source_columns: set[str]) -> str | None:
    name = column["name"]
    if column["default"] is not None or not column["notnull"] or column["pk"]:
        return None
    def coalesce(candidates: list[tuple[str, str]], fallback: str) -> str:
        values = [expression for column_name, expression in candidates if column_name in source_columns]
        values.append(fallback)
        return "COALESCE(" + ",".join(values) + ")"

    aliases = {
        "preview": coalesce(
            [("first_user_message", "src.first_user_message"), ("title", "src.title")], "''"
        ),
        "recency_at": coalesce(
            [("updated_at", "src.updated_at"), ("created_at", "src.created_at")], "0"
        ),
        "recency_at_ms": coalesce(
            [
                ("updated_at_ms", "src.updated_at_ms"),
                ("created_at_ms", "src.created_at_ms"),
                ("updated_at", "src.updated_at*1000"),
                ("created_at", "src.created_at*1000"),
            ],
            "0",
        ),
        "history_mode": "'full'",
        "memory_mode": "'disabled'",
        "is_pinned": "0",
    }
    if name in aliases:
        return aliases[name]
    declared = column["type"].upper()
    if "INT" in declared or "REAL" in declared or "NUM" in declared:
        return "0"
    if "BLOB" in declared:
        return "X''"
    return "''"


def _replace_table(connection: sqlite3.Connection, table: str) -> int:
    if not _table_exists(connection, "main", table) or not _table_exists(connection, "src", table):
        return 0
    target_columns = _columns(connection, "main", table)
    source_columns = {item["name"] for item in _columns(connection, "src", table)}
    names: list[str] = []
    expressions: list[str] = []
    for column in target_columns:
        name = column["name"]
        if name in source_columns:
            names.append(_quote(name))
            expressions.append(f"src.{_quote(name)}")
            continue
        fallback = _fallback_expression(column, source_columns)
        if fallback is not None:
            names.append(_quote(name))
            expressions.append(fallback)
    if not names:
        return 0
    sql = (
        f"INSERT OR IGNORE INTO main.{_quote(table)} ({','.join(names)}) "
        f"SELECT {','.join(expressions)} FROM src.{_quote(table)} AS src"
    )
    before = connection.total_changes
    connection.execute(sql)
    return connection.total_changes - before


def _build_restored_database(
    package_root: Path,
    target_database_template: Path,
    output_database: Path,
    translator: PathTranslator,
) -> dict[str, int]:
    shutil.copy2(target_database_template, output_database)
    source_database = package_root / "codex" / "state.snapshot.sqlite"
    threads_manifest = backup.read_json(package_root / "manifest" / "threads.json")
    connection = sqlite3.connect(output_database)
    connection.execute("PRAGMA busy_timeout=10000")
    try:
        if backup.sqlite_quick_check(connection) != "ok":
            raise RestoreError("Lokale database-template is beschadigd.")
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("ATTACH DATABASE ? AS src", (str(source_database),))
        delete_order = (
            "thread_dynamic_tools",
            "thread_spawn_edges",
            "project_roots",
            "threads",
            "projects",
            "thread_sections",
        )
        insert_order = (
            "thread_sections",
            "projects",
            "project_roots",
            "threads",
            "thread_dynamic_tools",
            "thread_spawn_edges",
        )
        counts: dict[str, int] = {}
        with connection:
            for table in delete_order:
                if _table_exists(connection, "main", table):
                    connection.execute(f"DELETE FROM {_quote(table)}")
            for table in insert_order:
                counts[table] = _replace_table(connection, table)
            if _table_exists(connection, "main", "project_roots"):
                rows = connection.execute(
                    "SELECT project_id,position,path FROM project_roots"
                ).fetchall()
                for project_id, position, path in rows:
                    connection.execute(
                        "UPDATE project_roots SET path=? WHERE project_id=? AND position=?",
                        (translator.text(str(path)), project_id, position),
                    )
            thread_columns = {
                item["name"] for item in _columns(connection, "main", "threads")
            }
            for item in threads_manifest:
                thread_id = str(item["id"])
                rollout_relative = item.get("backupRelativePath")
                if not rollout_relative:
                    raise RestoreError(f"Thread zonder rollout in manifest: {thread_id}")
                rollout_target = translator.target_profile / ".codex" / Path(
                    *PurePosixPath(rollout_relative).parts[1:]
                )
                assignments: list[str] = []
                values: list[Any] = []
                if "rollout_path" in thread_columns:
                    assignments.append("rollout_path=?")
                    values.append(str(rollout_target))
                for column in ("cwd", "sandbox_policy", "agent_path"):
                    if column in thread_columns:
                        row = connection.execute(
                            f"SELECT {_quote(column)} FROM threads WHERE id=?", (thread_id,)
                        ).fetchone()
                        if row and row[0] is not None:
                            assignments.append(f"{_quote(column)}=?")
                            values.append(translator.text(str(row[0])))
                if assignments:
                    values.append(thread_id)
                    connection.execute(
                        f"UPDATE threads SET {','.join(assignments)} WHERE id=?", values
                    )
        connection.execute("DETACH DATABASE src")
        check = backup.sqlite_quick_check(connection)
        if check != "ok":
            raise RestoreError(f"Herstelde database faalt quick_check: {check}")
        counts["finalThreads"] = int(
            connection.execute("SELECT count(*) FROM threads").fetchone()[0]
        )
        return counts
    finally:
        connection.close()


def _rewrite_copy(source: Path, destination: Path, translator: PathTranslator) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".restore.tmp")
    with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as reader:
        with temporary.open("w", encoding="utf-8", newline="\n") as writer:
            for line in reader:
                writer.write(translator.text(line.rstrip("\r\n")) + "\n")
    os.replace(temporary, destination)


def _restore_sessions(package_root: Path, target_codex: Path, translator: PathTranslator) -> int:
    count = 0
    for directory_name in ("sessions", "archived_sessions"):
        source_root = package_root / "codex" / directory_name
        target_root = target_codex / directory_name
        if target_root.exists():
            _remove_path(target_root)
        if not source_root.exists():
            continue
        for source in source_root.rglob("*.jsonl"):
            destination = target_root / source.relative_to(source_root)
            _rewrite_copy(source, destination, translator)
            count += 1
    index = package_root / "codex" / "session_index.jsonl"
    if index.is_file():
        _rewrite_copy(index, target_codex / "session_index.jsonl", translator)
    return count


def _restore_global_state(package_root: Path, target_codex: Path, translator: PathTranslator) -> None:
    target_path = target_codex / ".codex-global-state.json"
    current = backup.read_json(target_path) if target_path.is_file() else {}
    source = backup.read_json(package_root / "codex" / "portable-global-state.json")
    for key in PORTABLE_STATE_KEYS:
        current.pop(key, None)
    for key, value in translator.value(source).items():
        current[key] = value
    backup.write_json(target_path, current)


def _restore_portable_profile(
    package_root: Path, target_codex: Path, translator: PathTranslator
) -> int:
    source_root = package_root / "codex" / "portable-profile"
    count = 0
    if not source_root.is_dir():
        return count
    for entry in source_root.iterdir():
        destination = target_codex / entry.name
        if entry.name.lower() in {value.lower() for value in PROTECTED_NAMES | RUNTIME_NAMES}:
            continue
        if destination.exists():
            _remove_path(destination)
        if entry.is_dir():
            for source in entry.rglob("*"):
                if not source.is_file():
                    continue
                target = destination / source.relative_to(entry)
                if source.suffix.lower() in {
                    ".json", ".jsonl", ".toml", ".md", ".txt", ".yaml", ".yml", ".ini", ".cfg"
                }:
                    _rewrite_copy(source, target, translator)
                else:
                    backup.copy_file(source, target)
                count += 1
        elif entry.is_file():
            if entry.suffix.lower() in {
                ".json", ".jsonl", ".toml", ".md", ".txt", ".yaml", ".yml", ".ini", ".cfg"
            }:
                _rewrite_copy(entry, destination, translator)
            else:
                backup.copy_file(entry, destination)
            count += 1
    return count


def _restore_attachments(package_root: Path, translator: PathTranslator) -> int:
    count = 0
    for item in translator.mappings.get("attachments", []):
        if not item.get("sourcePresent"):
            continue
        source = package_root / Path(*PurePosixPath(item["backupRelativePath"]).parts)
        target = translator.attachment_targets[str(item["id"])]
        _safe_target(target, translator.target_profile)
        backup.copy_file(source, target)
        count += 1
    return count


def _restore_projects(
    package_root: Path,
    safety_root: Path,
    translator: PathTranslator,
    journal: dict[str, Any],
    progress: Callable[[str], None] | None,
) -> int:
    projects = backup.read_json(package_root / "manifest" / "projects.json")
    copied = 0
    project_journal: list[dict[str, Any]] = journal.setdefault("projects", [])
    for item in projects:
        project_id = str(item["id"])
        source = package_root / Path(*PurePosixPath(item["backupRelativePath"]).parts)
        target = translator.project_targets[project_id]
        _safe_target(target, translator.target_profile)
        record = {
            "id": project_id,
            "target": str(target),
            "existedBefore": target.exists(),
            "safetyRelativePath": f"projects-before-restore/{project_id}",
        }
        if target.exists():
            safety = safety_root / record["safetyRelativePath"]
            if progress:
                progress(f"Bestaand project veiligstellen: {target}")
            _copy_all(target, safety)
            _remove_path(target)
        project_journal.append(record)
        if progress:
            progress(f"Project herstellen: {target}")
        files, _ = _copy_all(source, target)
        copied += files
    return copied


def _purge_target_portable_data(target_codex: Path) -> None:
    protected = {value.lower() for value in PROTECTED_NAMES | RUNTIME_NAMES}
    for entry in target_codex.iterdir():
        if entry.name.lower() in protected:
            continue
        _remove_path(entry)


def rollback_restore(safety_root: Path, target_profile: Path) -> None:
    journal_path = safety_root / "restore-journal.json"
    journal = backup.read_json(journal_path)
    target_codex = target_profile / ".codex"
    if target_codex.exists():
        _remove_path(target_codex)
    _copy_all(safety_root / "codex-before-restore", target_codex)
    for item in reversed(journal.get("projects", [])):
        target = Path(item["target"])
        _safe_target(target, target_profile)
        if target.exists():
            _remove_path(target)
        if item.get("existedBefore"):
            source = safety_root / item["safetyRelativePath"]
            _copy_all(source, target)
    journal["status"] = "rolled-back"
    journal["rolledBackAtUtc"] = backup.utc_now()
    backup.write_json(journal_path, journal)


def verify_restored(
    package_root: Path, target_profile: Path, translator: PathTranslator | None = None
) -> dict[str, Any]:
    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    target_codex = target_profile / ".codex"
    translator = translator or PathTranslator(package_root, target_profile)
    errors: list[str] = []
    checks: dict[str, Any] = {}
    package = backup.read_json(package_root / "manifest" / "package.json")
    database = target_codex / "state_5.sqlite"
    try:
        connection = sqlite3.connect(database)
        try:
            check = backup.sqlite_quick_check(connection)
            checks["sqliteQuickCheck"] = check
            if check != "ok":
                errors.append(f"SQLite quick_check: {check}")
            thread_count = int(connection.execute("SELECT count(*) FROM threads").fetchone()[0])
            checks["threads"] = thread_count
            if thread_count != int(package["counts"]["threads"]):
                errors.append(
                    f"Threadaantal {thread_count} wijkt af van back-up {package['counts']['threads']}"
                )
            rollout_rows = connection.execute("SELECT id,rollout_path FROM threads").fetchall()
        finally:
            connection.close()
        for thread_id, rollout_path in rollout_rows:
            path = Path(str(rollout_path).replace("\\\\?\\", ""))
            if not path.is_file():
                errors.append(f"Rollout ontbreekt voor {thread_id}: {path}")
                continue
            rollout_id, rollout_error = backup.parse_session_meta(path)
            if rollout_error or rollout_id != str(thread_id):
                errors.append(f"Rollout-id ongeldig voor {thread_id}: {rollout_error or rollout_id}")
    except Exception as exc:
        errors.append(f"Databasecontrole mislukt: {exc}")
    projects = backup.read_json(package_root / "manifest" / "projects.json")
    expected_hashes: dict[str, str] = {}
    with (package_root / "manifest" / "sha256.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            expected_hashes[row["relative_path"]] = row["sha256"].lower()
    checked_projects = 0
    for item in projects:
        target = translator.project_targets[str(item["id"])]
        if not target.is_dir():
            errors.append(f"Projectmap ontbreekt: {target}")
            continue
        files = [path for path in target.rglob("*") if path.is_file()]
        size = sum(path.stat().st_size for path in files)
        if len(files) != int(item["fileCount"]):
            errors.append(f"Bestandsaantal wijkt af voor project {target}")
        if size != int(item["totalBytes"]):
            errors.append(f"Byteaantal wijkt af voor project {target}")
        prefix = str(item["backupRelativePath"]).rstrip("/") + "/"
        for relative_path, expected_hash in expected_hashes.items():
            if not relative_path.startswith(prefix):
                continue
            project_relative = PurePosixPath(relative_path[len(prefix) :])
            target_file = target / Path(*project_relative.parts)
            if not target_file.is_file():
                errors.append(f"Projectbestand ontbreekt: {target_file}")
            elif backup.sha256_file(target_file) != expected_hash:
                errors.append(f"Projecthash wijkt af: {target_file}")
        checked_projects += 1
    checks["projects"] = checked_projects
    return {"valid": not errors, "errors": errors, "checks": checks}


def restore_backup(
    package_root: Path,
    target_profile: Path,
    safety_root: Path,
    progress: Callable[[str], None] | None = None,
    fail_after_database_for_test: bool = False,
) -> dict[str, Any]:
    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    target_codex = target_profile / ".codex"
    safety_root = safety_root.resolve()
    journal_path = safety_root / "restore-journal.json"
    journal = backup.read_json(journal_path)
    if journal.get("status") != "prepared":
        raise RestoreError("Veiligheidskopie is niet in status prepared.")
    translator = PathTranslator(package_root, target_profile)
    auth_path = target_codex / "auth.json"
    auth_hash_before = backup.sha256_file(auth_path)
    temporary_database = safety_root / "state_5.restored.tmp.sqlite"
    try:
        journal["status"] = "restoring"
        journal["startedAtUtc"] = backup.utc_now()
        backup.write_json(journal_path, journal)
        project_files = _restore_projects(
            package_root, safety_root, translator, journal, progress
        )
        backup.write_json(journal_path, journal)
        if progress:
            progress("Doeldatabase schema-bewust opbouwen...")
        database_counts = _build_restored_database(
            package_root,
            safety_root / "codex-before-restore" / "state_5.sqlite",
            temporary_database,
            translator,
        )
        if fail_after_database_for_test:
            raise RestoreError("Opzettelijke foutinjectie na database-opbouw")
        if progress:
            progress("Lokale Codex-gebruikersdata vervangen...")
        _purge_target_portable_data(target_codex)
        target_codex.mkdir(parents=True, exist_ok=True)
        # Machine-identiteit en aanmelding komen uit de veiligheidskopie terug.
        safety_codex = safety_root / "codex-before-restore"
        for protected_name in PROTECTED_NAMES:
            source = safety_codex / protected_name
            if source.is_file():
                backup.copy_file(source, target_codex / protected_name)
        portable_files = _restore_portable_profile(package_root, target_codex, translator)
        sessions = _restore_sessions(package_root, target_codex, translator)
        attachments = _restore_attachments(package_root, translator)
        _restore_global_state(package_root, target_codex, translator)
        for suffix in ("-wal", "-shm"):
            path = target_codex / f"state_5.sqlite{suffix}"
            if path.exists():
                path.unlink()
        os.replace(temporary_database, target_codex / "state_5.sqlite")
        if backup.sha256_file(target_codex / "auth.json") != auth_hash_before:
            raise RestoreError("Lokale aanmelding is onverwacht gewijzigd.")
        if progress:
            progress("Volledige eindcontrole uitvoeren...")
        verification = verify_restored(package_root, target_profile, translator)
        if not verification["valid"]:
            raise RestoreError("Eindcontrole mislukt: " + "; ".join(verification["errors"][:5]))
        journal.update(
            {
                "status": "complete",
                "completedAtUtc": backup.utc_now(),
                "databaseCounts": database_counts,
                "projectFilesCopied": project_files,
                "portableFilesCopied": portable_files,
                "sessionsCopied": sessions,
                "attachmentsCopied": attachments,
                "verification": verification,
                "pathMappings": {
                    key: str(value) for key, value in translator.project_targets.items()
                },
            }
        )
        backup.write_json(journal_path, journal)
        reports = windows.documents_folder(target_profile) / "Codex Restore Reports"
        reports.mkdir(parents=True, exist_ok=True)
        backup.write_json(
            reports / f"restore-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json",
            journal,
        )
        return journal
    except Exception:
        journal["error"] = traceback.format_exc()
        backup.write_json(journal_path, journal)
        if progress:
            progress("Herstel mislukt; automatische rollback uitvoeren...")
        rollback_restore(safety_root, target_profile)
        raise
