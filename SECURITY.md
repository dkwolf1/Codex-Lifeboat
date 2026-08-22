# Security

Backup packages are not encrypted. They may contain source code, `.env` files,
API keys and other confidential project files. Keep the USB drive secure and do
not share a backup package without reviewing its contents.

The application deliberately does not transfer `auth.json`, installation IDs,
sandbox secrets, locks or active runtime files to another computer. Restoration
preserves the destination computer's local identity and authentication.

Never publish a real backup package in this Git repository. Use synthetic data,
as the included self-test does, for development and testing.
