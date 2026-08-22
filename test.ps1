[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$testRoot = Join-Path $repoRoot ".build\selftest-$stamp"

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    py -3 (Join-Path $repoRoot 'src\run_codex_transfer.py') --self-test --work $testRoot
    if ($LASTEXITCODE -ne 0) {
        throw "De zelftest is mislukt (exitcode $LASTEXITCODE)."
    }
    Write-Host "Zelftest geslaagd. Resultaat: $testRoot\self-test-result.json" -ForegroundColor Green
}
finally {
    Pop-Location
}
