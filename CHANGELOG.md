# Changelog

## Unreleased

- Excluded the machine-specific `.codex/plugins` download cache and active plugin
  runtime from new backups; plugin settings and user skills remain portable.
- Restore now ignores plugin-runtime payloads found in older backups and preserves
  the destination computer's local plugin runtime, so existing backups stay usable.
- Inaccessible historical temporary chat attachments now produce a clear warning
  instead of aborting the complete backup during the availability check.

## 3.4.2 - 2026-08-25

- Replaced the ambiguous path-portability count with local, privacy-conscious
  details for schema field, path category, current availability, preservation,
  translation status, and low/medium/high impact.
- Clarified that unknown path values remain included unchanged and do not block a
  valid backup or restore; only their link to the previous location may need review.
- Full paths are hidden by default and can be revealed locally, while copied and
  saved support reports strip every local-only field and path.
- **Verify restore** now repeats the path audit and separately reports references
  that still point to an old source location.
- Reworked the main window into a clearer professional dashboard with navigation,
  focused backup and restore actions, status cards, and improved bilingual labels.
- Fixed the sidebar title being clipped on Windows display scaling.

## 3.4.1 - 2026-08-24

- Made normal backup creation substantially faster by avoiding an immediate
  second read of every copied payload byte. Creation still writes SHA-256 for
  every file and performs database, manifest, size, path, and lineage structure
  checks; **Verify backup** remains the explicit independent full SHA-256 reread.
- Full verification no longer reparses huge conversation JSONL files after their
  bytes have already passed SHA-256 verification. Semantic lineage is calculated
  once during creation and its hashed manifest and payload resolution are checked.
- Enlarged the project-selection window to use the available screen, increased
  the visible project rows, and made it independently restorable from the Windows
  taskbar instead of relying on a hidden transient modal owner.
- Fixed severe change-history slowdown when hundreds of historical attachment
  paths occur alongside very large conversation rollouts. Attachment paths are
  grouped by parent location and absent groups are rejected with a fast precheck,
  while semantic fingerprints remain byte-for-byte compatible.
- Final structural validation no longer repeats semantic rollout analysis.
- Added phase 13.5: strict prefix-only conversation synchronization proves that
  every existing destination record and all chat metadata match the beginning of
  the longer backup chat before adopting its incoming continuation automatically.
- Any edited record, metadata difference, unreadable JSONL, empty destination, or
  destination-ahead history remains an explicit conflict; no arbitrary chat merge
  or in-place append is attempted.
- Added read-only, cross-username, divergence, invalid-data, transactional-restore,
  and repeated-restore regression coverage for the prefix proof.
- Added phase 13.4: one durable atomic metadata writer now flushes, parses,
  validates, and replaces critical JSON and checksum state from the same folder.
- Backup configuration, manifests, reports, restore journals, project identity,
  lineage/device state, and external-root mappings use the hardened writer.
- Added interruption regression coverage proving a failed final replacement keeps
  the complete previous value and removes temporary metadata.
- Added phase 13.3: read-only Git-aware explanations for project conflicts.
- Restore review now distinguishes matching commits, backup-ahead, computer-ahead,
  divergent history, unrelated history, and uncommitted/untracked changes.
- Git evidence is advisory only: it never merges, commits, resets, pushes, or changes
  a restore decision, and complete Lifeboat hashes remain authoritative.
- Added phase 13.2: a read-only, schema-aware audit for path references in known
  and future Codex database and global-state fields.
- The audit distinguishes translated paths, intentionally excluded machine state,
  unmapped external paths, and unrecognized schema fields without guessing fixes.
- Project selection and diagnostics show the audit result, while every backup
  stores a separately hashed `reports/portability-audit.json`.
- Audit reports never contain raw paths; unknown field names are represented by
  stable fingerprints, and attention results warn without blocking backup.
- Added phase 13.1: a read-only diagnostics center covering Windows, Codex data,
  SQLite integrity, application state, installation detection, removable storage,
  free space, recovery points, and local Lifeboat state.
- Added copy and save actions for an anonymized JSON support report that excludes
  user/computer names, drive letters, absolute paths, project/file names,
  conversation content, authentication data, and environment values.
- Added regression coverage proving diagnostics leave the inspected source tree
  unchanged and do not expose the synthetic profile identity.

## 3.4.0 - 2026-08-24

- Prepared phase 12 as a clearly marked public testing release rather than a
  stable claim while physical Windows 10 and multi-computer evidence is pending.
- Added English-first and Dutch testing guides, release notes, release checklists,
  and a privacy-aware compatibility-result issue form.
