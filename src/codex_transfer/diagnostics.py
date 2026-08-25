"""Read-only system diagnostics with a privacy-safe support report."""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from . import __version__, atomic_io, backup, portability_audit, recovery, windows


REPORT_VERSION = 1
STATUS_PASS = "pass"
STATUS_NOTICE = "notice"
STATUS_FAIL = "fail"


def _check(
    check_id: str,
    status: str,
    title: str,
    summary: str,
    **facts: Any,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "title": title,
        "summary": summary,
        "facts": facts,
    }


def _exception_name(exc: BaseException) -> str:
    """Return useful failure information without leaking paths or file names."""

    return type(exc).__name__


def _codex_processes() -> list[str]:
    if os.name != "nt":
        return []
    completed = windows.run_hidden(["tasklist.exe", "/FO", "CSV", "/NH"])
    if completed.returncode != 0:
        raise RuntimeError("process query failed")
    output = completed.stdout.lower()
    return [
        name.removesuffix(".exe")
        for name in ("codex.exe", "chatgpt.exe")
        if f'"{name}"' in output
    ]


def _nearest_existing(path: Path) -> Path | None:
    candidate = path.resolve(strict=False)
    while not candidate.exists():
        if candidate == candidate.parent:
            return None
        candidate = candidate.parent
    return candidate


def _database_inventory(database: Path) -> dict[str, int | str]:
    connection = backup.connect_read_only(database)
    try:
        quick_check = backup.sqlite_quick_check(connection)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        thread_count = int(
            connection.execute('SELECT count(*) FROM "threads"').fetchone()[0]
        ) if "threads" in tables else 0
        project_count = int(
            connection.execute(
                'SELECT count(DISTINCT "project_id") FROM "project_roots"'
            ).fetchone()[0]
        ) if "project_roots" in tables else 0
        root_count = int(
            connection.execute('SELECT count(*) FROM "project_roots"').fetchone()[0]
        ) if "project_roots" in tables else 0
        return {
            "quickCheck": quick_check,
            "threadCount": thread_count,
            "projectCount": project_count,
            "registeredRootCount": root_count,
        }
    finally:
        connection.close()


def _session_file_count(codex_home: Path) -> int:
    count = 0
    for folder_name in ("sessions", "archived_sessions"):
        root = codex_home / folder_name
        if not root.is_dir() or root.is_symlink():
            continue
        for _folder, _directories, files in os.walk(root, followlinks=False):
            count += sum(1 for name in files if name.lower().endswith(".jsonl"))
    return count


def _drive_inventory(drives: Iterable[Path]) -> dict[str, int]:
    count = 0
    total = 0
    free = 0
    for drive in drives:
        count += 1
        try:
            usage = shutil.disk_usage(drive)
        except OSError:
            continue
        total += int(usage.total)
        free += int(usage.free)
    return {"count": count, "totalBytes": total, "freeBytes": free}


def _sensitive_values(profile: Path, codex_home: Path) -> list[str]:
    values = {
        str(profile),
        str(codex_home),
        profile.name,
        os.environ.get("USERNAME", ""),
        os.environ.get("USERDOMAIN", ""),
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERPROFILE", ""),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("APPDATA", ""),
        os.environ.get("TEMP", ""),
        os.environ.get("TMP", ""),
    }
    return sorted(
        (value for value in values if value and len(value) >= 3),
        key=len,
        reverse=True,
    )


def anonymize_text(value: str, sensitive_values: Iterable[str] = ()) -> str:
    """Remove common personal identifiers from diagnostic text."""

    result = value
    for sensitive in sensitive_values:
        result = re.sub(re.escape(str(sensitive)), "[redacted]", result, flags=re.I)
    result = re.sub(
        r"(?i)(?:\\\\\?\\)?[a-z]:\\[^\r\n\"']*",
        "[local path redacted]",
        result,
    )
    result = re.sub(r"\\\\[^\\\s]+\\[^\r\n\"']*", "[network path redacted]", result)
    result = re.sub(r"(?i)\bS-1-(?:\d+-){2,}\d+\b", "[user SID redacted]", result)
    result = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[email redacted]",
        result,
        flags=re.I,
    )
    result = re.sub(
        r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)",
        "[IP address redacted]",
        result,
    )
    return result


