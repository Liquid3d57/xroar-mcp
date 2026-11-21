#!/usr/bin/env bash
# Build the patched XRoar natively on Windows, with MinGW cross-toolchain.
#
#   bash build/build-windows.sh              SDL3 GUI build
#   bash build/build-windows.sh headless     no windowing or SDL dependency
#   set MINGWROOT=C:\msys64\mingw64 && bash build/build-windows.sh  (cmd.exe)
#   MINGWROOT="C:\msys64\mingw64" bash build/build-windows.sh    (PowerShell/bash)
#
# Output: bin/xroar-dev.exe (override with $XROAR_WIN_BIN).
#
# THIS IS THE BUILD THAT PASSES -Werror, deliberately. MinGW is the stricter
# target and it is where a missing declaration shows up as a truncated pointer
# rather than as silence. Run it when you add a patch even if you never intend
# to use the binary -- it found four such bugs the first time it was tried.
# On native Windows with MSYS2, ensure your MinGW-w64 toolchain is on PATH
# (typically via msys2 MINGW64 shell) and pkg-config can find the mingw libraries.
# Set MINGWROOT to your mingw prefix, e.g.: MINGWROOT="C:\msys64\mingw64" (PowerShell/bash)
# or: set MINGWROOT=C:\msys64\mingw64 && bash build/build-windows.sh (cmd.exe)
set -euo pipefail
MINGWROOT="${MINGWROOT:-C:\msys64\mingw64}"
HOSTTRIPLE="${HOSTTRIPLE:-x86_64-w64-mingw32}"

HERE="$(cd "$(dirname "$0")/.." && pwd)"
VER=1.12.1
MODE="${1:-gui}"
JOBS="$(nproc 2>/dev/null || echo 4)"

BIN="${XROAR_WIN_BIN:-$HERE/bin/xroar-dev.exe}"

case "$MODE" in
    gui|headless) ;;
    *) echo "usage: $0 [gui|headless]" >&2; exit 2 ;;
esac

# Under native Windows, `command -v` returns real paths (no /mnt/ WSL mounts),
# so the WSL guard is omitted. A missing tool will be caught early.
have() {
    local p
    p="$(command -v "$1" 2>/dev/null)" || return 1
    # On native Windows there are no /mnt/ prefixes; keep the guard minimal.
    return 0
}

missing=()
# Native Windows: check for the cross-compiler triple (e.g. x86_64-w64-mingw32-gcc)
have "$HOSTTRIPLE-gcc" || missing+=("mingw-w64 cross-toolchain")
have autoreconf        || missing+=("autoconf automake libtool")
have pkg-config        || missing+=(pkg-config)
if [ "$MODE" = gui ]; then
    # The native Windows UI is implemented on SDL3, not SDL2.
    # Set PKG_CONFIG_LIBDIR so pkg-config finds sdl3 from the mingw prefix.
    PKG_CONFIG_LIBDIR="$MINGWROOT/lib/pkgconfig"
    # pkg-config should find sdl3 from the mingw prefix; if not, check for
    # manual SDL3 installation (headers + DLL under MINGWROOT).
    if pkg-config --exists sdl3 2>/dev/null; then
        : # sdl3 found via pkg-config
    elif [ -d "$MINGWROOT/include/SDL3" ] && [ -f "$MINGWROOT/bin/SDL3.dll" ]; then
        # Manual SDL3 installation detected - allow build with warning
        missing+=("SDL3 (found via manual installation at $MINGWROOT)")
    else
        # Neither pkg-config nor manual installation found
        missing+=("SDL3 dev libraries (set MINGWROOT to your mingw prefix, or install SDL3 manually:")
        missing+=("  curl -LO https://github.com/libsdl-org/SDL/releases/download/release-3.4.12/SDL3-devel-3.4.12-mingw.tar.gz")
        missing+=("  tar xzf SDL3-devel-3.4.12-mingw.tar.gz")
        missing+=("  mkdir -p <dir> && cp -r SDL3-3.4.12/x86_64-w64-mingw32/* <dir/>")
        missing+=("  MINGWROOT=<dir> bash build/build-windows.sh")
    fi
