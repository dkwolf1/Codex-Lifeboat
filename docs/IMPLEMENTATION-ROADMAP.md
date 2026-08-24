# Universal round-trip restore implementation roadmap

[Dutch translation](nl/IMPLEMENTATION-ROADMAP.md) · [Approved specification](ROUND-TRIP-RESTORE-SPEC.md)

This roadmap implements safe, repeatable hand-off of one complete Codex working
state between arbitrary Windows 10/11 computers. A phase may start only after
the preceding phase's automated gate passes. Dangerous restore behavior remains
disabled until all foundations it depends on are verified.

## Phase 0 — Specification and safety boundary

**Status:** Complete in 3.3.0

- Freeze managed scope, conflict rules, cleanup policy, and terminology.
- Define that this is linear snapshot hand-off, not concurrent cloud sync.
- Permit writes only to reviewed Codex data and approved project roots.
- Preserve destination authentication and machine identity.
- Maintain an automatic rollback path for every restore mutation.

**Gate:** English and Dutch specifications exist and existing backup, validation,
restore, rollback, and GUI regression tests pass.

## Phase 1 — Universal location model

**Status:** Complete in 3.3.0

- Describe profile-relative and Windows known-folder locations without usernames.
- Describe external drives, removable media, and UNC roots without silently
  selecting a target.
- Record portable locations for projects, attachments, and explicit extra paths.
- Introduce package format 2.1 while retaining format 2.0 support.

**Gate:** Tests cover username changes, redirected known folders, profile paths,
external roots, UNC paths, schema validation, and legacy format acceptance.

## Phase 2 — Permanent project identity

**Status:** Complete in 3.4.0

- Assign each logical project a persistent UUID independent of its current path.
- Keep a machine-local registry outside project directories.
- Carry identity records in the package and install them on the destination.
- Migrate legacy path-derived IDs without adding files to user projects.
- Use Codex project IDs and Git metadata only as matching evidence.

**Gate:** One project retains its Lifeboat ID across username and path changes;
same-named projects remain distinct; a repeated backup reuses the installed ID.

## Phase 3 — Complete Codex inventory

**Status:** Complete in 3.4.0

- Inventory Recent, projectless, pinned, and archived conversations.
- Include rollout files, indexes, relationships, assignments, and available
  referenced attachments.
- Discover every project demonstrably associated with Codex.
- Detect duplicate, overlapping, nested, missing, and reparse-point roots.
- Write one independently validated inventory manifest and retain package-format
  compatibility with 2.0, 2.1, and 2.2.

**Gate:** All fixture conversations and managed projects appear exactly once and
every manifest object resolves to verified payload data.

## Phase 4 — Backup lineage and change history

**Status:** Complete in 3.4.0

- Add backup ID, parent backup ID, anonymous source-device ID, and per-item state.
- Distinguish new, changed, removed, unchanged, and independently changed data.
- Recognize the B-to-A-to-B return journey as one lineage.
- Keep the anonymous device and lineage state outside Codex and project folders,
  and include lineage-state restoration in the automatic rollback boundary.

**Gate:** Three-way comparison correctly detects linear updates and divergence.

## Phase 5 — Project Location Mapper

**Status:** Complete in 3.4.0

- Resolve portable locations against the destination computer.
- Ask once for external-root mappings and remember them per computer.
- Offer use, create, choose another location, or skip.
- Reject missing, colliding, unsafe, and unavailable destinations.
- Abort safely without writing when a required location is skipped; selective
  per-project restore remains part of the phase-6 plan.

**Gate:** No external project can be restored until its exact target is reviewed.

## Phase 6 — Comparison and restore plan

**Status:** Complete in 3.4.0

- Show source, target, state, proposed action, size, and free-space requirements.
- Separate identical, incoming, destination-only, removed, and conflicting items.
- Keep restore disabled until mappings and conflicts are resolved.
- Select only projects that the reviewed plan proves require creation or replacement;
  identical and destination-only projects remain untouched.

**Gate:** The preview completely predicts the write set and performs no writes.

## Phase 7 — Transactional mirror restore

**Status:** Complete in 3.4.0

- Stage each selected managed project beside its final target on the same volume.
- Verify the complete staged file set, byte count, and every SHA-256 hash before
  changing the active project.
- Atomically quarantine the previous target and activate the verified mirror;
  stale files disappear through whole-directory replacement, never overlay copying.
