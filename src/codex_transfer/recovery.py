"""Managed recovery-point inventory and conservative retention for restores."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any, Callable

from . import backup, windows


RECOVERY_INDEX_VERSION = 1
DEFAULT_KEEP = 2


def _tree_bytes(root: Path) -> int:
    total = 0
    if not root.exists() or root.is_symlink():
        return 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _resolved_equal(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)


def _is_managed_point(path: Path, profile: Path) -> bool:
    root = windows.recovery_points_folder(profile).resolve(strict=False)
    resolved = path.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return False
    return bool(relative.parts) and len(relative.parts) == 1


def _journal_project_payloads(journal: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    for item in journal.get("projects", []):
        if (
            item.get("strategy") == "transactional-mirror"
            and item.get("existedBefore")
            and item.get("previousTargetDisposition") == "recovery"
            and item.get("quarantinePath")
        ):
            result.append(Path(str(item["quarantinePath"])))
        elif (
            item.get("strategy") == "destination-project-disposition"
            and item.get("disposition") == "delete-to-recovery"
            and item.get("movedPath")
        ):
            result.append(Path(str(item["movedPath"])))
    return result


def _journal_required_payloads(journal: dict[str, Any]) -> list[Path]:
    result = list(_journal_project_payloads(journal))
    for item in journal.get("projects", []):
        if (
            item.get("strategy") == "transactional-mirror"
            and item.get("existedBefore")
            and item.get("previousTargetDisposition") == "archive"
            and item.get("quarantinePath")
        ):
            result.append(Path(str(item["quarantinePath"])))
        elif (
            item.get("strategy") == "destination-project-disposition"
            and item.get("disposition") == "archive"
            and item.get("movedPath")
        ):
            result.append(Path(str(item["movedPath"])))
    return result


def _database_valid(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        connection = backup.connect_read_only(path)
        try:
            return backup.sqlite_quick_check(connection) == "ok"
        finally:
            connection.close()
    except Exception:
        return False


def inspect_point(path: Path, profile: Path) -> dict[str, Any]:
    path = path.resolve(strict=False)
    errors: list[str] = []
    journal_path = path / "restore-journal.json"
    journal: dict[str, Any] = {}
    if not _is_managed_point(path, profile):
        errors.append("point is outside the managed recovery folder")
    if path.is_symlink():
        errors.append("point is a symbolic link")
    if not journal_path.is_file():
        errors.append("restore journal is missing")
    else:
        try:
            journal = backup.read_json(journal_path)
        except Exception as exc:
            errors.append(f"restore journal is unreadable: {exc}")
    if journal:
        if journal.get("status") != "complete":
            errors.append("restore did not complete")
        if not _resolved_equal(
            Path(str(journal.get("targetProfile") or "")), profile
        ):
            errors.append("restore belongs to another profile")
        if not _resolved_equal(
            Path(str(journal.get("safetyRoot") or "")), path
        ):
            errors.append("journal recovery path does not match")
        if not _database_valid(path / "codex-before-restore" / "state_5.sqlite"):
            errors.append("recovery database is missing or invalid")
        for payload in _journal_required_payloads(journal):
            if not payload.is_dir() or payload.is_symlink():
                errors.append(f"required project recovery payload is missing: {payload}")
    completed = str(
        journal.get("completedAtUtc")
        or journal.get("preparedAtUtc")
        or dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
    ) if path.exists() else ""
    payloads = _journal_required_payloads(journal)
    return {
        "path": str(path),
        "name": path.name,
        "status": journal.get("status") or "unknown",
        "completedAtUtc": completed,
        "valid": not errors,
        "errors": errors,
        "centralBytes": _tree_bytes(path),
        "projectRecoveryBytes": sum(_tree_bytes(item) for item in payloads),
        "projectRecoveryPaths": [str(item) for item in payloads],
    }


def list_points(profile: Path) -> dict[str, Any]:
    profile = profile.resolve(strict=False)
    root = windows.recovery_points_folder(profile).resolve(strict=False)
    points = []
    if root.is_dir() and not root.is_symlink():
        points = [
            inspect_point(path, profile)
            for path in root.iterdir()
            if path.is_dir() and not path.is_symlink()
        ]
    points.sort(key=lambda item: str(item.get("completedAtUtc") or ""), reverse=True)
    valid = [item for item in points if item["valid"]]
    return {
        "recoveryIndexVersion": RECOVERY_INDEX_VERSION,
        "root": str(root),
        "keep": DEFAULT_KEEP,
        "points": points,
        "validPoints": len(valid),
        "invalidPoints": len(points) - len(valid),
        "totalBytes": sum(
            int(item["centralBytes"]) + int(item["projectRecoveryBytes"])
            for item in points
        ),
    }


def _safe_hidden_recovery_path(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    return (
        ".codex-lifeboat-recovery" in resolved.parts
        and resolved != Path(resolved.anchor)
        and not resolved.is_symlink()
    )


def _prune_empty_recovery_parents(path: Path) -> None:
    parent = path.parent
    while parent.name != ".codex-lifeboat-recovery":
        if not parent.is_dir() or parent.is_symlink():
            return
        try:
            next(parent.iterdir())
            return
        except StopIteration:
            parent.rmdir()
            parent = parent.parent


def _cleanup_staging(journal: dict[str, Any]) -> tuple[int, int]:
    removed = 0
    freed = 0
    for item in journal.get("projects", []):
        if item.get("strategy") != "transactional-mirror":
            continue
        staging_value = item.get("stagingPath")
        target_value = item.get("target")
        if not staging_value or not target_value:
            continue
        staging = Path(str(staging_value)).resolve(strict=False)
        target = Path(str(target_value)).resolve(strict=False)
        if (
            not staging.name.startswith(".codex-lifeboat-stage-")
            or staging.parent != target.parent
            or not target.is_dir()
            or not staging.is_dir()
            or staging.is_symlink()
        ):
            continue
        size = _tree_bytes(staging)
        shutil.rmtree(staging)
        removed += 1
        freed += size
    return removed, freed


def _remove_old_point(path: Path, profile: Path) -> tuple[int, int]:
    if not _is_managed_point(path, profile) or path.is_symlink():
        raise ValueError(f"Refusing to remove unmanaged recovery point: {path}")
    journal = backup.read_json(path / "restore-journal.json")
    payloads = _journal_project_payloads(journal)
    for payload in payloads:
        if not _safe_hidden_recovery_path(payload):
            raise ValueError(f"Refusing to remove unsafe project recovery path: {payload}")
    removed_payloads = 0
    freed = 0
    for payload in payloads:
        if payload.is_dir():
            freed += _tree_bytes(payload)
            shutil.rmtree(payload)
            _prune_empty_recovery_parents(payload)
            removed_payloads += 1
    freed += _tree_bytes(path)
    shutil.rmtree(path)
    return removed_payloads, freed


def enforce_retention(
    profile: Path,
    keep: int = DEFAULT_KEEP,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Keep newest valid recovery points and conservatively remove only older valid ones."""

    if keep < 2:
        raise ValueError("At least two valid recovery points must be retained.")
    profile = profile.resolve(strict=False)
    before = list_points(profile)
    valid = [item for item in before["points"] if item["valid"]]
    retained = valid[:keep]
    expired = valid[keep:]
    staging_removed = 0
    freed = 0
    for point in before["points"]:
        if not point["valid"]:
            continue
        journal_path = Path(str(point["path"])) / "restore-journal.json"
        if not journal_path.is_file():
            continue
        try:
            journal = backup.read_json(journal_path)
            count, size = _cleanup_staging(journal)
            staging_removed += count
            freed += size
        except Exception:
            continue
    removed_points: list[str] = []
    removed_payloads = 0
    for point in expired:
        path = Path(str(point["path"]))
        if progress:
            progress(f"Removing expired verified recovery point: {path}")
        payload_count, size = _remove_old_point(path, profile)
        removed_payloads += payload_count
        freed += size
        removed_points.append(str(path))
    after = list_points(profile)
    return {
        "recoveryIndexVersion": RECOVERY_INDEX_VERSION,
        "keep": keep,
        "root": before["root"],
        "retainedPoints": [str(item["path"]) for item in retained],
        "removedPoints": removed_points,
        "removedProjectPayloads": removed_payloads,
        "stagingDirectoriesRemoved": staging_removed,
        "bytesFreed": freed,
        "validPointsAfter": after["validPoints"],
        "invalidPointsRetained": after["invalidPoints"],
        "totalBytesAfter": after["totalBytes"],
    }
