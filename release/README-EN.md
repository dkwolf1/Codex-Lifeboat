# Codex Transfer Assistant 3.0

A self-contained bilingual Windows 10/11 application for complete Codex backups,
read-only backup validation, functional 1-to-1 restoration and final verification.

## Source computer

1. Fully close Codex.
2. Insert the USB drive.
3. Start `Codex-Overzetassistent.exe`.
4. Select **Create complete backup** and then **Verify backup**.

## New computer

1. Install Codex, open it once and sign in.
2. Fully close Codex.
3. Start the assistant from the USB drive.
4. Select **Complete restore**.
5. The app creates a local safety copy before asking permission to replace data.
6. Select **Verify restore** when finished.

The package includes project files (including `.git` and `.env`), local chats,
archives, available attachments, skills and portable configuration. Authentication
and machine identity remain local to the destination computer.

The backup is intentionally not encrypted. Keep the USB drive physically secure.
This unsigned test release may trigger Windows SmartScreen; verify its SHA-256
before choosing **More info** → **Run anyway**.

This is an independent migration utility and not an official OpenAI product.
