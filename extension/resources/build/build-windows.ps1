#!/usr/bin/env pwsh
# build-windows.ps1 - PowerShell wrapper for XRoar Windows build
#
# Sets up the MinGW-w64 environment and invokes the bash build script.
# Handles MSYS2 detection and environment variable configuration.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File build/build-windows.ps1
#   powershell -ExecutionPolicy Bypass -File build/build-windows.ps1 gui
#   powershell -ExecutionPolicy Bypass -File build/build-windows.ps1 headless
#
# On first run, it will detect your environment and configure MINGWROOT.
# Then it invokes the bash build script (build-windows.sh).

#----------------------------------------------------------------------------
# Step 1: Detect MSYS2 environment and set MINGWROOT
#----------------------------------------------------------------------------
$isMSYS2 = $env:MSYSTEM -match '^(MINGW64|UCRT64|CLANG64)$'

# Determine MINGWROOT path
$MINGWROOT = $env:MINGWROOT
if (-not $MINGWROOT) {
    if ($isMSYS2) {
        # Under MSYS2, use the standard location
        $MINGWROOT = "C:\msys64\mingw64"
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] MSYS2 detected - using MINGWROOT: $MINGWROOT" -ForegroundColor Cyan
    }
    else {
        # Not under MSYS2 - ask user for path or use default
        $MINGWROOT = Read-Host "Enter your MinGW-w64 installation path (default: C:\msys64\mingw64)"
        if ([string]::IsNullOrWhiteSpace($MINGWROOT)) {
            $MINGWROOT = "C:\msys64\mingw64"
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Using default: $MINGWROOT" -ForegroundColor Yellow
        }
    }
}

# Normalize path to absolute
if (-not [System.IO.Path]::IsPathRooted($MINGWROOT)) {
    $MINGWROOT = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) $MINGWROOT
}
$MINGWROOT = [System.IO.Path]::GetFullPath($MINGWROOT)

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] MINGWROOT = $MINGWROOT" -ForegroundColor Cyan

# Set environment variable for the bash build script
$env:MINGWROOT = $MINGWROOT

# Determine build mode from argument
$mode = $args[0]
if ($mode -ne 'gui' -and $mode -ne 'headless') {
    Write-Error "Invalid mode: $mode. Use 'gui' or 'headless'."
    exit 2
}
$env:MODE = $mode

# Provide the command to run the bash build script
Write-Host "" -ForegroundColor Cyan
Write-Host "The environment is configured. Now run the bash build script:" -ForegroundColor Yellow
Write-Host "  bash `"$here/build/windows.sh`" `"`$mode`"" -ForegroundColor Gray
Write-Host "" -ForegroundColor Cyan

# Show MSYS2 package installation guidance if not under MSYS2
if (-not $isMSYS2) {
    Write-Host "Note: For automatic package installation, run under MSYS2 MINGW64 shell:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File build/build-windows.ps1" -ForegroundColor Gray
    Write-Host "  This will attempt: pacman -S --needed --noconfirm mingw-w64-x86_64-toolchain autoconf automake libtool pkg-config" -ForegroundColor Gray
}