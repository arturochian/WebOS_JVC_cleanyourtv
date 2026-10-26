<#
.SYNOPSIS
    restore.ps1 - Native Windows PowerShell Rollback Utility for WebOS TV Enhancement Suite.

.DESCRIPTION
    Reverts launcher configurations and local assets from a selected or latest snapshot,
    verifying cryptographic SHA-256 manifests. Optionally re-packages and redeploys the
    restored launcher to the TV or completely uninstalls it.

.PARAMETER Latest
    Restores from the most recent valid snapshot in backup/ (default behavior).

.PARAMETER Snapshot
    Specifies a specific snapshot directory path or timestamp slug (e.g. '20261025_204500').

.PARAMETER List
    Lists all available backup snapshots with creation timestamp, app count, and integrity status.

.PARAMETER VerifyOnly
    Validates snapshot integrity and SHA-256 checksums without modifying local files or the TV.

.PARAMETER ReinstallToTV
    Re-packages the restored application and redeploys it to the webOS TV via @webos-tools/cli.

.PARAMETER UninstallFromTV
    Uninstalls the custom launcher (com.gathin.tvhome) from the webOS TV, restoring default home.

.PARAMETER Device
    The webOS device name configured in @webos-tools/cli (default: 'jvc-tv').

.PARAMETER AppId
    The webOS application identifier (default: 'com.gathin.tvhome').

.PARAMETER Force
    Overwrites target files without interactive confirmation prompt.

.PARAMETER Quiet
    Suppresses verbose console output.

.EXAMPLE
    .\restore.ps1 -Latest
    Restores local app configuration from the latest snapshot.

.EXAMPLE
    .\restore.ps1 -List
    Displays an inventory table of all snapshots in backup/.

.EXAMPLE
    .\restore.ps1 -Snapshot 20261025_205354 -VerifyOnly
    Verifies cryptographic integrity of the specified snapshot.

.EXAMPLE
    .\restore.ps1 -Latest -ReinstallToTV -Device jvc-tv
    Restores from latest snapshot, packages IPK, and deploys to JVC TV.

.EXAMPLE
    .\restore.ps1 -UninstallFromTV -Device jvc-tv
    Uninstalls the custom launcher from the TV.
#>

[CmdletBinding()]
param (
    [switch]$Latest,
    [string]$Snapshot = "",
    [switch]$List,
    [switch]$VerifyOnly,
    [switch]$ReinstallToTV,
    [switch]$UninstallFromTV,
    [string]$Device = "jvc-tv",
    [string]$AppId = "com.gathin.tvhome",
    [switch]$Force,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

function Write-Banner {
    if (-not $Quiet) {
        Write-Host "=================================================================" -ForegroundColor Cyan
        Write-Host "  CleanYourTV Rollback & Restore Engine (Windows Native)         " -ForegroundColor Cyan
        Write-Host "  Tested for LG webOS Hub / JVC LT-32KB116                       " -ForegroundColor DarkCyan
        Write-Host "=================================================================`n" -ForegroundColor Cyan
    }
}

function Invoke-AresTool {
    param (
        [string]$ToolName,
        [string[]]$ToolArgs
    )
    # Check if tool is available directly in PATH
    $cmd = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($cmd) {
        & $cmd.Source @ToolArgs
        return $LASTEXITCODE
    }

    # Fallback to npx.cmd on Windows to avoid execution policy restrictions
    $npx = Get-Command "npx.cmd" -ErrorAction SilentlyContinue
    if (-not $npx) {
        $npx = Get-Command "npx" -ErrorAction SilentlyContinue
    }

    if (-not $npx) {
        Write-Host "[ERROR] Neither '$ToolName' nor 'npx' was found in PATH." -ForegroundColor Red
        Write-Host "Please ensure Node.js is installed or run: npm install -g @webos-tools/cli" -ForegroundColor Yellow
        return 1
    }

    $allArgs = @("-y", "-p", "@webos-tools/cli", $ToolName) + $ToolArgs
    & $npx.Source @allArgs
    return $LASTEXITCODE
}

# --- Step 1: Verify Python Environment ---
$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[FATAL] Python was not found on your system PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.9+ from https://www.python.org/ or Windows Store." -ForegroundColor Yellow
    exit 1
}

$restorePy = Join-Path $ScriptDir "restore.py"
if (-not (Test-Path $restorePy)) {
    Write-Host "[FATAL] 'restore.py' not found in $ScriptDir." -ForegroundColor Red
    exit 1
}