- Persist every transaction transition in the restore journal and roll completed
  mutations back in reverse order after any failure.
- Skip identical projects on repeated restore and leave no staging or duplicate
  active project directories.

**Gate:** Repeated restore is idempotent; interruption and injected failures leave
the original state recoverable and create no duplicate folders.

## Phase 8 — Conversation mirror and conflicts

**Status:** Complete in 3.4.0

- Mirror Recent, pin, archive, deletion, project assignment, projectless state,
  dynamic tools, and spawn relationships.
- Keep one active database record and one valid rollout per conversation ID.
- Treat destination-only conversations and independent edits on both computers as
  blocking conflicts until the user makes a per-chat decision.
- Provide explicit keep-backup, keep-computer, keep-both, skip, and cancel choices.
- Give a kept destination copy a deterministic new conversation ID, rewrite its
  rollout identity, rebuild Recent without duplicates, and verify the exact ID set.
- Restore the complete pre-restore Codex state after an injected conversation failure.

**Gate:** Active Codex shows the expected conversations without duplicates or
resurrected deleted items; safety recovery remains possible.

## Phase 9 — Destination-only projects and data

**Status:** Complete in 3.4.0

- Retain destination-only projects by default and report them.
- Resolve independently changed project roots without silently merging their files.
- Offer keep-backup, keep-computer, archive-and-replace, skip, and cancel for
  independently changed project roots.
- Offer visible archive or separately confirmed removal to recovery quarantine for
  destination-only projects; no project bytes are destroyed.
- Keep or remove the matching database, global-state, and Lifeboat identity
  registrations according to the reviewed choice.
- Journal each move and automatically roll it back after any later failure.

**Gate:** Passed. No destination-only bytes are destroyed without separate consent;
retention, archive, recoverable removal, registration cleanup, and rollback tests pass.

## Phase 10 — Recovery point retention

**Status:** Complete in 3.4.0

- Store indexed recovery points under the machine-local Lifeboat data folder,
  outside active Codex data and user project folders.
- Keep the two newest independently valid points by default; incomplete or invalid
  points are retained for manual inspection rather than deleted automatically.
- Remove only older verified points and their exact journaled hidden project
  payloads; visible user archives remain untouched.
- Remove verified stale staging directories and expose point status, disk usage,
  retention policy, and confirmed manual cleanup in the GUI.
- Never scan or automatically delete USB backup packages.

**Gate:** Passed. Four successive valid fixture points are reduced to the two newest,
invalid data and USB packages remain untouched, stale staging is removed, cleanup is
idempotent, and restore uses the managed recovery location.

## Phase 10.1 — Backup inventory and project selection

**Status:** Complete in 3.4.0

- Scan every discovered project before backup and show its current path, logical
  file count, logical size, and largest immediate child folders.
- Keep Codex conversations, settings, and available attachments locked on; every
  existing project is selected by default.
- Recalculate the estimated selected file count and size immediately when a user
  includes or excludes a project.
- Require a second explicit confirmation when project files are excluded and record
  the complete selection in the package report.
- Preserve conversations belonging to an excluded project as projectless history,
  while removing that project's active database and global-state registrations from
  the portable snapshot.
- Never silently exclude dependency, cache, build, Git, environment, or other
  project folders; the size breakdown informs the user's whole-project decision.

**Gate:** Passed. Read-only preview leaves the source unchanged, all projects start
selected, size totals react to selection, a selectively excluded project has no
payload or active registration, its conversations remain present, and independent
package validation succeeds.

## Phase 11 — Universal Windows test matrix

**Status:** Automated gate complete in 3.4.0; physical trials pending

- Test Windows 10/11, different usernames, OneDrive redirection, drive changes,
  external/USB/UNC roots, long and Unicode paths, reparse points, nested roots,
  low disk space, interruption, corruption, and schema differences.
- Test projectless and archived conversations and independent edits on both PCs.
- Test format 2.0 migration and repeated round trips.

**Automated gate:** Source, packaged executable, and freshly extracted release
candidate pass the complete simulated matrix. The physical-device gate remains open.

The automated matrix and dual Windows CI profiles are now active. See
[`PHASE-11-TEST-MATRIX.md`](PHASE-11-TEST-MATRIX.md). Physical Windows 10/11,
USB-removal, and release-candidate round-trip evidence remain pending.
The source build, packaged executable, and freshly extracted portable ZIP pass
the complete local 75-check suite and 12/12 automated scenarios on Windows 11.

