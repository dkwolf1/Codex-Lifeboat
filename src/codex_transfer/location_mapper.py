"""Safe, persistent target mapping for portable project locations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from . import atomic_io, path_model, windows


MAPPING_REGISTRY_VERSION = 1


class LocationMappingError(ValueError):
    pass


def empty_registry() -> dict[str, Any]:
    return {"mappingRegistryVersion": MAPPING_REGISTRY_VERSION, "externalRoots": {}}


def load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_registry()
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value.get("mappingRegistryVersion") != MAPPING_REGISTRY_VERSION or not isinstance(
        value.get("externalRoots"), dict
    ):
        raise LocationMappingError(f"Unsupported or invalid location mapping registry: {path}")
    return value


def save_registry(path: Path, value: dict[str, Any]) -> None:
    def validate(persisted: Any) -> None:
        if persisted.get("mappingRegistryVersion") != MAPPING_REGISTRY_VERSION or not isinstance(
            persisted.get("externalRoots"), dict
        ):
            raise LocationMappingError("Refusing to write invalid location mapping registry")

    atomic_io.write_json(path, value, validate=validate)


def external_roots(registry: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for root_id, item in registry.get("externalRoots", {}).items():
        if isinstance(item, dict) and item.get("targetRoot"):
            result[str(root_id)] = str(item["targetRoot"])
    return result


def remember_external_roots(
    registry: dict[str, Any], mappings: Mapping[str, str], updated_at_utc: str
) -> None:
    roots = registry.setdefault("externalRoots", {})
    for root_id, target in mappings.items():
        roots[str(root_id)] = {
            "targetRoot": str(Path(target).resolve(strict=False)),
            "updatedAtUtc": updated_at_utc,
        }


def _normalized(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False))))


def _contains(child: Path, parent: Path) -> bool:
    child_key = _normalized(child)
    parent_key = _normalized(parent)
    return child_key == parent_key or child_key.startswith(parent_key + os.sep)


def _nearest_existing_parent(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return None


def validate_external_root(
    root: Path, target_profile: Path, package_root: Path | None = None
) -> list[str]:
    root = root.resolve(strict=False)
    target_profile = target_profile.resolve(strict=False)
    errors: list[str] = []
    if not root.is_absolute():
        return ["target root is not absolute"]
    protected_exact = {
        target_profile,
        windows.documents_folder(target_profile),
        windows.desktop_folder(target_profile),
        Path(root.anchor),
    }
    protected_trees = [
        target_profile / ".codex",
        os.environ.get("WINDIR"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ]
    if root in {value.resolve(strict=False) for value in protected_exact}:
        errors.append("target root is an unsafe broad or protected directory")
    if _contains(target_profile, root):
        errors.append("target root is too broad and contains the destination profile")
    for value in protected_trees:
        if value and _contains(root, Path(value)):
            errors.append("target root is inside a protected system or Codex directory")
    if package_root and (
        _contains(root, package_root) or _contains(package_root, root)
    ):
        errors.append("target root overlaps the selected backup package")
    anchor = Path(root.anchor)
    if root.anchor and not anchor.exists():
        errors.append("target drive or network share is unavailable")
    existing_parent = _nearest_existing_parent(root)
    if existing_parent is None:
        errors.append("no accessible parent directory exists")
    elif not os.access(existing_parent, os.W_OK):
        errors.append("nearest existing parent directory is not writable")
    if root.exists() and (
        root.is_symlink() or bool(getattr(os.path, "isjunction", lambda _path: False)(root))
    ):
        errors.append("target root is a symbolic link or junction")
    return errors


def build_plan(
    project_mappings: list[dict[str, Any]],
    target_profile: Path,
    selected_external_roots: Mapping[str, str] | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Resolve every project and reject unresolved or colliding destinations."""

    target_profile = target_profile.resolve(strict=False)
    known_folders = windows.known_folders(target_profile)
    selected_external_roots = selected_external_roots or {}
    items: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    required: dict[str, dict[str, Any]] = {}
    for mapping in project_mappings:
        if not mapping.get("sourcePresent", True):
            continue
        mapping_id = str(mapping.get("id", ""))
        location = mapping.get("location")
        if path_model.validate_location(location):
            issues.append({"id": mapping_id, "error": "invalid portable location"})
            continue
        kind = str(location["kind"])
        target: Path | None = None
        status = "automatic"
        if kind == "external-root":
            root_id = str(location["rootId"])
            root_value = selected_external_roots.get(root_id)
            if not root_value:
                required.setdefault(
                    root_id,
                    {
                        "rootId": root_id,
                        "sourceRootHint": location.get("sourceRootHint"),
                        "sourceAnchor": location.get("sourceAnchor"),
                        "projectIds": [],
                    },
                )["projectIds"].append(mapping_id)
                status = "needs-user"
            else:
                root = Path(root_value).resolve(strict=False)
                for error in validate_external_root(root, target_profile, package_root):
                    issues.append({"id": root_id, "error": error})
                resolved = path_model.resolve_portable_location(
                    location,
                    str(target_profile),
                    known_folders,
                    {root_id: str(root)},
                )
                target = Path(str(resolved)).resolve(strict=False) if resolved else None
                status = "mapped"
        else:
            resolved = path_model.resolve_portable_location(
                location, str(target_profile), known_folders
            )
            target = Path(str(resolved)).resolve(strict=False) if resolved else None
        if target is None and status != "needs-user":
            issues.append({"id": mapping_id, "error": "target location cannot be resolved"})
        items.append(
            {
                "id": mapping_id,
                "name": Path(str(mapping.get("originalPath", mapping_id))).name,
                "kind": kind,
                "status": status,
                "sourcePath": mapping.get("originalPath"),
                "targetPath": str(target) if target else None,
                "rootId": location.get("rootId"),
            }
        )

    resolved_items = [item for item in items if item.get("targetPath")]
    for index, item in enumerate(resolved_items):
        target = Path(str(item["targetPath"]))
        if target == target_profile / ".codex":
            issues.append({"id": item["id"], "error": "project target overlaps Codex data"})
        if target.exists() and (
            target.is_symlink()
            or bool(getattr(os.path, "isjunction", lambda _path: False)(target))
        ):
            issues.append({"id": item["id"], "error": "project target is a link or junction"})
        for other in resolved_items[index + 1 :]:
            other_target = Path(str(other["targetPath"]))
            if _contains(target, other_target) or _contains(other_target, target):
                issues.append(
                    {
                        "id": item["id"],
                        "error": f"target collides or overlaps with project {other['id']}",
                    }
                )
    return {
        "planVersion": 1,
        "ready": not issues and not required,
        "items": items,
        "requiredExternalRoots": list(required.values()),
        "issues": issues,
    }
