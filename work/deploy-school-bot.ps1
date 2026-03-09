param(
    [string]$ServerHost = "45.152.113.91",
    [int]$ServerPort = 4422,
    [string]$ServerUser = "school_bot",
    [string]$ServerAppDir = "/opt/school_bot",
    [string]$ServiceName = "school_bot",
    [string]$KeyPath = "",
    [string]$SourceDir = "",
    [string]$ArchivePath = "$env:TEMP\school_bot.tar.gz",
    [switch]$SkipPipInstall
)

$ErrorActionPreference = "Stop"

function Resolve-SourceDir {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        return $ExplicitPath
    }
    return (Split-Path -Parent $PSScriptRoot)
}

function Resolve-KeyPath {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        return $ExplicitPath
    }

    $candidates = @(
        "C:\Users\Oleg\.ssh\id_ed25519_rag",
        "C:\Users\Олег\.ssh\id_ed25519_rag",
        "$env:USERPROFILE\.ssh\id_ed25519_rag"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    throw "SSH key not found. Pass -KeyPath explicitly."
}

function Resolve-SshTools {
    $gitSshCandidates = @(
        "E:\Progs\Git\usr\bin\ssh.exe",
        "D:\Programs\Git\usr\bin\ssh.exe"
    )
    $gitScpCandidates = @(
        "E:\Progs\Git\usr\bin\scp.exe",
        "D:\Programs\Git\usr\bin\scp.exe"
    )

    for ($i = 0; $i -lt $gitSshCandidates.Count; $i++) {
        if ((Test-Path $gitSshCandidates[$i]) -and (Test-Path $gitScpCandidates[$i])) {
            return @{
                ssh = $gitSshCandidates[$i]
                scp = $gitScpCandidates[$i]
                useNullKnownHosts = $true
            }
        }
    }

    return @{
        ssh = "$env:WINDIR\System32\OpenSSH\ssh.exe"
        scp = "$env:WINDIR\System32\OpenSSH\scp.exe"
        useNullKnownHosts = $false
    }
}

function Build-SshArgs {
    param(
        [string]$Key,
        [int]$Port,
        [bool]$UseNullKnownHosts
    )

    $args = @(
        "-i", $Key,
        "-p", "$Port",
        "-o", "StrictHostKeyChecking=no"
    )

    if ($UseNullKnownHosts) {
        $args += @("-o", "UserKnownHostsFile=/dev/null")
    }

    return $args
}

function Build-ScpArgs {
    param(
        [string]$Key,
        [int]$Port,
        [bool]$UseNullKnownHosts
    )

    $args = @(
        "-i", $Key,
        "-P", "$Port",
        "-o", "StrictHostKeyChecking=no"
    )

    if ($UseNullKnownHosts) {
        $args += @("-o", "UserKnownHostsFile=/dev/null")
    }

    return $args
}

$resolvedSourceDir = Resolve-SourceDir -ExplicitPath $SourceDir
$resolvedKeyPath = Resolve-KeyPath -ExplicitPath $KeyPath
$tools = Resolve-SshTools

if (-not (Test-Path (Join-Path $resolvedSourceDir "bot.py"))) {
    throw "Source directory must contain bot.py: $resolvedSourceDir"
}

Write-Host "Source: $resolvedSourceDir"
Write-Host ("Server: {0}@{1}:{2}" -f $ServerUser, $ServerHost, $ServerPort)
Write-Host "App dir: $ServerAppDir"
Write-Host "SSH exe: $($tools.ssh)"
Write-Host "SCP exe: $($tools.scp)"
Write-Host "Key: $resolvedKeyPath"
Write-Host "Archive: $ArchivePath"

if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}

tar -czf $ArchivePath `
    --exclude=venv `
    --exclude=data `
    --exclude=.git `
    --exclude=.env `
    --exclude=.env.* `
    --exclude=__pycache__ `
    -C $resolvedSourceDir .

if (-not (Test-Path $ArchivePath)) {
    throw "Failed to create archive: $ArchivePath"
}

$sshArgs = Build-SshArgs -Key $resolvedKeyPath -Port $ServerPort -UseNullKnownHosts:$tools.useNullKnownHosts
$scpArgs = Build-ScpArgs -Key $resolvedKeyPath -Port $ServerPort -UseNullKnownHosts:$tools.useNullKnownHosts
$remote = "$ServerUser@$ServerHost"
$remoteArchive = "/tmp/school_bot.tar.gz"

Write-Host "Uploading archive..."
& $tools.scp @scpArgs $ArchivePath "$remote`:$remoteArchive"
if ($LASTEXITCODE -ne 0) {
    throw "SCP upload failed with code $LASTEXITCODE"
}

$skipPip = if ($SkipPipInstall) { "1" } else { "0" }
$remoteScript = @"
set -e
cd $ServerAppDir
tar -xzf $remoteArchive
if [ "$skipPip" = "0" ]; then
  venv/bin/pip install -r requirements.txt
fi
if sudo -n true >/dev/null 2>&1; then
  sudo systemctl restart $ServiceName
else
  pkill -f '$ServerAppDir/venv/bin/python bot.py' || true
fi

# Wait for service to settle to active (avoid false negatives on "activating")
state=""
for i in `$(seq 1 30); do
  state=`$(systemctl is-active $ServiceName || true)
  if [ "`$state" = "active" ]; then
    break
  fi
  if [ "`$state" = "failed" ]; then
    break
  fi
  sleep 1
done

if [ "`$state" != "active" ]; then
  echo "Service state after restart: `$state"
  systemctl status $ServiceName --no-pager -l || true
  journalctl -u $ServiceName -n 60 --no-pager || true
  exit 1
fi

systemctl is-active $ServiceName
systemctl status $ServiceName --no-pager -l
"@
$remoteScript = $remoteScript -replace "`r", ""

Write-Host "Deploying on server..."
$escapedArgs = @($sshArgs + @($remote, "bash -s")) | ForEach-Object {
    if ($_ -match '[\s"]') {
        '"' + ($_ -replace '"', '\"') + '"'
    } else {
        $_
    }
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $tools.ssh
$psi.Arguments = ($escapedArgs -join " ")
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError = $false

$proc = [System.Diagnostics.Process]::Start($psi)
$proc.StandardInput.Write($remoteScript)
$proc.StandardInput.Close()
$proc.WaitForExit()
$remoteExitCode = $proc.ExitCode

if ($remoteExitCode -ne 0) {
    throw "Remote deploy failed with code $remoteExitCode"
}

Write-Host "Deploy completed."
