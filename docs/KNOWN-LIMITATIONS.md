# Known limitations

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
   local Codex inventory, and backup lineage. Release 3.4.4 implements reviewed
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
10. Selection is per complete project. Codex data is always included. Inaccessible
    paths below `.chatgpt-projects/**/work/_deps` are excluded only after a complete
    read-only preflight displays the exact set and the user explicitly approves it.
    Any path outside that dependency boundary, any changed set, and any unclassified
    error remains fatal. Excluded dependency payload must be reconstructed by Codex
    or the relevant package manager after restore.
11. Git conflict explanations require a readable Git worktree and the Git executable.
    When either side or the required history is unavailable, Lifeboat reports
    insufficient evidence and falls back to its complete file hashes and explicit
    conflict choices. It never fetches missing history.
12. Automatic chat continuation is intentionally limited to a strict proof: the
    existing non-empty destination rollout and all relevant metadata must exactly
    equal the beginning of the longer backup rollout after portable path
    normalization. Edited records, changed metadata, malformed JSONL, an empty
    rollout, destination-ahead history, and arbitrary divergence require an
    explicit user decision. Lifeboat does not perform a general-purpose chat merge.
13. Version 3.4.11 is stable after automated source/EXE/ZIP testing and a successful
    physical Windows 11 A-to-B-to-A hand-off. A physical Windows 10 run and removal
    of a real USB drive during an active write are not yet documented.
14. Restore is transactional with automatic rollback but is not yet a general
    resumable file-copy engine. Very large restores can take substantial time.
    Version 3.4.11 conservatively accounts for logical bytes, estimated allocation
    overhead and a safety reserve, and rechecks free space during large writes;
    another process can still consume space unexpectedly.
15. The backup omits entries with reserved Windows device names. Review the
    warnings in the backup report for the omitted paths.
