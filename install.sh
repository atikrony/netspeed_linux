#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
#  NetSpeed Installer
#  Installs (or uninstalls) the netspeed panel indicator.
#  Works on Debian/Ubuntu, Linux Mint (Cinnamon), and derivatives.
# ──────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/netspeed"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/netspeed.desktop"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✔]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✘]${NC} $*"; }

# ── Dependency check ──────────────────────────────────────
install_deps() {
    local missing=()

    python3 -c "import gi; gi.require_version('Gtk','3.0')" 2>/dev/null \
        || missing+=(gir1.2-gtk-3.0)

    # XApp is native to Linux Mint / Cinnamon
    if [ "${XDG_CURRENT_DESKTOP:-}" = "X-Cinnamon" ] || [ "${DESKTOP_SESSION:-}" = "cinnamon" ]; then
        python3 -c "import gi; gi.require_version('XApp','1.0')" 2>/dev/null \
            || missing+=(gir1.2-xapp-1.0)
    else
        python3 -c "import gi; gi.require_version('AppIndicator3','0.1')" 2>/dev/null \
            || missing+=(gir1.2-appindicator3-0.1)
    fi

    python3 -c "import cairo" 2>/dev/null \
        || missing+=(python3-cairo)

    if [ ${#missing[@]} -gt 0 ]; then
        warn "Installing missing dependencies: ${missing[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y -qq "${missing[@]}"
        info "Dependencies installed."
    else
        info "All dependencies already satisfied."
    fi
}

# ── Install ───────────────────────────────────────────────
do_install() {
    install_deps

    mkdir -p "$INSTALL_DIR" "$AUTOSTART_DIR"

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp "$SCRIPT_DIR/netspeed.py" "$INSTALL_DIR/netspeed.py"
    chmod +x "$INSTALL_DIR/netspeed.py"

    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=NetSpeed
Comment=Network speed indicator for the panel
Exec=python3 $INSTALL_DIR/netspeed.py
Icon=network-transmit-receive
Terminal=false
X-GNOME-Autostart-enabled=true
Categories=Utility;
