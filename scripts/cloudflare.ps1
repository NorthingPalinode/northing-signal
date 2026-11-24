param(
    [int]$Port = 8000,
    [string]$TunnelToken = $env:CLOUDFLARE_TUNNEL_TOKEN,
    [ValidateSet('http2', 'quic', 'auto')]
    [string]$Protocol = 'http2',
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
$tunnelProcess = $null
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
        # The server's output goes to log files, so a crash leaves its reason behind.
        $logDir = Join-Path $root '.local\logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $serverLog = Join-Path $logDir "cloudflare-server-$stamp.stderr.log"
        $serverProcess = Start-Process -FilePath $venvPython -ArgumentList $uvicornArgs -WorkingDirectory $root -PassThru -NoNewWindow `
            -RedirectStandardOutput (Join-Path $logDir "cloudflare-server-$stamp.stdout.log") -RedirectStandardError $serverLog
        $null = $serverProcess.Handle  # keeps ExitCode readable after the process ends
        Write-Host "Server log: $serverLog"
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            if ($serverProcess.HasExited) {
                throw "Northing Signal exited early with code $($serverProcess.ExitCode). See $serverLog"
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
        Write-Host "Starting Cloudflare Named Tunnel (fixed domain, protocol=$Protocol)... Press Ctrl+C to stop."
        $tunnelArgs = @('tunnel', '--no-autoupdate', '--protocol', $Protocol, 'run', '--token', $TunnelToken)
    } else {
        Write-Host "Starting Cloudflare Quick Tunnel -> http://127.0.0.1:$Port (protocol=$Protocol) ... Press Ctrl+C to stop."
        Write-Host 'A public https://*.trycloudflare.com URL will appear below.'
        $tunnelArgs = @('tunnel', '--no-autoupdate', '--protocol', $Protocol, '--url', "http://127.0.0.1:$Port")
    }
    $tunnelProcess = Start-Process -FilePath $cloudflared -ArgumentList $tunnelArgs -NoNewWindow -PassThru
    $null = $tunnelProcess.Handle

    # A tunnel in front of a stopped server only shows visitors errors: when the server goes,
    # the tunnel goes too, and the reason is in the server log.
    $failedChecks = 0
    while (-not $tunnelProcess.HasExited) {
        Start-Sleep -Seconds 5
        if ($serverProcess) {
            if ($serverProcess.HasExited) {
                throw "Northing Signal exited with code $($serverProcess.ExitCode); tunnel stopped. See $serverLog"
            }
        } elseif (Test-LocalHealth -TargetPort $Port) {
            $failedChecks = 0
        } elseif (++$failedChecks -ge 3) {
            throw "The reused Northing Signal on port $Port stopped answering; tunnel stopped."
        }
    }
    Write-Host "cloudflared exited with code $($tunnelProcess.ExitCode)."
} finally {
    foreach ($process in @($tunnelProcess, $serverProcess)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
