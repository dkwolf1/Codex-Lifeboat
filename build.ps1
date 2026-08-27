[CmdletBinding()]
param(
    [string]$Version = '3.4.3',
    [string]$PythonPath,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildRoot = Join-Path $repoRoot '.build'
$venvRoot = Join-Path $buildRoot '.venv'
$python = if ($PythonPath) { $PythonPath } else { Join-Path $venvRoot 'Scripts\python.exe' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$releaseRoot = Join-Path $buildRoot "release-$stamp"
$distRoot = Join-Path $repoRoot 'dist'
$zipPath = Join-Path $distRoot 'Codex-Lifeboat-Windows-x64-Portable.zip'
$distExePath = Join-Path $distRoot 'Codex-Lifeboat.exe'

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version must use semantic x.y.z form: $Version"
}
$versionChecks = @(
    @{ Path = 'pyproject.toml'; Pattern = "version = `"$Version`"" },
    @{ Path = 'src\codex_transfer\__init__.py'; Pattern = "__version__ = `"$Version`"" },
    @{ Path = 'src\codex_transfer\backup.py'; Pattern = "GENERATOR_VERSION = `"$Version`"" },
    @{ Path = 'src\codex_transfer\restore.py'; Pattern = "RESTORE_VERSION = `"$Version`"" },
    @{ Path = 'version_info.txt'; Pattern = "StringStruct(u'ProductVersion', u'$Version')" }
)
foreach ($check in $versionChecks) {
    $checkPath = Join-Path $repoRoot $check.Path
    $content = Get-Content -LiteralPath $checkPath -Raw
    if (-not $content.Contains($check.Pattern)) {
        throw "Release version $Version does not match $($check.Path)."
    }
}
$releaseNotesPath = Join-Path $repoRoot "docs\releases\v$Version.md"
if (-not (Test-Path -LiteralPath $releaseNotesPath -PathType Leaf)) {
    throw "English release notes are missing: $releaseNotesPath"
}
$dutchReleaseNotesPath = Join-Path $repoRoot "docs\nl\releases\v$Version.md"
if (-not (Test-Path -LiteralPath $dutchReleaseNotesPath -PathType Leaf)) {
    throw "Dutch release notes are missing: $dutchReleaseNotesPath"
}

New-Item -ItemType Directory -Force -Path $buildRoot,$releaseRoot,$distRoot | Out-Null

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    if ($PythonPath) {
        throw "The specified Python executable does not exist: $PythonPath"
    }
    py -3 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the Python build environment. Install Python 3.11 or newer.'
    }
}

& $python -c "import PyInstaller; assert PyInstaller.__version__ == '6.22.2'"
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install --disable-pip-version-check -r (Join-Path $repoRoot 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
}

$env:PYTHONPATH = Join-Path $repoRoot 'src'
if (-not $SkipTests) {
    $selfTestRoot = Join-Path $buildRoot ("selftest-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    & $python (Join-Path $repoRoot 'src\run_codex_transfer.py') --self-test --work $selfTestRoot
    if ($LASTEXITCODE -ne 0) { throw 'The self-test failed; no release was built.' }
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name 'Codex-Lifeboat' `
    --version-file (Join-Path $repoRoot 'version_info.txt') `
    --paths (Join-Path $repoRoot 'src') `
    --distpath $releaseRoot `
    --workpath (Join-Path $buildRoot 'pyinstaller') `
    --specpath $buildRoot `
    (Join-Path $repoRoot 'src\run_codex_transfer.py')
if ($LASTEXITCODE -ne 0) { throw 'Building the Windows application failed.' }

$exePath = Join-Path $releaseRoot 'Codex-Lifeboat.exe'
if (-not $SkipTests) {
    $packagedSelfTestRoot = Join-Path $buildRoot ("packaged-selftest-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $packagedProcess = Start-Process `
        -FilePath $exePath `
        -ArgumentList @('--self-test', '--work', ('"{0}"' -f $packagedSelfTestRoot)) `
        -Wait `
        -PassThru `
        -WindowStyle Hidden
    $packagedResultPath = Join-Path $packagedSelfTestRoot 'self-test-result.json'
    if (-not (Test-Path -LiteralPath $packagedResultPath -PathType Leaf)) {
        throw 'The packaged executable did not produce a self-test result; no release was built.'
    }
    $packagedResult = Get-Content -LiteralPath $packagedResultPath -Raw | ConvertFrom-Json
    if ($packagedProcess.ExitCode -ne 0 -or -not $packagedResult.passed) {
        $failedChecks = @(
            $packagedResult.checks.PSObject.Properties |
                Where-Object { -not $_.Value } |
                ForEach-Object { $_.Name }
        ) -join ', '
        throw "The packaged executable failed its self-test: $failedChecks"
    }
    $packagedMatrix = $packagedResult.phase11Matrix
    if (-not $packagedMatrix -or $packagedMatrix.automatedPassed -ne $packagedMatrix.automatedTotal) {
        throw 'The packaged executable failed the Phase 11 compatibility matrix.'
    }
}

Copy-Item -LiteralPath (Join-Path $repoRoot 'README.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\nl\README.md') -Destination (Join-Path $releaseRoot 'LEESMIJ.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\KNOWN-LIMITATIONS.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\nl\KNOWN-LIMITATIONS.md') -Destination (Join-Path $releaseRoot 'BEKENDE-GRENZEN.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\TESTING-GUIDE.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\nl\TESTHANDLEIDING.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath $releaseNotesPath -Destination (Join-Path $releaseRoot 'RELEASE-NOTES.md') -Force
Copy-Item -LiteralPath $dutchReleaseNotesPath -Destination (Join-Path $releaseRoot 'RELEASE-NOTES-NL.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\RELEASE-CHECKLIST.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs\nl\RELEASE-CHECKLIST.md') -Destination (Join-Path $releaseRoot 'RELEASE-CHECKLIST-NL.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'LICENSE') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'SECURITY.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'THIRD-PARTY-NOTICES.txt') -Destination $releaseRoot -Force

$exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
Set-Content -LiteralPath (Join-Path $releaseRoot 'SHA256.txt') -Encoding ascii -Value "$exeHash  Codex-Lifeboat.exe"
Copy-Item -LiteralPath $exePath -Destination $distExePath -Force

if (Test-Path -LiteralPath $zipPath -PathType Leaf) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $releaseRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
Set-Content -LiteralPath (Join-Path $distRoot 'SHA256.txt') -Encoding ascii -Value @(
    "$exeHash  $(Split-Path -Leaf $distExePath)"
    "$zipHash  $(Split-Path -Leaf $zipPath)"
)

if ($SkipTests) {
    Write-Host "Build completed without tests: $zipPath" -ForegroundColor Yellow
} else {
    Write-Host "Build and tests passed: $zipPath" -ForegroundColor Green
}
Write-Host "SHA-256: $zipHash"
