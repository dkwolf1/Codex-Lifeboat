"""Portable Windows location descriptions for backup manifests.

The location model deliberately separates a project's logical location from the
source computer's absolute path.  Phase 1 only records and validates these
descriptions; later restore-planning phases will use them for user-confirmed
external-root mappings.
"""

from __future__ import annotations

import hashlib
import ntpath
from pathlib import PureWindowsPath
from typing import Any, Mapping


LOCATION_SCHEMA_VERSION = 1
KNOWN_FOLDER_KEYS = (
    "desktop",
    "documents",
    "downloads",
    "pictures",
    "music",
    "videos",
)


class LocationError(ValueError):
    pass


def _path(value: str) -> PureWindowsPath:
    normalized = ntpath.normpath(str(value).strip())
    candidate = PureWindowsPath(normalized)
    if not normalized or not candidate.is_absolute():
        raise LocationError(f"Expected an absolute Windows path: {value!r}")
    return candidate


def _relative_to_casefold(
    child: PureWindowsPath, parent: PureWindowsPath
) -> PureWindowsPath | None:
    child_parts = child.parts
    parent_parts = parent.parts
    if len(child_parts) < len(parent_parts):
        return None
    if tuple(part.casefold() for part in child_parts[: len(parent_parts)]) != tuple(
        part.casefold() for part in parent_parts
    ):
        return None
    remaining = child_parts[len(parent_parts) :]
    return PureWindowsPath(*remaining) if remaining else PureWindowsPath()


def _portable_relative(value: PureWindowsPath) -> str:
    text = value.as_posix()
    return "" if text == "." else text


def _logical_path(kind: str, key: str, relative: str) -> str:
    suffix = f"/{relative}" if relative else ""
    return f"{kind}://{key}{suffix}"


def describe_location(
    value: str,
    source_profile: str,
    known_folders: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Describe an absolute Windows path without depending on a username.

    Known folders take precedence over the broader profile root. External paths
    retain their original source hint, but are marked as requiring an explicit
    target mapping before a future mirror restore may modify them.
    """

    candidate = _path(value)
    profile = _path(source_profile)
    folders: list[tuple[str, PureWindowsPath]] = []
    for raw_key, raw_value in (known_folders or {}).items():
        key = str(raw_key).casefold()
        if key not in KNOWN_FOLDER_KEYS or not raw_value:
            continue
        try:
            folders.append((key, _path(str(raw_value))))
        except LocationError:
            continue
    folders.sort(key=lambda item: len(item[1].parts), reverse=True)

    for key, root in folders:
        relative_path = _relative_to_casefold(candidate, root)
        if relative_path is None:
            continue
        relative = _portable_relative(relative_path)
        return {
            "schemaVersion": LOCATION_SCHEMA_VERSION,
            "kind": "known-folder",
            "knownFolder": key,
            "relativePath": relative,
            "logicalPath": _logical_path("known-folder", key, relative),
            "originalPath": str(candidate),
            "requiresTargetMapping": False,
        }

    profile_relative = _relative_to_casefold(candidate, profile)
    if profile_relative is not None:
        relative = _portable_relative(profile_relative)
        return {
            "schemaVersion": LOCATION_SCHEMA_VERSION,
            "kind": "profile",
            "relativePath": relative,
            "logicalPath": _logical_path("profile", "user", relative),
            "originalPath": str(candidate),
            "requiresTargetMapping": False,
        }

    root_hint = candidate.parent
    relative_to_root = candidate.name
    root_key_material = str(root_hint).rstrip("\\/").casefold().encode("utf-8")
    root_id = "external-" + hashlib.sha256(root_key_material).hexdigest()[:12]
    anchor_relative = _relative_to_casefold(candidate, PureWindowsPath(candidate.anchor))
    return {
        "schemaVersion": LOCATION_SCHEMA_VERSION,
        "kind": "external-root",
        "rootId": root_id,
        "relativePath": relative_to_root,
        "logicalPath": _logical_path("external-root", root_id, relative_to_root),
        "originalPath": str(candidate),
        "sourceRootHint": str(root_hint),
        "sourceAnchor": candidate.anchor,
        "anchorRelativePath": _portable_relative(anchor_relative or PureWindowsPath()),
        "requiresTargetMapping": True,
    }


def validate_location(value: Any) -> list[str]:
    """Return schema errors for a serialized location descriptor."""

    if not isinstance(value, dict):
        return ["location must be an object"]
    errors: list[str] = []
    if value.get("schemaVersion") != LOCATION_SCHEMA_VERSION:
        errors.append("unsupported location schemaVersion")
    kind = value.get("kind")
    if kind not in {"known-folder", "profile", "external-root"}:
        errors.append("invalid location kind")
    relative = value.get("relativePath")
    if not isinstance(relative, str):
        errors.append("relativePath must be a string")
    elif relative:
        candidate = PureWindowsPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
            errors.append("relativePath is not portable")
    logical = value.get("logicalPath")
    if not isinstance(logical, str) or "://" not in logical:
        errors.append("logicalPath is missing or invalid")
    try:
        _path(str(value.get("originalPath", "")))
    except LocationError:
        errors.append("originalPath is not an absolute Windows path")
    if kind == "known-folder" and value.get("knownFolder") not in KNOWN_FOLDER_KEYS:
        errors.append("unknown knownFolder")
    if kind == "external-root":
        if not value.get("rootId") or not value.get("sourceRootHint"):
            errors.append("external-root metadata is incomplete")
        if value.get("requiresTargetMapping") is not True:
            errors.append("external-root must require target mapping")
    elif kind in {"known-folder", "profile"}:
        if value.get("requiresTargetMapping") is not False:
            errors.append("portable locations must not require target mapping")
    return errors


def suggested_target_expression(location: Mapping[str, Any]) -> str:
    """Return a readable, username-independent target suggestion."""

    errors = validate_location(dict(location))
    if errors:
        raise LocationError("; ".join(errors))
    relative = str(location.get("relativePath") or "").replace("/", "\\")
    suffix = f"\\{relative}" if relative else ""
    if location["kind"] == "known-folder":
        return f"%{str(location['knownFolder']).upper()}%{suffix}"
    if location["kind"] == "profile":
        return f"%USERPROFILE%{suffix}"
    return str(location["originalPath"])


def resolve_portable_location(
    location: Mapping[str, Any],
    target_profile: str,
    target_known_folders: Mapping[str, str] | None = None,
    external_roots: Mapping[str, str] | None = None,
) -> PureWindowsPath | None:
    """Resolve a validated descriptor on a target computer.

    External locations deliberately return ``None`` until their root has been
    explicitly mapped. This prevents silent fallback directories.
    """

    errors = validate_location(dict(location))
    if errors:
        raise LocationError("; ".join(errors))
    relative = PureWindowsPath(str(location.get("relativePath") or ""))
    kind = location["kind"]
    if kind == "profile":
        return _path(target_profile) / relative
    if kind == "known-folder":
        key = str(location["knownFolder"])
        root_value = (target_known_folders or {}).get(key)
        if not root_value:
            return None
        return _path(str(root_value)) / relative
    root_value = (external_roots or {}).get(str(location.get("rootId")))
    if not root_value:
        return None
    return _path(str(root_value)) / relative