# --- Step 2: Handle Uninstall Request ---
if ($UninstallFromTV) {
    Write-Banner
    Write-Host "[UNINSTALL] Uninstalling custom launcher '$AppId' from TV device '$Device'..." -ForegroundColor Yellow
    $code = Invoke-AresTool -ToolName "ares-install" -ToolArgs @("-r", "-d", $Device, $AppId)
    if ($code -eq 0) {
        Write-Host "[SUCCESS] Successfully uninstalled '$AppId' from device '$Device'." -ForegroundColor Green
        Write-Host "Your TV has been reverted to the standard LG webOS Home screen.`n" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] ares-install reported exit code $code during uninstallation." -ForegroundColor DarkYellow
    }
    exit $code
}

# --- Step 3: Handle List Request ---
if ($List) {
    Write-Banner
    & python $restorePy --list
    exit $LASTEXITCODE
}

# --- Step 4: Assemble restore.py Arguments ---
$pyArgs = [System.Collections.Generic.List[string]]::new()

if ($VerifyOnly) {
    $pyArgs.Add("--verify-only")
}

if ($Snapshot -and $Snapshot.Trim() -ne "") {
    $pyArgs.Add("--snapshot")
    $pyArgs.Add($Snapshot)
} else {
    $pyArgs.Add("--latest")
}

if ($Force) {
    $pyArgs.Add("--force")
}

if ($Quiet) {
    $pyArgs.Add("--quiet")
}

# --- Step 5: Execute restore.py ---
Write-Banner
& python $restorePy $pyArgs

$restoreExitCode = $LASTEXITCODE
if ($restoreExitCode -ne 0) {
    Write-Host "`n[ERROR] restore.py exited with failure code: $restoreExitCode" -ForegroundColor Red
    exit $restoreExitCode
}

# If --verify-only was run, exit cleanly
if ($VerifyOnly) {
    exit 0
}

# --- Step 6: Handle Reinstall to TV ---
if ($ReinstallToTV) {
    Write-Host "`n[DEPLOY] Step: Re-deploying restored application to TV ($Device)..." -ForegroundColor Cyan

    $appDir = Join-Path $ScriptDir "app"
    $buildDir = Join-Path $ScriptDir "build"

    if (-not (Test-Path $appDir)) {
        Write-Host "[ERROR] Target app directory '$appDir' does not exist." -ForegroundColor Red
        exit 1
    }

    # Ensure build directory exists
    if (-not (Test-Path $buildDir)) {
        New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    }

    Write-Host "[PACKAGE] 1/3 Packaging IPK via ares-package..." -ForegroundColor Cyan
    $pkgCode = Invoke-AresTool -ToolName "ares-package" -ToolArgs @($appDir, "-o", $buildDir)
    if ($pkgCode -ne 0) {
        Write-Host "[ERROR] ares-package failed with exit code $pkgCode." -ForegroundColor Red
        exit $pkgCode
    }

    # Locate generated IPK
    $ipkFiles = Get-ChildItem -Path $buildDir -Filter "$AppId*.ipk" | Sort-Object LastWriteTime -Descending
    if (-not $ipkFiles -or $ipkFiles.Count -eq 0) {
        $ipkFiles = Get-ChildItem -Path $buildDir -Filter "*.ipk" | Sort-Object LastWriteTime -Descending
    }

    if (-not $ipkFiles -or $ipkFiles.Count -eq 0) {
        Write-Host "[ERROR] Could not find generated .ipk file in '$buildDir'." -ForegroundColor Red
        exit 1
    }

    $ipkPath = $ipkFiles[0].FullName
    Write-Host "  Found package: $($ipkFiles[0].Name)" -ForegroundColor DarkGray

    Write-Host "[INSTALL] 2/3 Installing package to TV device '$Device'..." -ForegroundColor Cyan
    $installCode = Invoke-AresTool -ToolName "ares-install" -ToolArgs @("-d", $Device, $ipkPath)
    if ($installCode -ne 0) {
        Write-Host "[ERROR] ares-install failed with exit code $installCode." -ForegroundColor Red
        exit $installCode
    }

    Write-Host "[LAUNCH] 3/3 Launching $AppId on TV..." -ForegroundColor Cyan
    $launchCode = Invoke-AresTool -ToolName "ares-launch" -ToolArgs @("-d", $Device, $AppId)
    if ($launchCode -ne 0) {
        Write-Host "[WARNING] ares-launch exited with code $launchCode." -ForegroundColor DarkYellow
    } else {
        Write-Host "[SUCCESS] Restored application re-deployed and launched on TV successfully!`n" -ForegroundColor Green
    }
}

exit 0
