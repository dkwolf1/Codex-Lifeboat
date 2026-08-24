# Contributing

Bug reports, compatibility findings, documentation improvements and tested code
changes are welcome.

## Before opening an issue

1. Read `docs/KNOWN-LIMITATIONS.md` and `SECURITY.md`.
2. Confirm that Codex was fully closed during backup or restore.
3. Run `test-phase11.ps1` when a development environment is available.
4. Remove usernames, project contents, API keys and authentication data from logs.

## Pull requests

Keep changes focused, add or update tests, preserve both English and Dutch GUI
behavior, and run `test-phase11.ps1` before submitting. `test.ps1` remains the
shorter source-suite entry point. English is the primary project language;
user-facing Dutch translations should remain available and accurate.

Never commit real Codex backup packages, `auth.json`, personal databases, `.env`
files from actual projects or machine-specific recovery reports.

Compatibility testers can follow `docs/TESTING-GUIDE.md` and use the structured
**Compatibility test result** issue form. Successful tests are welcome; sanitize
all paths, screenshots, and logs before submitting them.
