# Roadmap: reliable Codex backup and restore

> This is the original architecture roadmap. For current delivery status, use the
> [implementation roadmap for phases 0–12](IMPLEMENTATION-ROADMAP.md).

[Dutch translation](nl/ROADMAP.md)

[Universal round-trip restore specification](ROUND-TRIP-RESTORE-SPEC.md)

[Implementation roadmap: phases 0–12](IMPLEMENTATION-ROADMAP.md)

## 1. Goal

Build a repeatable workflow that transfers a complete Codex working environment
from Windows computer A to Windows computer B without damaging the destination
login, installation identity or machine-specific settings.

The solution must transfer projects, Git repositories, local conversations,
archives, titles, project links and available attachments. It must support different
Windows usernames and paths, handle Codex version differences safely, produce
verifiable evidence before and after every operation, and provide rollback.

## 2. Core design decision

Never copy the entire `.codex` directory from one computer over another. Split the
profile into two categories.

### Portable data

- Project directories and Git repositories
- `sessions` and `archived_sessions`
- A consistent SQLite snapshot containing conversation data
- `session_index.jsonl`
- Portable project and conversation fields from `.codex-global-state.json`
- Locally available referenced attachments
- Selected skills, instructions and user configuration

### Machine-specific data

Never restore these from the source computer:

- `auth.json` and other authentication data
- `installation_id` and `cap_sid`
- Sandboxes, caches and temporary files
- Active SQLite `-shm` files
- Browser cookies, local app caches and Windows package data
- Processes, locks, runtime state and local permission status

Restoration therefore means importing data into a working local installation,
not replacing the complete profile.

## 3. Versioned backup package

```text
Codex-PortableBackup-YYYYMMDD-HHMMSS/
├── manifest/
│   ├── package.json
│   ├── projects.json
│   ├── threads.json
│   ├── path-mappings.json
│   └── sha256.csv
├── projects/
├── codex/
│   ├── state.snapshot.sqlite
│   ├── sessions/
│   ├── archived_sessions/
│   ├── session_index.jsonl
│   └── portable-global-state.json
├── attachments/
└── reports/
```

The package manifest records the format and tool version, creation date, source
profile, Codex version, database schema, original project paths, counts, size,
required free space, SQLite health, completion state and hash manifest.

## 4. Standard workflow

### Backup

1. Inventory projects, conversations, attachments, versions and free space.
2. Require Codex to be fully closed before the final snapshot.
3. Use the SQLite Backup API instead of blindly copying active database files.
4. Copy project and session data into a temporary package.
5. Record SHA-256 for every package file.
6. Validate the complete temporary package independently.
7. Mark and rename it as complete only after validation succeeds.

### Backup validation

1. Validate manifests, hashes, counts and database references without writing.
2. Require every database conversation to have the expected rollout data.
3. Require valid JSON metadata and matching conversation IDs.
4. Require SQLite `quick_check` to return `ok`.

### Restore

1. Install Codex, open it once, sign in and close it fully.
2. Validate the backup before making any destination changes.
3. Translate source profile paths to the destination Windows profile.
4. Create a consistent rollback copy of the current destination state.
5. Restore projects, sessions and portable profile data.
6. Import database rows using columns understood by both schemas.
7. Preserve destination authentication and machine identity.
8. Run complete final verification before Codex is restarted.

## 5. Delivery phases

### Phase 0 — Specification and baseline

Classify every portable and machine-specific item, document SQLite structures,
define path mappings and freeze backup package format 2.0.

Acceptance: every included and excluded item has a documented reason, and no
source credentials are required for restoration.

### Phase 1 — Backup generator 2.0

Implement automatic project discovery, optional extra directories, safe process
checks, consistent SQLite snapshots, portable state export, attachment inventory,
SHA-256 manifests, atomic completion and clear reports.

Acceptance: interrupted backups are never complete, source files remain unchanged,
and every completed backup immediately passes independent validation.

### Phase 2 — Restore/import engine 2.0

Implement path mapping, free-space and compatibility checks, destination conflict
handling, schema-aware SQLite import, idempotency, an import journal, resumability,
rollback and complete final reporting.

Acceptance: repeated restoration creates no duplicates; existing destination data,
authentication and identity remain valid; every project and conversation opens;
and injected failures leave a recoverable state.

### Phase 3 — Automated compatibility matrix

Test empty and populated destinations, different usernames and drives, newer and
older schemas, repeated restoration, forced interruption, damaged sessions,
missing attachments, conflicting project files and insufficient disk space.

Acceptance: every release runs the same disposable test suite and stores both
machine-readable and human-readable results.

### Phase 4 — Ease of use

Deliver a one-click graphical workflow, clear progress, actionable errors, a fixed
log location and a final summary of projects, conversations, files, hashes and
warnings. A normal user must never rename or delete `.codex` directories manually.

### Phase 5 — Maintenance and distribution

Maintain semantic versions and a changelog, run periodic test restores, document
backup retention, keep copies on separate physical media, publish signed releases
when practical, and maintain discoverable English documentation.

## 6. Safety rules

1. Never restore while Codex is running.
2. Never replace the destination's complete `.codex` directory.
3. Never migrate authentication, installation IDs or caches.
4. Never copy an active SQLite database as a lone file.
5. Never silently overwrite conflicting project data.
6. Never continue after failed hash or database validation.
7. Never call a backup complete before independent verification.
8. Never remove the safety copy automatically after a successful restore.

## 7. Definition of done

The product is complete when backup, validation, restore and verification are
separate operations; packages are versioned and fully hashed; SQLite snapshots are
consistent; restoration is transactional; different usernames and paths work;
destination identity is preserved; rollback is proven; the compatibility matrix
passes; and a non-technical user can complete the workflow through the GUI alone.
