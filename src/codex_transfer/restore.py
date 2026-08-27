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
    from . import backup, lineage, location_mapper, path_model, portability_audit, project_identity, recovery, restore_plan, windows
    from .validate import validate
except ImportError:
    import backup
    import lineage
    import location_mapper
    import path_model
    import portability_audit
    import project_identity
    import recovery
    import restore_plan
    import windows
    from validate import validate


RESTORE_VERSION = "3.4.2"
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
    "plugins",
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


def _safe_target(
    path: Path, profile: Path, approved_external_roots: tuple[Path, ...] = ()
) -> None:
    resolved = path.resolve(strict=False)
    profile_resolved = profile.resolve(strict=False)
    allowed_roots = {
        profile_resolved,
        windows.documents_folder(profile).resolve(strict=False),
        windows.desktop_folder(profile).resolve(strict=False),
    }
    if resolved in allowed_roots or resolved == Path(resolved.anchor):
        raise RestoreError(f"Unsafe broad destination path rejected: {resolved}")
    for allowed in allowed_roots:
        try:
            resolved.relative_to(allowed)
            return
        except ValueError:
            continue
    for allowed in approved_external_roots:
        try:
            relative = resolved.relative_to(allowed.resolve(strict=False))
            if relative.parts:
                return
        except ValueError:
            continue
    raise RestoreError(f"Destination path is outside the destination profile: {resolved}")


def resolved_external_roots(
    target_profile: Path, supplied: dict[str, str] | None = None
) -> dict[str, str]:
    registry = location_mapper.load_registry(
        windows.location_mapping_registry_path(target_profile)
    )
    result = location_mapper.external_roots(registry)
    result.update({str(key): str(value) for key, value in (supplied or {}).items()})
    return result


def plan_restore_locations(
    package_root: Path,
    target_profile: Path,
    external_roots: dict[str, str] | None = None,
) -> dict[str, Any]:
    mappings = backup.read_json(package_root / "manifest" / "path-mappings.json")
    if mappings.get("mappingVersion") != 2:
        return {"planVersion": 1, "ready": True, "items": [], "requiredExternalRoots": [], "issues": []}
    return location_mapper.build_plan(
        mappings.get("projects", []),
        target_profile,
        resolved_external_roots(target_profile, external_roots),
        package_root,
    )


def _copy_all(source: Path, destination: Path) -> tuple[int, int]:
    warnings: list[str] = []
    return backup.copy_tree(source, destination, [], warnings)


def _same_volume(first: Path, second: Path) -> bool:
    first_anchor = os.path.normcase(first.resolve(strict=False).anchor)
    second_anchor = os.path.normcase(second.resolve(strict=False).anchor)
    return bool(first_anchor and first_anchor == second_anchor)


def _atomic_directory_move(source: Path, destination: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise RestoreError(f"Transactional source directory is unavailable: {source}")
    if destination.exists() or destination.is_symlink():
        raise RestoreError(f"Transactional destination already exists: {destination}")
    if not _same_volume(source, destination):
        raise RestoreError(
            f"Transactional directory move crosses volumes: {source} -> {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _project_manifest_entries(
    package_root: Path, project: dict[str, Any]
) -> dict[str, tuple[int, str]]:
    prefix = str(project["backupRelativePath"]).rstrip("/") + "/"
    entries: dict[str, tuple[int, str]] = {}
    with (package_root / "manifest" / "sha256.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            relative_path = str(row["relative_path"])
            if relative_path.startswith(prefix):
                entries[relative_path[len(prefix) :]] = (
                    int(row["size"]),
                    str(row["sha256"]).lower(),
                )
    return entries


def _verify_staged_project(
    package_root: Path, project: dict[str, Any], staging: Path
) -> dict[str, int]:
    expected = _project_manifest_entries(package_root, project)
    actual: dict[str, Path] = {}
    for path in staging.rglob("*"):
        if path.is_symlink():
            raise RestoreError(f"Staged project unexpectedly contains a link: {path}")
        if path.is_file():
            actual[path.relative_to(staging).as_posix()] = path
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing[:3]))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected[:3]))
        raise RestoreError("Staged project file set differs: " + "; ".join(details))
    total_bytes = 0
    for relative_path, (expected_size, expected_hash) in expected.items():
        path = actual[relative_path]
        size = path.stat().st_size
        if size != expected_size:
            raise RestoreError(f"Staged project file size differs: {path}")
        if backup.sha256_file(path).lower() != expected_hash:
            raise RestoreError(f"Staged project hash differs: {path}")
        total_bytes += size
    if len(actual) != int(project["fileCount"]):
        raise RestoreError("Staged project file count differs from its inventory.")
    if total_bytes != int(project["totalBytes"]):
        raise RestoreError("Staged project byte count differs from its inventory.")
    return {"files": len(actual), "bytes": total_bytes}


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
    external_roots: dict[str, str] | None = None,
    comparison_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    target_codex = target_profile / ".codex"
    result = validate(package_root, False)
    if not result.get("valid"):
        raise RestoreError("The selected backup is invalid: " + "; ".join(result["errors"][:5]))
    if not target_codex.is_dir() or not (target_codex / "state_5.sqlite").is_file():
        raise RestoreError(
            "Codex is nog niet eenmaal gestart op deze computer. Installeer, open en sluit Codex eerst."
        )
    if not (target_codex / "auth.json").is_file():
        raise RestoreError(
            "No local Codex authentication found. Open Codex, sign in and fully close the app."
        )
    backup.check_codex_not_running(target_codex, allow_running_test)
    if comparison_plan is None and not allow_running_test:
        raise RestoreError("A reviewed phase-6 comparison plan is required before restore.")
    if comparison_plan is not None:
        if comparison_plan.get("planVersion") != restore_plan.PLAN_VERSION:
            raise RestoreError("The reviewed restore plan has an unsupported version.")
        if Path(str(comparison_plan.get("package", ""))).resolve(strict=False) != package_root:
            raise RestoreError("The reviewed restore plan belongs to another backup.")
        if Path(str(comparison_plan.get("targetProfile", ""))).resolve(strict=False) != target_profile:
            raise RestoreError("The reviewed restore plan belongs to another destination.")
        decision_errors = restore_plan.validate_plan_decisions(comparison_plan)
        if decision_errors:
            raise RestoreError(
                "The reviewed restore plan is inconsistent: "
                + "; ".join(decision_errors[:5])
            )
        if not comparison_plan.get("ready"):
            raise RestoreError("The reviewed restore plan still contains blocking issues.")
    location_plan = plan_restore_locations(
        package_root, target_profile, external_roots
    )
    if not location_plan["ready"]:
        details = [item["error"] for item in location_plan.get("issues", [])]
        if location_plan.get("requiredExternalRoots"):
            details.append("one or more external project roots require a reviewed target")
        raise RestoreError("Project location mapping is incomplete: " + "; ".join(details[:5]))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safety_root = windows.recovery_points_folder(target_profile) / stamp
    if safety_root.exists():
        safety_root = safety_root.with_name(safety_root.name + "-" + uuid.uuid4().hex[:6])
    if progress:
        progress(f"Creating safety copy: {safety_root}")
    _copy_codex_safety(target_codex, safety_root / "codex-before-restore")
    identity_registry_path = windows.project_registry_path(target_profile).resolve(
        strict=False
    )
    identity_registry_backup = (
        safety_root / "lifeboat-state-before-restore" / "project-registry.json"
    )
    identity_registry_existed = identity_registry_path.is_file()
    if identity_registry_existed:
        backup.copy_file(identity_registry_path, identity_registry_backup)
    lineage_state_path = windows.lineage_state_path(target_profile).resolve(strict=False)
    lineage_state_backup = (
        safety_root / "lifeboat-state-before-restore" / "lineage-state.json"
    )
    lineage_state_existed = lineage_state_path.is_file()
    if lineage_state_existed:
        backup.copy_file(lineage_state_path, lineage_state_backup)
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
        "identityRegistryPath": str(identity_registry_path),
        "identityRegistryExistedBefore": identity_registry_existed,
        "lineageStatePath": str(lineage_state_path),
        "lineageStateExistedBefore": lineage_state_existed,
        "locationPlan": location_plan,
        "approvedExternalRoots": list(
            resolved_external_roots(target_profile, external_roots).values()
        ),
        "comparisonPlan": comparison_plan,
        "status": "prepared",
    }
    backup.write_json(safety_root / "restore-journal.json", metadata)
    return metadata