## Phase 12 — Public release and stable-release evidence

**Status:** Public testing prepared in 3.4.0

- Complete English-first documentation and Dutch translation.
- Publish signed artifacts when available, SHA-256, notices, limitations, and an
  operator-friendly migration guide.
- Run a multi-user Windows release-candidate trial and collect sanitized results.

**Gate:** Publish v4.0.0 only after independent round-trip recovery evidence is
complete and no safety-critical issue remains open.

Version 3.4.0 is therefore prepared as a transparent pre-release, with English
primary documentation, Dutch translation, SHA-256 assets, security reporting,
known limitations, and a structured community compatibility-report form.

## Phase 13 — Reliability and portability follow-up

### Phase 13.1 — Diagnostics center and anonymized report

**Status:** Implemented in 3.4.0 source

- Add one read-only GUI action for system diagnostics.
- Check Windows 10/11 compatibility, extracted launch location, Codex folder and
  SQLite integrity, Codex process state, installed version detection, removable
  storage, local free space, recovery points, and local Lifeboat state.
- Show pass, notice, and failure results in English and Dutch.
- Copy or save a structured JSON support report.
- Exclude user and computer names, drive letters, absolute paths, project and file
  names, conversation titles/content, authentication data, and environment values.
- Regression-test both source immutability and anonymization.

**Gate:** The full self-test passes, the diagnostic scan does not change the
inspected profile, and known synthetic identity values do not occur in the report.

### Phase 13.2 — Schema-aware path portability audit

**Status:** Implemented in 3.4.0 source

- Inspect path-bearing SQLite and global-state fields without changing the source.
- Distinguish known translated paths, intentionally excluded machine-specific state,
  known fields with unmapped external paths, and unknown future fields.
- Show the result before backup and in the diagnostics center.
- Store an independently hashed `reports/portability-audit.json` in every backup.
- Store only counts, classifications, reason codes, and stable fingerprints—never
  paths, project names, user identity, or conversation content.
- Warn and continue when review is needed; never guess a translation or silently
  discard an unrecognized field.

**Gate:** Passed. Synthetic known and future fields are classified correctly, the
scan is read-only, reports contain no raw paths, the audit is hash-verified inside
the package, and the complete source suite passes.

### Phase 13.3 — Git-aware conflict explanation

**Status:** Implemented in 3.4.0 source

- Inspect both project worktrees without locks or writes when Git is available.
- Distinguish the same commit, backup-ahead, computer-ahead, divergent, unrelated,
  dirty-worktree, and insufficient-evidence situations.
- Show the explanation when a project is selected in restore review.
- Keep complete Lifeboat file hashes authoritative and retain every existing
  explicit conflict decision.
- Never merge, commit, reset, rebase, fetch, push, or alter a worktree.

**Gate:** Passed. Synthetic histories cover forward progress, divergence, and local
changes; no path is exposed and Git evidence never changes a restore action.

### Phase 13.4 — Durable atomic metadata storage

**Status:** Implemented in 3.4.0 source

- Route critical JSON and checksum metadata through one same-directory writer.
- Flush the complete temporary file, read it back, parse and optionally validate it,
  atomically replace the target, and remove temporary evidence on failure.
- Cover configuration, manifests, reports, restore journals, project identities,
  lineage/device state, external-root mappings, and checksum sidecars.
- Preserve the previous complete value when interruption occurs before replacement.

**Gate:** Passed. Injected replacement failure retains the old parseable value,
successful retry installs the complete new value, and no temporary metadata remains.

### Phase 13.5 — Strict prefix-only conversation synchronization

**Status:** Implemented in 3.4.0

- Compare source and destination rollout JSONL as normalized semantic records,
  streaming in order and without modifying either file.
- Automatically accept only a non-empty destination that is an exact prefix of a
  longer backup conversation and whose relevant database metadata is unchanged.
- Use the existing transactional restore path to install the complete proven
  continuation; do not append directly to an active rollout.
- Keep edited records, metadata differences, malformed data, empty destinations,
  destination-ahead histories, and arbitrary divergence as explicit conflicts.
- Show the safe continuation and record counts in English and Dutch restore review.

**Gate:** Passed. Cross-username semantic paths, divergence, metadata changes,
invalid JSONL, read-only planning, transactional restore, and repeated idempotent
restore are covered by the complete 75-check source and packaged test gates.

Phase 13.6 (optional backup encryption) remains separate follow-up work.
