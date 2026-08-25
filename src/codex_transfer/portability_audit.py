"""Schema-aware, read-only audit for computer-bound paths in Codex state."""

from __future__ import annotations

import hashlib
import json
import ntpath
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from . import backup


AUDIT_VERSION = 2
WINDOWS_PATH = re.compile(
    r"(?i)(?<![a-z0-9_+.-])(?:\\\\\?\\)?[a-z]:[\\/](?![\\/])"
    r"(?:[^\x00\r\n\"<>|?*\s,;:.)\]}][^\x00\r\n\"<>|?*]{0,2047})?"
)
UNC_PATH = re.compile(r"\\\\[^\\\s\"']+\\[^\x00\r\n\"<>|?*]{1,2048}")
PATHISH_COLUMN = re.compile(
    r"(?i)(?:^|_)(?:path|paths|cwd|root|roots|directory|directories|folder|folders|workspace|workspaces)(?:_|$)"
)

KNOWN_DATABASE_FIELDS = {
    "project_roots.path": "project-location-mapping",
    "threads.rollout_path": "destination-rollout-path",
    "threads.cwd": "project-location-mapping",
    "threads.sandbox_policy": "portable-text-translation",
    "threads.agent_path": "portable-text-translation",
}
STRUCTURED_DATABASE_FIELDS = {
    "projects.metadata",
    "threads.sandbox_policy",
}
CONTENT_FIELDS = {
    "threads.title",
    "threads.first_user_message",
    "threads.preview",
    "thread_dynamic_tools.description",
    "thread_dynamic_tools.input_schema",
}
KNOWN_EXCLUDED_GLOBAL_KEYS = {
    "electron-main-window-bounds",
    "electron-persisted-atom-state",
}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _paths(value: str) -> list[str]:
    candidates = [match.group(0) for match in WINDOWS_PATH.finditer(value)]
    candidates.extend(match.group(0) for match in UNC_PATH.finditer(value))
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.rstrip(" .,;:)]}")
        normalized = ntpath.normcase(ntpath.normpath(candidate))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(candidate)
    return unique


def _flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten_strings(item)


def _structured_strings(value: Any) -> Iterable[str]:
    if not isinstance(value, str):
        return []
    stripped = value.strip()
    if stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            return [value]
        return list(_flatten_strings(parsed))
    return [value]


def _without_extended_prefix(value: str | Path) -> str:
    text = str(value).replace("/", "\\")
    if text.lower().startswith("\\\\?\\unc\\"):
        return "\\\\" + text[8:]
    if text.startswith("\\\\?\\"):
        return text[4:]
    return text


def _normalized(value: str | Path) -> str:
    return ntpath.normcase(ntpath.normpath(_without_extended_prefix(value)))


def _under(candidate: str, root: str) -> bool:
    candidate_value = _normalized(candidate)
    root_value = _normalized(root).rstrip("\\")
    return candidate_value == root_value or candidate_value.startswith(root_value + "\\")


def _field_token(source: str, field: str, known: bool) -> str:
    if known:
        return field
    fingerprint = hashlib.sha256(f"{source}:{field}".encode("utf-8")).hexdigest()[:10]
    return f"{source}.unrecognized-field-{fingerprint}"


def _impact(classification: str, path_kind: str, path_status: str) -> str:
    if classification == "needs-review" and path_kind == "old-source-location":
        return "high"
    if classification in {"translated", "excluded"} or path_status == "missing":
        return "low"
    return "medium"


def _handling(classification: str) -> str:
    if classification == "excluded":
        return "excluded-machine-state"
    if classification == "translated":
        return "preserved-and-translated"
    return "preserved-unchanged"


def _database_schema(connection) -> dict[str, list[dict[str, Any]]]:
    schema: dict[str, list[dict[str, Any]]] = {}
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for table in tables:
        schema[table] = [
            {"name": str(row[1]), "type": str(row[2] or "").upper()}
            for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
        ]
    return schema


def _collect_database_roots(connection, schema: dict[str, list[dict[str, Any]]]) -> list[str]:
    roots: list[str] = []
    table_names = set(schema)
    if "project_roots" in table_names:
        columns = {item["name"] for item in schema["project_roots"]}
        if "path" in columns:
            roots.extend(
                str(row[0])
                for row in connection.execute(
                    'SELECT "path" FROM "project_roots" WHERE typeof("path")="text"'
                )
                if row[0]
            )
    if "threads" in table_names:
        columns = {item["name"] for item in schema["threads"]}
        if "cwd" in columns:
            roots.extend(
                str(row[0])
                for row in connection.execute(
                    'SELECT DISTINCT "cwd" FROM "threads" WHERE typeof("cwd")="text"'
                )
                if row[0]
            )
    return roots


