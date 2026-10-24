#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
#  NetSpeed Installer
#  Installs the netspeed panel indicator, start menu shortcut,
#  and autostart entry for Debian-based systems.
# ──────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/netspeed"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"
ICONS_BASE="$HOME/.local/share/icons/hicolor"
PIXMAPS_DIR="$HOME/.local/share/pixmaps"
BIN_DIR="$HOME/.local/bin"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✔]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
note()  { echo -e "${BLUE}[i]${NC} $*"; }
error() { echo -e "${RED}[✘]${NC} $*"; exit 1; }

# ── Dependency check ──────────────────────────────────────
install_deps() {
    local missing=()

    python3 -c "import gi; gi.require_version('Gtk','3.0')" 2>/dev/null         || missing+=(gir1.2-gtk-3.0)

    # XApp is native to Linux Mint / Cinnamon
    if [ "${XDG_CURRENT_DESKTOP:-}" = "X-Cinnamon" ] || [ "${DESKTOP_SESSION:-}" = "cinnamon" ]; then
        python3 -c "import gi; gi.require_version('XApp','1.0')" 2>/dev/null             || missing+=(gir1.2-xapp-1.0)
    else
        python3 -c "import gi; (gi.require_version('AppIndicator3','0.1') if 'AppIndicator3' in gi._overridesdir else gi.require_version('AyatanaAppIndicator3','0.1'))" 2>/dev/null             || missing+=(gir1.2-appindicator3-0.1)
    fi

    python3 -c "import cairo" 2>/dev/null         || missing+=(python3-cairo)

    if [ ${#missing[@]} -gt 0 ]; then
        warn "Installing missing dependencies: ${missing[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y "${missing[@]}"
        info "Dependencies installed."
    else
        info "All dependencies already satisfied."
    fi
}

# ── Install ───────────────────────────────────────────────
do_install() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    echo ""
    echo -e "${GREEN}═══ NetSpeed Installer ═══${NC}"
    echo ""

    install_deps

    # Stop any currently running instance
    if pgrep -f "netspeed.py" >/dev/null 2>&1; then
        note "Stopping running NetSpeed instance…"
        pkill -f "netspeed.py" 2>/dev/null || true
        sleep 1
    fi

    # Create directories
    mkdir -p "$INSTALL_DIR" "$AUTOSTART_DIR" "$APPLICATIONS_DIR" "$PIXMAPS_DIR" "$BIN_DIR"

    # Copy main python script
    cp "$SCRIPT_DIR/netspeed.py" "$INSTALL_DIR/netspeed.py"
    chmod 0755 "$INSTALL_DIR/netspeed.py"

    # Copy icons
    if [ -f "$SCRIPT_DIR/netspeed.png" ]; then
        cp "$SCRIPT_DIR/netspeed.png" "$INSTALL_DIR/netspeed.png"
        cp "$SCRIPT_DIR/netspeed.png" "$PIXMAPS_DIR/netspeed.png"
    fi

    # Copy pre-generated multi-size icons from deb assets if available
    for size in 16 22 24 32 48 64 96 128 256 512; do
        target_dir="$ICONS_BASE/${size}x${size}/apps"
        mkdir -p "$target_dir"
        if [ -f "$SCRIPT_DIR/deb/usr/share/icons/hicolor/${size}x${size}/apps/netspeed.png" ]; then
            cp "$SCRIPT_DIR/deb/usr/share/icons/hicolor/${size}x${size}/apps/netspeed.png" "$target_dir/netspeed.png"
        elif [ -f "$SCRIPT_DIR/netspeed.png" ]; then
            cp "$SCRIPT_DIR/netspeed.png" "$target_dir/netspeed.png"
        fi
    done

    # 1. Create Start Menu shortcut (.desktop file)
    cat > "$APPLICATIONS_DIR/netspeed.desktop" <<DESKTOPEOF
[Desktop Entry]
Type=Application
Name=NetSpeed
GenericName=Network Speed Indicator
Comment=Monitor real-time network speed and data usage in your panel
Exec=python3 $INSTALL_DIR/netspeed.py
Icon=netspeed
Terminal=false
Categories=Network;Utility;Monitor;
Keywords=network;speed;indicator;bandwidth;download;upload;
StartupNotify=false
DESKTOPEOF
    chmod 0644 "$APPLICATIONS_DIR/netspeed.desktop"

    # 2. Create Autostart shortcut
    cat > "$AUTOSTART_DIR/netspeed.desktop" <<AUTOSTARTEOF
[Desktop Entry]
Type=Application
Name=NetSpeed
Comment=Network speed indicator for the panel
Exec=python3 $INSTALL_DIR/netspeed.py
Icon=netspeed
Terminal=false
X-GNOME-Autostart-enabled=true
Categories=Utility;
AUTOSTARTEOF
    chmod 0644 "$AUTOSTART_DIR/netspeed.desktop"

    # 3. Create command-line launcher in ~/.local/bin
    cat > "$BIN_DIR/netspeed" <<LAUNCHEREOF
#!/usr/bin/env bash
exec python3 "$HOME/.local/share/netspeed/netspeed.py" "\$@"
LAUNCHEREOF
    chmod 0755 "$BIN_DIR/netspeed"

    # Update desktop and icon databases
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPLICATIONS_DIR" 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f "$ICONS_BASE" 2>/dev/null || true
    fi

    # Refresh Cinnamon menu if running
    gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon --method org.Cinnamon.Eval 'try { imports.ui.main.AppletManager.getRunningInstancesForUuid("menu@cinnamon.org").forEach(m => m._refreshApps()); } catch(e){}' >/dev/null 2>&1 || true

    # Launch NetSpeed in background
    nohup python3 "$INSTALL_DIR/netspeed.py" >/dev/null 2>&1 &

    echo ""
    info "NetSpeed installed successfully!"
    echo "  • Start Menu:    Shortcut added to Application Menu (Internet / Utilities)"
    echo "  • Icon:          Transparent PNG icon registered for all desktop themes"
    echo "  • Autostart:     Enabled on login ($AUTOSTART_DIR/netspeed.desktop)"
    echo "  • Terminal:      You can run 'netspeed' anytime"
    echo "  • Status:        NetSpeed is running in your panel"
    echo ""
}

do_install "$@"
