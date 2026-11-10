$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
Push-Location $taskRoot
try {
    $env:PYTHONUTF8 = '1'
    & $taskPython -m ruff check backend tests_reader
    if ($LASTEXITCODE -ne 0) { throw 'Static checks failed' }
    New-Item -ItemType Directory -Path (Join-Path $taskRoot '.tmp') -Force | Out-Null
    & $taskPython -m pytest -q --basetemp .tmp/reader-check
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    Push-Location frontend
    try {
        & npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
} finally { Pop-Location }