fi
if [ ${#missing[@]} -gt 0 ]; then
    echo "MISSING: ${missing[*]}" >&2
    # Check if running under MSYS2 MINGW64 shell - if so, try to install missing packages
    if [ "${MSYSTEM:-}" = "MINGW64" ] || [ "${MSYSTEM:-}" = "UCRT64" ] || [ "${MSYSTEM:-}" = "CLANG64" ]; then
        echo >&2
        echo "Attempting to install missing packages via pacman (MSYS2 MINGW64 shell)..." >&2
        # Install the cross-toolchain and required build tools
        pacman -S --needed --noconfirm \
            mingw-w64-x86_64-toolchain \
            autoconf \
            automake \
            libtool \
            pkg-config 2>/dev/null && \
          echo "Packages installed successfully. Rerun the build script." >&2 || \
          echo "Package installation failed. Please install manually:" >&2
        cat >&2 <<'MANUALEOF'

  On native Windows with MSYS2 MINGW64 shell, install the required packages:
    pacman -S --needed base-devel autoconf automake libtool pkg-config \
      mingw-w64-x86_64-toolchain

  The headless build needs no SDL. For the GUI build, if pkg-config does
  not find sdl3 automatically, set MINGWROOT to your mingw prefix path,
  e.g.:  MINGWROOT="C:\msys64\mingw64" bash build/build-windows.sh

  SDL3 can also be installed manually:
    curl -LO https://github.com/libsdl-org/SDL/releases/download/release-3.4.12/SDL3-devel-3.4.12-mingw.tar.gz
    tar xzf SDL3-devel-3.4.12-mingw.tar.gz
    mkdir -p <your-mingw-dir> && cp -r SDL3-3.4.12/x86_64-w64-mingw32/* <your-mingw-dir/>
    MINGWROOT=<your-mingw-dir> bash build/build-windows.sh
MANUALEOF
        exit 2
    else
        # Not running under MSYS2 - provide manual installation instructions
        cat >&2 <<'EOF'

  On native Windows, ensure the MinGW-w64 cross-toolchain is on PATH:
    pacman -S mingw-w64-x86_64-toolchain  (msys2 MINGW64 shell)
  or install a standalone MinGW-w64 distribution and add its bin/ to PATH.

  pkg-config must be able to find the mingw libraries (typically via
  MINGWROOT or the pkg-config path).

  The headless build needs no SDL. For the GUI build, if pkg-config does
  not find sdl3 automatically, set MINGWROOT to your mingw prefix path,
  e.g.:  MINGWROOT=C:\mingw64 bash build/build-windows.sh

  SDL3 can also be installed manually:
    curl -LO https://github.com/libsdl-org/SDL/releases/download/release-3.4.12/SDL3-devel-3.4.12-mingw.tar.gz
    tar xzf SDL3-devel-3.4.12-mingw.tar.gz
    mkdir -p <your-mingw-dir> && cp -r SDL3-3.4.12/x86_64-w64-mingw32/* <your-mingw-dir/>
    MINGWROOT=<your-mingw-dir> bash build/build-windows.sh
EOF
        exit 2
    fi
fi

cd "$HERE"
echo ">> extracting xroar-$VER"
rm -rf "xroar-$VER"
tar xzf "xroar/xroar-$VER.tar.gz"
cd "xroar-$VER"

echo ">> applying $(ls "$HERE"/xroar/[0-9]*.patch | wc -l) patches"
for p in "$HERE"/xroar/[0-9]*.patch; do
    # --no-backup-if-mismatch: a hunk that lands at an offset is still an exact
    # context match, but patch would leave a .orig beside the file. Offsets are
    # normal here -- editing any early patch shifts every later one -- and the
    # backups are pure litter in a tree that is deleted and rebuilt anyway.
    patch -p1 -s --no-backup-if-mismatch < "$p" || { echo "FAILED: $(basename "$p")" >&2; exit 1; }
done


echo ">> autoreconf"
autoreconf -fi

# --without-tre: MinGW has no POSIX regex.h; patch 02 supplies a matcher for
#   the fixed set of delimiter expressions XRoar actually uses.
# --without-opengl: skips the Mesa probe.
#
# SCREENSHOTS COMPILE OUT unless a mingw libpng is present under MINGWROOT.
# The series does that cleanly -- CLI and trap hooks go together, so
# -trap-screenshot reports "compiled out" rather than half-working -- and the
# acceptance check below will say MISSING, correctly.
#
# NOTE: If your MinGW installation includes regex.h (some do via libsystre),
# you may need to use --with-tre instead of --without-tre. Check configure
# output for HAVE_TRE and adjust accordingly.
if [ "$MODE" = headless ]; then
    echo ">> configure (mingw headless; no Windows UI or SDL)"
    ./configure --host="$HOSTTRIPLE" \
      --disable-windows32-ui --without-sdl3 --without-sdl2 \
      --without-tre --without-opengl
else
    echo ">> configure (mingw SDL3 GUI)"
    ./configure --host="$HOSTTRIPLE" \
      --without-tre --without-opengl \
      PKG_CONFIG_LIBDIR="$MINGWROOT/lib/pkgconfig" \
      SDL3_CFLAGS="-I$MINGWROOT/include" \
      SDL3_LIBS="-L$MINGWROOT/lib -lmingw32 -lSDL3 -mwindows"
fi

make ARFLAGS=cr -j"$JOBS" CFLAGS="-O2 -g -Werror"

mkdir -p "$(dirname "$BIN")"
cp src/xroar.exe "$BIN"
# The GUI executable needs the SDL3 runtime; headless has no non-system DLL.
if [ "$MODE" = gui ] && [ -f "$MINGWROOT/bin/SDL3.dll" ]; then
    cp "$MINGWROOT/bin/SDL3.dll" "$(dirname "$BIN")/"
fi

# Collect runtime DLLs so the built binary runs without LD_LIBRARY_PATH.
# This mirrors the build-msys2.sh approach: find DLLs referenced by the binary
# and copy them beside it.
echo ">> collecting runtime DLLs"
copied=0
if command -v ldd >/dev/null 2>&1; then
    for dll in $(ldd "$BIN" 2>/dev/null | awk '/mingw32|SDL3/ {print $3}'); do
        [ -f "$dll" ] || continue
        cp -u "$dll" "$(dirname "$BIN")/" && copied=$((copied+1))
    done
fi
echo "   $copied DLL(s) beside the binary"

echo
echo ">> installed: $BIN"
# trap-screenshot is tolerated here: it needs a mingw libpng, which no distro
# packages, and the series compiles the CLI and the trap hooks out together so
# a build without it is consistent rather than half-wired. Everything else is
# still a hard failure.
bash "$HERE"/build/acceptance.sh "$BIN" trap-screenshot
