# Public testing guide for Codex Lifeboat 3.4.1

[Nederlandse vertaling](nl/TESTHANDLEIDING.md)

Version 3.4.1 is a public beta/release candidate. Automated tests cover simulated
Windows users, paths, conflicts, failures, rollback, package corruption, and
round trips. Community testing is intended to add real Windows 10/11, USB, and
multi-computer evidence.

## Before testing

- Keep an independent copy of every irreplaceable project.
- Start with non-critical or disposable data when possible.
- Never publish a backup package: it can contain source code, `.env` files, API
  keys, Git history, and conversation content.
- Download `Codex-Lifeboat-Windows-x64-Portable.zip`, extract it completely, and
  verify `SHA256.txt`.
- Fully close Codex before every backup, restore, or verification operation.

## Recommended two-computer test

1. On computer A, note the Windows version, username, Codex version, project
   locations, conversation count, and whether Documents/Desktop uses OneDrive.
2. Create a backup and run **Verify backup**.
3. On computer B, install Codex, open it once, sign in, and close it completely.
4. Restore the backup, review every proposed path and conflict decision, and run
   **Verify restore**.
5. Open Codex and confirm recent, archived, pinned, project-linked, and projectless
   conversations plus the selected project files.
6. Make a small, identifiable project and conversation change on computer B.
7. Back up and verify computer B.
8. Return to computer A, review the comparison plan carefully, restore, verify,
   and confirm that no duplicate chats, projects, or stale files were created.
9. Open **Manage recovery points** and confirm that the local pre-restore recovery
   point is visible. USB backups should not appear in that list.

## Useful additional scenarios

- Different Windows usernames on A and B.
- Windows 10 to Windows 11 and the reverse.
- OneDrive-redirected Documents or Desktop.
- Projects on `C:\git`, another drive, USB, or a UNC network path.
- Destination-only chats and projects.
- The same project edited independently on both computers.
- A project deliberately excluded from the backup inventory.

## Report the result

Use the repository's **Compatibility test result** issue form. Report both
successes and failures; successful combinations are valuable evidence.

Include the Lifeboat version, both Windows versions, storage type, whether the
usernames or paths differed, which four operations succeeded, and the exact
sanitized error if something failed. Remove usernames, project names, message
content, keys, tokens, and private paths from screenshots and logs.

Do not attach a real backup, `auth.json`, `.env`, SQLite database, recovery point,
or project archive.
