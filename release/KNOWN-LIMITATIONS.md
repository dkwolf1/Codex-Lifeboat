# Known limitations of release 3.0.0

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
