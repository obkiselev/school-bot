param(
    [string]$LmStudioUrl = "http://127.0.0.1:1234/v1/models",
    [string]$LocalBridgeUrl = "http://127.0.0.1:8787/v1/models",
    [string]$ServerHost = "45.152.113.91",
    [int]$ServerPort = 4422,
    [string]$ServerUser = "school_bot",
    [string]$ServerTunnelUrl = "http://127.0.0.1:12340/v1/models",
    [string]$ServerEnvPath = "/opt/school_bot/.env",
    [string]$BridgeToken = "",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519_rag",
    [switch]$CheckServer = $true
)

$ErrorActionPreference = "Stop"

function Resolve-BridgeToken {
    param([string]$Explicit)
    if ($Explicit) { return $Explicit }
    if ($env:LLM_BRIDGE_TOKEN) { return $env:LLM_BRIDGE_TOKEN }
    if ($env:LLM_API_KEY) { return $env:LLM_API_KEY }
    return ""
}

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Token = ""
    )
    $headers = @{}
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }

    try {
        $resp = Invoke-WebRequest -Uri $Url -Method Get -Headers $headers -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        [PSCustomObject]@{
            Name = $Name
            Ok = $true
            Detail = "HTTP $($resp.StatusCode)"
        }
    } catch {
        $status = ""
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = "HTTP " + [int]$_.Exception.Response.StatusCode
        }
        $msg = if ($status) { $status } else { $_.Exception.Message }
        [PSCustomObject]@{
            Name = $Name
            Ok = $false
            Detail = $msg
        }
    }
}

function Resolve-SshExe {
    $candidates = @(
        "$env:WINDIR\System32\OpenSSH\ssh.exe",
        "E:\Progs\Git\usr\bin\ssh.exe",
        "D:\Programs\Git\usr\bin\ssh.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return "ssh"
}

function Test-Server {
    param(
        [string]$SshExe,
        [string]$ServerHost,
        [int]$Port,
        [string]$User,
        [string]$Key,
        [string]$TunnelUrl,
        [string]$Token,
        [string]$EnvPath
    )

    if (-not (Test-Path $Key)) {
        return [PSCustomObject]@{
            Name = "Server checks"
            Ok = $false
            Detail = "SSH key not found: $Key"
        }
    }

    $remote = "$User@$ServerHost"
    $authHeader = if ($Token) { "-H 'Authorization: Bearer $Token'" } else { "" }
    $cmd = @(
        "set -e",
        "echo 'ENV:'",
        "grep -E '^(LLM_BRIDGE_URL|LLM_BASE_URL|LLM_API_KEY|LLM_FALLBACK_ENABLED)=' $EnvPath || true",
        "echo 'TUNNEL:'",
        "curl -s -o /dev/null -w '%{http_code}' $authHeader '$TunnelUrl' || true"
    ) -join "; "

    try {
        $output = & $SshExe -i $Key -p $Port -o StrictHostKeyChecking=no $remote $cmd 2>&1
        $outText = ($output | Out-String).Trim()
        $tunnelLine = ($outText -split "`r?`n" | Select-Object -Last 1).Trim()
        $ok = $tunnelLine -eq "200"
        $detail = if ($ok) { "Tunnel endpoint HTTP 200" } else { "Tunnel endpoint status: $tunnelLine" }
        [PSCustomObject]@{
            Name = "Server checks"
            Ok = $ok
            Detail = "$detail`n$outText"
        }
    } catch {
        [PSCustomObject]@{
            Name = "Server checks"
            Ok = $false
            Detail = $_.Exception.Message
        }
    }
}

$token = Resolve-BridgeToken -Explicit $BridgeToken
$results = @()

$results += Test-Endpoint -Name "LM Studio local" -Url $LmStudioUrl
$results += Test-Endpoint -Name "Bridge local" -Url $LocalBridgeUrl -Token $token

if ($CheckServer) {
    $sshExe = Resolve-SshExe
    $results += Test-Server `
        -SshExe $sshExe `
        -ServerHost $ServerHost `
        -Port $ServerPort `
        -User $ServerUser `
        -Key $KeyPath `
        -TunnelUrl $ServerTunnelUrl `
        -Token $token `
        -EnvPath $ServerEnvPath
}

Write-Host ""
Write-Host "LLM stack check"
Write-Host "==============="
foreach ($item in $results) {
    $mark = if ($item.Ok) { "[OK]" } else { "[FAIL]" }
    Write-Host "$mark $($item.Name): $($item.Detail)"
}

$failed = ($results | Where-Object { -not $_.Ok }).Count
if ($failed -gt 0) {
    Write-Host ""
    Write-Host "Action hints:"
    Write-Host "1) Start LM Studio server on 127.0.0.1:1234."
    Write-Host "2) Start llm_bridge with the same token."
    Write-Host "3) Start reverse tunnel: work/start-llm-reverse-tunnel.ps1."
    Write-Host "4) Ensure VPS .env has LLM_BRIDGE_URL=http://127.0.0.1:12340/v1 and LLM_API_KEY=<token>."
    exit 1
}

Write-Host ""
Write-Host "All checks passed."
exit 0
