# Test results 3.4.0

Date: August 24, 2026
Platform: Windows 11 build environment; target compatibility Windows 10/11 x64

## Automated end-to-end test

The complete 66-check phase-0-through-11 source suite was executed successfully.
The latest 3.4.0 standalone executable and the executable started from a freshly
extracted portable ZIP both passed the same 66-check packaged gate and the 12/12
automated Phase 11 matrix.

| Check | Result |
|---|---|
| Valid package structure and independent validation | Passed |
| Source files identical before and after backup | Passed |
| Source `auth.json` excluded | Passed |
| Stable restore executable included in portable backup | Passed |
| SQLite snapshot normalized to a single-file journal | Passed |
| Independent validation does not modify the package | Passed |
| Hash and validation progress reaches 100% | Passed |
| Non-measurable finalization and preflight work switches to active indeterminate progress | Passed |
| Unknown Store version does not block backup | Passed |
| Direct execution from ZIP preview is detected and blocked | Passed |
| Portable path model translates different usernames and redirected known folders | Passed |
| Long and Unicode portable paths retain their meaning across usernames | Passed |
| Insufficient destination space is rejected before payload copying | Passed |
| External and UNC roots require explicit target mapping | Passed |
| Package format 2.1 records validated portable locations | Passed |
| Legacy package format 2.0 remains supported | Passed |
| Legacy package format 2.1 remains supported | Passed |
| Legacy package format 2.2 remains supported | Passed |
| Legacy package format 2.3 remains supported | Passed |
| Same-named projects receive distinct permanent identities | Passed |
| Project identity survives a path change and restore | Passed |
| Restored identity survives the next return backup | Passed |
| Recent, projectless, pinned and archived conversations inventoried once | Passed |
| Rollouts, Recent index, sections, tools and spawn relations cross-validated | Passed |
| Present and missing referenced attachments inventoried with conversation IDs | Passed |
| Tool-output paths excluded from attachment discovery | Passed |
| Unreadable historical attachment reported without aborting backup | Passed |
| Project root collisions, nesting, absence and reparse status inventoried | Passed |
| Unique backup, parent and anonymous source-device IDs | Passed |
| B-to-A-to-B return backup retains one continuous lineage | Passed |
| New, changed, removed, unchanged and independently changed classification | Passed |
| Three-way divergent sibling detection | Passed |
| Multi-megabyte conversation lineage digest streams with byte progress | Passed |
| Genuine empty Codex and project trees pass independent validation | Passed |
| Missing empty lineage tree is rejected as package damage | Passed |
| Empty portable Codex directories survive restore | Passed |
| Read-only comparison preview predicts selected project and Codex writes | Passed |
| Comparison preview leaves package, projects and Codex profile unchanged | Passed |
| Conflicting and destination-only managed data blocks restore | Passed |
| Identical and destination-only projects are not redundantly copied | Passed |
| Per-volume required and available free space reported before restore | Passed |
| Legacy packages receive a read-only compatibility comparison plan | Passed |
| Destination-only and independently edited chats block until reviewed | Passed |
| Keep-backup, keep-computer, keep-both, skip, and cancel choices | Passed |
| Keep-both creates one deterministic new ID and rewrites rollout identity | Passed |
| Recent, archive, pin, projectless and project assignment state mirrored | Passed |
| Dynamic tools and spawn relationships retained for destination copies | Passed |
| Project registration required by an explicitly retained target chat remains valid | Passed |
| Exact reviewed conversation-ID set with one record and rollout per ID | Passed |
| Recent index contains every active chat exactly once and no archived chat | Passed |
| Explicit source-side deletion removes a destination-only chat | Passed |
| Repeated restore with retained and cloned chats is idempotent | Passed |
| Forced failure immediately after conversation mirroring | Rollback passed |
| Destination-only project retained by default without duplicate data | Passed |
| Retained project remains in database, global state and identity registry | Passed |
| Destination-only project visibly archived with exact fingerprint | Passed |
| Separately confirmed project removal moves all bytes to recovery quarantine | Passed |
| Archive and removal clear only the reviewed active Codex registrations | Passed |
| Project conflict choices: backup, computer, archive-and-replace, skip, cancel | Passed |
| Independently changed project roots are never file-merged | Passed |
| Final verification follows each reviewed project decision | Passed |
| Forced failure after destination-project move | Rollback passed |
| Visual backup result summarizes chats, projects, files, size and protection | Passed |
| Read-only pre-backup inventory leaves every source file unchanged | Passed |
| Project path, file count, logical size and largest folders shown before copy | Passed |
| Every existing project selected by default; Codex data remains locked on | Passed |
| Explicit project exclusion keeps chats but omits payload and active registrations | Passed |
| English and Dutch result and recovery interfaces instantiate correctly | Passed |
| Backend warnings no longer produce a mixed-language English result dialog | Passed |
| Empty Recovery Points view explains when points are created and disables cleanup | Passed |
| Restore safety point uses the managed machine-local recovery folder | Passed |
| Freshly extracted portable ZIP passes the complete packaged matrix | Passed |
| Generated EXE and ZIP SHA-256 values match the generated artifacts | Passed |
| Four valid recovery points are reduced to the two newest | Passed |
| Invalid or incomplete recovery evidence remains untouched | Passed |
| Exact hidden payloads belonging only to expired valid points are removed | Passed |
| Visible project archives and USB backup packages are never removed | Passed |
| Verified stale staging data is removed | Passed |
| Repeated recovery cleanup is idempotent | Passed |
| Selected project staged on the final target volume | Passed |
| Staged file set, byte count, and every SHA-256 hash verified before activation | Passed |
| Existing project atomically quarantined and exact mirror activated | Passed |
| Stale destination-only project files removed without overlay copying | Passed |
| Repeated identical restore skips all project copying | Passed |
| No temporary staging or duplicate active project folders after restore | Passed |
| Forced failure immediately after project quarantine | Rollback passed |
| Forced failure immediately after verified project activation | Rollback passed |
| Known-folder and profile project targets resolved automatically | Passed |
| External project restore blocked until its exact root is reviewed | Passed |
| Approved external roots persisted per destination computer | Passed |
| Unsafe, offline, linked, broad, and colliding project targets rejected | Passed |
| Exact `.git`, `.env` and uncommitted project files | Passed |
| Skills and portable Codex configuration restored | Passed |
| Different source and destination usernames translated | Passed |
| Older source to newer destination schema | Passed |
| Newer source fields to older destination schema | Passed |
| Existing destination project secured and replaced | Passed |
| Destination authentication unchanged | Passed |
| Damaged package rejected | Passed |
| Forced failure after project identity registration | Rollback passed |
| Destination identity registry restored during rollback | Passed |
| Destination lineage state restored during rollback | Passed |
| Safety copy retained after successful restore | Passed |
| Four GUI operations in English and Dutch | Passed |
| Standalone executable starts without an immediate crash | Passed |

## Phase 11 compatibility matrix

All 12 simulated two-computer scenarios passed. Four real-hardware checks remain
explicitly pending: a physical Windows 10 run, a second physical Windows 11 run,
USB removal during writing, and the final release-candidate PC-A-to-PC-B-to-PC-A
journey. See `docs/PHASE-11-TEST-MATRIX.md`.

The synthetic fixture contains three database conversations (project-linked,
projectless and pinned, and projectless and archived), active and archived
rollouts, a Recent index, conversation relations, a present and a missing
attachment, a project with `.git` and `.env`, a skill, portable configuration,
an empty Codex data directory, existing destination data and two different
destination database schemas.
