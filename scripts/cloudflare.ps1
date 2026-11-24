param(
    [int]$Port = 8000,
    [string]$TunnelToken = $env:CLOUDFLARE_TUNNEL_TOKEN,
    [switch]$Rebuild,
    [switch]$AllowNoAuth
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

function Resolve-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles 'cloudflared\cloudflared.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'cloudflared\cloudflared.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\cloudflared.exe')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    throw 'cloudflared was not found. Install it first: winget install --id Cloudflare.cloudflared'
}

function Test-LocalHealth([int]$TargetPort) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$TargetPort/api/health" -UseBasicParsing -TimeoutSec 2
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

Push-Location $root
$serverProcess = $null
try {
    $cloudflared = Resolve-Cloudflared

    if (-not $AllowNoAuth) {
        $authValue = $env:READER_AUTH
        if (-not $authValue -and (Test-Path -LiteralPath '.env')) {
            foreach ($line in Get-Content -LiteralPath '.env') {
                if ($line -match '^\s*READER_AUTH\s*=\s*(.+?)\s*$') {
                    $authValue = $Matches[1].Trim().Trim('"').Trim("'")
                }
            }
        }
        if ($authValue -and $authValue.ToLowerInvariant() -eq 'off') {
            throw 'READER_AUTH=off disables sign-in. Set READER_AUTH=token before exposing over Cloudflare Tunnel (or pass -AllowNoAuth explicitly).'
        }
    }

    if ($Rebuild -or -not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw 'Virtual environment is missing. Run scripts/start.ps1 once first to initialize dependencies.'
        }
        $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
        Push-Location frontend
        try {
            & $npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }

    if (-not (Test-LocalHealth -TargetPort $Port)) {
        Write-Host "Starting Northing Signal on http://127.0.0.1:$Port ..."
        $uvicornArgs = @(
            '-m', 'uvicorn', 'northing_signal.briefing.app:create_app',
            '--factory', '--app-dir', 'backend',
            '--host', '127.0.0.1', '--port', "$Port",
            '--proxy-headers', '--forwarded-allow-ips', '127.0.0.1,::1'
        )
        $serverProcess = Start-Process -FilePath $venvPython -ArgumentList $uvicornArgs -WorkingDirectory $root -PassThru -NoNewWindow
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            if ($serverProcess.HasExited) {
                throw "Northing Signal exited early with code $($serverProcess.ExitCode)."
            }
            if (Test-LocalHealth -TargetPort $Port) {
                $ready = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) {
            throw "Northing Signal did not become healthy on http://127.0.0.1:$Port within 20 seconds."
        }
        Write-Host "Northing Signal is ready on http://127.0.0.1:$Port"
    } else {
        Write-Host "Reusing existing Northing Signal instance on http://127.0.0.1:$Port"
    }

    if ($TunnelToken) {
        Write-Host 'Starting Cloudflare Named Tunnel (fixed domain)... Press Ctrl+C to stop.'
        & $cloudflared tunnel --no-autoupdate run --token $TunnelToken
    } else {
        Write-Host "Starting Cloudflare Quick Tunnel -> http://127.0.0.1:$Port ... Press Ctrl+C to stop."
        Write-Host 'A public https://*.trycloudflare.com URL will appear below.'
        & $cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$Port"
    }
} finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
