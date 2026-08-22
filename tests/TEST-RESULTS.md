# Test results 3.1.0

Date: August 22, 2026
Platform: Windows 11 build environment; target compatibility Windows 10/11 x64

## Automated end-to-end test

The same suite was executed against the source code and the standalone executable.
The executable test did not use an external Python runtime.

| Check | Result |
|---|---|
| Valid package structure and independent validation | Passed |
| Source files identical before and after backup | Passed |
| Source `auth.json` excluded | Passed |
| Exact `.git`, `.env` and uncommitted project files | Passed |
| Skills and portable Codex configuration restored | Passed |
| Different source and destination usernames translated | Passed |
| Older source to newer destination schema | Passed |
| Newer source fields to older destination schema | Passed |
| Existing destination project secured and replaced | Passed |
| Destination authentication unchanged | Passed |
| Damaged package rejected | Passed |
| Forced failure after database preparation | Rollback passed |
| Safety copy retained after successful restore | Passed |
| Four GUI operations in English and Dutch | Passed |
| Standalone executable starts without an immediate crash | Passed |

The synthetic fixture contains one database conversation, an active rollout, a
project with `.git` and `.env`, a skill, portable configuration, existing
destination data and two different destination database schemas.
