[CmdletBinding()]
param(
    [string]$BackupPath,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$helper = Join-Path $scriptRoot 'tools\validate_backup.py'
if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    $helper = Join-Path $scriptRoot 'validate_backup.py'
}
if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    throw 'Onafhankelijke Python-validator niet gevonden: validate_backup.py'
}

if (-not $BackupPath) {
    $BackupPath = Read-Host 'Volledig pad van de Codex-PortableBackup-map'
}
$BackupPath = $BackupPath.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $BackupPath -PathType Container)) {
    throw "Back-upmap niet gevonden: $BackupPath"
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
$pythonArgs += @($helper, $BackupPath)
if ($Json) { $pythonArgs += '--json' }

& $python.Source @pythonArgs
$result = $LASTEXITCODE
if ($result -ne 0) {
    throw "De back-up is ongeldig of beschadigd (validatorcode $result)."
}