def _anonymize(value: Any, sensitive_values: Iterable[str]) -> Any:
    if isinstance(value, dict):
        return {str(key): _anonymize(item, sensitive_values) for key, item in value.items()}
    if isinstance(value, list):
        return [_anonymize(item, sensitive_values) for item in value]
    if isinstance(value, str):
        return anonymize_text(value, sensitive_values)
    return value


def _shareable(value: Any) -> Any:
    """Remove GUI-only local evidence before a report leaves this computer."""

    if isinstance(value, dict):
        return {
            str(key): _shareable(item)
            for key, item in value.items()
            if not str(key).startswith("_local")
        }
    if isinstance(value, list):
        return [_shareable(item) for item in value]
    return value


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(_shareable(report), ensure_ascii=False, indent=2) + "\n"


def save_report(path: Path, report: dict[str, Any]) -> None:
    """Atomically save a user-requested support report."""

    atomic_io.write_json(path, _shareable(report))


def build_report(
    profile: Path | None = None,
    codex_home: Path | None = None,
    *,
    process_probe: Callable[[], list[str]] | None = None,
    installation_probe: Callable[[], dict[str, Any]] | None = None,
    drives_probe: Callable[[], list[Path]] | None = None,
    recovery_probe: Callable[[Path], dict[str, Any]] | None = None,
    portability_probe: Callable[[Path, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run non-mutating checks and return an anonymized support report."""

    profile = (profile or Path.home()).resolve(strict=False)
    codex_home = (codex_home or profile / ".codex").resolve(strict=False)
    process_probe = process_probe or _codex_processes
    installation_probe = installation_probe or windows.installed_codex_version
    drives_probe = drives_probe or windows.removable_drives
    recovery_probe = recovery_probe or recovery.list_points
    default_portability_probe = portability_probe is None
    portability_probe = portability_probe or portability_audit.audit
    checks: list[dict[str, Any]] = []
    inventory: dict[str, Any] = {
        "conversationCount": 0,
        "projectCount": 0,
        "registeredProjectRootCount": 0,
        "sessionFileCount": 0,
        "removableDriveCount": 0,
        "removableDriveFreeBytes": 0,
        "validRecoveryPointCount": 0,
        "extraRecoveryPointCount": 0,
        "recoveryStorageBytes": 0,
        "portablePathReferenceCount": 0,
        "portabilityNeedsReviewCount": 0,
        "unrecognizedPortabilityFieldCount": 0,
    }

    windows_supported = os.name == "nt" and platform.release() in {"10", "11"}
    checks.append(
        _check(
            "windows",
            STATUS_PASS if windows_supported else STATUS_FAIL,
            "Windows compatibility",
            (
                f"Windows {platform.release()} detected."
                if windows_supported
                else "This computer is not running a supported Windows 10/11 environment."
            ),
            release=platform.release(),
            architecture=platform.machine() or "unknown",
        )
    )

    if windows.launched_from_compressed_folder():
        checks.append(
            _check(
                "launch_location",
                STATUS_FAIL,
                "Application launch location",
                "Codex Lifeboat appears to be running from inside a compressed archive.",
                extracted=False,
            )
        )
    else:
        checks.append(
            _check(
                "launch_location",
                STATUS_PASS,
                "Application launch location",
                "Codex Lifeboat is running from an extracted location.",
                extracted=True,
            )
        )

    codex_present = codex_home.is_dir()
    database = codex_home / "state_5.sqlite"
    database_present = database.is_file()
    checks.append(
        _check(
            "codex_data",
            STATUS_PASS if codex_present and database_present else STATUS_FAIL,
            "Codex data",
            (
                "The Codex data folder and state database were found."
                if codex_present and database_present
                else "The Codex data folder or state database is missing."
            ),
            folderPresent=codex_present,
            databasePresent=database_present,
        )
    )

    if codex_present:
        try:
            with os.scandir(codex_home) as entries:
                next(entries, None)
            checks.append(
                _check(
                    "codex_readable",
                    STATUS_PASS,
                    "Codex data access",
                    "The Codex data folder can be read.",
                    readable=True,
                )
            )
        except OSError as exc:
            checks.append(
                _check(
                    "codex_readable",
                    STATUS_FAIL,
                    "Codex data access",
                    "The Codex data folder could not be read.",
                    readable=False,
                    errorType=_exception_name(exc),
                )
            )

    if database_present:
        try:
            database_inventory = _database_inventory(database)
            inventory.update(
                conversationCount=int(database_inventory["threadCount"]),
                projectCount=int(database_inventory["projectCount"]),
                registeredProjectRootCount=int(database_inventory["registeredRootCount"]),
            )
            database_ok = database_inventory["quickCheck"] == "ok"
            checks.append(
                _check(
                    "database",
                    STATUS_PASS if database_ok else STATUS_FAIL,
                    "Codex database",
                    (
                        "The database is consistent and contains "
                        f"{inventory['conversationCount']} conversation(s) and "
                        f"{inventory['projectCount']} registered project(s)."
                        if database_ok
                        else "The read-only SQLite integrity check did not pass."
                    ),
                    **database_inventory,
                )
            )
        except Exception as exc:
            checks.append(
                _check(
                    "database",
                    STATUS_FAIL,
                    "Codex database",
                    "The database could not be inspected in read-only mode.",
                    errorType=_exception_name(exc),
                )
            )
        try:
            inventory["sessionFileCount"] = _session_file_count(codex_home)
        except OSError:
            pass

    try:
        portability = (
            portability_probe(profile, codex_home, include_local_details=True)
            if default_portability_probe
            else portability_probe(profile, codex_home)
        )
        local_portability_findings = portability.pop("_localFindings", [])
        portability_summary = portability.get("summary") or {}
        path_references = int(portability_summary.get("pathReferences", 0))
        translated_references = int(
            portability_summary.get("translatedReferences", 0)
        )
        excluded_references = int(
            portability_summary.get("excludedMachineStateReferences", 0)
        )
        covered_references = translated_references + excluded_references
        needs_review = int(portability_summary.get("needsReviewReferences", 0))
        unknown_fields = int(
            portability_summary.get("unrecognizedSchemaFields", 0)
        )
        review_fields = int(portability_summary.get("fieldsNeedingReview", 0))
        scan_errors = int(portability_summary.get("scanErrors", 0))
        review_findings = [
            item
            for item in portability.get("findings", [])
            if item.get("classification") == "needs-review"
        ]
        missing_review = sum(
            int(item.get("occurrences", 0))
            for item in review_findings
            if item.get("pathStatus") == "missing"
        )
        impact_counts = {
            impact: sum(
                int(item.get("occurrences", 0))
                for item in review_findings
                if item.get("impact") == impact
            )
            for impact in ("low", "medium", "high")
        }
        inventory.update(
            portablePathReferenceCount=path_references,
            portabilityNeedsReviewCount=needs_review,
            unrecognizedPortabilityFieldCount=unknown_fields,
        )
        checks.append(
            _check(
                "portability_audit",
                STATUS_NOTICE if needs_review or scan_errors else STATUS_PASS,
                "Path portability audit",
                (
                    f"{covered_references} path reference(s) are covered; "
                    f"{needs_review} preserved reference(s) across {review_fields} field(s) need review. "
                    f"{missing_review} point to paths that are no longer present. "
                    "Backup and restore can continue; no database data is omitted."
                    if needs_review or scan_errors
                    else f"All {path_references} detected path reference(s) are covered by known translation or exclusion rules."
                ),
                pathReferences=path_references,
                translatedReferences=translated_references,
                excludedMachineStateReferences=excluded_references,
                coveredReferences=covered_references,
                needsReviewReferences=needs_review,
                unrecognizedSchemaFields=unknown_fields,
                fieldsNeedingReview=review_fields,
                missingReviewReferences=missing_review,
                lowImpactReferences=impact_counts["low"],
                mediumImpactReferences=impact_counts["medium"],
                highImpactReferences=impact_counts["high"],
                reviewDataPreserved=True,
                scanErrors=scan_errors,
            )
        )
    except Exception as exc:
        local_portability_findings = []
        portability = {
            "portabilityAuditVersion": portability_audit.AUDIT_VERSION,
            "status": "attention",
            "summary": {
                "pathReferences": 0,
                "translatedReferences": 0,
                "excludedMachineStateReferences": 0,
                "needsReviewReferences": 0,
                "unrecognizedSchemaFields": 0,
                "fieldsNeedingReview": 0,
                "scanErrors": 1,
            },
            "coverage": {},
            "findings": [],
            "privacy": {
                "containsPathValues": False,
                "unknownFieldNamesAreFingerprinted": True,
            },
        }
        checks.append(
            _check(
                "portability_audit",
                STATUS_NOTICE,
                "Path portability audit",
                "The path portability audit could not be completed.",
                errorType=_exception_name(exc),
            )
        )

    try:
        running = process_probe()
        checks.append(
            _check(
                "codex_closed",
                STATUS_NOTICE if running else STATUS_PASS,
                "Codex application state",
                (
                    "Codex is still running; close it before backup or restore."
                    if running
                    else "Codex is not running."
                ),
                running=bool(running),
                matchingProcessCount=len(running),
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "codex_closed",
                STATUS_NOTICE,
                "Codex application state",
                "The running-process check was unavailable.",
                errorType=_exception_name(exc),
            )
        )

    try:
        installation = installation_probe()
        detected = bool(installation.get("detected"))
        version = str(installation.get("version") or "unknown")
        checks.append(
            _check(
                "installation",
                STATUS_PASS if detected else STATUS_NOTICE,
                "Codex installation",
                (
                    f"Codex installation version {version} was detected."
                    if detected
                    else "The installed Codex application version could not be detected."
                ),
                detected=detected,
                version=version,
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "installation",
                STATUS_NOTICE,
                "Codex installation",
                "The installed Codex application version could not be detected.",
                detected=False,
                errorType=_exception_name(exc),
            )
        )

    try:
        drive_inventory = _drive_inventory(drives_probe())
        inventory["removableDriveCount"] = drive_inventory["count"]
        inventory["removableDriveFreeBytes"] = drive_inventory["freeBytes"]
        checks.append(
            _check(
                "removable_storage",
                STATUS_PASS if drive_inventory["count"] else STATUS_NOTICE,
                "Removable storage",
                (
                    f"{drive_inventory['count']} removable storage device(s) detected."
                    if drive_inventory["count"]
                    else "No removable storage device was detected; a local folder can still be selected."
                ),
                **drive_inventory,
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "removable_storage",
                STATUS_NOTICE,
                "Removable storage",
                "Removable storage detection was unavailable.",
                errorType=_exception_name(exc),
            )
        )

    existing_volume = _nearest_existing(profile)
    if existing_volume:
        try:
            usage = shutil.disk_usage(existing_volume)
            free_bytes = int(usage.free)
            checks.append(
                _check(
                    "local_space",
                    STATUS_PASS if free_bytes >= 5 * 1024**3 else STATUS_NOTICE,
                    "Local free space",
                    (
                        "At least 5 GiB of free space is available on the user-profile volume."
                        if free_bytes >= 5 * 1024**3
                        else "Less than 5 GiB of free space is available on the user-profile volume."
                    ),
                    freeBytes=free_bytes,
                    totalBytes=int(usage.total),
                )
            )
        except OSError as exc:
            checks.append(
                _check(
                    "local_space",
                    STATUS_NOTICE,
                    "Local free space",
                    "Local free space could not be measured.",
                    errorType=_exception_name(exc),
                )
            )

    try:
        recovery_inventory = recovery_probe(profile)
        valid_points = int(recovery_inventory.get("validPoints", 0))
        invalid_points = int(recovery_inventory.get("invalidPoints", 0))
        recovery_bytes = int(recovery_inventory.get("totalBytes", 0))
        inventory.update(
            validRecoveryPointCount=valid_points,
            extraRecoveryPointCount=invalid_points,
            recoveryStorageBytes=recovery_bytes,
        )
        checks.append(
            _check(
                "recovery_points",
                STATUS_NOTICE if invalid_points else STATUS_PASS,
                "Recovery points",
                (
                    f"{valid_points} valid recovery point(s) and {invalid_points} extra retained point(s) found."
                ),
                validPoints=valid_points,
                extraRetainedPoints=invalid_points,
                totalBytes=recovery_bytes,
                keepPolicy=int(recovery_inventory.get("keep", recovery.DEFAULT_KEEP)),
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "recovery_points",
                STATUS_NOTICE,
                "Recovery points",
                "Recovery points could not be inspected.",
                errorType=_exception_name(exc),
            )
        )

    local_state = windows.lifeboat_data_folder(profile)
    checks.append(
        _check(
            "local_state",
            STATUS_PASS,
            "Lifeboat local state",
            (
                "The local Lifeboat state folder is present."
                if local_state.is_dir()
                else "No local Lifeboat state folder exists yet; it will be created when needed."
            ),
            present=local_state.is_dir(),
        )
    )
    checks.append(
        _check(
            "atomic_metadata",
            STATUS_PASS,
            "Atomic metadata storage",
            (
                f"All {len(atomic_io.HARDENED_STORES)} critical metadata groups use "
                "validated same-folder replacement."
            ),
            atomicMetadataVersion=atomic_io.ATOMIC_METADATA_VERSION,
            hardenedStoreCount=len(atomic_io.HARDENED_STORES),
            writePattern="flush-validate-replace",
        )
    )

    counts = {
        status: sum(1 for item in checks if item["status"] == status)
        for status in (STATUS_PASS, STATUS_NOTICE, STATUS_FAIL)
    }
    overall = (
        "blocked" if counts[STATUS_FAIL] else "attention" if counts[STATUS_NOTICE] else "ready"
    )
    report: dict[str, Any] = {
        "diagnosticReportVersion": REPORT_VERSION,
        "createdAtUtc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "product": {
            "name": "Codex Lifeboat",
            "version": __version__,
            "executionMode": "packaged" if getattr(sys, "frozen", False) else "source",
        },
        "privacy": {
            "anonymized": True,
            "containsAbsolutePaths": False,
            "excluded": [
                "user and computer names",
                "drive letters and absolute paths",
                "project and file names",
                "conversation titles and content",
                "authentication data and environment values",
            ],
        },
        "system": {
            "platform": "Windows" if os.name == "nt" else platform.system() or "unknown",
            "release": platform.release(),
            "build": platform.version(),
            "architecture": platform.machine() or "unknown",
            "python": platform.python_version(),
        },
        "summary": {
            "overall": overall,
            "passed": counts[STATUS_PASS],
            "notices": counts[STATUS_NOTICE],
            "failed": counts[STATUS_FAIL],
        },
        "inventory": inventory,
        "portabilityAudit": portability,
        "checks": checks,
    }
    safe_report = _anonymize(report, _sensitive_values(profile, codex_home))
    if local_portability_findings:
        safe_report["_localPortabilityAudit"] = {
            "summary": dict(portability.get("summary") or {}),
            "findings": local_portability_findings,
        }
    return safe_report
