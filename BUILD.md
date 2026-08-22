# Build and test

Developer requirements: Windows 10/11 and Python 3.11 or newer. The pinned
PyInstaller version is installed automatically in a repository-local virtual
environment.

## Run the end-to-end self-test

```powershell
.\test.ps1
```

## Build the complete portable release

```powershell
.\build.ps1
```

The build script runs the complete self-test before creating any release. It then
builds the standalone `.exe`, creates a portable zip and writes SHA-256 checksums.
Temporary files are stored under `.build`. The two files intended for a GitHub
Release are written to `dist`:

```text
dist/
├── Codex-Lifeboat-Windows-x64-Portable.zip
└── SHA256.txt
```

Both directories are ignored by Git. Release binaries must be attached to a
GitHub Release and must not be committed to the repository.

End users do not need Python, PyInstaller, an installer or administrator rights.