def _global_state_roots(state: dict[str, Any]) -> list[str]:
    roots: list[str] = []
    projects = state.get("local-projects") or {}
    if isinstance(projects, dict):
        for project in projects.values():
            if not isinstance(project, dict):
                continue
            roots.extend(
                str(value)
                for value in (project.get("rootPaths") or [])
                if isinstance(value, str)
            )
    return roots


def audit(
    profile: Path,
    codex_home: Path,
    *,
    extra_project_roots: Iterable[str | Path] = (),
    legacy_roots: Iterable[str | Path] = (),
    include_local_details: bool = False,
) -> dict[str, Any]:
    """Find path-bearing Codex fields.

    The normal result remains safe to store or share. ``include_local_details``
    adds an in-memory-only view with real schema field names and a few local
    paths for the GUI. Callers must never persist that local view.
    """

    profile = profile.resolve(strict=False)
    codex_home = codex_home.resolve(strict=False)
    database = codex_home / "state_5.sqlite"
    state_path = codex_home / ".codex-global-state.json"
    state: dict[str, Any] = {}
    state_readable = True
    if state_path.is_file():
        try:
            loaded = backup.read_json(state_path)
            state = loaded if isinstance(loaded, dict) else {}
        except Exception:
            state_readable = False

    database_readable = True
    schema: dict[str, list[dict[str, Any]]] = {}
    database_values: list[tuple[str, bool, list[str]]] = []
    roots = [str(value) for value in extra_project_roots]
    connection = None
    if database.is_file():
        try:
            connection = backup.connect_read_only(database)
            schema = _database_schema(connection)
            roots.extend(_collect_database_roots(connection, schema))
            for table, columns in schema.items():
                for column in columns:
                    name = str(column["name"])
                    field = f"{table}.{name}"
                    if field in CONTENT_FIELDS:
                        continue
                    known = field in KNOWN_DATABASE_FIELDS
                    should_scan = (
                        known
                        or field in STRUCTURED_DATABASE_FIELDS
                        or bool(PATHISH_COLUMN.search(name))
                    )
                    if not should_scan:
                        continue
                    rows = connection.execute(
                        f"SELECT {_quote(name)} FROM {_quote(table)} "
                        f"WHERE typeof({_quote(name)})='text' AND length({_quote(name)})<=1048576"
                    )
                    found: list[str] = []
                    for row in rows:
                        for text in _structured_strings(row[0]):
                            found.extend(_paths(text))
                    if found:
                        database_values.append((field, known, found))
        except Exception:
            database_readable = False
        finally:
            if connection is not None:
                connection.close()
    elif not database.is_file():
        database_readable = False

    roots.extend(_global_state_roots(state))
    normalized_roots = sorted(
        {_normalized(value) for value in roots if _paths(str(value))},
        key=len,
        reverse=True,
    )
    normalized_legacy_roots = sorted(
        {
            _normalized(value)
            for value in legacy_roots
            if _paths(str(value)) and not _under(str(value), str(profile))
        },
        key=len,
        reverse=True,
    )

    grouped: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    local_grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    availability_cache: dict[str, str] = {}

    def availability(path: str) -> str:
        normalized = _normalized(path)
        if normalized in availability_cache:
            return availability_cache[normalized]
        filesystem_path = _without_extended_prefix(path)
        if filesystem_path.startswith("\\\\"):
            value = "not-checked"
        else:
            try:
                value = "present" if Path(filesystem_path).exists() else "missing"
            except OSError:
                value = "not-checked"
        availability_cache[normalized] = value
        return value

    def add(source: str, field: str, known: bool, path: str, known_strategy: str) -> None:
        if _under(path, str(profile)):
            path_kind = "profile-relative"
        elif any(_under(path, root) for root in normalized_roots):
            path_kind = "project-relative"
        elif any(_under(path, root) for root in normalized_legacy_roots):
            path_kind = "old-source-location"
        else:
            path_kind = "external-or-unknown"

        if source == "sqlite":
            if known and (
                field in {"project_roots.path", "threads.rollout_path", "threads.cwd"}
                or path_kind in {"profile-relative", "project-relative"}
            ):
                classification = "translated"
                reason = known_strategy
            elif known:
                classification = "needs-review"
                reason = "external-path-has-no-known-mapping"
            else:
                classification = "needs-review"
                reason = "unrecognized-database-field"
        elif known and known_strategy == "known-machine-specific-state":
            classification = "excluded"
            reason = known_strategy
        elif known and path_kind in {"profile-relative", "project-relative"}:
            classification = "translated"
            reason = "portable-state-translation"
        elif known:
            classification = "needs-review"
            reason = "external-path-has-no-known-mapping"
        else:
            classification = "needs-review"
            reason = "unrecognized-global-state-field"
        token = _field_token(source, field, known)
        path_status = availability(path)
        key = (source, token, classification, path_kind + ":" + reason, path_status)
        grouped[key] += 1
        if include_local_details:
            local_key = (source, field, classification, path_kind + ":" + reason, path_status)
            local = local_grouped.setdefault(
                local_key,
                {"paths": [], "seen": set(), "occurrences": 0},
            )
            local["occurrences"] += 1
            normalized_path = _normalized(path)
            if normalized_path not in local["seen"]:
                local["seen"].add(normalized_path)
                if len(local["paths"]) < 5:
                    local["paths"].append(path)

    for field, known, values in database_values:
        strategy = KNOWN_DATABASE_FIELDS.get(field, "unrecognized")
        for path in values:
            add("sqlite", field, known, path, strategy)

    for top_level_key, value in state.items():
        portable = top_level_key in backup.PORTABLE_STATE_KEYS
        excluded = top_level_key in KNOWN_EXCLUDED_GLOBAL_KEYS
        # These stores are excluded as a whole and can contain arbitrary UI or
        # conversation text. Scanning that text creates URL/prose false positives
        # without changing any backup or restore decision.
        if excluded:
            continue
        known = portable or excluded
        strategy = (
            "portable-state-translation"
            if portable
            else "known-machine-specific-state"
            if excluded
            else "unrecognized"
        )
        for text in _flatten_strings(value):
            for path in _paths(text):
                add("global-state", str(top_level_key), known, path, strategy)

    findings: list[dict[str, Any]] = []
    for (source, field, classification, combined, path_status), occurrences in sorted(grouped.items()):
        path_kind, reason = combined.split(":", 1)
        impact = _impact(classification, path_kind, path_status)
        handling = _handling(classification)
        findings.append(
            {
                "source": source,
                "schemaField": field,
                "classification": classification,
                "pathKind": path_kind,
                "pathStatus": path_status,
                "reason": reason,
                "occurrences": occurrences,
                "impact": impact,
                "backupHandling": handling,
                "translationPlanned": classification == "translated",
                "dataIncluded": classification != "excluded",
            }
        )
    local_findings: list[dict[str, Any]] = []
    if include_local_details:
        for (source, field, classification, combined, path_status), details in sorted(
            local_grouped.items()
        ):
            path_kind, reason = combined.split(":", 1)
            impact = _impact(classification, path_kind, path_status)
            local_findings.append(
                {
                    "source": source,
                    "schemaField": field,
                    "classification": classification,
                    "pathKind": path_kind,
                    "pathStatus": path_status,
                    "reason": reason,
                    "occurrences": int(details["occurrences"]),
                    "impact": impact,
                    "backupHandling": _handling(classification),
                    "translationPlanned": classification == "translated",
                    "dataIncluded": classification != "excluded",
                    "localPaths": list(details["paths"]),
                }
            )
    translated = sum(
        item["occurrences"] for item in findings if item["classification"] == "translated"
    )
    excluded = sum(
        item["occurrences"] for item in findings if item["classification"] == "excluded"
    )
    needs_review = sum(
        item["occurrences"] for item in findings if item["classification"] == "needs-review"
    )
    unknown_fields = len(
        {
            item["schemaField"]
            for item in findings
            if item["reason"].startswith("unrecognized-")
        }
    )
    review_fields = len(
        {
            item["schemaField"]
            for item in findings
            if item["classification"] == "needs-review"
        }
    )
    unmapped_external = sum(
        item["occurrences"]
        for item in findings
        if item["reason"] == "external-path-has-no-known-mapping"
    )
    unrecognized_references = sum(
        item["occurrences"]
        for item in findings
        if item["reason"].startswith("unrecognized-")
    )
    old_source_references = sum(
        item["occurrences"]
        for item in findings
        if item["classification"] == "needs-review"
        and item["pathKind"] == "old-source-location"
    )
    scan_errors = int(not database_readable) + int(not state_readable)
    result = {
        "portabilityAuditVersion": AUDIT_VERSION,
        "status": "attention" if needs_review or scan_errors else "portable",
        "summary": {
            "pathReferences": translated + excluded + needs_review,
            "translatedReferences": translated,
            "excludedMachineStateReferences": excluded,
            "needsReviewReferences": needs_review,
            "fieldsNeedingReview": review_fields,
            "unrecognizedSchemaFields": unknown_fields,
            "unrecognizedFieldReferences": unrecognized_references,
            "unmappedExternalReferences": unmapped_external,
            "oldSourceReferences": old_source_references,
            "scanErrors": scan_errors,
        },
        "coverage": {
            "databaseReadable": database_readable,
            "globalStatePresent": state_path.is_file(),
            "globalStateReadable": state_readable,
            "databaseTablesInspected": len(schema),
        },
        "findings": findings,
        "privacy": {
            "containsPathValues": False,
            "unknownFieldNamesAreFingerprinted": True,
        },
    }
    if include_local_details:
        result["_localFindings"] = local_findings
    return result
