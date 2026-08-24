"""Read-only comparison and restore planning for package format 2.4."""

from __future__ import annotations

import csv
import copy
import os
import shutil
import sqlite3
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import (
    backup,
    conversation_prefix,
    git_insight,
    lineage,
    location_mapper,
    project_identity,
    windows,
)


PLAN_VERSION = 2
PLAN_STATES = {"identical", "incoming", "destination-only", "removed", "conflicting"}
CONVERSATION_DECISIONS = (
    "keep-source",
    "keep-target",
    "keep-both",
    "skip",
    "cancel",
)
PROJECT_DECISIONS_CONFLICT = (
    "keep-source",
    "keep-target",
    "archive",
    "skip",
    "cancel",
)
PROJECT_DECISIONS_DESTINATION_ONLY = (
    "retain",
    "archive",
    "delete",
    "cancel",
)


def _tree_fingerprint(
    root: Path,
    metadata: Any,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[str | None, int, int]:
    if not root.is_dir():
        return None, 0, 0
    files: list[Path] = []
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if not (current_path / name).is_symlink()
            and not is_junction(current_path / name)
        ]
        files.extend(
            current_path / name
            for name in names
            if not (current_path / name).is_symlink()
        )
    files.sort(key=lambda path: path.relative_to(root).as_posix().casefold())
    total = sum(path.stat().st_size for path in files)
    completed = 0
    rows: list[dict[str, Any]] = []
    for path in files:
        size = path.stat().st_size

        def update(amount: int) -> None:
            nonlocal completed
            completed += amount
            if progress:
                progress(
                    completed,
                    max(total, 1),
                    f"Comparing target: {completed}/{total} bytes",
                )

        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size": size,
                "sha256": backup.sha256_file(path, update),
            }
        )
    if progress and not files:
        progress(1, 1, "Comparing target: empty directory")
    return lineage.aggregate_fingerprint(rows, metadata), len(files), total


def _classify(
    source: str | None,
    target: str | None,
    base: str | None,
    source_state: str,
) -> tuple[str, str, bool, str | None]:
    if source is None:
        if target is None:
            return "identical", "none", False, None
        return (
            "removed",
            "retain",
            False,
            "Removal is reported but retained until destination-only cleanup is implemented.",
        )
    if target is None:
        return "incoming", "create", False, None
    if source == target:
        return "identical", "none", False, None
    if source_state == "independentlyChanged":
        return "conflicting", "resolve", True, "Both backup branches changed this item."
    if base:
        source_changed = source != base
        target_changed = target != base
        if source_changed and not target_changed:
            return "incoming", "replace", False, None
        if target_changed:
            return (
                "conflicting",
                "resolve",
                True,
                "The destination differs from the common restore base.",
            )
    return (
        "conflicting",
        "resolve",
        True,
        "The existing destination has no proven common base with this backup.",
    )


def _hash_rows(package_root: Path) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    with (package_root / "manifest" / "sha256.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            result[str(row["relative_path"])] = (
                int(row["size"]),
                str(row["sha256"]).lower(),
            )
    return result


def _payload_size(
    rows: dict[str, tuple[int, str]], payload: str | None, kind: str
) -> int:
    if not payload:
        return 0
    if kind == "file":
        return rows.get(payload, (0, ""))[0]
    prefix = payload.rstrip("/") + "/"
    return sum(size for path, (size, _digest) in rows.items() if path.startswith(prefix))


