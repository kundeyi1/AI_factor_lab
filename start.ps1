param(
    [int]$Port = 8010,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Url = "http://127.0.0.1:$Port/"
$OutLog = Join-Path $ProjectRoot "server.out.log"
$ErrLog = Join-Path $ProjectRoot "server.err.log"

function Test-AppReady {
    param([string]$TargetUrl)
    try {
        $response = Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-AppReady $Url)) {
    Write-Host "Starting AI Factor Lab at $Url ..."
    Start-Process `
        -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -WindowStyle Hidden | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-AppReady $Url) {
            $ready = $true
            break
        }
    }

    if (-not $ready) {
        Write-Host "Startup failed. See logs:"
        Write-Host "  $ErrLog"
        Write-Host "  $OutLog"
        exit 1
    }
} else {
    Write-Host "AI Factor Lab is already running at $Url"
}

if (-not $NoBrowser) {
    Start-Process $Url
}

Write-Host "Ready: $Url"
