[CmdletBinding()]
param(
    [string]$ConfigPath,
    [string]$DestinationRoot,
    [string]$SourceProfile,
    [string]$SourceCodexHome,
    [switch]$AllowRunningTest
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$helper = Join-Path $scriptRoot 'tools\backup_codex.py'
if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    # In een back-uppakket staan de helpers naast dit script in tools.
    $helper = Join-Path $scriptRoot 'backup_codex.py'
}
if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    throw "Python-helper niet gevonden: backup_codex.py"
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
$usePyLauncher = $false
if (-not $python) {
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    $usePyLauncher = $true
}
if (-not $python) {
    throw 'Python 3 is niet gevonden. Installeer Python 3 en probeer opnieuw.'
}

$pythonArgs = @()
if ($usePyLauncher) { $pythonArgs += '-3' }
$pythonArgs += $helper
if ($ConfigPath) { $pythonArgs += @('--config', $ConfigPath) }
if ($DestinationRoot) { $pythonArgs += @('--destination', $DestinationRoot) }
if ($SourceProfile) { $pythonArgs += @('--source-profile', $SourceProfile) }
if ($SourceCodexHome) { $pythonArgs += @('--source-codex-home', $SourceCodexHome) }
if ($AllowRunningTest) { $pythonArgs += '--allow-running-test' }

Write-Host ''
Write-Host 'Codex Portable Backup 2.0' -ForegroundColor Cyan
Write-Host 'De bron wordt alleen gelezen. Een tijdelijke .building-map blijft bij fouten bewaard.'
Write-Host ''

& $python.Source @pythonArgs
$result = $LASTEXITCODE
if ($result -ne 0) {
    throw "Back-upgenerator is mislukt (code $result). Lees de getoonde fout en backup-error.txt."
}
