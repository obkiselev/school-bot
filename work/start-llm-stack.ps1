param(
    [string]$BridgeToken = "sbot_WLVXqU8MkosRy3S5p1ZY9uNgrDTQefmt",
    [string]$UpstreamBaseUrl = "http://127.0.0.1:1234",
    [string]$BridgeHost = "127.0.0.1",
    [int]$BridgePort = 8787,
    [int]$WarmupSeconds = 4
)

$ErrorActionPreference = "Stop"

function Test-Endpoint {
    param(
        [string]$Url,
        [string]$Token = ""
    )
    $headers = @{}
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }

    try {
        $resp = Invoke-WebRequest -Uri $Url -Method Get -Headers $headers -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        return $false
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Split-Path -Parent $scriptDir
$bridgeModelsUrl = "http://$BridgeHost`:$BridgePort/v1/models"
$lmModelsUrl = "$UpstreamBaseUrl/v1/models"

Write-Host "LLM stack bootstrap"
Write-Host "==================="
Write-Host "Repo: $repoDir"
Write-Host "Token: $BridgeToken"
Write-Host ""

if (-not (Test-Endpoint -Url $lmModelsUrl)) {
    Write-Warning "LM Studio endpoint is not reachable at $lmModelsUrl."
    Write-Warning "Open LM Studio and start local server first."
} else {
    Write-Host "[OK] LM Studio endpoint reachable: $lmModelsUrl"
}

# Start bridge only if it is not already healthy with current token.
if (-not (Test-Endpoint -Url $bridgeModelsUrl -Token $BridgeToken)) {
    Write-Host "Starting local llm_bridge in a new window..."
    $bridgeCmd = @(
        "$env:LLM_BRIDGE_TOKEN='$BridgeToken'",
        "$env:LLM_UPSTREAM_BASE_URL='$UpstreamBaseUrl'",
        "$env:LLM_BRIDGE_HOST='$BridgeHost'",
        "$env:LLM_BRIDGE_PORT='$BridgePort'",
        "Set-Location '$repoDir'",
        "python -m llm_bridge.server"
    ) -join "; "
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $bridgeCmd | Out-Null
} else {
    Write-Host "[OK] Local llm_bridge already running with this token."
}

Write-Host "Starting reverse tunnel in a new window..."
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptDir\start-llm-reverse-tunnel.ps1`"" | Out-Null

Write-Host "Waiting $WarmupSeconds seconds before health check..."
Start-Sleep -Seconds $WarmupSeconds

Write-Host ""
Write-Host "Running LLM stack check..."
& "$scriptDir\check-llm-stack.ps1" -BridgeToken $BridgeToken
$checkCode = $LASTEXITCODE

Write-Host ""
if ($checkCode -eq 0) {
    Write-Host "[READY] LLM stack is up."
} else {
    Write-Warning "[NOT READY] Check failed. See output above."
}

exit $checkCode
