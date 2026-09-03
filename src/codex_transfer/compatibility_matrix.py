from __future__ import annotations

import platform
from typing import Any


AUTOMATED_SCENARIOS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "different-usernames-and-known-folders",
        "Different Windows usernames and redirected known folders",
        ("portablePathModel", "portableLocationsRecorded", "projectIdentitiesSurviveRoundTrip"),
    ),
    (
        "external-usb-and-unc-roots",
        "External, USB, changed-drive and UNC project roots",
        ("projectLocationMapper", "usbDriveClassification"),
    ),
    (
        "long-and-unicode-paths",
        "Long and Unicode portable path handling",
        ("longUnicodePathModel",),
    ),
    (
        "nested-missing-and-reparse-roots",
        "Nested, missing and reparse-point project roots",
        ("projectRootInventoryAnalysis",),
    ),
    (
        "low-disk-space",
        "Low destination disk space is rejected before copying",
        ("lowDiskSpaceRejected",),
    ),
    (
        "interruption-and-rollback",
        "Interrupted project and conversation restore rolls back",
        ("rollbackAfterProjectQuarantine", "rollbackAfterProjectActivation", "conversationRollbackPreserved"),
    ),
    (
        "corrupt-backup",
        "Corrupt or incomplete package is rejected",
        ("tamperRejected", "missingEmptyTreeRejected"),
    ),
    (
        "schema-compatibility",
        "Newer source schema restores to an older destination schema",
        ("newerSourceToOlderTarget",),
    ),
    (
        "conversation-variants",
        "Recent, projectless, pinned and archived conversations",
        ("completePhase3Inventory", "conversationMirrorExact"),
    ),
    (
        "independent-edits",
        "Independent changes on both computers require explicit decisions",
        ("conversationConflictChoicesComplete", "projectConflictChoicesComplete"),
    ),
    (
        "legacy-and-round-trip",
        "Format 2.0 compatibility and repeated A-to-B-to-A round trips",
        ("legacyFormat20Supported", "repeatedRestoreIsIdempotent", "lineageSurvivesRoundTrip"),
    ),
    (
        "progress-state-transitions",
        "Measured and non-measurable work have unambiguous progress states",
        ("progressTransitionsClear",),
    ),
)


MANUAL_SCENARIOS: tuple[tuple[str, str, str, str | None], ...] = (
    ("windows-10-real-device", "Run the packaged executable on a physical Windows 10 computer", "pending", None),
    (
        "windows-11-real-device",
        "Run the packaged executable on a second physical Windows 11 computer",
        "passed",
        "Project-owner physical test completed 2026-09-02",
    ),
    ("usb-removal-during-write", "Remove a real USB drive during backup and confirm safe failure handling", "pending", None),
    (
        "release-candidate-round-trip",
        "Complete a real PC A to PC B to PC A release-candidate hand-off",
        "passed",
        "Backup, Verify backup, Restore, Verify restore, and continued Codex use completed 2026-09-02",
    ),
)


def build_matrix(checks: dict[str, bool]) -> dict[str, Any]:
    automated: list[dict[str, Any]] = []
    for scenario_id, description, required_checks in AUTOMATED_SCENARIOS:
        missing = [name for name in required_checks if not checks.get(name, False)]
        automated.append(
            {
                "id": scenario_id,
                "description": description,
                "status": "passed" if not missing else "failed",
                "checks": list(required_checks),
                "failedChecks": missing,
            }
        )
    return {
        "matrixVersion": 1,
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "automated": automated,
        "automatedPassed": sum(item["status"] == "passed" for item in automated),
        "automatedTotal": len(automated),
        "manual": [
            {
                "id": scenario_id,
                "description": description,
                "status": status,
                **({"evidence": evidence} if evidence else {}),
            }
            for scenario_id, description, status, evidence in MANUAL_SCENARIOS
        ],
    }
