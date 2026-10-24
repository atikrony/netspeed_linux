#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
#  build-deb.sh — Build the netspeed .deb package
#  Uses a temp directory to avoid permission issues on
#  NTFS / exFAT / FUSE mounts that force 777.
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEB_SRC="$SCRIPT_DIR/deb"
OUTPUT="$SCRIPT_DIR/netspeed_1.0.0_all.deb"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✔]${NC} $*"; }
error() { echo -e "${RED}[✘]${NC} $*"; exit 1; }

# Copy to a temp dir where we can set proper permissions
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cp -r "$DEB_SRC/"* "$TMPDIR/"

# Set correct permissions (dpkg-deb is strict)
find "$TMPDIR" -type d -exec chmod 0755 {} +
chmod 0644 "$TMPDIR/DEBIAN/control"
chmod 0755 "$TMPDIR/DEBIAN/postinst"
chmod 0755 "$TMPDIR/DEBIAN/prerm"
if [ -f "$TMPDIR/DEBIAN/postrm" ]; then
    chmod 0755 "$TMPDIR/DEBIAN/postrm"
fi
chmod 0755 "$TMPDIR/usr/bin/netspeed"
chmod 0755 "$TMPDIR/usr/share/netspeed/netspeed.py"
chmod 0644 "$TMPDIR/etc/xdg/autostart/netspeed.desktop"
if [ -f "$TMPDIR/usr/share/applications/netspeed.desktop" ]; then
    chmod 0644 "$TMPDIR/usr/share/applications/netspeed.desktop"
fi

info "Building .deb package for double-click and quick installation…"
dpkg-deb --build "$TMPDIR" "$OUTPUT"

if [ -f "$OUTPUT" ]; then
    info "Package built successfully: $OUTPUT"
    echo ""
    echo "  Package:         $( basename "$OUTPUT" )"
    echo "  Size:            $( ls -lh "$OUTPUT" | awk '{print $5}' )"
    echo "  Double-click:    Open with GDebi, Software Install, or Eddy"
    echo "  Terminal:        sudo apt install ./$( basename "$OUTPUT" )"
    echo "  Uninstall:       ./uninstall.sh (or sudo apt remove netspeed)"
    echo ""
else
    error "Build failed."
fi
