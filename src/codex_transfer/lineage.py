"""Portable backup lineage and per-item change classification."""

from __future__ import annotations

import functools
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

from . import atomic_io


LINEAGE_VERSION = 1
STATE_VERSION = 1
DEVICE_VERSION = 1
ITEM_STATES = {"new", "changed", "removed", "unchanged", "independentlyChanged"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: Any) -> None:
    atomic_io.write_json(path, value)


def empty_state() -> dict[str, Any]:
    return {"stateVersion": STATE_VERSION, "baseBackupId": None, "items": {}}


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_state()
    value = _read_json(path)
    if value.get("stateVersion") != STATE_VERSION or not isinstance(
        value.get("items"), dict
    ):
        raise ValueError(f"Unsupported or invalid lineage state: {path}")
    return value


def save_state(path: Path, state: dict[str, Any]) -> None:
    _write_json(path, state)


def load_or_create_device_id(path: Path) -> str:
    if path.is_file():
        value = _read_json(path)
        if value.get("deviceVersion") != DEVICE_VERSION:
            raise ValueError(f"Unsupported device state: {path}")
        device_id = str(value.get("deviceId", ""))
        uuid.UUID(device_id)
        return device_id
    device_id = str(uuid.uuid4())
    _write_json(
        path,
        {"deviceVersion": DEVICE_VERSION, "deviceId": device_id},
    )
    return device_id


def aggregate_fingerprint(
    rows: Iterable[dict[str, Any]], metadata: Any | None = None
) -> str:
    normalized = [
        {
            "path": str(item["relative_path"]),
            "size": int(item["size"]),
            "sha256": str(item["sha256"]).lower(),
        }
        for item in rows
    ]
    normalized.sort(key=lambda item: item["path"].casefold())
    payload = {"files": normalized, "metadata": metadata}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def portable_replacements(
    package: dict[str, Any], mappings: dict[str, Any]
) -> list[tuple[str, str]]:
    replacements: list[tuple[str, str]] = []
    source = package.get("source", {})
    for value, token in (
        (source.get("codexHome"), "%CODEX_HOME%"),
        (source.get("profilePath"), "%PROFILE%"),
    ):
        if value:
            replacements.append((str(value), token))
    for group, prefix in (("projects", "PROJECT"), ("attachments", "ATTACHMENT")):
        for item in mappings.get(group, []):
            if item.get("originalPath") and item.get("id"):
                replacements.append(
                    (
                        str(item["originalPath"]),
                        f"%{prefix}:{Path(str(item['originalPath'])).name.casefold()}%"
                        if group == "attachments"
                        else f"%{prefix}:{item['id']}%",
                    )
                )
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    return replacements


@functools.lru_cache(maxsize=8)
def _replacement_engine(
    replacements: tuple[tuple[str, str], ...]
) -> tuple[
    re.Pattern[str] | None,
    dict[str, str],
    re.Pattern[str] | None,
    tuple[str, ...],
]:
    variants: dict[str, tuple[str, str]] = {}
    attachment_groups: dict[str, tuple[str, set[str]]] = {}
    for original, token in replacements:
        canonical = original.replace("/", "\\")
        separator = canonical.rfind("\\")
        if token.startswith("%ATTACHMENT:") and separator > 0:
            parent = canonical[:separator]
            name = canonical[separator + 1 :]
            if name:
                key = parent.casefold()
                group = attachment_groups.setdefault(key, (parent, set()))
                group[1].add(name)
                continue
        for variant in {
            original,
            original.replace("\\", "/"),
            original.replace("/", "\\"),
        }:
            if variant:
                variants.setdefault(variant.casefold(), (variant, token))
    pattern = None
    tokens: dict[str, str] = {}
    if variants:
        ordered = sorted((item[0] for item in variants.values()), key=len, reverse=True)
        pattern = re.compile(
            "|".join(re.escape(item) for item in ordered), re.IGNORECASE
        )
        tokens = {key: item[1] for key, item in variants.items()}

    attachment_pattern = None
    attachment_parents: tuple[str, ...] = ()
    if attachment_groups:
        groups: list[str] = []
        parents: list[str] = []
        for parent, names in sorted(
            attachment_groups.values(), key=lambda item: len(item[0]), reverse=True
        ):
            parent_pattern = re.escape(parent).replace(r"\\", r"[\\/]")
            parents.append(parent_pattern)
            name_pattern = "|".join(
                re.escape(name) for name in sorted(names, key=len, reverse=True)
            )
            groups.append(f"{parent_pattern}[\\\\/](?:{name_pattern})")
        attachment_pattern = re.compile("|".join(groups), re.IGNORECASE)
        attachment_parents = tuple(
            parent.casefold() for parent, _names in attachment_groups.values()
        )
    return pattern, tokens, attachment_pattern, attachment_parents


