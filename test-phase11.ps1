[CmdletBinding()]
param(
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $repoRoot 'test.ps1') -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) {
    throw "The base self-test failed."
}

$resultFile = Get-ChildItem -LiteralPath (Join-Path $repoRoot '.build') -Directory |
    Where-Object Name -Like 'selftest-*' |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1 |
    ForEach-Object { Join-Path $_.FullName 'self-test-result.json' }

if (-not $resultFile -or -not (Test-Path -LiteralPath $resultFile -PathType Leaf)) {
    throw "The Phase 11 matrix result could not be found."
}

$result = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json
$matrix = $result.phase11Matrix
if (-not $matrix) {
    throw "The self-test did not produce a Phase 11 matrix."
}
if ($matrix.automatedPassed -ne $matrix.automatedTotal) {
    $failed = $matrix.automated | Where-Object status -Ne 'passed'
    $failed | Format-Table id, status, failedChecks -AutoSize
    throw "Phase 11 automated compatibility matrix failed."
}

Write-Host "Phase 11 automated matrix passed: $($matrix.automatedPassed)/$($matrix.automatedTotal) scenarios." -ForegroundColor Green
Write-Host "Manual real-device scenarios still pending: $($matrix.manual.Count)."
Write-Host "Evidence: $resultFile"
