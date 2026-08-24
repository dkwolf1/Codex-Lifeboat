"""Persistent project identities stored outside user project directories."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import ntpath
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from . import atomic_io


REGISTRY_VERSION = 1
IDENTITY_MANIFEST_VERSION = 1


class IdentityError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_path(value: str | Path) -> str:
    return ntpath.normcase(ntpath.normpath(str(value))).casefold()


def empty_registry() -> dict[str, Any]:
    return {"registryVersion": REGISTRY_VERSION, "projects": []}


def validate_registry(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["registry must be an object"]
    errors: list[str] = []
    if value.get("registryVersion") != REGISTRY_VERSION:
        errors.append("unsupported registryVersion")
    projects = value.get("projects")
    if not isinstance(projects, list):
        return errors + ["projects must be a list"]
    project_ids: set[str] = set()
    root_ids: set[str] = set()
    for project in projects:
        if not isinstance(project, dict):
            errors.append("project entry must be an object")
            continue
        project_id = str(project.get("projectId", ""))
        try:
            uuid.UUID(project_id)
        except ValueError:
            errors.append(f"invalid projectId: {project_id!r}")
        if project_id in project_ids:
            errors.append(f"duplicate projectId: {project_id}")
        project_ids.add(project_id)
        roots = project.get("roots")
        if not isinstance(roots, list) or not roots:
            errors.append(f"project {project_id} has no roots")
            continue
        for root in roots:
            if not isinstance(root, dict):
                errors.append(f"project {project_id} has an invalid root")
                continue
            root_id = str(root.get("rootId", ""))
            try:
                uuid.UUID(root_id)
            except ValueError:
                errors.append(f"invalid rootId: {root_id!r}")
            if root_id in root_ids:
                errors.append(f"duplicate rootId: {root_id}")
            root_ids.add(root_id)
            if not isinstance(root.get("pathKeys"), list) or not root.get("pathKeys"):
                errors.append(f"root {root_id} has no pathKeys")
    return errors


def load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_registry()
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise IdentityError(f"Cannot read project identity registry {path}: {exc}") from exc
    errors = validate_registry(value)
    if errors:
        raise IdentityError(f"Invalid project identity registry {path}: {'; '.join(errors)}")
    return value


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    errors = validate_registry(registry)
    if errors:
        raise IdentityError("Refusing to write invalid identity registry: " + "; ".join(errors))
    atomic_io.write_json(path, registry, validate=lambda value: _require_valid(value))


def _require_valid(value: Any) -> None:
    errors = validate_registry(value)
    if errors:
        raise IdentityError("Invalid persisted identity registry: " + "; ".join(errors))


def _git_remote_hashes(project_path: Path) -> list[str]:
    config = project_path / ".git" / "config"
    if not config.is_file():
        return []
    try:
        text = config.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    hashes: set[str] = set()
    for match in re.finditer(r"(?im)^\s*url\s*=\s*(.+?)\s*$", text):
        normalized = match.group(1).strip().rstrip("/").casefold()
        if normalized:
            hashes.add(hashlib.sha256(normalized.encode("utf-8")).hexdigest())
    return sorted(hashes)


def identity_evidence(project_path: Path) -> dict[str, Any]:
    return {
        "pathKey": canonical_path(project_path),
        "gitRemoteHashes": _git_remote_hashes(project_path),
        "hasGitMetadata": (project_path / ".git").exists(),
    }


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if value}, key=str.casefold)


def _new_project(name: str, codex_ids: list[str]) -> dict[str, Any]:
    return {
        "projectId": str(uuid.uuid4()),
        "names": [name] if name else [],
        "codexProjectIds": _unique(codex_ids),
        "roots": [],
        "createdAtUtc": utc_now(),
        "lastSeenAtUtc": utc_now(),
    }


def _new_root(evidence: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "rootId": str(uuid.uuid4()),
        "pathKeys": [evidence["pathKey"]],
        "lastKnownPath": str(path),
        "gitRemoteHashes": list(evidence["gitRemoteHashes"]),
        "createdAtUtc": utc_now(),
        "lastSeenAtUtc": utc_now(),
    }


def assign_identity(
    registry: dict[str, Any],
    project_path: Path,
    name: str,
    codex_project_ids: Iterable[str],
) -> dict[str, Any]:
    """Find or create an unambiguous project/root identity and update registry."""

    errors = validate_registry(registry) if registry.get("projects") else []
    if errors:
        raise IdentityError("Invalid in-memory registry: " + "; ".join(errors))
    evidence = identity_evidence(project_path)
    codex_ids = _unique(codex_project_ids)
    projects: list[dict[str, Any]] = registry.setdefault("projects", [])

    path_matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    remote_matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    codex_matches: list[dict[str, Any]] = []
    for project in projects:
        if set(project.get("codexProjectIds", [])) & set(codex_ids):
            codex_matches.append(project)
        for root in project.get("roots", []):
            if evidence["pathKey"] in root.get("pathKeys", []):
                path_matches.append((project, root))
            if evidence["gitRemoteHashes"] and set(evidence["gitRemoteHashes"]) & set(
                root.get("gitRemoteHashes", [])
            ):
                remote_matches.append((project, root))

    match_basis = "new"
    if path_matches:
        if len(path_matches) > 1:
            raise IdentityError(f"Ambiguous registered path for {project_path}")
        project, root = path_matches[0]
        match_basis = "registered-path"
        if len(codex_matches) > 1 or (
            codex_matches and codex_matches[0]["projectId"] != project["projectId"]
        ):
            raise IdentityError(f"Path and Codex identity disagree for {project_path}")
    elif codex_matches:
        if len(codex_matches) > 1:
            raise IdentityError(f"Ambiguous Codex identity for {project_path}")
        project = codex_matches[0]
        project_remote_matches = [
            match for match in remote_matches if match[0]["projectId"] == project["projectId"]
        ]
        if remote_matches and not project_remote_matches:
            raise IdentityError(f"Codex and Git identity disagree for {project_path}")
        if len(project_remote_matches) == 1:
            root = project_remote_matches[0][1]
            match_basis = "codex-and-git"
        else:
            root = _new_root(evidence, project_path)
            project.setdefault("roots", []).append(root)
            match_basis = "codex-project-new-root"
    elif remote_matches:
        if len(remote_matches) > 1:
            raise IdentityError(f"Ambiguous Git identity for {project_path}")
        project, root = remote_matches[0]
        match_basis = "git-remote"
    else:
        project = _new_project(name, codex_ids)
        root = _new_root(evidence, project_path)
        project["roots"].append(root)
        projects.append(project)

    project["names"] = _unique([*project.get("names", []), name])
    project["codexProjectIds"] = _unique(
        [*project.get("codexProjectIds", []), *codex_ids]
    )
    project["lastSeenAtUtc"] = utc_now()
    root["pathKeys"] = _unique([*root.get("pathKeys", []), evidence["pathKey"]])
    root["gitRemoteHashes"] = _unique(
        [*root.get("gitRemoteHashes", []), *evidence["gitRemoteHashes"]]
    )
    root["lastKnownPath"] = str(project_path)
    root["lastSeenAtUtc"] = utc_now()
    return {
        "projectId": project["projectId"],
        "rootId": root["rootId"],
        "matchBasis": match_basis,
        "codexProjectIds": list(project["codexProjectIds"]),
        "gitEvidence": {
            "hasGitMetadata": evidence["hasGitMetadata"],
            "remoteHashes": list(evidence["gitRemoteHashes"]),
        },
    }


def register_restored_roots(
    registry: dict[str, Any], identity_manifest: dict[str, Any], targets: dict[str, Path]
) -> None:
    if identity_manifest.get("identityVersion") != IDENTITY_MANIFEST_VERSION:
        raise IdentityError("Unsupported project identity manifest version")
    for item in identity_manifest.get("roots", []):
        root_id = str(item["rootId"])
        target = targets.get(root_id)
        if target is None:
            raise IdentityError(f"No restored target registered for root {root_id}")
        project_id = str(item["projectId"])
        project = next(
            (entry for entry in registry["projects"] if entry["projectId"] == project_id),
            None,
        )
        if project is None:
            incoming_codex_ids = set(item.get("codexProjectIds", []))
            conflicting = [
                entry
                for entry in registry["projects"]
                if incoming_codex_ids & set(entry.get("codexProjectIds", []))
            ]
            if conflicting:
                raise IdentityError(
                    f"Incoming project identity conflicts with local Codex identity: {project_id}"
                )
            project = _new_project(str(item.get("name", "")), item.get("codexProjectIds", []))
            project["projectId"] = project_id
            project["roots"] = []
            registry["projects"].append(project)
        root_owner = next(
            (
                entry
                for entry in registry["projects"]
                if entry["projectId"] != project_id
                and any(root.get("rootId") == root_id for root in entry.get("roots", []))
            ),
            None,
        )
        if root_owner is not None:
            raise IdentityError(f"Root identity {root_id} belongs to another project")
        root = next(
            (entry for entry in project["roots"] if entry["rootId"] == root_id), None
        )
        evidence = identity_evidence(target)
        if root is None:
            root = _new_root(evidence, target)
            root["rootId"] = root_id
            project["roots"].append(root)
        project["names"] = _unique([*project.get("names", []), str(item.get("name", ""))])
        project["codexProjectIds"] = _unique(
            [*project.get("codexProjectIds", []), *item.get("codexProjectIds", [])]
        )
        project["lastSeenAtUtc"] = utc_now()
        root["pathKeys"] = _unique([*root.get("pathKeys", []), evidence["pathKey"]])
        root["lastKnownPath"] = str(target)
        root["lastSeenAtUtc"] = utc_now()


def validate_identity_manifest(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["identity manifest must be an object"]
    errors: list[str] = []
    if value.get("identityVersion") != IDENTITY_MANIFEST_VERSION:
        errors.append("unsupported identityVersion")
    roots = value.get("roots")
    if not isinstance(roots, list):
        return errors + ["roots must be a list"]
    root_ids: set[str] = set()
    for item in roots:
        if not isinstance(item, dict):
            errors.append("identity root must be an object")
            continue
        for key in ("projectId", "rootId"):
            try:
                uuid.UUID(str(item.get(key, "")))
            except ValueError:
                errors.append(f"invalid {key}: {item.get(key)!r}")
        root_id = str(item.get("rootId", ""))
        if root_id in root_ids:
            errors.append(f"duplicate identity rootId: {root_id}")
        root_ids.add(root_id)
    return errors
