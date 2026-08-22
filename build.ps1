[CmdletBinding()]
param(
    [string]$Version = '3.0.0',
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildRoot = Join-Path $repoRoot '.build'
$venvRoot = Join-Path $buildRoot '.venv'
$python = if ($PythonPath) { $PythonPath } else { Join-Path $venvRoot 'Scripts\python.exe' }
$releaseRoot = Join-Path $repoRoot 'release'
$versionReleaseRoot = Join-Path $repoRoot "releases\$Version"
$zipPath = Join-Path $versionReleaseRoot "Codex-Transfer-Assistant-$Version-Windows-x64-Portable.zip"

New-Item -ItemType Directory -Force -Path $buildRoot,$releaseRoot,$versionReleaseRoot | Out-Null

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    if ($PythonPath) {
        throw "The specified Python executable does not exist: $PythonPath"
    }
    py -3 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the Python build environment. Install Python 3.11 or newer.'
    }
}

& $python -c 'import PyInstaller; assert PyInstaller.__version__ == "6.22.2"'
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install --disable-pip-version-check -r (Join-Path $repoRoot 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
}

$env:PYTHONPATH = Join-Path $repoRoot 'src'
$selfTestRoot = Join-Path $buildRoot ("selftest-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $python (Join-Path $repoRoot 'src\run_codex_transfer.py') --self-test --work $selfTestRoot
if ($LASTEXITCODE -ne 0) { throw 'The self-test failed; no release was built.' }

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name 'Codex-Transfer-Assistant' `
    --version-file (Join-Path $repoRoot 'version_info.txt') `
    --paths (Join-Path $repoRoot 'src') `
    --distpath $releaseRoot `
    --workpath (Join-Path $buildRoot 'pyinstaller') `
    --specpath $buildRoot `
    (Join-Path $repoRoot 'src\run_codex_transfer.py')
if ($LASTEXITCODE -ne 0) { throw 'Building the Windows application failed.' }

Copy-Item -LiteralPath (Join-Path $repoRoot 'README.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'README-NL.md') -Destination (Join-Path $releaseRoot 'LEESMIJ.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'KNOWN-LIMITATIONS.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'KNOWN-LIMITATIONS-NL.md') -Destination (Join-Path $releaseRoot 'BEKENDE-GRENZEN.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'THIRD-PARTY-NOTICES.txt') -Destination $releaseRoot -Force

$exePath = Join-Path $releaseRoot 'Codex-Transfer-Assistant.exe'
$exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
Set-Content -LiteralPath (Join-Path $releaseRoot 'SHA256.txt') -Encoding ascii -Value "$exeHash  Codex-Transfer-Assistant.exe"

if (Test-Path -LiteralPath $zipPath -PathType Leaf) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $releaseRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
Set-Content -LiteralPath (Join-Path $versionReleaseRoot 'SHA256.txt') -Encoding ascii -Value "$zipHash  $(Split-Path -Leaf $zipPath)"

Write-Host "Build and tests passed: $zipPath" -ForegroundColor Green
Write-Host "SHA-256: $zipHash"
