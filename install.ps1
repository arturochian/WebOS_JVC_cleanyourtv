<#
.SYNOPSIS
    CleanYourTV Windows Native Deployment Script for LG webOS Hub TVs (JVC Smart TVs)

.DESCRIPTION
    Automates the end-to-end deployment workflow:
    1. Validates environment dependencies (Python, Node.js, CLI tooling).
    2. Executes pre-flight automated SSAP backup snapshot (if backup.py is present).
    3. Generates required webOS icons (80x80 and 130x130) without macOS dependencies.
    4. Synchronizes installed apps and HDMI inputs from TV via SSAP.
    5. Packages web application into webOS IPK via @webos-tools/cli.
    6. Deploys and launches the custom launcher on the TV with 1-touch Quick Access guidance.
    7. Provides robust error trapping with rollback recommendations.

.PARAMETER TvHost
    IP address of the target webOS TV (default: $env:TV_HOST or 192.168.1.100).
.PARAMETER Device
    Ares device name configured in Developer Mode (default: $env:DEVICE or jvc-tv).
.PARAMETER AppId
    WebOS Application ID (default: com.gathin.tvhome).
.PARAMETER SkipSync
    Skip pulling apps and inputs from the TV.
.PARAMETER SkipIcons
    Skip icon resizing.
.PARAMETER SkipBuild
    Skip packaging into IPK.
.PARAMETER SkipInstall
    Skip installing IPK onto the TV.
.PARAMETER SkipLaunch
    Skip launching the application on the TV.
.PARAMETER SkipBackup
    Skip pre-flight snapshot backup.
.PARAMETER OfflineMock
    Execute workflow using simulated offline responses without physical TV.
.PARAMETER Help
    Show usage and help documentation.

.EXAMPLE
    .\install.ps1 -TvHost 192.168.1.100 -Device jvc-tv
.EXAMPLE
    .\install.ps1 -OfflineMock -SkipInstall -SkipLaunch
#>

