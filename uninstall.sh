#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
#  NetSpeed Uninstaller
#  Quickly and cleanly uninstalls NetSpeed from your system.
# ──────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✔]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
note()  { echo -e "${BLUE}[i]${NC} $*"; }

echo ""
echo -e "${YELLOW}═══ NetSpeed Uninstaller ═══${NC}"
echo ""

# 1. Stop any currently running NetSpeed processes
if pgrep -f "netspeed.py" >/dev/null 2>&1; then
    note "Stopping running NetSpeed instance…"
    pkill -f "netspeed.py" 2>/dev/null || true
    sleep 1
    info "Stopped running process."
else
    info "No running NetSpeed instance found."
fi

# 2. Check if installed as a system .deb package
if dpkg -s netspeed >/dev/null 2>&1; then
    note "NetSpeed system package detected. Removing via apt…"
    if [ "$EUID" -ne 0 ]; then
        sudo apt-get remove -y netspeed
    else
        apt-get remove -y netspeed
    fi
    info "NetSpeed .deb package removed."
fi

# 3. Check for local user installation files
LOCAL_INSTALL="$HOME/.local/share/netspeed"
AUTOSTART_FILE="$HOME/.config/autostart/netspeed.desktop"
APP_DESKTOP="$HOME/.local/share/applications/netspeed.desktop"
BIN_FILE="$HOME/.local/bin/netspeed"
PIXMAP_FILE="$HOME/.local/share/pixmaps/netspeed.png"
ICONS_BASE="$HOME/.local/share/icons/hicolor"

REMOVED_LOCAL=false

if [ -d "$LOCAL_INSTALL" ]; then
    rm -rf "$LOCAL_INSTALL"
    REMOVED_LOCAL=true
fi

if [ -f "$AUTOSTART_FILE" ]; then
    rm -f "$AUTOSTART_FILE"
    REMOVED_LOCAL=true
fi

if [ -f "$APP_DESKTOP" ]; then
    rm -f "$APP_DESKTOP"
    REMOVED_LOCAL=true
fi

if [ -f "$BIN_FILE" ]; then
    rm -f "$BIN_FILE"
    REMOVED_LOCAL=true
fi

if [ -f "$PIXMAP_FILE" ]; then
    rm -f "$PIXMAP_FILE"
    REMOVED_LOCAL=true
fi

for size in 16 22 24 32 48 64 96 128 256 512; do
    icon_file="$ICONS_BASE/${size}x${size}/apps/netspeed.png"
    if [ -f "$icon_file" ]; then
        rm -f "$icon_file"
        REMOVED_LOCAL=true
    fi
done

if [ "$REMOVED_LOCAL" = true ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f "$ICONS_BASE" 2>/dev/null || true
    fi
    info "Local user installation files, shortcuts, and icons removed."
fi

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  NetSpeed has been completely uninstalled from your system.${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