def _replace_paths(value: str, replacements: list[tuple[str, str]]) -> str:
    result = value.replace("\r\n", "\n").replace("\r", "\n")
    pattern, tokens, attachment_pattern, attachment_parents = (
        _replacement_engine(tuple(replacements))
    )
    folded_result = result.casefold() if attachment_parents else ""
    if (
        attachment_pattern is not None
        and attachment_parents
        and any(parent in folded_result for parent in attachment_parents)
    ):
        result = attachment_pattern.sub(
            lambda match: (
                "%ATTACHMENT:"
                + match.group(0).replace("/", "\\").rsplit("\\", 1)[-1].casefold()
                + "%"
            ),
            result,
        )
    if pattern is not None:
        result = pattern.sub(
            lambda match: tokens[match.group(0).casefold()], result
        )
    return result


@functools.lru_cache(maxsize=8)
def _without_attachment_replacements(
    replacements: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, str], ...]:
    return tuple(
        pair for pair in replacements if not pair[1].startswith("%ATTACHMENT:")
    )


def _replacements_present_in_text(
    value: str, replacements: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    replacement_tuple = tuple(replacements)
    _pattern, _tokens, _attachments, attachment_parents = _replacement_engine(
        replacement_tuple
    )
    if not attachment_parents:
        return replacements
    folded = value.casefold()
    if any(
        parent in folded
        or parent.replace("\\", "\\\\") in folded
        or parent.replace("\\", "/") in folded
        for parent in attachment_parents
    ):
        return replacements
    return list(_without_attachment_replacements(replacement_tuple))


def _fallback_jsonl_digest(
    path: Path, replacements: list[tuple[str, str]]
) -> str:
    digest = hashlib.sha256()
    first_line = True
    with path.open("rb") as handle:
        for raw_line in handle:
            line = raw_line.decode("utf-8-sig" if first_line else "utf-8")
            first_line = False
            active = _replacements_present_in_text(line, replacements)
            digest.update(_replace_paths(line, active).encode("utf-8"))
    return digest.hexdigest()


def _normalize_semantic_value(
    value: Any, replacements: list[tuple[str, str]]
) -> Any:
    if isinstance(value, str):
        return _replace_paths(value, replacements)
    if isinstance(value, list):
        return [_normalize_semantic_value(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_semantic_value(item, replacements)
            for key, item in value.items()
        }
    return value


def normalize_semantic_value(
    value: Any, replacements: list[tuple[str, str]]
) -> Any:
    """Return the canonical, path-portable form used by lineage comparisons."""

    return _normalize_semantic_value(value, replacements)


def semantic_file_digest(
    path: Path,
    replacements: list[tuple[str, str]],
    progress: Callable[[int], None] | None = None,
) -> str:
    if path.suffix.casefold() == ".jsonl":
        raw_digest = hashlib.sha256()
        semantic_digest = hashlib.sha256()
        text_decodable = True
        json_valid = True
        first_line = True
        with path.open("rb") as handle:
            for raw_line in handle:
                raw_digest.update(raw_line)
                if progress:
                    progress(len(raw_line))
                try:
                    line = raw_line.decode("utf-8-sig" if first_line else "utf-8")
                except UnicodeError:
                    text_decodable = False
                    first_line = False
                    continue
                first_line = False
                if not line.strip():
                    continue
                active_replacements = _replacements_present_in_text(
                    line, replacements
                )
                if len(raw_line) > 2 * 1024 * 1024:
                    normalized = _replace_paths(
                        line, active_replacements
                    ).rstrip("\n")
                else:
                    try:
                        normalized = json.dumps(
                            normalize_semantic_value(
                                json.loads(line), active_replacements
                            ),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    except (json.JSONDecodeError, TypeError):
                        json_valid = False
                        continue
                semantic_digest.update(normalized.encode("utf-8"))
                semantic_digest.update(b"\n")
        if not text_decodable:
            return raw_digest.hexdigest()
        if not json_valid:
            return _fallback_jsonl_digest(path, replacements)
        return semantic_digest.hexdigest()

    try:
        text = path.read_text(encoding="utf-8-sig")
        if progress:
            progress(path.stat().st_size)
    except (OSError, UnicodeError):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                if progress:
                    progress(len(chunk))
        return digest.hexdigest()
    try:
        if path.suffix.casefold() == ".json":
            text = json.dumps(
                normalize_semantic_value(json.loads(text), replacements),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            text = _replace_paths(text, replacements)
    except (json.JSONDecodeError, TypeError):
        text = _replace_paths(text, replacements)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def item_map(items: Iterable[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item["key"]): str(item.get("currentFingerprint") or item["fingerprint"])
        for item in items
        if item.get("state") != "removed"
        and (item.get("currentFingerprint") or item.get("fingerprint"))
    }


def classify_items(
    current: dict[str, dict[str, Any]],
    base: dict[str, str] | None,
    peer: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    base = base or {}
    peer = peer or {}
    result: list[dict[str, Any]] = []
    for key in sorted(set(base) | set(current), key=str.casefold):
        current_item = current.get(key)
        current_fingerprint = (
            str(current_item["fingerprint"]) if current_item else None
        )
        base_fingerprint = base.get(key)
        peer_fingerprint = peer.get(key)
        if base_fingerprint is None:
            state = "new" if current_item else "unchanged"
        elif current_item is None:
            state = "removed"
        elif current_fingerprint == base_fingerprint:
            state = "unchanged"
        else:
            state = "changed"

        current_changed = current_fingerprint != base_fingerprint
        peer_changed = bool(peer) and peer_fingerprint != base_fingerprint
        if current_changed and peer_changed and current_fingerprint != peer_fingerprint:
            state = "independentlyChanged"

        record = dict(current_item or {"key": key, "kind": key.split("/", 1)[0]})
        record.pop("fingerprint", None)
        record.update(
            {
                "state": state,
                "currentFingerprint": current_fingerprint,
                "baseFingerprint": base_fingerprint,
                "peerFingerprint": peer_fingerprint,
            }
        )
        result.append(record)
    return result


def build_manifest(
    backup_id: str,
    source_device_id: str,
    created_at_utc: str,
    current: dict[str, dict[str, Any]],
    base_state: dict[str, Any],
    peer_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent_backup_id = base_state.get("baseBackupId")
    peer_items = item_map(peer_manifest.get("items", [])) if peer_manifest else {}
    items = classify_items(current, base_state.get("items", {}), peer_items)
    counts = {state: 0 for state in sorted(ITEM_STATES)}
    for item in items:
        counts[item["state"]] += 1
    diverged = counts["independentlyChanged"] > 0
    relation = "root" if not parent_backup_id else ("diverged" if diverged else "linear")
    return {
        "lineageVersion": LINEAGE_VERSION,
        "backupId": backup_id,
        "parentBackupId": parent_backup_id,
        "sourceDeviceId": source_device_id,
        "createdAtUtc": created_at_utc,
        "relation": relation,
        "peerBackupId": peer_manifest.get("backupId") if peer_manifest else None,
        "items": items,
        "counts": counts,
    }


def state_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "stateVersion": STATE_VERSION,
        "baseBackupId": manifest.get("backupId"),
        "items": item_map(manifest.get("items", [])),
    }


def validate_manifest(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["root must be an object"]
    if value.get("lineageVersion") != LINEAGE_VERSION:
        errors.append("unsupported lineageVersion")
    for field in ("backupId", "sourceDeviceId"):
        try:
            uuid.UUID(str(value.get(field, "")))
        except ValueError:
            errors.append(f"{field} must be a UUID")
    parent = value.get("parentBackupId")
    if parent:
        try:
            uuid.UUID(str(parent))
        except ValueError:
            errors.append("parentBackupId must be null or a UUID")
    if value.get("relation") not in {"root", "linear", "diverged"}:
        errors.append("invalid relation")
    items = value.get("items")
    if not isinstance(items, list):
        return errors + ["items must be a list"]
    keys: set[str] = set()
    actual_counts = {state: 0 for state in sorted(ITEM_STATES)}
    for item in items:
        if not isinstance(item, dict) or not item.get("key"):
            errors.append("item without key")
            continue
        key = str(item["key"])
        if key in keys:
            errors.append(f"duplicate item key: {key}")
        keys.add(key)
        state = item.get("state")
        if state not in ITEM_STATES:
            errors.append(f"invalid state for {key}")
            continue
        actual_counts[state] += 1
        current = item.get("currentFingerprint")
        if state == "removed" and current is not None:
            errors.append(f"removed item {key} has a current fingerprint")
        if current is not None and (
            len(str(current)) != 64
            or any(character not in "0123456789abcdef" for character in str(current))
        ):
            errors.append(f"invalid current fingerprint for {key}")
    if value.get("counts") != actual_counts:
        errors.append("counts do not match items")
    return errors