def _legacy_location_plan(
    package: dict[str, Any],
    mappings: dict[str, Any],
    target_profile: Path,
) -> dict[str, Any]:
    source_profile = Path(str(package.get("source", {}).get("profilePath", "")))
    source_known = package.get("source", {}).get("knownFolders") or {}
    target_known = windows.known_folders(target_profile)
    items: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    targets: set[str] = set()
    for mapping in mappings.get("projects", []):
        if not mapping.get("sourcePresent", True):
            continue
        mapping_id = str(mapping.get("id", ""))
        original = Path(str(mapping.get("originalPath", ""))).resolve(strict=False)
        target: Path | None = None
        for key in ("documents", "desktop"):
            source_root = source_known.get(key)
            if not source_root:
                continue
            try:
                relative = original.relative_to(Path(str(source_root)).resolve(strict=False))
                target = Path(target_known[key]) / relative
                break
            except ValueError:
                pass
        if target is None and source_profile:
            try:
                relative = original.relative_to(source_profile.resolve(strict=False))
                target = target_profile / relative
            except ValueError:
                issues.append(
                    {
                        "id": mapping_id,
                        "error": "legacy external project has no portable reviewed mapping; create a current backup",
                    }
                )
        target_key = str(target).casefold() if target else ""
        if target_key and target_key in targets:
            issues.append({"id": mapping_id, "error": "legacy project targets collide"})
        targets.add(target_key)
        items.append(
            {
                "id": mapping_id,
                "name": original.name or mapping_id,
                "kind": "legacy-profile",
                "status": "automatic" if target else "needs-user",
                "sourcePath": str(original),
                "targetPath": str(target) if target else None,
                "rootId": None,
            }
        )
    return {
        "planVersion": 1,
        "ready": not issues,
        "items": items,
        "requiredExternalRoots": [],
        "issues": issues,
    }