- Hardened CI and release workflows with immutable action revisions and GitHub
  build-provenance attestations for the EXE, portable ZIP, and checksum file.
- Release builds now reject inconsistent version declarations and include the
  license, security policy, testing guides, release notes, and notices in the ZIP.

- Clarified backup and verification progress: hashing at 100% now transitions to
  named, animated analysis, preflight, final-validation, and safe-completion stages.
- Redesigned the project-selection dialog with a modern header, live metric cards,
  clearer included/excluded/protected states, improved controls, and row toggling.
- Recovery Points now explains the empty state and disables cleanup when no older
  verified point is eligible for removal.
- Started phase 11 with a machine-readable 12-scenario Windows compatibility
  matrix, low-space and long/Unicode-path tests, and Windows 2022/2025 CI profiles.
- The release build now requires the packaged executable to pass that Phase 11
  matrix in addition to the complete end-to-end self-test.
- Added phase 10.1: a read-only pre-backup inventory showing every project's path,
  logical file count, logical size, and largest immediate child folders.
- All projects start selected while Codex conversations, settings, and attachments
  remain locked on; selected totals update before the destination is confirmed.
- Added explicit whole-project exclusion with a second warning and package-report
  evidence. Excluded project chats remain as projectless history while active project
  registrations and project payload bytes are omitted consistently.
- Added the official English and Dutch implementation roadmap for phases 0–12.
- Added permanent UUID identities for logical projects and managed project roots.
- Added a machine-local atomic identity registry outside Codex and project folders.
- Installs restored identities on the destination so a return backup reuses them.
- Uses registered paths, Codex project IDs, and hashed Git remotes as ordered
  identity evidence while rejecting ambiguous matches.
- Added package format 2.2 with an independently validated project identity manifest.
- Added the complete phase-3 inventory for recent, projectless, pinned, and
  archived conversations, rollouts, indexes, relationships, project roots, and
  referenced attachments.
- Detects nested, missing, multi-source, and reparse-point project roots before copy.
- Added package format 2.3 with independent cross-validation of every inventory item.
- Retains validation support for package formats 2.0, 2.1, and 2.2.
- Added backup lineage with unique backup IDs, parent IDs, and anonymous persistent
  source-device IDs.
- Classifies each managed item as new, changed, removed, unchanged, or independently changed.
- Recognizes restored B-to-A-to-B hand-offs as one continuous lineage and detects
  divergent siblings with a three-way comparison.
- Added rollback-safe machine-local lineage state and package format 2.4 while
  retaining validation support for formats 2.0 through 2.3.
- Added the Project Location Mapper for username-independent known folders and
  explicitly reviewed external-drive, USB, and network project roots.
- Remembers approved external-root destinations per computer and blocks restore
  before any write when a mapping is missing, offline, unsafe, or colliding.
- Added English and Dutch mapping prompts with a final location review.
- Fixed attachment discovery so paths mentioned only in tool output are not
  mistaken for real conversation attachments.
- An unreadable historical attachment is now recorded as unavailable with a
  visible warning instead of aborting the complete backup.
- Streams multi-gigabyte conversation change analysis with bounded memory and
  replaces hundreds of portable paths in one pass instead of one scan per path.
- Shows live change-history file and byte progress after the initial hash reaches 100%.
- Accepts genuine empty Codex and project directories during independent lineage
  validation while still rejecting a missing directory or untracked payload data.
- Preserves empty portable Codex directories during restore for an exact round trip.
- Added a read-only comparison and restore plan showing source, target, state,
  proposed action, size, write set, and per-volume free-space requirements.
- Separates identical, incoming, destination-only, removed, and conflicting data;
  unresolved conflicts or locations now keep restore disabled.
- Identical and destination-only projects are retained without redundant copying,
  and a reviewed phase-6 plan is required by the normal GUI restore path.
- Added transactional project mirrors that are staged and fully SHA-256 verified
  on the destination volume before the active directory changes.
- Atomically quarantines the previous project and activates the verified mirror,
  eliminating stale overlay files while retaining a recoverable previous copy.
- Persists every project transaction state and rolls back in reverse order after
  failures immediately following quarantine, activation, or later restore work.
- Repeated restores skip identical projects and leave no staging or duplicate
  active project directories.
- Added per-conversation conflict decisions: keep the backup, keep this computer,
  keep both, skip, or cancel the complete restore.
- Destination-only and independently edited conversations now block restore until
  their decisions are recorded in the reviewed plan.
- Mirrors active, archived, pinned, project-linked, and projectless conversations
  together with rollouts, dynamic tools, spawn relationships, and the Recent index.
