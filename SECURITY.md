# Security policy

## Supported versions

Security updates are provided for the latest published release of Codex Lifeboat.
Older releases should be upgraded before reporting a problem.

## Reporting a vulnerability

Do not disclose suspected vulnerabilities in a public issue. Use GitHub's private
vulnerability reporting feature for this repository. Include the affected version,
Windows version, impact, reproduction steps, and a minimal example containing no
real credentials, conversations, or project data.

If private vulnerability reporting is temporarily unavailable, open a public issue
that only asks the maintainer to establish private contact. Do not include technical
details of the vulnerability in that issue.

## Backup data

Backup packages are not encrypted. They may contain source code, `.env` files,
API keys, and other confidential project files. Keep backup media secure and do not
share a package without reviewing its contents.

Codex Lifeboat deliberately does not transfer `auth.json`, installation IDs,
sandbox secrets, locks, or active runtime files. Restoration preserves the
destination computer's local identity and authentication.

Never publish a real backup package in this repository. Development and tests must
use synthetic data only.