class PathTranslator:
    def __init__(
        self,
        package_root: Path,
        target_profile: Path,
        external_roots: dict[str, str] | None = None,
    ):
        self.package_root = package_root
        self.target_profile = target_profile.resolve(strict=False)
        self.package = backup.read_json(package_root / "manifest/package.json")
        self.mappings = backup.read_json(package_root / "manifest/path-mappings.json")
        self.source_profile = Path(self.package["source"]["profilePath"])
        self.source_known_folders = self.package.get("source", {}).get("knownFolders") or {}
        self.target_known_folders = windows.known_folders(self.target_profile)
        self.external_roots = resolved_external_roots(
            self.target_profile, external_roots
        )
        self.approved_external_roots = tuple(
            Path(value).resolve(strict=False) for value in self.external_roots.values()
        )
        self.project_targets: dict[str, Path] = {}
        self.attachment_targets: dict[str, Path] = {}
        self.replacements: list[tuple[str, str]] = []
        for item in self.mappings.get("projects", []):
            original = Path(item["originalPath"])
            project_id = str(item["id"])
            target = self._project_target(original, project_id, item.get("location"))
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

    def _project_target(
        self, original: Path, project_id: str, location: dict[str, Any] | None = None
    ) -> Path:
        # Portable locations are resolved without relying on the source username.
        # External roots are accepted only after the mapper has approved them.
        if location and not path_model.validate_location(location):
            if location.get("kind") in {"known-folder", "profile", "external-root"}:
                resolved = path_model.resolve_portable_location(
                    location,
                    str(self.target_profile),
                    self.target_known_folders,
                    self.external_roots,
                )
                if resolved is not None:
                    target = Path(str(resolved))
                    _safe_target(
                        target, self.target_profile, self.approved_external_roots
                    )
                    return target
                if location.get("kind") == "external-root":
                    raise RestoreError(
                        f"External project {original} has no reviewed target mapping."
                    )
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
        _safe_target(target, self.target_profile, self.approved_external_roots)
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


def _selected_rows(
    connection: sqlite3.Connection,
    table: str,
    where: str,
    values: tuple[Any, ...],
) -> list[dict[str, Any]]:
    if not _table_exists(connection, "main", table):
        return []
    connection.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM {_quote(table)} WHERE {where}", values
            ).fetchall()
        ]
    finally:
        connection.row_factory = None


def _insert_row(
    connection: sqlite3.Connection, table: str, row: dict[str, Any]
) -> None:
    if not row or not _table_exists(connection, "main", table):
        return
    available = {item["name"] for item in _columns(connection, "main", table)}
    names = [name for name in row if name in available]
    if not names:
        return
    placeholders = ",".join("?" for _name in names)
    connection.execute(
        f"INSERT OR REPLACE INTO {_quote(table)} "
        f"({','.join(_quote(name) for name in names)}) VALUES({placeholders})",
        tuple(row[name] for name in names),
    )


def _conversation_decisions(
    comparison_plan: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("key", "")).split("/", 1)[1]: item
        for item in (comparison_plan or {}).get("items", [])
        if item.get("kind") == "conversation"
        and "/" in str(item.get("key", ""))
        and item.get("decision") in {"keep-target", "keep-both", "skip", "keep-source"}
    }


def _project_decisions(
    comparison_plan: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("key", "")).split("/", 1)[1]: item
        for item in (comparison_plan or {}).get("items", [])
        if item.get("kind") == "project"
        and "/" in str(item.get("key", ""))
        and item.get("decision") in {
            "retain-default", "retain", "keep-source", "keep-target",
            "archive", "delete", "skip",
        }
    }


def _remove_dispositioned_identity_roots(
    registry: dict[str, Any], comparison_plan: dict[str, Any] | None
) -> int:
    root_ids = {
        project_id
        for project_id, item in _project_decisions(comparison_plan).items()
        if not item.get("source")
        and item.get("proposedAction") in {"archive", "delete-project"}
    }
    if not root_ids:
        return 0
    removed = 0
    retained_projects: list[dict[str, Any]] = []
    for project in registry.get("projects", []):
        roots = project.get("roots", [])
        kept_roots = [
            root for root in roots if str(root.get("rootId")) not in root_ids
        ]
        removed += len(roots) - len(kept_roots)
        if kept_roots:
            project["roots"] = kept_roots
            retained_projects.append(project)
    registry["projects"] = retained_projects
    return removed


