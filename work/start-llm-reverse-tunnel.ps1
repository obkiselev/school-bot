param(
    [string]$ServerHost = "45.152.113.91",
    [int]$ServerPort = 4422,
    [string]$ServerUser = "school_bot",
    [int]$ServerBindPort = 12340,
    [Alias("LocalLmPort")]
    [int]$LocalBridgePort = 8787,
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519_rag",
    [switch]$Once
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

$sshExe = "$env:WINDIR\System32\OpenSSH\ssh.exe"
if (-not (Test-Path $sshExe)) {
    $sshExe = "ssh"
}

$sshArgs = @(
    "-N",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-i", $KeyPath,
    "-p", "$ServerPort",
    "-R", "127.0.0.1:$ServerBindPort`:127.0.0.1:$LocalBridgePort",
    "$ServerUser@$ServerHost"
)

Write-Host "Starting reverse tunnel: server 127.0.0.1:$ServerBindPort -> local bridge 127.0.0.1:$LocalBridgePort"
Write-Host "SSH key: $KeyPath"

if ($Once) {
    & $sshExe @sshArgs
    exit $LASTEXITCODE
}

while ($true) {
    & $sshExe @sshArgs
    $code = $LASTEXITCODE
    Write-Warning "Tunnel exited with code $code. Reconnecting in 5 seconds..."
    Start-Sleep -Seconds 5
}
