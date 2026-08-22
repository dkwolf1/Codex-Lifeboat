# Product specification 3.1

## Supported environment

- Windows 10 and Windows 11, 64-bit
- Local Codex/ChatGPT desktop installation
- Different Windows usernames and known-folder locations
- Older-to-newer and newer-to-older migration through shared SQLite columns
- Offline operation with a warning when version checking is unavailable
- Best-effort online version checking through Microsoft Store/winget
- English and Dutch user interfaces
- Operation without administrator privileges, Python or an installer

## User promise

After successful final verification, the destination computer contains the same
included project bytes, conversations, archives, project links, available
attachments, skills and portable settings as the source. Paths are translated to
the new Windows profile. Authentication and machine identity remain those of the
destination computer.

## Four operations

1. **Backup:** consistent snapshot, complete project copy and SHA-256 manifest.
2. **Backup verification:** read-only verification of hashes, SQLite, conversations and projects.
3. **Restore:** safety copy and consent first, replacement with automatic rollback second.
4. **Restore verification:** validation of SQLite, conversation rollouts and project hashes.

## Failure behavior

- An interrupted backup remains `.building-*` and is never reported as complete.
- A damaged backup is rejected before restoration begins.
- Existing destination data is secured and explicitly reported first.
- Any failure during restoration triggers automatic rollback.
- A safety copy is never removed automatically after success.
