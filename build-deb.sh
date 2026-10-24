#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
#  build-deb.sh — Build the netspeed .deb package
#  Uses a temp directory to avoid permission issues on
#  NTFS / exFAT / FUSE mounts that force 777.
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEB_SRC="$SCRIPT_DIR/deb"
OUTPUT="$SCRIPT_DIR/netspeed_1.0.0.deb"
OUTPUT_ALL="$SCRIPT_DIR/netspeed_1.0.0_all.deb"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✔]${NC} $*"; }
error() { echo -e "${RED}[✘]${NC} $*"; exit 1; }

# Keep deb/usr/share/netspeed/netspeed.py in sync with root netspeed.py
if [ -f "$SCRIPT_DIR/netspeed.py" ]; then
    cp "$SCRIPT_DIR/netspeed.py" "$DEB_SRC/usr/share/netspeed/netspeed.py"
fi

# Copy to a temp dir where we can set proper permissions
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cp -r "$DEB_SRC/"* "$TMPDIR/"
find "$TMPDIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TMPDIR" -name "*.pyc" -delete 2>/dev/null || true

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
if [ -d "$TMPDIR/usr/share/icons" ]; then
    find "$TMPDIR/usr/share/icons" -type f -exec chmod 0644 {} +
fi
if [ -d "$TMPDIR/usr/share/pixmaps" ]; then
    find "$TMPDIR/usr/share/pixmaps" -type f -exec chmod 0644 {} +
fi

info "Building .deb package for double-click and quick installation…"
dpkg-deb --build "$TMPDIR" "$OUTPUT"
cp "$OUTPUT" "$OUTPUT_ALL"

# Set Windows-like custom icon & thumbnail on the .deb files
if [ -f "$SCRIPT_DIR/netspeed.png" ]; then
    if command -v gio >/dev/null 2>&1; then
        ICON_URI="file://$SCRIPT_DIR/netspeed.png"
        gio set -t string "$OUTPUT" metadata::custom-icon "$ICON_URI" 2>/dev/null || true
        gio set -t string "$OUTPUT_ALL" metadata::custom-icon "$ICON_URI" 2>/dev/null || true
    fi

    # Pre-render standard Freedesktop thumbnail caches (Nemo, Nautilus, Caja)
    python3 -c "
import os, hashlib
from PIL import Image, PngImagePlugin

deb_paths = ['$OUTPUT', '$OUTPUT_ALL']
icon_path = '$SCRIPT_DIR/netspeed.png'
if os.path.exists(icon_path):
    base_img = Image.open(icon_path)
    for p in deb_paths:
        if not os.path.exists(p):
            continue
        uri = 'file://' + os.path.abspath(p)
        md5 = hashlib.md5(uri.encode('utf-8')).hexdigest()
        mtime = str(int(os.path.getmtime(p)))
        fsize = str(os.path.getsize(p))

        meta = PngImagePlugin.PngInfo()
        meta.add_text('Thumb::URI', uri)
        meta.add_text('Thumb::MTime', mtime)
        meta.add_text('Thumb::Size', fsize)
        meta.add_text('Thumb::Mimetype', 'application/vnd.debian.binary-package')

        for folder, dim in {'normal': 128, 'large': 256, 'x-large': 512}.items():
            cache_dir = os.path.expanduser(f'~/.cache/thumbnails/{folder}')
            os.makedirs(cache_dir, exist_ok=True)
            base_img.resize((dim, dim), Image.Resampling.LANCZOS).save(
                os.path.join(cache_dir, f'{md5}.png'), 'PNG', pnginfo=meta
            )
" 2>/dev/null || true
fi

if [ -f "$OUTPUT" ]; then
    info "Package built successfully with custom icon: $OUTPUT"
    echo ""
    echo "  Package:         $( basename "$OUTPUT" )"
    echo "  Size:            $( ls -lh "$OUTPUT" | awk '{print $5}' )"
    echo "  Icon:            $( basename "$SCRIPT_DIR/netspeed.png" ) (Attached to .deb file)"
    echo "  Double-click:    Open with GDebi, Software Install, or Eddy"
    echo "  Terminal:        sudo apt install ./$( basename "$OUTPUT" )"
    echo "  Uninstall:       ./uninstall.sh (or sudo apt remove netspeed)"
    echo ""
else
    error "Build failed."
fi