- “Keep both” creates a deterministic destination-copy ID and rewrites the copied
  rollout identity, preventing duplicate database or rollout IDs.
- Final verification checks the exact reviewed conversation-ID set and requires
  Recent to match all non-archived conversations without invalid or duplicate rows.
- Added automatic rollback coverage immediately after conversation mirroring and
  idempotent repeated-restore coverage for retained and cloned conversations.
- Destination-only project roots are retained by default and remain registered in
  the Codex database, global state, and Lifeboat identity registry.
- Added explicit retain, visible archive, recoverable delete, and cancel decisions
  for destination-only or lineage-removed projects.
- Added keep-backup, keep-computer, archive-and-replace, skip, and cancel decisions
  for independently changed project roots; files are never silently merged.
- Explicit project removal first moves every byte to a same-volume recovery
  quarantine and requires a separate confirmation in the English and Dutch GUI.
- Final verification checks the reviewed project fingerprint and active Codex
  registrations for retained, archived, removed, and replaced roots.
- Journals destination-project moves and automatically restores them after an
  injected failure, including their registrations and original active paths.
- Replaced terse backup completion popups with an English/Dutch visual result
  dashboard for conversations, projects, files, size, attachments, identities,
  lineage, integrity guarantees, and grouped notices.
- Added a persistent latest-result card so successful backup evidence remains
  visible after the result dialog closes.
- Standardized backend warning text in English and localizes warning categories in
  the GUI, preventing mixed Dutch/English completion dialogs.
- Added a recovery-point manager showing valid and retained-extra points, total
  disk use, the two-point retention policy, and confirmed safe cleanup.
- Restore safety copies now use one machine-local managed recovery folder outside
  active Codex data and project folders.
- Automatically keeps the two newest independently valid recovery points, removes
  only older verified points and exact hidden payloads, and preserves invalid or
  incomplete points for inspection.
- Cleans verified stale staging directories while never deleting visible project
  archives or scanning USB backup packages.

## 3.3.0 - 2026-08-23

- Added the approved universal round-trip restore specification in English and Dutch.
- Added portable path descriptors for Windows known folders, profile-relative
  locations, external drives, removable media, and network roots.
- Records portable locations for projects, attachments, and explicitly included paths.
- Added package format 2.1 while retaining read and validation support for 2.0.
- Added regression coverage for username changes, redirected Documents folders,
  profile-relative paths, external-root mapping, and UNC locations.

## 3.2.0 - 2026-08-23

- Modernized the Windows interface with clearer visual hierarchy, action cards,
  status feedback, and a more readable activity log.
- Rewritten and corrected the English and Dutch interface text.
- Improved restore wording so every action is explicit and unambiguous.

## 3.1.4 - 2026-08-23

- Blocks execution directly from Windows Explorer's temporary ZIP preview and
  gives explicit Extract All instructions.
- Makes the transition from 100% hashing to independent verification visible.
- Calculates the hash-manifest digest while writing it, avoiding a redundant
  reopen at the phase boundary.

## 3.1.3 - 2026-08-23

- Added live file, byte and percentage progress during hashing and validation.
- Removed a redundant third full payload hash pass while retaining independent
  full verification before a backup is finalized.
- Detects USB-backed fixed disks in addition to drives marked removable and
  refreshes the drive list automatically.
- Treats an unknown Microsoft Store version as unavailable information instead
  of incorrectly warning that a newer version may exist.

## 3.1.2 - 2026-08-22

- Fixed final validation of real Codex snapshots that use SQLite WAL mode.
- Snapshot databases are now normalized to a single self-contained file.
- The independent validator now opens snapshots as immutable and verifies that
  validation did not modify the backup package.

## 3.1.1 - 2026-08-22

- Fixed backup failure with `WinError 3` when the portable application was
  launched from a transient Windows location.
- The running application now stages a stable copy of itself at startup so the
  restore executable can always be included in the USB backup.

## 3.1.0 - 2026-08-22

- Renamed the public product and executable to Codex Lifeboat.
- Simplified the repository and moved binaries to GitHub Releases.
- Added a prominent, unambiguous Windows download section.
- Added Windows CI, automated release, dependency updates, and repository templates.
- Completed Python package metadata and reorganized translated documentation.

## 3.0.0 - 2026-08-22

- First standalone Windows 10/11 release.
- Bilingual graphical assistant for backup, validation, restore and final verification.
- Functional migration of Codex projects, conversations, settings, skills and local attachments.
- Preservation of destination authentication and machine identity.
- SHA-256 validation, safety copies and automatic rollback.
- Compatibility warning with an explicit option to continue.
