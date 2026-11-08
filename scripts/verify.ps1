param([switch]$Legacy)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
Push-Location $taskRoot
try {
    $env:PYTHONUTF8 = '1'
    & $taskPython -m ruff check backend tests_reader
    if ($LASTEXITCODE -ne 0) { throw 'Static checks failed' }
    & $taskPython -m pytest -q --basetemp .tmp/reader-check
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    if ($Legacy) {
        & $taskPython -m pytest -q tests --basetemp .tmp/legacy-check
        if ($LASTEXITCODE -ne 0) { throw 'Historical suite failed; see its original acceptance scope.' }
        & $taskPython evals/run_baseline.py
        if ($LASTEXITCODE -ne 0) { throw 'Legacy lexical seed evaluation failed' }
    }
    Push-Location frontend
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
} finally { Pop-Location }
