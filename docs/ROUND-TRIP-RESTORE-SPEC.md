# Universal round-trip restore specification

[Dutch translation](nl/ROUND-TRIP-RESTORE-SPEC.md)

## Objective

Codex Lifeboat must support a linear hand-off between arbitrary Windows 10/11
computers: back up computer B, continue on computer A, then return the newer
state to B without manual deletion, duplicate data, stale files, or dependence
on usernames, drive letters, or a particular folder layout.

This is verified snapshot transfer, not concurrent cloud synchronization.

## Managed scope

Lifeboat automatically includes data demonstrably associated with Codex:

- every database conversation, including Recent, projectless, pinned, and
  archived conversations;
- session rollouts, indexes, project assignments, relationships, and available
  referenced attachments;
- portable settings, skills, and instructions;
- projects registered by Codex, referenced by a conversation, used as a
  conversation working directory, or explicitly added by the user;
- complete managed project bytes, including `.git`, `.env`, hidden files, and
  uncommitted work.

Lifeboat does not search entire disks for unrelated projects.

## Location rules

- Windows known folders and profile-relative paths are stored logically, not as
  username-dependent target paths.
- External, removable, and network roots require an explicit target mapping
  before mirror restore may change them.
- A missing external root is never silently redirected to a fallback folder.
- Project identity must not depend on its current path. Permanent project IDs
  are introduced in a later phase.
- Embedded Codex paths may be translated; managed project file bytes remain
  exact.

## Restore rules

- An initialized destination does not require Codex reinstallation or a new
  sign-in. Codex only needs to be fully closed.
- Authentication and machine identity remain those of the destination.
- A complete comparison and restore plan precedes every write.
- Managed project roots are mirrored as units, never overlaid file by file.
- Existing targets are secured and verified before replacement.
- Any failure triggers automatic rollback.
- Repeating the same restore produces the same active state without duplicates.

## Conflicts and destination-only data

- Independent changes on both computers block automatic restore and require an
  explicit per-item decision.
- Destination-only projects are retained by default and reported. The user may
  archive or explicitly delete them.
- Conversation deletion and archive state travel with the active backup line.
- A new destination-only conversation is a conflict, not silent deletion.
- Lifeboat never performs an automatic content merge.

## Cleanup and recovery

- Active Codex data must contain no generated `-old`, `-backup`, `failed`, or
  duplicate restore folders.
- Temporary staging data is removed after verified completion.
- Recovery points are kept outside active Codex data in one managed location.
- The default future retention policy keeps the two newest valid recovery
  points and never automatically deletes the newest viable point.
- USB backup packages are never deleted automatically.

## Safety boundary

Lifeboat may only remove or replace paths that are present in the reviewed
restore plan and are proven descendants of approved managed roots. It must
never scan and clean an entire profile, drive, network share, or arbitrary
directory.

## Current 3.4.0 delivery boundary

Release 3.4.0 implements phases 0–10.1: portable paths, permanent project identity,
complete local inventory, backup lineage, reviewed location mapping, read-only
comparison, transactional project mirrors, and explicit conversation conflict
decisions, plus reviewed destination-only and independently changed project-root
decisions, managed recovery retention, and selectable pre-backup inventory. The
automated Phase 11 matrix passes locally for source, EXE, and extracted ZIP; physical
cross-computer evidence and the stable-release gate remain in phases 11–12.
