param(
    [ValidateSet("native", "docker", "both")]
    [string]$Mode = "native",
    [string]$SourceRoot = "",
    [switch]$SkipPackageInstall,
    [switch]$Headless = $true,
    [ValidateRange(1,65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repoUrl = "https://github.com/Liquid3d57/xroar-mcp.git"

function Assert-Command($Name, $WingetId) {
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
    if ($SkipPackageInstall) { throw "Required command '$Name' was not found." }
    Write-Output "Installing $Name..."
    winget install --exact --id $WingetId --accept-package-agreements --accept-source-agreements
}

function Get-SourceTree {
    if ($SourceRoot) { $root = (Resolve-Path $SourceRoot).Path }
    else {
        $candidate = Split-Path -Parent $PSScriptRoot
        if (Test-Path (Join-Path $candidate "mcp-server/server.py")) { $root = $candidate }
        elseif (Test-Path (Join-Path $PSScriptRoot "mcp-server/server.py")) { $root = $PSScriptRoot }
        else { $root = "" }
    }

    if ($root) { return $root }

    Assert-Command git "Git.Git"
    $root = Join-Path $env:LOCALAPPDATA "xroar-mcp"
    if (-not (Test-Path (Join-Path $root ".git"))) {
        New-Item -ItemType Directory -Path $root -Force | Out-Null
        git clone $repoUrl $root
    }
    return $root
}

function Set-Ini {
    [CmdletBinding(SupportsShouldProcess)]
    param($Root)

    $ini = Join-Path $Root "config.ini"
    $lines = @("[server]", "host = 127.0.0.1", "port = $Port")
    if ($PSCmdlet.ShouldProcess($ini, "Write server configuration")) {
        Set-Content -Path $ini -Value $lines -Encoding ascii
    }
}

function Install-Native($Root) {
    Assert-Command python "Python.Python.3.12"
    Assert-Command git "Git.Git"
    Assert-Command bash "MSYS2.MSYS2"

    $msysRoot = "C:\msys64"
    $msysBash = Join-Path $msysRoot "usr/bin/bash.exe"
    if (-not (Test-Path $msysBash)) { throw "MSYS2 is required. Install MSYS2.MSYS2 and rerun this script." }

    $packages = "base-devel autoconf automake libtool texinfo patch mingw-w64-x86_64-toolchain mingw-w64-x86_64-libpng mingw-w64-x86_64-pkgconf mingw-w64-x86_64-libsystre mingw-w64-x86_64-libtre"
    if (-not $Headless) { $packages += " mingw-w64-x86_64-sdl3" }
    & $msysBash -lc "pacman -Syu --noconfirm"
    & $msysBash -lc "pacman -S --needed --noconfirm $packages"
    if ($LASTEXITCODE -ne 0) { throw "MSYS2 package installation failed." }

    $mode = if ($Headless) { "headless" } else { "gui" }
    & $msysBash -lc "cd '$($Root.Replace('\', '/'))' && MSYSTEM=MINGW64 bash build/build-msys2.sh $mode"
    if ($LASTEXITCODE -ne 0) { throw "Native XRoar build failed." }
}

function Install-Docker($Root) {
    Assert-Command docker "Docker.DockerDesktop"
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is installed but the Docker engine is not running." }

    $compose = Join-Path $Root "docker-compose.yml"
    $env:MCP_PORT = "$Port"
    docker compose -f $compose build
    if ($LASTEXITCODE -ne 0) { throw "Docker image build failed." }
    docker compose -f $compose up -d
    if ($LASTEXITCODE -ne 0) { throw "Docker container start failed." }
}

$root = Get-SourceTree
Set-Ini $root

if ($Mode -eq "native" -or $Mode -eq "both") { Install-Native $root }
if ($Mode -eq "docker" -or $Mode -eq "both") { Install-Docker $root }

Write-Output "MCP setup complete."
Write-Output "Native server: http://127.0.0.1:$Port"
Write-Output "Docker server: http://127.0.0.1:$Port"