def _source_lineage_items(
    package_root: Path,
    package: dict[str, Any],
    mappings: dict[str, Any],
    rows: dict[str, tuple[int, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    lineage_path = package_root / "manifest" / "lineage.json"
    if lineage_path.is_file():
        manifest = backup.read_json(lineage_path)
        return {str(item["key"]): item for item in manifest.get("items", [])}, manifest

    result: dict[str, dict[str, Any]] = {}
    projects = backup.read_json(package_root / "manifest" / "projects.json")
    for item in projects:
        payload = str(item["backupRelativePath"])
        prefix = payload.rstrip("/") + "/"
        selected = [
            {
                "relative_path": path[len(prefix) :],
                "size": size,
                "sha256": digest,
            }
            for path, (size, digest) in rows.items()
            if path.startswith(prefix)
        ]
        metadata = {
            "projectIdentityId": item.get("projectIdentityId"),
            "name": item.get("name"),
        }
        item_id = str(item["id"])
        result[f"project/{item_id}"] = {
            "key": f"project/{item_id}",
            "kind": "project",
            "id": item_id,
            "state": "new",
            "currentFingerprint": lineage.aggregate_fingerprint(selected, metadata),
            "baseFingerprint": None,
            "payloadRelativePath": payload,
            "payloadKind": "tree",
            "metadata": metadata,
        }
    replacements = lineage.portable_replacements(package, mappings)
    for item in backup.read_json(package_root / "manifest" / "threads.json"):
        payload = item.get("backupRelativePath")
        if not payload:
            continue
        source_path = package_root / Path(*str(payload).split("/"))
        digest = lineage.semantic_file_digest(source_path, replacements)
        metadata = {
            key: item.get(key)
            for key in (
                "title", "archived", "pinned", "projectless", "projectId",
                "historyMode", "memoryMode",
            )
        }
        item_id = str(item["id"])
        result[f"conversation/{item_id}"] = {
            "key": f"conversation/{item_id}",
            "kind": "conversation",
            "id": item_id,
            "state": "new",
            "currentFingerprint": lineage.aggregate_fingerprint(
                [{"relative_path": source_path.name, "size": 0, "sha256": digest}],
                metadata,
            ),
            "baseFingerprint": None,
            "payloadRelativePath": payload,
            "payloadKind": "file",
            "metadata": metadata,
        }
    return result, {
        "backupId": None,
        "parentBackupId": None,
        "relation": "legacy",
        "items": list(result.values()),
    }


def _target_replacements(
    target_profile: Path,
    project_targets: dict[str, Path],
    mappings: dict[str, Any],
) -> list[tuple[str, str]]:
    replacements = [
        (str(target_profile / ".codex"), "%CODEX_HOME%"),
        (str(target_profile), "%PROFILE%"),
    ]
    replacements.extend(
        (str(path), f"%PROJECT:{item_id}%")
        for item_id, path in project_targets.items()
    )
    for item in mappings.get("projects", []):
        if item.get("id") and item.get("originalPath"):
            replacements.append(
                (str(item["originalPath"]), f"%PROJECT:{item['id']}%")
            )
    for item in mappings.get("attachments", []):
        if not item.get("id"):
            continue
        name = Path(str(item.get("originalPath", "attachment.bin"))).name
        target = (
            windows.documents_folder(target_profile)
            / "Codex Attachments"
            / str(item["id"])
            / name
        )
        token = f"%ATTACHMENT:{name.casefold()}%"
        replacements.append((str(target), token))
        if item.get("originalPath"):
            replacements.append((str(item["originalPath"]), token))
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    return replacements


def _target_conversations(
    target_profile: Path,
    replacements: list[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    database = target_profile / ".codex" / "state_5.sqlite"
    if not database.is_file():
        return {}
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            str(row[1]) for row in connection.execute('PRAGMA table_info("threads")')
        }
        wanted = [
            name
            for name in (
                "id", "rollout_path", "title", "archived", "is_pinned",
                "project_id", "history_mode", "memory_mode",
            )
            if name in columns
        ]
        rows = connection.execute(
            "SELECT " + ",".join(f'"{name}"' for name in wanted) + ' FROM "threads"'
        ).fetchall()
    finally:
        connection.close()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = dict(row)
        thread_id = str(value.get("id", ""))
        rollout_value = str(value.get("rollout_path") or "").replace("\\\\?\\", "")
        rollout = Path(rollout_value) if rollout_value else None
        fingerprint = None
        size = 0
        metadata = {
            "title": value.get("title"),
            "archived": bool(value.get("archived")),
            "pinned": bool(value.get("is_pinned")),
            "projectless": not bool(value.get("project_id")),
            "projectId": value.get("project_id"),
            "historyMode": value.get("history_mode"),
            "memoryMode": value.get("memory_mode"),
        }
        if rollout and rollout.is_file():
            size = rollout.stat().st_size
            digest = lineage.semantic_file_digest(rollout, replacements)
            fingerprint = lineage.aggregate_fingerprint(
                [{"relative_path": rollout.name, "size": 0, "sha256": digest}],
                metadata,
            )
        result[thread_id] = {
            "fingerprint": fingerprint,
            "path": str(rollout) if rollout else None,
            "size": size,
            "title": value.get("title") or thread_id,
            "archived": bool(value.get("archived")),
            "metadata": metadata,
        }
    return result


def _free_space(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required: dict[str, int] = {}
    for item in items:
        if item.get("proposedAction") not in {
            "create", "replace", "replace-managed-data", "keep-both",
            "archive-and-replace",
        }:
            continue
        target = item.get("target")
        if not target:
            continue
        anchor = Path(str(target)).anchor or str(Path(str(target)).resolve(strict=False).anchor)
        required[anchor] = required.get(anchor, 0) + int(item.get("requiredBytes", 0))
    result: list[dict[str, Any]] = []
    for anchor, needed in sorted(required.items()):
        try:
            free = shutil.disk_usage(anchor).free
        except OSError:
            free = 0
        result.append(
            {
                "volume": anchor,
                "requiredBytes": needed,
                "freeBytes": free,
                "sufficient": free >= needed,
            }
        )
    return result


def _refresh_plan(plan: dict[str, Any]) -> dict[str, Any]:
    items = plan.get("items", [])
    counts = {state: 0 for state in sorted(PLAN_STATES)}
    for item in items:
        state = str(item.get("state"))
        if state in counts:
            counts[state] += 1
    disks = _free_space(items)
    blocking_reasons = [
        str(item.get("reason") or "Unresolved restore-plan item.")
        for item in items
        if item.get("blocking")
    ]
    location_plan = plan.get("locationPlan") or {}
    blocking_reasons.extend(
        str(item.get("error")) for item in location_plan.get("issues", [])
    )
    if location_plan.get("requiredExternalRoots"):
        blocking_reasons.append("One or more external project roots are unresolved.")
    for disk in disks:
        if not disk["sufficient"]:
            blocking_reasons.append(f"Insufficient free space on {disk['volume']}.")
    if plan.get("cancelled"):
        blocking_reasons.append("Restore was cancelled during conflict review.")
    write_set = [
        {
            "operation": item.get("proposedAction"),
            "itemKey": item.get("key"),
            "source": item.get("source"),
            "target": item.get("target"),
            "bytes": item.get("sourceBytes", 0),
            "decision": item.get("decision"),
        }
        for item in items
        if (
            item.get("kind") in {"project", "codex"}
            and item.get("proposedAction") not in {"none", "retain", "resolve"}
        )
        or (
            item.get("kind") == "conversation"
            and item.get("proposedAction") in {"create", "replace", "delete", "keep-both"}
        )
    ]
    plan.update(
        {
            "ready": not blocking_reasons,
            "counts": counts,
            "diskRequirements": disks,
            "writeSet": write_set,
            "blockingReasons": blocking_reasons,
        }
    )
    return plan


def resolve_conversation_decision(
    plan: dict[str, Any], item_key: str, decision: str
) -> dict[str, Any]:
    """Return a new plan with one explicit conversation decision applied."""

    if decision not in CONVERSATION_DECISIONS:
        raise ValueError(f"Unsupported conversation decision: {decision}")
    result = copy.deepcopy(plan)
    if decision == "cancel":
        result["cancelled"] = True
        return _refresh_plan(result)
    item = next(
        (
            candidate
            for candidate in result.get("items", [])
            if candidate.get("key") == item_key
        ),
        None,
    )
    if not item or item.get("kind") != "conversation":
        raise ValueError(f"Conversation plan item not found: {item_key}")
    if decision not in item.get("availableDecisions", []):
        raise ValueError(f"Decision is not available for {item_key}: {decision}")
    source_present = bool(item.get("source"))
    target_present = bool(item.get("target"))
    action = "retain"
    selected = False
    if decision == "keep-source":
        action = "replace" if source_present and target_present else (
            "create" if source_present else "delete"
        )
        selected = True
    elif decision == "keep-both" and source_present and target_present:
        action = "keep-both"
        selected = True
        clone_seed = ":".join(
            (
                "codex-lifeboat-destination-copy",
                str(result.get("backupId") or result.get("package")),
                item_key,
                str(item.get("targetFingerprint") or "unknown"),
            )
        )
        clone_id = str(uuid.uuid5(uuid.NAMESPACE_URL, clone_seed))
        directory = "archived_sessions" if item.get("targetArchived") else "sessions"
        item["cloneId"] = clone_id
        item["cloneRelativePath"] = f"{directory}/lifeboat-{clone_id}.jsonl"
    item.update(
        {
            "decision": decision,
            "proposedAction": action,
            "selected": selected,
            "blocking": False,
            "reason": f"Resolved explicitly: {decision}.",
        }
    )
    result["cancelled"] = False
    return _refresh_plan(result)


def resolve_project_decision(
    plan: dict[str, Any], item_key: str, decision: str
) -> dict[str, Any]:
    """Return a new plan with one explicit project-root decision applied."""

    result = copy.deepcopy(plan)
    if decision == "cancel":
        result["cancelled"] = True
        return _refresh_plan(result)
    item = next(
        (
            candidate
            for candidate in result.get("items", [])
            if candidate.get("key") == item_key
        ),
        None,
    )
    if not item or item.get("kind") != "project":
        raise ValueError(f"Project plan item not found: {item_key}")
    if decision not in item.get("availableDecisions", []):
        raise ValueError(f"Decision is not available for {item_key}: {decision}")
    source_present = bool(item.get("source"))
    action = "retain"
    selected = False
    if decision == "keep-source":
        action = "replace" if item.get("target") else "create"
        selected = True
    elif decision == "archive":
        action = "archive-and-replace" if source_present else "archive"
        selected = True
    elif decision == "delete":
        action = "delete-project"
        selected = True
    item.update(
        {
            "decision": decision,
            "proposedAction": action,
            "selected": selected,
            "blocking": False,
            "reason": f"Resolved explicitly: {decision}.",
        }
    )
    result["cancelled"] = False
    return _refresh_plan(result)


def validate_plan_decisions(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("planVersion") != PLAN_VERSION:
        errors.append("unsupported restore-plan version")
    if plan.get("cancelled"):
        errors.append("restore plan was cancelled")
    for item in plan.get("items", []):
        if item.get("kind") == "project":
            decision = item.get("decision")
            if item.get("blocking"):
                errors.append(f"unresolved project: {item.get('key')}")
            if decision in {
                "keep-source", "keep-target", "archive", "delete", "skip", "retain"
            }:
                if decision not in item.get("availableDecisions", []):
                    errors.append(f"project decision was not offered for {item.get('key')}")
                source_present = bool(item.get("source"))
                expected_action = "retain"
                if decision == "keep-source":
                    expected_action = "replace" if item.get("target") else "create"
                elif decision == "archive":
                    expected_action = "archive-and-replace" if source_present else "archive"
                elif decision == "delete":
                    expected_action = "delete-project"
                if item.get("proposedAction") != expected_action:
                    errors.append(f"project action is inconsistent for {item.get('key')}")
            elif decision == "retain-default":
                if item.get("proposedAction") != "retain":
                    errors.append(f"default retention is inconsistent for {item.get('key')}")
            elif decision not in {None, "automatic"}:
                errors.append(f"invalid project decision for {item.get('key')}: {decision}")
            continue
        if item.get("kind") != "conversation":
            continue
        decision = item.get("decision")
        if item.get("blocking"):
            errors.append(f"unresolved conversation: {item.get('key')}")
        if decision and decision != "automatic" and decision not in CONVERSATION_DECISIONS:
            errors.append(f"invalid decision for {item.get('key')}: {decision}")
        if decision in {"keep-source", "keep-target", "keep-both", "skip"}:
            if decision not in item.get("availableDecisions", []):
                errors.append(f"decision was not offered for {item.get('key')}")
            source_present = bool(item.get("source"))
            target_present = bool(item.get("target"))
            expected_action = "retain"
            if decision == "keep-source":
                expected_action = (
                    "replace" if source_present and target_present else
                    "create" if source_present else "delete"
                )
            elif decision == "keep-both" and source_present and target_present:
                expected_action = "keep-both"
            if item.get("proposedAction") != expected_action:
                errors.append(f"decision action is inconsistent for {item.get('key')}")
        if item.get("proposedAction") == "keep-both":
            if not item.get("cloneId") or not item.get("cloneRelativePath"):
                errors.append(f"keep-both clone is incomplete: {item.get('key')}")
            else:
                try:
                    uuid.UUID(str(item["cloneId"]))
                except ValueError:
                    errors.append(f"keep-both clone ID is invalid: {item.get('key')}")
                relative = PurePosixPath(str(item["cloneRelativePath"]))
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not relative.parts
                    or relative.parts[0] not in {"sessions", "archived_sessions"}
                ):
                    errors.append(f"keep-both clone path is unsafe: {item.get('key')}")
    refreshed = _refresh_plan(copy.deepcopy(plan))
    if bool(plan.get("ready")) != bool(refreshed.get("ready")):
        errors.append("restore-plan ready state is inconsistent")
    if plan.get("writeSet") != refreshed.get("writeSet"):
        errors.append("restore-plan write set is inconsistent")
    return errors


def build_restore_plan(
    package_root: Path,
    target_profile: Path,
    external_roots: dict[str, str] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    allow_running_test: bool = False,
) -> dict[str, Any]:
    """Build a complete comparison preview without writing to either side."""

    package_root = package_root.resolve()
    target_profile = target_profile.resolve(strict=False)
    backup.check_codex_not_running(target_profile / ".codex", allow_running_test)
    package = backup.read_json(package_root / "manifest" / "package.json")
    mappings = backup.read_json(package_root / "manifest" / "path-mappings.json")
    location_plan = (
        location_mapper.build_plan(
            mappings.get("projects", []),
            target_profile,
            external_roots or {},
            package_root,
        )
        if mappings.get("mappingVersion") == 2
        else _legacy_location_plan(package, mappings, target_profile)
    )
    targets = {
        str(item["id"]): Path(str(item["targetPath"]))
        for item in location_plan.get("items", [])
        if item.get("targetPath")
    }
    hash_rows = _hash_rows(package_root)
    source_items, lineage_manifest = _source_lineage_items(
        package_root, package, mappings, hash_rows
    )
    local_lineage = lineage.load_state(windows.lineage_state_path(target_profile))
    registry = project_identity.load_registry(windows.project_registry_path(target_profile))
    identity_path = package_root / "manifest" / "project-identities.json"
    identity_roots = (
        {
            str(item.get("rootId")): item
            for item in backup.read_json(identity_path).get("roots", [])
        }
        if identity_path.is_file()
        else {}
    )
    common_base = local_lineage.get("baseBackupId") in {
        lineage_manifest.get("parentBackupId"),
        lineage_manifest.get("backupId"),
    }
    local_base_items = local_lineage.get("items", {}) if common_base else {}
    items: list[dict[str, Any]] = []

    for project in backup.read_json(package_root / "manifest" / "projects.json"):
        item_id = str(project["id"])
        key = f"project/{item_id}"
        source = source_items[key]
        target = targets.get(item_id)
        metadata = source.get("metadata")
        target_fp, target_files, target_bytes = _tree_fingerprint(
            target, metadata, progress
        ) if target else (None, 0, 0)
        source_fp = source.get("currentFingerprint")
        base_fp = local_base_items.get(key) or source.get("baseFingerprint")
        state, action, blocking, reason = _classify(
            source_fp, target_fp, base_fp, str(source.get("state"))
        )
        source_bytes = int(project.get("totalBytes", 0))
        identity = identity_roots.get(item_id, {})
        source_project = package_root / Path(
            *PurePosixPath(str(project.get("backupRelativePath") or "")).parts
        )
        git_evidence = git_insight.compare_repositories(source_project, target)
        items.append(
            {
                "key": key,
                "kind": "project",
                "name": project.get("name") or item_id,
                "source": project.get("originalPath"),
                "target": str(target) if target else None,
                "state": state,
                "proposedAction": action,
                "selected": action in {"create", "replace"},
                "sourceBytes": source_bytes,
                "targetBytes": target_bytes,
                "targetFiles": target_files,
                "requiredBytes": source_bytes + (target_bytes if action == "replace" else 0),
                "blocking": blocking,
                "reason": reason,
                "originalReason": reason,
                "decision": None if blocking else "automatic",
                "availableDecisions": (
                    list(PROJECT_DECISIONS_CONFLICT) if blocking else []
                ),
                "targetFingerprint": target_fp,
                "fingerprintMetadata": metadata,
                "projectIdentityId": project.get("projectIdentityId"),
                "codexProjectIds": list(identity.get("codexProjectIds", [])),
                "gitInsight": git_evidence,
            }
        )

    replacements = _target_replacements(target_profile, targets, mappings)
    source_replacements = lineage.portable_replacements(package, mappings)
    target_threads = _target_conversations(target_profile, replacements)
    source_thread_ids: set[str] = set()
    for key, source in source_items.items():
        if source.get("kind") != "conversation" or source.get("state") == "removed":
            continue
        thread_id = str(source.get("id"))
        source_thread_ids.add(thread_id)
        target = target_threads.get(thread_id)
        target_fp = target.get("fingerprint") if target else None
        base_fp = local_base_items.get(key) or source.get("baseFingerprint")
        state, action, blocking, reason = _classify(
            source.get("currentFingerprint"),
            target_fp,
            base_fp,
            str(source.get("state")),
        )
        prefix_sync = None
        if blocking and target and source.get("payloadRelativePath"):
            source_rollout = package_root / Path(
                *PurePosixPath(str(source["payloadRelativePath"])).parts
            )
            target_rollout = Path(str(target.get("path") or ""))
            prefix_sync = conversation_prefix.compare(
                source_rollout,
                target_rollout,
                source_replacements,
                replacements,
                source.get("metadata"),
                target.get("metadata"),
            )
            if prefix_sync.get("automatic"):
                missing = int(prefix_sync.get("additionalSourceRecords", 0))
                state, action, blocking = "incoming", "replace", False
                reason = (
                    "The conversation on this computer is an exact, unchanged "
                    f"prefix of the backup; {missing} appended record(s) are incoming."
                )
        source_bytes = _payload_size(
            hash_rows, source.get("payloadRelativePath"), str(source.get("payloadKind"))
        )
        items.append(
            {
                "key": key,
                "kind": "conversation",
                "name": (source.get("metadata") or {}).get("title") or thread_id,
                "source": source.get("payloadRelativePath"),
                "target": target.get("path") if target else None,
                "state": state,
                "proposedAction": action,
                "selected": action in {"create", "replace"},
                "sourceBytes": source_bytes,
                "targetBytes": int(target.get("size", 0)) if target else 0,
                "requiredBytes": source_bytes,
                "blocking": blocking,
                "reason": reason,
                "originalReason": reason,
                "decision": None if blocking else "automatic",
                "availableDecisions": list(CONVERSATION_DECISIONS) if blocking else [],
                "targetFingerprint": target.get("fingerprint") if target else None,
                "targetArchived": bool(target.get("archived")) if target else False,
                "prefixSync": prefix_sync,
            }
        )
    for thread_id in sorted(set(target_threads) - source_thread_ids, key=str.casefold):
        target = target_threads[thread_id]
        items.append(
            {
                "key": f"conversation/{thread_id}",
                "kind": "conversation",
                "name": target.get("title") or thread_id,
                "source": None,
                "target": target.get("path"),
                "state": "destination-only",
                "proposedAction": "retain",
                "selected": False,
                "sourceBytes": 0,
                "targetBytes": int(target.get("size", 0)),
                "requiredBytes": 0,
                "blocking": True,
                "reason": "A destination-only conversation requires an explicit decision.",
                "originalReason": "A destination-only conversation requires an explicit decision.",
                "decision": None,
                "availableDecisions": list(CONVERSATION_DECISIONS),
                "targetFingerprint": target.get("fingerprint"),
                "targetArchived": bool(target.get("archived")),
            }
        )

    registry_roots = {
        str(root.get("rootId")): (project, root)
        for project in registry.get("projects", [])
        for root in project.get("roots", [])
    }
    for key, source in source_items.items():
        if source.get("state") != "removed":
            continue
        item_id = str(source.get("id") or key.split("/", 1)[-1])
        if source.get("kind") == "conversation":
            target = target_threads.get(item_id)
            items.append(
                {
                    "key": key,
                    "kind": "conversation",
                    "name": target.get("title") if target else item_id,
                    "source": None,
                    "target": target.get("path") if target else None,
                    "state": "removed",
                    "proposedAction": "retain" if target else "none",
                    "selected": False,
                    "sourceBytes": 0,
                    "targetBytes": int(target.get("size", 0)) if target else 0,
                    "requiredBytes": 0,
                    "blocking": bool(target),
                    "reason": (
                        "Conversation removal needs an explicit decision."
                        if target else None
                    ),
                    "originalReason": (
                        "Conversation removal needs an explicit decision."
                        if target else None
                    ),
                    "decision": None if target else "automatic",
                    "availableDecisions": (
                        list(CONVERSATION_DECISIONS) if target else []
                    ),
                    "targetFingerprint": target.get("fingerprint") if target else None,
                    "targetArchived": bool(target.get("archived")) if target else False,
                }
            )
        elif source.get("kind") == "project":
            registered = registry_roots.get(item_id)
            target_path = (
                Path(str(registered[1].get("lastKnownPath", "")))
                if registered else None
            )
            target_exists = bool(target_path and target_path.exists())
            target_fp, target_files, target_bytes = (
                _tree_fingerprint(target_path, None, progress)
                if target_exists and target_path
                else (None, 0, 0)
            )
            items.append(
                {
                    "key": key,
                    "kind": "project",
                    "name": (
                        (registered[0].get("names") or [item_id])[0]
                        if registered else item_id
                    ),
                    "source": None,
                    "target": str(target_path) if target_exists else None,
                    "state": "removed",
                    "proposedAction": "retain" if target_exists else "none",
                    "selected": False,
                    "sourceBytes": 0,
                    "targetBytes": target_bytes,
                    "targetFiles": target_files,
                    "requiredBytes": 0,
                    "blocking": False,
                    "reason": "Removed project is retained by default." if target_exists else None,
                    "originalReason": "Project was removed in the backup lineage." if target_exists else None,
                    "decision": "retain-default" if target_exists else "automatic",
                    "availableDecisions": (
                        list(PROJECT_DECISIONS_DESTINATION_ONLY) if target_exists else []
                    ),
                    "targetFingerprint": target_fp,
                    "fingerprintMetadata": None,
                    "projectIdentityId": registered[0].get("projectId") if registered else None,
                    "codexProjectIds": list(registered[0].get("codexProjectIds", [])) if registered else [],
                }
            )

    incoming_root_ids = {
        str(item.get("id")) for item in mappings.get("projects", [])
    } | {
        str(item.get("id"))
        for item in source_items.values()
        if item.get("kind") == "project"
    }
    for project in registry.get("projects", []):
        for root in project.get("roots", []):
            root_id = str(root.get("rootId"))
            if root_id in incoming_root_ids:
                continue
            path = Path(str(root.get("lastKnownPath", "")))
            if not path.exists():
                continue
            target_fingerprint, files, size = _tree_fingerprint(path, None, progress)
            items.append(
                {
                    "key": f"project/{root_id}",
                    "kind": "project",
                    "name": (project.get("names") or [path.name or root_id])[0],
                    "source": None,
                    "target": str(path),
                    "state": "destination-only",
                    "proposedAction": "retain",
                    "selected": False,
                    "sourceBytes": 0,
                    "targetBytes": size,
                    "targetFiles": files,
                    "requiredBytes": 0,
                    "blocking": False,
                    "reason": "Destination-only project is retained by default.",
                    "originalReason": "Destination-only project is retained by default.",
                    "decision": "retain-default",
                    "availableDecisions": list(PROJECT_DECISIONS_DESTINATION_ONLY),
                    "targetFingerprint": target_fingerprint,
                    "fingerprintMetadata": None,
                    "projectIdentityId": project.get("projectId"),
                    "codexProjectIds": list(project.get("codexProjectIds", [])),
                }
            )

    codex_source_bytes = sum(
        size
        for path, (size, _digest) in hash_rows.items()
        if path.startswith("codex/") or path.startswith("attachments/")
    )
    codex_target = target_profile / ".codex"
    codex_target_bytes = sum(
        path.stat().st_size
        for path in codex_target.rglob("*")
        if path.is_file()
    ) if codex_target.is_dir() else 0
    items.append(
        {
            "key": "codex/managed-state",
            "kind": "codex",
            "name": "Codex conversations, settings and available attachments",
            "source": str(package_root / "codex"),
            "target": str(codex_target),
            "state": "incoming",
            "proposedAction": "replace-managed-data",
            "selected": True,
            "sourceBytes": codex_source_bytes,
            "targetBytes": codex_target_bytes,
            "requiredBytes": codex_source_bytes + codex_target_bytes,
            "blocking": False,
            "reason": "Authentication, machine identity and runtime data remain local.",
        }
    )

    state_order = {
        "conflicting": 0,
        "incoming": 1,
        "removed": 2,
        "destination-only": 3,
        "identical": 4,
    }
    items.sort(
        key=lambda item: (
            state_order.get(str(item.get("state")), 99),
            str(item.get("kind", "")).casefold(),
            str(item.get("name", "")).casefold(),
        )
    )
    plan = {
        "planVersion": PLAN_VERSION,
        "backupId": lineage_manifest.get("backupId"),
        "package": str(package_root),
        "targetProfile": str(target_profile),
        "cancelled": False,
        "items": items,
        "locationPlan": location_plan,
    }
    return _refresh_plan(plan)
