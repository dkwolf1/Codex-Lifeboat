[CmdletBinding()]
param(
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$testRoot = Join-Path $repoRoot ".build\selftest-$stamp"

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "The specified Python executable does not exist: $PythonPath"
        }
        & $PythonPath (Join-Path $repoRoot 'src\run_codex_transfer.py') --self-test --work $testRoot
    }
    else {
        py -3 (Join-Path $repoRoot 'src\run_codex_transfer.py') --self-test --work $testRoot
    }
    if ($LASTEXITCODE -ne 0) {
        throw "The self-test failed (exit code $LASTEXITCODE)."
    }
    Write-Host "Self-test passed. Result: $testRoot\self-test-result.json" -ForegroundColor Green
}
finally {
    Pop-Location
}