[CmdletBinding()]
param(
    [string]$TvHost = $(if ($env:TV_HOST) { $env:TV_HOST } else { "192.168.1.100" }),
    [string]$Device = $(if ($env:DEVICE) { $env:DEVICE } else { "jvc-tv" }),
    [string]$AppId = "com.gathin.tvhome",
    [switch]$SkipSync,
    [switch]$SkipIcons,
    [switch]$SkipBuild,
    [switch]$SkipInstall,
    [switch]$SkipLaunch,
    [switch]$SkipBackup,
    [switch]$OfflineMock,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit 0
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  CleanYourTV - Windows Deployment Automation (webOS Hub) " -ForegroundColor Cyan
Write-Host "  Target TV: $TvHost  |  Target Device: $Device            " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# -------------------------------------------------------------------------
# Helper: Invoke Ares CLI via npx.cmd to bypass PowerShell execution policy
# -------------------------------------------------------------------------
function Invoke-Ares {
    param(
        [Parameter(Mandatory = $true)][string]$Tool,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    $cmdName = "ares-$Tool"
    if (Get-Command $cmdName -ErrorAction SilentlyContinue) {
        Write-Verbose "Executing local command: $cmdName $Arguments"
        & $cmdName @Arguments
    } else {
        Write-Verbose "Executing via npx.cmd: npx.cmd -y -p @webos-tools/cli $cmdName $Arguments"
        & "npx.cmd" -y -p @webos-tools/cli $cmdName @Arguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Ares CLI command '$cmdName' failed with exit code $LASTEXITCODE."
    }
}

try {
    # -------------------------------------------------------------------------
    # 1. Dependency Checks
    # -------------------------------------------------------------------------
    Write-Host "`n[1/6] Checking system prerequisites..." -ForegroundColor Yellow

    if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
        throw "Python 3 is required but was not found in PATH. Please install Python 3.9+."
    }
    $pyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    Write-Host "  [OK] Python version: $pyVer" -ForegroundColor Green

    if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
        throw "Node.js is required but was not found in PATH. Please install Node.js 18+."
    }
    $nodeVer = node -v
    Write-Host "  [OK] Node.js version: $nodeVer" -ForegroundColor Green

    # -------------------------------------------------------------------------
    # 2. Pre-Flight Backup Snapshot (R2 Safety Integration)
    # -------------------------------------------------------------------------
    if (-not $SkipBackup -and (Test-Path "backup.py")) {
        Write-Host "`n[2/6] Executing pre-flight state backup..." -ForegroundColor Yellow
        $backupArgs = @("backup.py", "--tv", $TvHost)
        if ($OfflineMock) { $backupArgs += "--offline-mock" }
        python @backupArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Pre-flight backup completed with non-zero exit code ($LASTEXITCODE)."
        } else {
            Write-Host "  [OK] Pre-flight backup snapshot saved." -ForegroundColor Green
        }
    } else {
        Write-Host "`n[2/6] Pre-flight backup skipped." -ForegroundColor Gray
    }

    # -------------------------------------------------------------------------
    # 3. Icon Generation (Python Pillow engine)
    # -------------------------------------------------------------------------
    if (-not $SkipIcons) {
        Write-Host "`n[3/6] Generating webOS icons (80x80, 130x130)..." -ForegroundColor Yellow
        python tools/generate_icons.py
        if ($LASTEXITCODE -ne 0) {
            throw "Icon generation failed."
        }
        Write-Host "  [OK] Icons generated successfully in app/." -ForegroundColor Green
    } else {
        Write-Host "`n[3/6] Icon generation skipped." -ForegroundColor Gray
    }

    # -------------------------------------------------------------------------
    # 4. App & Input Synchronization via SSAP
    # -------------------------------------------------------------------------
    if (-not $SkipSync) {
        Write-Host "`n[4/6] Synchronizing TV applications and external inputs..." -ForegroundColor Yellow
        $syncArgs = @("sync-apps.py", $TvHost)
        if ($OfflineMock) { $syncArgs += "--offline-mock" }
        python @syncArgs
        if ($LASTEXITCODE -ne 0) {
            throw "App synchronization failed. Make sure TV is powered on and connected."
        }
        Write-Host "  [OK] Applications and inputs synchronized to app/apps.js." -ForegroundColor Green
    } else {
        Write-Host "`n[4/6] App synchronization skipped." -ForegroundColor Gray
    }

    # -------------------------------------------------------------------------
    # 5. Build WebOS IPK Package
    # -------------------------------------------------------------------------
    if (-not $SkipBuild) {
        Write-Host "`n[5/6] Packaging webOS IPK..." -ForegroundColor Yellow
        if (-not (Test-Path "build")) {
            New-Item -ItemType Directory -Path "build" | Out-Null
        }
        Invoke-Ares "package" "app" "-o" "build"
        $ipkFile = Get-ChildItem -Path "build" -Filter "*.ipk" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $ipkFile) {
            throw "Package generation completed but no .ipk file was found in build/."
        }
        Write-Host "  [OK] Created package: $($ipkFile.FullName)" -ForegroundColor Green
    } else {
        Write-Host "`n[5/6] IPK packaging skipped." -ForegroundColor Gray
    }

    # -------------------------------------------------------------------------
    # 6. Deploy & Launch on TV
    # -------------------------------------------------------------------------
    if (-not $SkipInstall) {
        Write-Host "`n[6/6] Installing IPK to TV device '$Device'..." -ForegroundColor Yellow
        $ipkFile = Get-ChildItem -Path "build" -Filter "*.ipk" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $ipkFile) {
            throw "No .ipk found to install. Run without -SkipBuild."
        }
        Invoke-Ares "install" "-d" $Device $ipkFile.FullName
        Write-Host "  [OK] Package installed successfully on $Device." -ForegroundColor Green

        if (-not $SkipLaunch) {
            Write-Host "Launching $AppId on $Device..." -ForegroundColor Yellow
            Invoke-Ares "launch" "-d" $Device $AppId
            Write-Host "  [OK] $AppId launched successfully." -ForegroundColor Green
        }
    } else {
        Write-Host "`n[6/6] Installation to TV skipped." -ForegroundColor Gray
    }

    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host "  Deployment Workflow Completed Successfully!             " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "`n[JVC Remote Tip]: While TV Home is open on your screen," -ForegroundColor Cyan
    Write-Host "hold number key '1' on your JVC remote to bind it as a   " -ForegroundColor Cyan
    Write-Host "1-touch Quick Access button for instant launching anytime!" -ForegroundColor Cyan

    exit 0
}
catch {
    Write-Host "`n[ERROR] Deployment failed: $_" -ForegroundColor Red
    Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "Recovery Recommendation:" -ForegroundColor Yellow
    Write-Host "To roll back your local configuration or TV to the last" -ForegroundColor Yellow
    Write-Host "known good state, execute:" -ForegroundColor Yellow
    Write-Host "  .\restore.ps1 -Latest" -ForegroundColor Cyan
    Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
    exit 1
}
