# Known limitations of release 3.4.0

1. There is no published stable import contract for the local Codex database.
   The assistant therefore inspects schemas and must be retested after major future
   Codex schema changes.
2. Version checking uses AppX/process information and winget when available. If
   winget or internet access is unavailable, the user is warned and may continue.
3. The executable is not signed with a commercial code-signing certificate, so
   Windows SmartScreen may display a warning.
4. Reparse points, junctions and symbolic links are not followed. This prevents
   loops and unintended copies outside a project; each skipped link is reported.
5. Backups are not encrypted and may contain project secrets.
6. Cloud-only conversations or projects absent from the local Codex profile can
   only be synchronized by Codex through the user's account.
7. Format 2.4 records external project roots, permanent identities, the complete
   local Codex inventory, and backup lineage. Release 3.4.0 implements reviewed
   decisions for conversation conflicts, project conflicts, and destination-only
   projects, but it is still linear hand-off rather than concurrent cloud sync.
8. Successful replacement and explicit project removal may retain same-volume
   hidden project payloads referenced by the two newest valid recovery points.
   Visible archives are deliberately excluded from automatic cleanup. Invalid or
   incomplete recovery points are also retained for manual inspection, so failures
   can require explicit cleanup after diagnosis.
9. Phase 10.1 reports logical file sizes. Package-manager hardlinks or deduplicated
   files (for example a pnpm store plus `node_modules`) can use less physical space
   on the source disk, but a portable backup stores each visible file independently.
10. Selection is currently per complete project. Codex data is always included and
    individual dependency/cache subfolders are not silently removed. Excluding a
    project keeps its chats as projectless history, but its files are not recoverable
    from that backup and the original working directory may not exist after restore.
11. Version 3.4.0 is a public pre-release. Source, packaged-EXE, and extracted-ZIP
    automation passes on Windows 11, but real Windows 10, second-computer,
    USB-removal, and complete A-to-B-to-A evidence is still being collected.