def _build_restored_database(
    package_root: Path,
    target_database_template: Path,
    output_database: Path,
    translator: PathTranslator,
    comparison_plan: dict[str, Any] | None = None,
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
        decisions = _conversation_decisions(comparison_plan)
        project_decisions = _project_decisions(comparison_plan)
        target_thread_ids_before = {
            str(row[0])
            for row in connection.execute('SELECT "id" FROM "threads"').fetchall()
        }
        source_thread_ids = {
            str(row[0])
            for row in connection.execute('SELECT "id" FROM src."threads"').fetchall()
        }
        preserve_ids = {
            thread_id
            for thread_id, item in decisions.items()
            if item.get("proposedAction") in {"retain", "keep-both"}
        }
        captured_threads: dict[str, dict[str, Any]] = {}
        captured_tools: dict[str, list[dict[str, Any]]] = {}
        captured_edges: list[dict[str, Any]] = []
        for thread_id in preserve_ids:
            rows = _selected_rows(connection, "threads", '"id"=?', (thread_id,))
            if rows:
                captured_threads[thread_id] = rows[0]
                reviewed_path = str(decisions[thread_id].get("target") or "").replace(
                    "\\\\?\\", ""
                )
                captured_path = str(rows[0].get("rollout_path") or "").replace(
                    "\\\\?\\", ""
                )
                if (
                    reviewed_path
                    and Path(reviewed_path).resolve(strict=False)
                    != Path(captured_path).resolve(strict=False)
                ):
                    raise RestoreError(
                        f"Conversation changed after plan review: {thread_id}"
                    )
                if decisions[thread_id].get("proposedAction") == "keep-both":
                    clone_id = str(decisions[thread_id].get("cloneId"))
                    if clone_id in (target_thread_ids_before | source_thread_ids):
                        raise RestoreError(
                            f"Conversation clone ID already exists: {clone_id}"
                        )
            captured_tools[thread_id] = _selected_rows(
                connection, "thread_dynamic_tools", '"thread_id"=?', (thread_id,)
            )
            captured_edges.extend(
                _selected_rows(
                    connection,
                    "thread_spawn_edges",
                    '"parent_thread_id"=? OR "child_thread_id"=?',
                    (thread_id, thread_id),
                )
            )
        required_target_project_ids = {
            str(row.get("project_id"))
            for row in captured_threads.values()
            if row.get("project_id")
        }
        removed_project_ids = {
            str(project_id)
            for item in project_decisions.values()
            if item.get("proposedAction") in {"archive", "delete-project"}
            for project_id in item.get("codexProjectIds", [])
        }
        retained_plan_project_ids = {
            str(project_id)
            for item in project_decisions.values()
            if item.get("proposedAction") == "retain"
            for project_id in item.get("codexProjectIds", [])
        }
        required_target_project_ids.update(retained_plan_project_ids)
        required_target_project_ids.difference_update(removed_project_ids)
        captured_projects: dict[str, dict[str, Any]] = {}
        captured_project_roots: dict[str, list[dict[str, Any]]] = {}
        for project_id in required_target_project_ids:
            rows = _selected_rows(
                connection, "projects", '"id"=?', (project_id,)
            )
            if rows:
                captured_projects[project_id] = rows[0]
            captured_project_roots[project_id] = _selected_rows(
                connection, "project_roots", '"project_id"=?', (project_id,)
            )
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
            clone_map: dict[str, str] = {}
            retained_count = 0
            cloned_count = 0
            retained_project_count = 0
            existing_project_ids = (
                {
                    str(row[0])
                    for row in connection.execute('SELECT "id" FROM "projects"').fetchall()
                }
                if _table_exists(connection, "main", "projects")
                else set()
            )
            for project_id, project_row in captured_projects.items():
                if project_id in existing_project_ids:
                    continue
                _insert_row(connection, "projects", project_row)
                for root_row in captured_project_roots.get(project_id, []):
                    _insert_row(connection, "project_roots", root_row)
                existing_project_ids.add(project_id)
                retained_project_count += 1
            for thread_id, item in decisions.items():
                action = item.get("proposedAction")
                captured = captured_threads.get(thread_id)
                if action == "retain" and captured:
                    if captured.get("project_id") not in existing_project_ids:
                        captured["project_id"] = None
                    if _table_exists(connection, "main", "thread_dynamic_tools"):
                        connection.execute(
                            'DELETE FROM "thread_dynamic_tools" WHERE "thread_id"=?',
                            (thread_id,),
                        )
                    if _table_exists(connection, "main", "thread_spawn_edges"):
                        connection.execute(
                            'DELETE FROM "thread_spawn_edges" '
                            'WHERE "parent_thread_id"=? OR "child_thread_id"=?',
                            (thread_id, thread_id),
                        )
                    connection.execute('DELETE FROM "threads" WHERE "id"=?', (thread_id,))
                    _insert_row(connection, "threads", captured)
                    for row in captured_tools.get(thread_id, []):
                        _insert_row(connection, "thread_dynamic_tools", row)
                    retained_count += 1
                elif action == "keep-both" and captured:
                    clone_id = str(item["cloneId"])
                    clone_map[thread_id] = clone_id
                    clone = dict(captured)
                    clone["id"] = clone_id
                    if clone.get("project_id") not in existing_project_ids:
                        clone["project_id"] = None
                    if "title" in clone:
                        clone["title"] = f"{clone.get('title') or thread_id} (destination copy)"
                    if "rollout_path" in clone:
                        clone["rollout_path"] = str(
                            translator.target_profile
                            / ".codex"
                            / Path(*PurePosixPath(str(item["cloneRelativePath"])).parts)
                        )
                    _insert_row(connection, "threads", clone)
                    for row in captured_tools.get(thread_id, []):
                        cloned_tool = dict(row)
                        cloned_tool["thread_id"] = clone_id
                        _insert_row(connection, "thread_dynamic_tools", cloned_tool)
                    cloned_count += 1
            if _table_exists(connection, "main", "thread_spawn_edges"):
                final_ids = {
                    str(row[0])
                    for row in connection.execute('SELECT "id" FROM "threads"').fetchall()
                }
                seen_edges: set[tuple[str, str]] = set()
                for row in captured_edges:
                    edge = dict(row)
                    parent = clone_map.get(
                        str(edge.get("parent_thread_id")),
                        str(edge.get("parent_thread_id")),
                    )
                    child = clone_map.get(
                        str(edge.get("child_thread_id")),
                        str(edge.get("child_thread_id")),
                    )
                    edge["parent_thread_id"] = parent
                    edge["child_thread_id"] = child
                    edge_key = (parent, child)
                    if parent in final_ids and child in final_ids and edge_key not in seen_edges:
                        _insert_row(connection, "thread_spawn_edges", edge)
                        seen_edges.add(edge_key)
            counts["retainedTargetThreads"] = retained_count
            counts["clonedTargetThreads"] = cloned_count
            counts["retainedTargetProjectsForThreads"] = retained_project_count
        connection.execute("DETACH DATABASE src")
        check = backup.sqlite_quick_check(connection)
        if check != "ok":
            raise RestoreError(f"Restored database failed quick_check: {check}")
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


def _rewrite_cloned_rollout(
    source: Path,
    destination: Path,
    translator: PathTranslator,
    original_id: str,
    clone_id: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".restore.tmp")
    with source.open("r", encoding="utf-8-sig", errors="strict") as reader:
        with temporary.open("w", encoding="utf-8", newline="\n") as writer:
            for number, line in enumerate(reader, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RestoreError(
                        f"Destination conversation has invalid JSON on line {number}: {source}"
                    ) from exc
                value = translator.value(value)
                if (
                    isinstance(value, dict)
                    and value.get("type") == "session_meta"
                    and isinstance(value.get("payload"), dict)
                    and str(value["payload"].get("id")) == original_id
                ):
                    value["payload"]["id"] = clone_id
                writer.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(temporary, destination)


def _restore_preserved_conversations(
    safety_root: Path,
    target_codex: Path,
    translator: PathTranslator,
    comparison_plan: dict[str, Any] | None,
) -> dict[str, int]:
    retained = 0
    cloned = 0
    safety_codex = safety_root / "codex-before-restore"
    target_codex_resolved = target_codex.resolve(strict=False)
    for thread_id, item in _conversation_decisions(comparison_plan).items():
        action = item.get("proposedAction")
        if action not in {"retain", "keep-both"}:
            continue
        original_value = str(item.get("target") or "").replace("\\\\?\\", "")
        if not original_value:
            raise RestoreError(f"Preserved conversation has no rollout path: {thread_id}")
        original = Path(original_value).resolve(strict=False)
        try:
            relative = original.relative_to(target_codex_resolved)
        except ValueError as exc:
            raise RestoreError(
                f"Conversation rollout is outside the destination Codex folder: {original}"
            ) from exc
        source = safety_codex / relative
        if not source.is_file():
            raise RestoreError(f"Safety copy lacks conversation rollout: {source}")
        if action == "retain":
            _rewrite_copy(source, target_codex / relative, translator)
            retained += 1
            continue
        clone_id = str(item["cloneId"])
        clone_relative = PurePosixPath(str(item["cloneRelativePath"]))
        destination = target_codex / Path(*clone_relative.parts)
        _rewrite_cloned_rollout(source, destination, translator, thread_id, clone_id)
        cloned += 1
    return {"retained": retained, "cloned": cloned}


def _rebuild_session_index(database: Path, target_codex: Path) -> int:
    connection = sqlite3.connect(database)
    try:
        columns = {
            str(row[1]) for row in connection.execute('PRAGMA table_info("threads")')
        }
        if "id" not in columns:
            raise RestoreError("Destination thread table has no conversation ID column.")
        title_expression = '"title"' if "title" in columns else '"id"'
        archived_expression = '"archived"' if "archived" in columns else "0"
        order_expression = (
            '"recency_at_ms" DESC' if "recency_at_ms" in columns else '"id"'
        )
        rows = connection.execute(
            f'SELECT "id",{title_expression},{archived_expression} '
            f'FROM "threads" ORDER BY {order_expression}'
        ).fetchall()
    finally:
        connection.close()
    active: list[dict[str, str]] = []
    seen: set[str] = set()
    for thread_id, title, archived in rows:
        value = str(thread_id)
        if bool(archived) or value in seen:
            continue
        seen.add(value)
        active.append({"id": value, "title": str(title or value)})
    destination = target_codex / "session_index.jsonl"
    temporary = destination.with_name(destination.name + ".restore.tmp")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for item in active:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(temporary, destination)
    return len(active)


def _restore_global_state(
    package_root: Path,
    target_codex: Path,
    translator: PathTranslator,
    comparison_plan: dict[str, Any] | None = None,
) -> None:
    target_path = target_codex / ".codex-global-state.json"
    current = backup.read_json(target_path) if target_path.is_file() else {}
    source = translator.value(
        backup.read_json(package_root / "codex" / "portable-global-state.json")
    )
    project_decisions = _project_decisions(comparison_plan)
    retained_project_ids = {
        str(project_id)
        for item in project_decisions.values()
        if item.get("proposedAction") == "retain"
        for project_id in item.get("codexProjectIds", [])
    }
    removed_project_ids = {
        str(project_id)
        for item in project_decisions.values()
        if item.get("proposedAction") in {"archive", "delete-project"}
        for project_id in item.get("codexProjectIds", [])
    }
    incoming_projects = dict(source.get("local-projects") or {})
    local_projects = dict(current.get("local-projects") or {})
    for project_id in retained_project_ids:
        if project_id in local_projects and project_id not in incoming_projects:
            incoming_projects[project_id] = local_projects[project_id]
    for project_id in removed_project_ids:
        incoming_projects.pop(project_id, None)
    if incoming_projects or "local-projects" in source or retained_project_ids:
        source["local-projects"] = incoming_projects

    incoming_order = [
        str(value)
        for value in (source.get("project-order") or [])
        if str(value) not in removed_project_ids
    ]
    local_order = [str(value) for value in (current.get("project-order") or [])]
    for project_id in local_order:
        if project_id in retained_project_ids and project_id not in incoming_order:
            incoming_order.append(project_id)
    if incoming_order or "project-order" in source or retained_project_ids:
        source["project-order"] = incoming_order

    for key in PORTABLE_STATE_KEYS:
        current.pop(key, None)
    for key, value in source.items():
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
            destination.mkdir(parents=True, exist_ok=True)
            for source in entry.rglob("*"):
                target = destination / source.relative_to(entry)
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not source.is_file():
                    continue
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
        _safe_target(
            target,
            translator.target_profile,
            translator.approved_external_roots,
        )
        backup.copy_file(source, target)
        count += 1
    return count


def _restore_projects(
    package_root: Path,
    safety_root: Path,
    translator: PathTranslator,
    journal: dict[str, Any],
    progress: Callable[[str], None] | None,
    comparison_plan: dict[str, Any] | None = None,
    fail_after_quarantine_for_test: bool = False,
    fail_after_activation_for_test: bool = False,
) -> int:
    projects = backup.read_json(package_root / "manifest" / "projects.json")
    copied = 0
    project_journal: list[dict[str, Any]] = journal.setdefault("projects", [])
    planned_items = {
        str(item.get("key")): item
        for item in (comparison_plan or {}).get("items", [])
        if item.get("kind") == "project"
    }
    for item in projects:
        project_id = str(item["id"])
        planned_item = planned_items.get(f"project/{project_id}") or {}
        planned_action = str(planned_item.get("proposedAction") or "")
        if planned_action in {"none", "retain"}:
            if progress:
                progress(f"Keeping identical or retained project: {translator.project_targets[project_id]}")
            continue
        source = package_root / Path(*PurePosixPath(item["backupRelativePath"]).parts)
        target = translator.project_targets[project_id]
        _safe_target(
            target,
            translator.target_profile,
            translator.approved_external_roots,
        )
        transaction_id = uuid.uuid4().hex[:12]
        project_token = uuid.uuid5(uuid.NAMESPACE_URL, project_id).hex[:12]
        staging = target.parent / (
            f".codex-lifeboat-stage-{project_token}-{transaction_id}"
        )
        if planned_action == "archive-and-replace":
            quarantine = (
                target.parent
                / "Codex Lifeboat Project Archives"
                / f"{target.name}-{transaction_id}"
            )
        else:
            recovery_root = (
                target.parent / ".codex-lifeboat-recovery" / safety_root.name
            )
            quarantine = recovery_root / f"{project_token}-{transaction_id}"
        _safe_target(
            staging,
            translator.target_profile,
            translator.approved_external_roots,
        )
        _safe_target(
            quarantine,
            translator.target_profile,
            translator.approved_external_roots,
        )
        if not _same_volume(staging, target) or not _same_volume(quarantine, target):
            raise RestoreError(f"Project transaction is not on one volume: {target}")
        record = {
            "id": project_id,
            "target": str(target),
            "existedBefore": target.exists(),
            "strategy": "transactional-mirror",
            "transactionId": transaction_id,
            "stagingPath": str(staging),
            "quarantinePath": str(quarantine),
            "previousTargetDisposition": (
                "archive" if planned_action == "archive-and-replace" else "recovery"
            ),
            "status": "planned",
        }
        if planned_action == "archive-and-replace":
            planned_item["dispositionPath"] = str(quarantine)
            planned_item["disposition"] = "archive"
        project_journal.append(record)
        backup.write_json(safety_root / "restore-journal.json", journal)
        if progress:
            progress(f"Staging project on destination volume: {target}")
        files, _ = _copy_all(source, staging)
        record["status"] = "staged"
        record["stagedAtUtc"] = backup.utc_now()
        backup.write_json(safety_root / "restore-journal.json", journal)
        verified = _verify_staged_project(package_root, item, staging)
        if files != verified["files"]:
            raise RestoreError("Staged copy count differs from verified project count.")
        record["stagedVerification"] = verified
        record["status"] = "staged-verified"
        record["verifiedAtUtc"] = backup.utc_now()
        backup.write_json(safety_root / "restore-journal.json", journal)
        if planned_action == "archive-and-replace" and not target.exists():
            raise RestoreError(f"Reviewed project to archive is no longer present: {target}")
        if target.exists():
            if progress:
                progress(
                    f"Archiving previous project: {target}"
                    if planned_action == "archive-and-replace"
                    else f"Quarantining previous project: {target}"
                )
            _atomic_directory_move(target, quarantine)
            record["status"] = "target-quarantined"
            record["quarantinedAtUtc"] = backup.utc_now()
            backup.write_json(safety_root / "restore-journal.json", journal)
            if fail_after_quarantine_for_test:
                raise RestoreError("Intentional failure after project quarantine")
        if progress:
            progress(f"Activating verified project mirror: {target}")
        _atomic_directory_move(staging, target)
        record["status"] = "activated"
        record["activatedAtUtc"] = backup.utc_now()
        backup.write_json(safety_root / "restore-journal.json", journal)
        if fail_after_activation_for_test:
            raise RestoreError("Intentional failure after project activation")
        record["status"] = "complete"
        record["completedAtUtc"] = backup.utc_now()
        backup.write_json(safety_root / "restore-journal.json", journal)
        copied += verified["files"]
    return copied


def _apply_destination_project_decisions(
    safety_root: Path,
    translator: PathTranslator,
    journal: dict[str, Any],
    progress: Callable[[str], None] | None,
    comparison_plan: dict[str, Any] | None,
    fail_after_move_for_test: bool = False,
) -> dict[str, Any]:
    archived = 0
    removed = 0
    paths: list[str] = []
    project_journal: list[dict[str, Any]] = journal.setdefault("projects", [])
    for project_id, item in _project_decisions(comparison_plan).items():
        action = item.get("proposedAction")
        if item.get("source") or action not in {"archive", "delete-project"}:
            continue
        target = Path(str(item.get("target") or ""))
        target_errors = location_mapper.validate_external_root(
            target, translator.target_profile
        )
        if target_errors:
            raise RestoreError(
                f"Reviewed destination-only project is unsafe: {target}: "
                + "; ".join(target_errors)
            )
        if not target.is_dir() or target.is_symlink():
            raise RestoreError(f"Reviewed destination-only project is unavailable: {target}")
        transaction_id = uuid.uuid4().hex[:12]
        project_token = uuid.uuid5(uuid.NAMESPACE_URL, project_id).hex[:12]
        if action == "archive":
            moved_path = (
                target.parent
                / "Codex Lifeboat Project Archives"
                / f"{target.name}-{transaction_id}"
            )
            disposition = "archive"
        else:
            moved_path = (
                target.parent
                / ".codex-lifeboat-recovery"
                / safety_root.name
                / f"deleted-{project_token}-{transaction_id}"
            )
            disposition = "delete-to-recovery"
        moved_errors = location_mapper.validate_external_root(
            moved_path, translator.target_profile
        )
        if moved_errors:
            raise RestoreError(
                f"Project disposition path is unsafe: {moved_path}: "
                + "; ".join(moved_errors)
            )
        if not _same_volume(target, moved_path):
            raise RestoreError(f"Project disposition crosses volumes: {target}")
        record = {
            "id": project_id,
            "target": str(target),
            "existedBefore": True,
            "strategy": "destination-project-disposition",
            "disposition": disposition,
            "movedPath": str(moved_path),
            "status": "planned",
        }
        item["dispositionPath"] = str(moved_path)
        item["disposition"] = disposition
        project_journal.append(record)
        backup.write_json(safety_root / "restore-journal.json", journal)
        if progress:
            progress(
                f"Archiving destination-only project: {target}"
                if action == "archive"
                else f"Removing destination-only project to recovery: {target}"
            )
        _atomic_directory_move(target, moved_path)
        record["status"] = "moved"
        record["movedAtUtc"] = backup.utc_now()
        backup.write_json(safety_root / "restore-journal.json", journal)
        if fail_after_move_for_test:
            raise RestoreError("Intentional failure after destination project move")
        record["status"] = "complete"
        record["completedAtUtc"] = backup.utc_now()
        backup.write_json(safety_root / "restore-journal.json", journal)
        paths.append(str(moved_path))
        if action == "archive":
            archived += 1
        else:
            removed += 1
    return {"archived": archived, "removed": removed, "paths": paths}


def rollback_restore(safety_root: Path, target_profile: Path) -> None:
    journal_path = safety_root / "restore-journal.json"
    journal = backup.read_json(journal_path)
    target_codex = target_profile / ".codex"
    if target_codex.exists():
        _remove_path(target_codex)
    _copy_all(safety_root / "codex-before-restore", target_codex)
    approved_external_roots = tuple(
        Path(value).resolve(strict=False)
        for value in journal.get("approvedExternalRoots", [])
    )
    for item in reversed(journal.get("projects", [])):
        target = Path(item["target"])
        if item.get("strategy") == "destination-project-disposition":
            moved_path = Path(item["movedPath"])
            target_errors = location_mapper.validate_external_root(
                target, target_profile
            )
            moved_errors = location_mapper.validate_external_root(
                moved_path, target_profile
            )
            if target_errors or moved_errors:
                raise RestoreError(
                    "Cannot safely roll back destination-only project: "
                    + "; ".join([*target_errors, *moved_errors])
                )
            if moved_path.exists():
                if target.exists() or target.is_symlink():
                    raise RestoreError(
                        f"Cannot roll back project because its target was recreated: {target}"
                    )
                _atomic_directory_move(moved_path, target)
            item["status"] = "rolled-back"
            item["rolledBackAtUtc"] = backup.utc_now()
            continue
        _safe_target(target, target_profile, approved_external_roots)
        if item.get("strategy") == "transactional-mirror":
            staging = Path(item["stagingPath"])
            quarantine = Path(item["quarantinePath"])
            _safe_target(staging, target_profile, approved_external_roots)
            _safe_target(quarantine, target_profile, approved_external_roots)
            if quarantine.exists():
                if target.exists() or target.is_symlink():
                    _remove_path(target)
                _atomic_directory_move(quarantine, target)
            elif not item.get("existedBefore"):
                activated_without_journal_update = (
                    item.get("status") == "staged-verified" and not staging.exists()
                )
                if (
                    item.get("status") in {"activated", "complete"}
                    or activated_without_journal_update
                ) and (target.exists() or target.is_symlink()):
                    _remove_path(target)
            if staging.exists() or staging.is_symlink():
                _remove_path(staging)
            item["status"] = "rolled-back"
            item["rolledBackAtUtc"] = backup.utc_now()
            continue
        if target.exists():
            _remove_path(target)
        if item.get("existedBefore"):
            source = safety_root / item["safetyRelativePath"]
            _copy_all(source, target)
    identity_registry_path = Path(
        journal.get("identityRegistryPath")
        or windows.project_registry_path(target_profile)
    )
    identity_registry_backup = (
        safety_root / "lifeboat-state-before-restore" / "project-registry.json"
    )
    if journal.get("identityRegistryExistedBefore"):
        if identity_registry_backup.is_file():
            backup.copy_file(identity_registry_backup, identity_registry_path)
    elif identity_registry_path.exists():
        identity_registry_path.unlink()
    lineage_state_path = Path(
        journal.get("lineageStatePath") or windows.lineage_state_path(target_profile)
    )
    lineage_state_backup = (
        safety_root / "lifeboat-state-before-restore" / "lineage-state.json"
    )
    if journal.get("lineageStateExistedBefore"):
        if lineage_state_backup.is_file():
            backup.copy_file(lineage_state_backup, lineage_state_path)
    elif lineage_state_path.exists():
        lineage_state_path.unlink()
    journal["status"] = "rolled-back"
    journal["rolledBackAtUtc"] = backup.utc_now()
    backup.write_json(journal_path, journal)


def _reported_comparison_plan(
    package_root: Path, target_profile: Path
) -> dict[str, Any] | None:
    reports = windows.documents_folder(target_profile) / "Codex Restore Reports"
    if not reports.is_dir():
        return None
    candidates = sorted(
        (path for path in reports.glob("restore-*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates:
        try:
            report = backup.read_json(path)
            if (
                report.get("status") == "complete"
                and Path(str(report.get("package", ""))).resolve(strict=False)
                == package_root.resolve(strict=False)
            ):
                return report.get("comparisonPlan")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def verify_restored(
    package_root: Path,
    target_profile: Path,
    translator: PathTranslator | None = None,
    comparison_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    target_codex = target_profile / ".codex"
    translator = translator or PathTranslator(package_root, target_profile)
    comparison_plan = comparison_plan or _reported_comparison_plan(
        package_root, target_profile
    )
    errors: list[str] = []
    notices: list[str] = []
    checks: dict[str, Any] = {}
    package = backup.read_json(package_root / "manifest" / "package.json")
    database = target_codex / "state_5.sqlite"
    database_project_ids: set[str] = set()
    try:
        connection = sqlite3.connect(database)
        try:
            check = backup.sqlite_quick_check(connection)
            checks["sqliteQuickCheck"] = check
            if check != "ok":
                errors.append(f"SQLite quick_check: {check}")
            actual_thread_ids = {
                str(row[0]) for row in connection.execute("SELECT id FROM threads").fetchall()
            }
            expected_thread_ids = {
                str(item["id"])
                for item in backup.read_json(package_root / "manifest" / "threads.json")
            }
            for thread_id, item in _conversation_decisions(comparison_plan).items():
                if item.get("proposedAction") == "retain":
                    expected_thread_ids.add(thread_id)
                elif item.get("proposedAction") == "keep-both":
                    expected_thread_ids.add(str(item["cloneId"]))
            thread_count = len(actual_thread_ids)
            checks["threads"] = thread_count
            checks["expectedThreadIds"] = len(expected_thread_ids)
            if actual_thread_ids != expected_thread_ids:
                missing_ids = sorted(expected_thread_ids - actual_thread_ids)
                unexpected_ids = sorted(actual_thread_ids - expected_thread_ids)
                errors.append(
                    "Conversation IDs differ from the reviewed restore plan: "
                    f"missing={missing_ids[:3]}, unexpected={unexpected_ids[:3]}"
                )
            rollout_rows = connection.execute("SELECT id,rollout_path FROM threads").fetchall()
            if connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='projects'"
            ).fetchone()[0]:
                database_project_ids = {
                    str(row[0])
                    for row in connection.execute('SELECT "id" FROM "projects"').fetchall()
                }
            thread_columns = {
                str(row[1])
                for row in connection.execute('PRAGMA table_info("threads")').fetchall()
            }
            active_thread_ids = (
                {
                    str(row[0])
                    for row in connection.execute(
                        'SELECT "id" FROM "threads" WHERE COALESCE("archived",0)=0'
                    ).fetchall()
                }
                if "archived" in thread_columns
                else set(actual_thread_ids)
            )
        finally:
            connection.close()
        session_index = backup.read_session_index(target_codex / "session_index.jsonl")
        index_ids = set(session_index.get("threadIds", []))
        checks["recentIndexEntries"] = len(index_ids)
        if session_index.get("invalidLines") or session_index.get("duplicateThreadIds"):
            errors.append("Recent conversation index contains invalid or duplicate entries.")
        if index_ids != active_thread_ids:
            errors.append("Recent conversation index does not match active conversations.")
        for thread_id, rollout_path in rollout_rows:
            path = Path(str(rollout_path).replace("\\\\?\\", ""))
            if not path.is_file():
                errors.append(f"Rollout ontbreekt voor {thread_id}: {path}")
                continue
            rollout_id, rollout_error = backup.parse_session_meta(path)
            if rollout_error or rollout_id != str(thread_id):
                errors.append(f"Invalid rollout ID for {thread_id}: {rollout_error or rollout_id}")
    except Exception as exc:
        errors.append(f"Database validation failed: {exc}")
    projects = backup.read_json(package_root / "manifest" / "projects.json")
    expected_hashes: dict[str, str] = {}
    with (package_root / "manifest" / "sha256.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            expected_hashes[row["relative_path"]] = row["sha256"].lower()
    plan_project_items = {
        str(item.get("key")): item
        for item in (comparison_plan or {}).get("items", [])
        if item.get("kind") == "project"
    }
    checked_projects = 0
    checked_dispositions = 0

    def verify_fingerprint(item: dict[str, Any], path: Path, label: str) -> None:
        nonlocal checked_dispositions
        expected = item.get("targetFingerprint")
        if not expected:
            errors.append(f"No reviewed fingerprint available for {label}: {path}")
            return
        if not path.is_dir():
            errors.append(f"Reviewed project directory missing for {label}: {path}")
            return
        actual, _files, _bytes = restore_plan._tree_fingerprint(
            path, item.get("fingerprintMetadata")
        )
        if actual != expected:
            errors.append(f"Reviewed project changed during {label}: {path}")
            return
        checked_dispositions += 1

    for item in projects:
        project_id = str(item["id"])
        target = translator.project_targets[project_id]
        plan_item = plan_project_items.get(f"project/{project_id}", {})
        action = str(plan_item.get("proposedAction") or "none")
        if action == "retain":
            verify_fingerprint(plan_item, target, "retention")
            checked_projects += 1
            continue
        if not target.is_dir():
            errors.append(f"Project directory missing: {target}")
            continue
        files = [path for path in target.rglob("*") if path.is_file()]
        size = sum(path.stat().st_size for path in files)
        if len(files) != int(item["fileCount"]):
            errors.append(f"File count differs for project {target}")
        if size != int(item["totalBytes"]):
            errors.append(f"Byteaantal wijkt af voor project {target}")
        prefix = str(item["backupRelativePath"]).rstrip("/") + "/"
        for relative_path, expected_hash in expected_hashes.items():
            if not relative_path.startswith(prefix):
                continue
            project_relative = PurePosixPath(relative_path[len(prefix) :])
            target_file = target / Path(*project_relative.parts)
            if not target_file.is_file():
                errors.append(f"Project file missing: {target_file}")
            elif backup.sha256_file(target_file) != expected_hash:
                errors.append(f"Projecthash wijkt af: {target_file}")
        checked_projects += 1
        if action == "archive-and-replace":
            disposition_value = plan_item.get("dispositionPath")
            if not disposition_value:
                errors.append(f"Reviewed project archive path is missing for {target}")
            else:
                verify_fingerprint(plan_item, Path(str(disposition_value)), "archive")

    for key, item in plan_project_items.items():
        if item.get("source") is not None:
            continue
        action = str(item.get("proposedAction") or "retain")
        target = Path(str(item.get("target") or ""))
        codex_project_ids = {str(value) for value in item.get("codexProjectIds", [])}
        if action == "retain":
            verify_fingerprint(item, target, "retention")
            checked_projects += 1
            missing_registrations = sorted(codex_project_ids - database_project_ids)
            if missing_registrations:
                errors.append(
                    "Retained project registrations are missing: "
                    + ", ".join(missing_registrations[:3])
                )
        elif action in {"archive", "delete-project"}:
            if target.exists():
                errors.append(f"Dispositioned project is still active: {target}")
            disposition_value = item.get("dispositionPath")
            if not disposition_value:
                errors.append(f"Project disposition path is missing for {target}")
            else:
                verify_fingerprint(item, Path(str(disposition_value)), action)
            unexpected_registrations = sorted(codex_project_ids & database_project_ids)
            if unexpected_registrations:
                errors.append(
                    "Dispositioned project registrations are still active: "
                    + ", ".join(unexpected_registrations[:3])
                )
    checks["projects"] = checked_projects
    checks["projectDispositions"] = checked_dispositions
    try:
        source_projects = backup.read_json(package_root / "manifest" / "projects.json")
        portability = portability_audit.audit(
            target_profile,
            target_codex,
            extra_project_roots=list(translator.project_targets.values()),
            legacy_roots=[translator.source_profile]
            + [str(item.get("sourcePath") or "") for item in source_projects],
        )
        portability_summary = portability.get("summary") or {}
        remaining = int(portability_summary.get("needsReviewReferences", 0))
        old_source = int(portability_summary.get("oldSourceReferences", 0))
        checks["pathPortability"] = {
            "status": "attention" if remaining else "portable",
            "needsReviewReferences": remaining,
            "oldSourceReferences": old_source,
            "fieldsNeedingReview": int(
                portability_summary.get("fieldsNeedingReview", 0)
            ),
        }
        if old_source:
            notices.append(
                f"{old_source} preserved path reference(s) still point to an old source location."
            )
        elif remaining:
            notices.append(
                f"{remaining} preserved path reference(s) remain unchanged because no safe translation rule is known."
            )
    except Exception as exc:
        checks["pathPortability"] = {"status": "not-checked"}
        notices.append(
            "Post-restore path portability could not be checked: "
            + type(exc).__name__
        )
    return {
        "valid": not errors,
        "errors": errors,
        "notices": notices,
        "checks": checks,
    }


def restore_backup(
    package_root: Path,
    target_profile: Path,
    safety_root: Path,
    progress: Callable[[str], None] | None = None,
    fail_after_database_for_test: bool = False,
    fail_after_identity_for_test: bool = False,
    fail_after_project_quarantine_for_test: bool = False,
    fail_after_project_activation_for_test: bool = False,
    fail_after_conversations_for_test: bool = False,
    fail_after_destination_project_move_for_test: bool = False,
    external_roots: dict[str, str] | None = None,
) -> dict[str, Any]:
    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    target_codex = target_profile / ".codex"
    safety_root = safety_root.resolve()
    journal_path = safety_root / "restore-journal.json"
    journal = backup.read_json(journal_path)
    if journal.get("status") != "prepared":
        raise RestoreError("Safety copy is not in prepared status.")
    translator = PathTranslator(package_root, target_profile, external_roots)
    auth_path = target_codex / "auth.json"
    auth_hash_before = backup.sha256_file(auth_path)
    temporary_database = safety_root / "state_5.restored.tmp.sqlite"
    try:
        journal["status"] = "restoring"
        journal["startedAtUtc"] = backup.utc_now()
        backup.write_json(journal_path, journal)
        project_files = _restore_projects(
            package_root,
            safety_root,
            translator,
            journal,
            progress,
            journal.get("comparisonPlan"),
            fail_after_project_quarantine_for_test,
            fail_after_project_activation_for_test,
        )
        project_dispositions = _apply_destination_project_decisions(
            safety_root,
            translator,
            journal,
            progress,
            journal.get("comparisonPlan"),
            fail_after_destination_project_move_for_test,
        )
        backup.write_json(journal_path, journal)
        if progress:
            progress("Building destination database with schema awareness...")
        database_counts = _build_restored_database(
            package_root,
            safety_root / "codex-before-restore" / "state_5.sqlite",
            temporary_database,
            translator,
            journal.get("comparisonPlan"),
        )
        if fail_after_database_for_test:
            raise RestoreError("Opzettelijke foutinjectie na database-opbouw")
        if progress:
            progress("Replacing local portable Codex user data...")
        target_codex.mkdir(parents=True, exist_ok=True)
        # Restore machine identity and authentication from the safety copy.
        safety_codex = safety_root / "codex-before-restore"
        for protected_name in PROTECTED_NAMES:
            source = safety_codex / protected_name
            if source.is_file():
                backup.copy_file(source, target_codex / protected_name)
        portable_files = _restore_portable_profile(package_root, target_codex, translator)
        sessions = _restore_sessions(package_root, target_codex, translator)
        conversation_decisions = _restore_preserved_conversations(
            safety_root,
            target_codex,
            translator,
            journal.get("comparisonPlan"),
        )
        if fail_after_conversations_for_test:
            raise RestoreError("Intentional failure after conversation mirror")
        attachments = _restore_attachments(package_root, translator)
        _restore_global_state(
            package_root,
            target_codex,
            translator,
            journal.get("comparisonPlan"),
        )
        for suffix in ("-wal", "-shm"):
            path = target_codex / f"state_5.sqlite{suffix}"
            if path.exists():
                path.unlink()
        os.replace(temporary_database, target_codex / "state_5.sqlite")
        current_index = backup.read_session_index(
            target_codex / "session_index.jsonl"
        )
        source_active_ids = {
            str(item["id"])
            for item in backup.read_json(
                package_root / "manifest" / "threads.json"
            )
            if not item.get("archived")
        }
        source_index_is_exact = bool(
            current_index.get("present")
            and not current_index.get("invalidLines")
            and not current_index.get("duplicateThreadIds")
            and set(current_index.get("threadIds", [])) == source_active_ids
        )
        if (
            conversation_decisions["retained"]
            or conversation_decisions["cloned"]
            or not source_index_is_exact
        ):
            recent_index_entries = _rebuild_session_index(
                target_codex / "state_5.sqlite", target_codex
            )
        else:
            recent_index_entries = len(source_active_ids)
        if backup.sha256_file(target_codex / "auth.json") != auth_hash_before:
            raise RestoreError("Lokale aanmelding is onverwacht gewijzigd.")
        if progress:
            progress("Running complete final verification...")
        verification = verify_restored(
            package_root,
            target_profile,
            translator,
            journal.get("comparisonPlan"),
        )
        if not verification["valid"]:
            raise RestoreError("Final verification failed: " + "; ".join(verification["errors"][:5]))
        identities_registered = 0
        project_identity_roots_removed = 0
        identity_manifest_path = package_root / "manifest" / "project-identities.json"
        if identity_manifest_path.is_file():
            identity_manifest = backup.read_json(identity_manifest_path)
            identity_registry_path = windows.project_registry_path(target_profile)
            identity_registry = project_identity.load_registry(identity_registry_path)
            project_identity.register_restored_roots(
                identity_registry, identity_manifest, translator.project_targets
            )
            project_identity_roots_removed = _remove_dispositioned_identity_roots(
                identity_registry, journal.get("comparisonPlan")
            )
            project_identity.save_registry(identity_registry_path, identity_registry)
            identities_registered = len(identity_manifest.get("roots", []))
        lineage_registered = False
        lineage_manifest_path = package_root / "manifest" / "lineage.json"
        if lineage_manifest_path.is_file():
            lineage_manifest = backup.read_json(lineage_manifest_path)
            lineage.save_state(
                windows.lineage_state_path(target_profile),
                lineage.state_from_manifest(lineage_manifest),
            )
            lineage_registered = True
        else:
            legacy_lineage_path = windows.lineage_state_path(target_profile)
            if legacy_lineage_path.exists():
                legacy_lineage_path.unlink()
        if fail_after_identity_for_test:
            raise RestoreError("Intentional failure injection after identity registration")
        journal.update(
            {
                "status": "complete",
                "completedAtUtc": backup.utc_now(),
                "databaseCounts": database_counts,
                "projectFilesCopied": project_files,
                "destinationProjectsArchived": project_dispositions["archived"],
                "destinationProjectsRemovedToRecovery": project_dispositions["removed"],
                "destinationProjectDispositionPaths": project_dispositions["paths"],
                "portableFilesCopied": portable_files,
                "sessionsCopied": sessions,
                "targetConversationsRetained": conversation_decisions["retained"],
                "targetConversationsCloned": conversation_decisions["cloned"],
                "recentIndexEntries": recent_index_entries,
                "attachmentsCopied": attachments,
                "projectIdentitiesRegistered": identities_registered,
                "projectIdentityRootsRemoved": project_identity_roots_removed,
                "lineageRegistered": lineage_registered,
                "verification": verification,
                "pathMappings": {
                    key: str(value) for key, value in translator.project_targets.items()
                },
            }
        )
        backup.write_json(journal_path, journal)
        try:
            retention = recovery.enforce_retention(
                target_profile,
                keep=recovery.DEFAULT_KEEP,
                progress=progress,
            )
            journal["recoveryRetention"] = retention
        except Exception as exc:
            # A completed restore remains successful if conservative cleanup cannot
            # prove that an older recovery point is safe to remove.
            journal["recoveryRetentionError"] = f"{type(exc).__name__}: {exc}"
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
            progress("Restore failed; running automatic rollback...")
        rollback_restore(safety_root, target_profile)
        raise
