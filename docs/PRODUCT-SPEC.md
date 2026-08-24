# Product specification 3.4

[Dutch translation](nl/PRODUCT-SPEC.md)

## Supported environment

- Windows 10 and Windows 11, x64.
- Local Codex desktop installation.
- Different Windows usernames, redirected known folders, drive letters, external
  disks, USB destinations, and explicitly mapped UNC roots.
- Offline operation with a warning when online version checking is unavailable.
- English primary interface and documentation with Dutch translation.
- Operation without administrator rights, Python, or an installer.

Version 3.4.0 is a public beta/release candidate until the remaining physical
Phase 11 tests are complete.

## User promise

After successful final verification, the destination contains the selected project
bytes, local conversations, archives, project links, available attachments, skills,
and portable settings represented by the source package. Portable paths are mapped
to the destination computer. Destination authentication and machine identity remain
unchanged. Conflicting or destination-only data is never silently overwritten.

## Operations

1. **Create backup:** read-only inventory, explicit project selection, consistent
   snapshot, complete copy, SHA-256 manifest, and independent validation.
2. **Verify backup:** read-only package, hash, SQLite, inventory, and lineage checks.
3. **Restore backup:** location mapping, comparison plan, explicit conflict choices,
   pre-restore recovery point, transactional replacement, and automatic rollback.
4. **Verify restore:** exact database, conversation, project, and decision checks.
5. **Manage recovery points:** inspect local rollback storage and remove only older
   independently valid points covered by the retention policy.

## Backup contents

Portable data includes selected complete project directories, recent and archived
session rollouts, a consistent SQLite snapshot, portable global state, available
referenced attachments, skills, instructions, and portable user configuration.

Source authentication, installation IDs, machine identity, sandboxes, caches,
temporary files, locks, active SQLite sidecars, and runtime state are excluded.

## Conflict and cleanup model

- Comparison is read-only and must predict the complete write set.
- Conversation conflicts require keep-backup, keep-computer, keep-both, skip, or cancel.
- Project conflicts require keep-backup, keep-computer, archive-and-replace, skip, or cancel.
- Destination-only projects are retained unless the user explicitly archives or
  moves them to recovery quarantine.
- Managed projects are staged and hash-verified before atomic activation.
- Recovery is conservative: USB backups, visible archives, incomplete evidence,
  and the two newest valid local points are not automatically deleted.

## Failure behavior

- An interrupted backup remains `.building-*` and is never reported as complete.
- A damaged backup is rejected before restoration changes the destination.
- Insufficient disk space and unresolved paths or conflicts block writes.
- Restore mutations are journaled and failures trigger reverse-order rollback.
- A successful restore retains its managed pre-restore recovery point.

## Definition of done for a stable release

The automated source, packaged executable, and portable ZIP matrices must pass;
physical Windows 10/11 and A-to-B-to-A trials must provide sanitized evidence; no
safety-critical issue may remain open; English and Dutch documentation, checksums,
license, notices, limitations, and security reporting must be published together.
