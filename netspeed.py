#!/usr/bin/env python3
"""
NetSpeed — A lightweight panel indicator for monitoring network speed.
Shows upload and download speeds stacked (U: / D:) in the system panel.
Works natively on Linux Mint / Cinnamon via XApp.StatusIcon and falls back
to AppIndicator3 on other desktop environments.
"""

import gi
gi.require_version('Gtk', '3.0')

USE_XAPP = False
try:
    gi.require_version('XApp', '1.0')
    from gi.repository import XApp
    USE_XAPP = True
except (ValueError, ImportError):
    USE_XAPP = False

if not USE_XAPP:
    try:
        gi.require_version('AppIndicator3', '0.1')
        from gi.repository import AppIndicator3
    except (ValueError, ImportError):
        pass

from gi.repository import Gtk, GLib, Gdk, Pango
import cairo
import time
import os
import signal
import sys
import tempfile
import json
import threading
import urllib.request
from datetime import date, datetime
from collections import OrderedDict


# ── Unit definitions ──────────────────────────────────────────

UNITS = OrderedDict([
    # Bit units (network-standard: 1 Kb = 1000 bits, matches browser speed tests)
    ("Mb/s",  {"divisor": 1000**2/8,      "label": "Mbps",  "long": "Megabits/s (Speedtest / Fast.com)"}),
    ("Kb/s",  {"divisor": 1000/8,         "label": "Kbps",  "long": "Kilobits/s"}),
    ("Gb/s",  {"divisor": 1000**3/8,      "label": "Gbps",  "long": "Gigabits/s"}),
    ("b/s",   {"divisor": 1/8,            "label": "bps",   "long": "Bits/s"}),
    ("Mib/s", {"divisor": 1024**2/8,      "label": "Mibps", "long": "Mebibits/s"}),
    ("Kib/s", {"divisor": 1024/8,         "label": "Kibps", "long": "Kibibits/s"}),
    ("Gib/s", {"divisor": 1024**3/8,      "label": "Gibps", "long": "Gibibits/s"}),

    # Byte units (decimal SI & binary)
    ("MB/s",  {"divisor": 1000**2,        "label": "MB/s",  "long": "Megabytes/s (Decimal)"}),
    ("KB/s",  {"divisor": 1000,           "label": "KB/s",  "long": "Kilobytes/s (Decimal)"}),
    ("GB/s",  {"divisor": 1000**3,        "label": "GB/s",  "long": "Gigabytes/s (Decimal)"}),
    ("B/s",   {"divisor": 1,              "label": "B/s",   "long": "Bytes/s"}),
    ("MiB/s", {"divisor": 1024**2,        "label": "MiB/s", "long": "Mebibytes/s (Binary)"}),
    ("KiB/s", {"divisor": 1024,           "label": "KiB/s", "long": "Kibibytes/s (Binary)"}),
    ("GiB/s", {"divisor": 1024**3,        "label": "GiB/s", "long": "Gibibytes/s (Binary)"}),
])

# Total-data units (no /s) — for displaying accumulated data
TOTAL_UNITS = OrderedDict([
    ("B",   {"divisor": 1,              "label": "B",   "long": "Bytes"}),
    ("KB",  {"divisor": 1000,           "label": "KB",  "long": "Kilobytes"}),
    ("MB",  {"divisor": 1000**2,        "label": "MB",  "long": "Megabytes"}),
    ("GB",  {"divisor": 1000**3,        "label": "GB",  "long": "Gigabytes"}),
    ("TB",  {"divisor": 1000**4,        "label": "TB",  "long": "Terabytes"}),
    ("KiB", {"divisor": 1024,           "label": "KiB", "long": "Kibibytes"}),
    ("MiB", {"divisor": 1024**2,        "label": "MiB", "long": "Mebibytes"}),
    ("GiB", {"divisor": 1024**3,        "label": "GiB", "long": "Gibibytes"}),
    ("TiB", {"divisor": 1024**4,        "label": "TiB", "long": "Tebibytes"}),
])


def format_speed(bytes_per_sec, unit_key):
    """Format a speed value into the chosen unit with consistent decimal precision."""
    info = UNITS.get(unit_key, UNITS["Mb/s"])
    val = bytes_per_sec / info["divisor"]
    if val >= 1000:
        return f"{val:.1f}"
    else:
        return f"{val:.2f}"


def auto_format_total(total_bytes):
    """Auto-format total bytes with the best human-readable unit."""
    if total_bytes < 1000:
        return f"{total_bytes:.0f} B"
    elif total_bytes < 1000 ** 2:
        return f"{total_bytes / 1000:.1f} KB"
    elif total_bytes < 1000 ** 3:
        return f"{total_bytes / (1000 ** 2):.2f} MB"
    elif total_bytes < 1000 ** 4:
        return f"{total_bytes / (1000 ** 3):.2f} GB"
    else:
        return f"{total_bytes / (1000 ** 4):.2f} TB"


class NetSpeedIndicator:
    """System panel indicator that displays real-time network speed."""

    REFRESH_INTERVAL_MS = 1000  # Update every 1 second
    DATA_DIR = os.path.expanduser("~/.local/share/netspeed")
    PANEL_HEIGHT = 38  # Default base height for 40px panels
    SETTINGS_FILE = "settings.json"
    GOATCOUNTER_ENDPOINT = "https://atiq.goatcounter.com/count"

    def __init__(self):
        self._icon_dir = tempfile.mkdtemp(prefix="netspeed_")
        self._icon_flip = False

        # Load settings (unit, font, color, and analytics preferences)
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self._load_settings()

        # Daily total tracking
        self.daily_up = 0
        self.daily_down = 0
        self.today = date.today().isoformat()
        self._load_daily_totals()

        # Monthly history
        self._load_monthly_history()

        # Modal window reference (if currently open)
        self._modal_dialog = None
        self._live_labels = {}

        # Build context menu (for right-click)
        menu = Gtk.Menu()

        self.menu_item_usage = Gtk.MenuItem(label=self._get_tooltip_text(single_line=True))
        self.menu_item_usage.set_sensitive(False)
        menu.append(self.menu_item_usage)

        menu.append(Gtk.SeparatorMenuItem())

        item_settings = Gtk.MenuItem(label="Settings & Usage…")
        item_settings.connect("activate", lambda _: self._show_modal(None))
        menu.append(item_settings)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self._quit)
        menu.append(item_quit)

        menu.show_all()

        # Render initial icon
        init_name, init_path = self._render_text_icon("0.00", "0.00")

        # Initialize Indicator backend
        if USE_XAPP:
            self.status_icon = XApp.StatusIcon.new_with_name("netspeed")
            self.status_icon.set_icon_name(init_path)
            self.status_icon.set_tooltip_text(self._get_tooltip_text())
            self.status_icon.set_visible(True)

            # Left click -> Open modal directly
            self.status_icon.connect("activate", lambda icon, btn, t: self._show_modal(None))

            # Right click -> Show menu
            self.status_icon.set_secondary_menu(menu)
        else:
            self.indicator = AppIndicator3.Indicator.new(
                "netspeed-indicator",
                init_name,
                AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
            )
            self.indicator.set_icon_theme_path(self._icon_dir)
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.indicator.set_menu(menu)

        # Track previous bytes for delta calculation
        self.prev_rx, self.prev_tx = self._read_bytes()
        self.prev_time = time.monotonic()
        self._save_counter = 0

        # Current speeds for tooltip / modal
        self.current_up_bps = 0.0
        self.current_down_bps = 0.0

        # Ping GoatCounter for active-user count (runs asynchronously in background)
        self._ping_analytics(path="/app-start", title="NetSpeed")

        # Start update loop
        GLib.timeout_add(self.REFRESH_INTERVAL_MS, self._update)

    # ── GoatCounter Analytics ───────────────────────────────

    def _ping_analytics(self, path="/app-start", title="NetSpeed"):
        """Send an anonymous active user ping to GoatCounter (once per day)."""
        if not self.analytics_enabled:
            return

        today = date.today().isoformat()
        if self.last_ping_date == today:
            return  # Already counted today

        def _worker():
            try:
                url = f"{self.GOATCOUNTER_ENDPOINT}?p={path}&t={title}"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "NetSpeed-Linux/1.0.0 (X11; Linux)"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    pass
                self.last_ping_date = today
                self._save_settings()
            except Exception:
                pass  # Fail silently if offline or blocked

        threading.Thread(target=_worker, daemon=True).start()

    # ── Settings persistence ────────────────────────────────

    def _load_settings(self):
        path = os.path.join(self.DATA_DIR, self.SETTINGS_FILE)
        self.unit_key = "Mb/s"  # Default to browser speed test standard
        self.font_family = "Sans"
        self.font_size = 13  # Increased default for maximum readability
        self.color_up = [0.18, 0.90, 0.44, 1.0]    # Vibrant green
        self.color_down = [0.0, 0.85, 1.0, 1.0]     # Vibrant cyan
        self.analytics_enabled = True
        self.last_ping_date = ""
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("unit") in UNITS:
                self.unit_key = data["unit"]
            if "font_family" in data and isinstance(data["font_family"], str):
                self.font_family = data["font_family"]
            if "font_size" in data and isinstance(data["font_size"], (int, float)):
                self.font_size = max(8, min(24, int(data["font_size"])))
            if "color_up" in data and len(data["color_up"]) >= 4:
                self.color_up = [float(c) for c in data["color_up"][:4]]
            if "color_down" in data and len(data["color_down"]) >= 4:
                self.color_down = [float(c) for c in data["color_down"][:4]]
            self.analytics_enabled = data.get("analytics_enabled", True)
            self.last_ping_date = data.get("last_ping_date", "")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

    def _save_settings(self):
        path = os.path.join(self.DATA_DIR, self.SETTINGS_FILE)
        try:
            with open(path, "w") as f:
                json.dump({
                    "unit": self.unit_key,
                    "font_family": self.font_family,
                    "font_size": self.font_size,
                    "color_up": self.color_up,
                    "color_down": self.color_down,
                    "analytics_enabled": self.analytics_enabled,
                    "last_ping_date": self.last_ping_date,
                }, f, indent=2)
        except OSError:
            pass

    # ── Icon rendering (stacked U: / D:) ───────────────────

    def _render_text_icon(self, up_text, down_text):
        """Render stacked U:/D: text as an icon image in a single column.

        Uses constant layout coordinates and a constant surface width so the
        indicator NEVER shifts horizontally when digits expand or contract.
        """
        # Measure text metrics
        measure = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        ctx = cairo.Context(measure)
        ctx.select_font_face(self.font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(self.font_size)
        font_ext = ctx.font_extents()

        ascent, descent, height, _, _ = font_ext

        # Measure prefix column
        ext_u_prefix = ctx.text_extents("U:")
        ext_d_prefix = ctx.text_extents("D:")
        prefix_w = max(ext_u_prefix.width, ext_d_prefix.width)

        # Unit column
        unit_label = UNITS.get(self.unit_key, UNITS["Mb/s"])["label"]
        ext_unit = ctx.text_extents(unit_label)
        unit_w = ext_unit.width

        # Fixed width for numbers (reserves space up to 999.99 so width is stable)
        max_num_sample = "999.99"
        num_col_w = max(
            ctx.text_extents(max_num_sample).width,
            ctx.text_extents(up_text).width,
            ctx.text_extents(down_text).width
        )

        # Fixed column positions
        x_prefix = 4
        x_num_right = x_prefix + prefix_w + 5 + num_col_w
        x_unit = x_num_right + 4

        # Total constant width — rock-solid, no horizontal jittering in panel
        w = max(int(x_unit + unit_w + 6), 24)
        h = max(int(ascent + height + descent + 2), 36)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)

        # Transparent background
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)

        ctx.select_font_face(self.font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(self.font_size)

        # ── Top row: Upload ──
        r_u, g_u, b_u, a_u = self.color_up
        ctx.set_source_rgba(r_u, g_u, b_u, a_u)
        y1 = ascent + 1

        # U: prefix
        ctx.move_to(x_prefix, y1)
        ctx.show_text("U:")

        # Upload speed number (right-aligned to x_num_right for decimal stability)
        ext_up = ctx.text_extents(up_text)
        ctx.move_to(x_num_right - ext_up.width, y1)
        ctx.show_text(up_text)

        # Upload unit label (fixed position)
        ctx.move_to(x_unit, y1)
        ctx.show_text(unit_label)

        # ── Bottom row: Download ──
        r_d, g_d, b_d, a_d = self.color_down
        ctx.set_source_rgba(r_d, g_d, b_d, a_d)
        y2 = h - descent - 2

        # D: prefix
        ctx.move_to(x_prefix, y2)
        ctx.show_text("D:")

        # Download speed number (right-aligned to x_num_right for decimal stability)
        ext_dn = ctx.text_extents(down_text)
        ctx.move_to(x_num_right - ext_dn.width, y2)
        ctx.show_text(down_text)

        # Download unit label (fixed position)
        ctx.move_to(x_unit, y2)
        ctx.show_text(unit_label)

        # Alternate icon names so caching mechanisms detect changes
        self._icon_flip = not self._icon_flip
        name = "netspeed-a" if self._icon_flip else "netspeed-b"
        path = os.path.join(self._icon_dir, f"{name}.png")
        surface.write_to_png(path)
        surface.finish()

        return name, path

    def _refresh_icon(self):
        """Immediately re-render and push updated icon to panel."""
        up_text = format_speed(self.current_up_bps, self.unit_key)
        dn_text = format_speed(self.current_down_bps, self.unit_key)
        name, path = self._render_text_icon(up_text, dn_text)
        if USE_XAPP:
            self.status_icon.set_icon_name(path)
        else:
            self.indicator.set_icon_full(name, self._get_tooltip_text())
        self._update_modal_labels()

    # ── Network reading (accurate) ────────────────────────

    def _get_active_interfaces(self):
        """Get list of active (UP and non-loopback) network interfaces."""
        active = []
        sys_net = "/sys/class/net"
        try:
            for iface in os.listdir(sys_net):
                if iface == "lo" or iface.startswith(("docker", "veth", "br-", "virbr")):
                    continue
                # Check if interface is UP (operstate)
                operstate_path = os.path.join(sys_net, iface, "operstate")
                try:
                    with open(operstate_path) as f:
                        state = f.read().strip()
                    if state == "up":
                        active.append(iface)
                except (FileNotFoundError, PermissionError):
                    carrier_path = os.path.join(sys_net, iface, "carrier")
                    try:
                        with open(carrier_path) as f:
                            if f.read().strip() == "1":
                                active.append(iface)
                    except (FileNotFoundError, PermissionError, OSError):
                        pass
        except FileNotFoundError:
            pass
        return active

    def _read_bytes(self):
        """Read total received and transmitted bytes from /proc/net/dev."""
        active_ifaces = self._get_active_interfaces()
        rx_total = 0
        tx_total = 0
        try:
            with open("/proc/net/dev", "r") as f:
                for line in f:
                    line = line.strip()
                    if ":" not in line:
                        continue
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo" or iface.startswith(("docker", "veth", "br-", "virbr")):
                        continue
                    # If active interfaces detected, filter by them
                    if active_ifaces and iface not in active_ifaces:
                        continue
                    fields = data.split()
                    if len(fields) >= 9:
                        rx_total += int(fields[0])   # bytes received
                        tx_total += int(fields[8])   # bytes transmitted
        except OSError:
            pass
        return rx_total, tx_total

    # ── Daily total persistence ───────────────────────────

    def _load_daily_totals(self):
        path = os.path.join(self.DATA_DIR, "daily.json")
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("date") == self.today:
                self.daily_up = data.get("up", 0)
                self.daily_down = data.get("down", 0)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

    def _save_daily_totals(self):
        path = os.path.join(self.DATA_DIR, "daily.json")
        try:
            with open(path, "w") as f:
                json.dump({
                    "date": self.today,
                    "up": self.daily_up,
                    "down": self.daily_down
                }, f, indent=2)
        except OSError:
            pass

    # ── Monthly history persistence ───────────────────────

    def _monthly_history_path(self):
        return os.path.join(self.DATA_DIR, "monthly_history.json")

    def _load_monthly_history(self):
        self.monthly_history = {}
        path = self._monthly_history_path()
        try:
            with open(path) as f:
                self.monthly_history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

    def _save_monthly_history(self):
        path = self._monthly_history_path()
        try:
            with open(path, "w") as f:
                json.dump(self.monthly_history, f, indent=2)
        except OSError:
            pass

    def _update_monthly(self, up_bytes, down_bytes):
        month_key = date.today().strftime("%Y-%m")
        if month_key not in self.monthly_history:
            self.monthly_history[month_key] = {"up": 0, "down": 0}
        self.monthly_history[month_key]["up"] += up_bytes
        self.monthly_history[month_key]["down"] += down_bytes

    # ── Tooltip ───────────────────────────────────────────

    def _get_tooltip_text(self, single_line=False):
        """Return formatted string of today's total usage for hover tooltip."""
        up_s = auto_format_total(self.daily_up)
        down_s = auto_format_total(self.daily_down)
        tot_s = auto_format_total(self.daily_up + self.daily_down)
        if single_line:
            return f"Today: ↑ {up_s}  ↓ {down_s}  (Total: {tot_s})"
        else:
            return (
                f"Today's Data Usage:\n"
                f"  ↑ Upload:    {up_s}\n"
                f"  ↓ Download:  {down_s}\n"
                f"  Total:       {tot_s}"
            )

    # ── Modal dialog ──────────────────────────────────────

    def _show_modal(self, _widget):
        """Show settings & usage modal dialog."""
        if self._modal_dialog is not None:
            self._modal_dialog.present()
            return

        dialog = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        dialog.set_title("NetSpeed — Settings & Usage")
        dialog.set_default_size(540, 680)  # Sized so all elements + credit are visible on start
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_border_width(12)
        dialog.connect("delete-event", self._on_modal_close)

        # Main vertical container with pinned footer
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        dialog.add(main_vbox)

        # Scrollable area for content frames
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main_vbox.pack_start(scrolled, True, True, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_start(4)
        content.set_margin_end(4)
        scrolled.add(content)

        # ── 1. Unit Selection Section ──

        unit_frame = Gtk.Frame(label="  Speed Unit  ")
        unit_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        unit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        unit_box.set_margin_start(12)
        unit_box.set_margin_end(12)
        unit_box.set_margin_top(6)
        unit_box.set_margin_bottom(6)

        desc = Gtk.Label(label="Select the unit for real-time speed display:")
        desc.set_halign(Gtk.Align.START)
        unit_box.pack_start(desc, False, False, 0)

        # Group units into categories
        categories = [
            ("Bit-based (Network / Browser Speed Tests)", ["Mb/s", "Kb/s", "Gb/s", "b/s", "Mib/s", "Kib/s", "Gib/s"]),
            ("Byte-based (File Downloads / Steam)", ["MB/s", "KB/s", "GB/s", "B/s", "MiB/s", "KiB/s", "GiB/s"]),
        ]

        combo = Gtk.ComboBoxText()
        idx = 0
        active_idx = 0
        for cat_name, unit_keys in categories:
            combo.append_text(f"── {cat_name} ──")
            idx += 1
            for uk in unit_keys:
                info = UNITS[uk]
                combo.append_text(f"  {info['long']} ({info['label']})")
                if uk == self.unit_key:
                    active_idx = idx
                idx += 1

        combo.set_active(active_idx)
        combo.connect("changed", self._on_unit_changed, categories)

        unit_box.pack_start(combo, False, False, 0)
        unit_frame.add(unit_box)
        content.pack_start(unit_frame, False, False, 0)

        # ── 2. Panel Appearance (Font & Color Pickers) ──

        app_frame = Gtk.Frame(label="  Panel Appearance  ")
        app_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        app_grid = Gtk.Grid()
        app_grid.set_column_spacing(14)
        app_grid.set_row_spacing(8)
        app_grid.set_margin_start(12)
        app_grid.set_margin_end(12)
        app_grid.set_margin_top(6)
        app_grid.set_margin_bottom(6)
        app_frame.add(app_grid)
        content.pack_start(app_frame, False, False, 0)

        # Font Family Chooser
        lbl_font = Gtk.Label(label="Font Family:")
        lbl_font.set_halign(Gtk.Align.START)
        font_btn = Gtk.FontButton.new_with_font(f"{self.font_family} {self.font_size}")
        font_btn.set_show_size(False)
        font_btn.set_title("Select Panel Font")
        font_btn.connect("font-set", self._on_font_set)
        app_grid.attach(lbl_font, 0, 0, 1, 1)
        app_grid.attach(font_btn, 1, 0, 1, 1)

        # Font Size Selector
        lbl_size = Gtk.Label(label="Font Size:")
        lbl_size.set_halign(Gtk.Align.START)
        size_adj = Gtk.Adjustment(value=self.font_size, lower=8, upper=24, step_increment=1, page_increment=2)
        size_spin = Gtk.SpinButton(adjustment=size_adj, climb_rate=1, digits=0)
        size_spin.connect("value-changed", self._on_font_size_changed)
        app_grid.attach(lbl_size, 2, 0, 1, 1)
        app_grid.attach(size_spin, 3, 0, 1, 1)

        # Upload (U:) Color Picker
        lbl_col_up = Gtk.Label(label="Upload Color:")
        lbl_col_up.set_halign(Gtk.Align.START)
        r_u, g_u, b_u, a_u = self.color_up
        col_btn_up = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(r_u, g_u, b_u, a_u))
        col_btn_up.set_title("Choose Upload Font Color")
        col_btn_up.connect("color-set", self._on_color_up_set)
        app_grid.attach(lbl_col_up, 0, 1, 1, 1)
        app_grid.attach(col_btn_up, 1, 1, 1, 1)

        # Download (D:) Color Picker
        lbl_col_dn = Gtk.Label(label="Download Color:")
        lbl_col_dn.set_halign(Gtk.Align.START)
        r_d, g_d, b_d, a_d = self.color_down
        col_btn_dn = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(r_d, g_d, b_d, a_d))
        col_btn_dn.set_title("Choose Download Font Color")
        col_btn_dn.connect("color-set", self._on_color_dn_set)
        app_grid.attach(lbl_col_dn, 2, 1, 1, 1)
        app_grid.attach(col_btn_dn, 3, 1, 1, 1)

        # ── 3. Current Speed Section ──

        speed_frame = Gtk.Frame(label="  Current Speed  ")
        speed_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        speed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        speed_box.set_margin_start(12)
        speed_box.set_margin_end(12)
        speed_box.set_margin_top(6)
        speed_box.set_margin_bottom(6)

        self._live_labels["speed_up"] = Gtk.Label()
        self._live_labels["speed_up"].set_halign(Gtk.Align.START)
        speed_box.pack_start(self._live_labels["speed_up"], False, False, 0)

        self._live_labels["speed_dn"] = Gtk.Label()
        self._live_labels["speed_dn"].set_halign(Gtk.Align.START)
        speed_box.pack_start(self._live_labels["speed_dn"], False, False, 0)

        speed_frame.add(speed_box)
        content.pack_start(speed_frame, False, False, 0)

        # ── 4. Today's Usage Section ──

        today_frame = Gtk.Frame(label="  Today's Usage  ")
        today_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        today_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        today_box.set_margin_start(12)
        today_box.set_margin_end(12)
        today_box.set_margin_top(6)
        today_box.set_margin_bottom(6)

        self._live_labels["today_up"] = Gtk.Label()
        self._live_labels["today_up"].set_halign(Gtk.Align.START)
        today_box.pack_start(self._live_labels["today_up"], False, False, 0)

        self._live_labels["today_dn"] = Gtk.Label()
        self._live_labels["today_dn"].set_halign(Gtk.Align.START)
        today_box.pack_start(self._live_labels["today_dn"], False, False, 0)

        self._live_labels["today_tot"] = Gtk.Label()
        self._live_labels["today_tot"].set_halign(Gtk.Align.START)
        today_box.pack_start(self._live_labels["today_tot"], False, False, 0)

        today_frame.add(today_box)
        content.pack_start(today_frame, False, False, 0)

        # ── 5. Monthly History Section ──

        month_frame = Gtk.Frame(label="  Monthly Usage History  ")
        month_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        month_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        month_box.set_margin_start(12)
        month_box.set_margin_end(12)
        month_box.set_margin_top(6)
        month_box.set_margin_bottom(6)

        if self.monthly_history:
            store = Gtk.ListStore(str, str, str, str)
            sorted_months = sorted(self.monthly_history.keys(), reverse=True)
            for month_key in sorted_months:
                rec = self.monthly_history[month_key]
                up = rec.get("up", 0)
                down = rec.get("down", 0)
                total = up + down
                try:
                    dt = datetime.strptime(month_key, "%Y-%m")
                    month_display = dt.strftime("%B %Y")
                except ValueError:
                    month_display = month_key

                store.append([
                    month_display,
                    auto_format_total(up),
                    auto_format_total(down),
                    auto_format_total(total),
                ])

            tree = Gtk.TreeView(model=store)
            tree.set_headers_visible(True)
            tree.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

            for i, title in enumerate(["Month", "Upload", "Download", "Total"]):
                renderer = Gtk.CellRendererText()
                if i == 0:
                    renderer.set_property("weight", Pango.Weight.BOLD)
                col = Gtk.TreeViewColumn(title, renderer, text=i)
                col.set_expand(True)
                col.set_resizable(True)
                tree.append_column(col)

            scroll_tree = Gtk.ScrolledWindow()
            scroll_tree.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll_tree.set_min_content_height(110)
            scroll_tree.add(tree)
            month_box.pack_start(scroll_tree, True, True, 0)
        else:
            lbl_empty = Gtk.Label(label="No monthly usage data recorded yet.")
            lbl_empty.set_halign(Gtk.Align.START)
            month_box.pack_start(lbl_empty, False, False, 0)

        month_frame.add(month_box)
        content.pack_start(month_frame, True, True, 0)

        # ── 6. Anonymous Analytics Preference ──
        chk_analytics = Gtk.CheckButton.new_with_label("Send anonymous active-user ping to help developer track stats")
        chk_analytics.set_active(self.analytics_enabled)
        chk_analytics.connect("toggled", self._on_analytics_toggled)
        content.pack_start(chk_analytics, False, False, 2)

        # ── Pinned Footer: Creator Credit & Close Button (Always in Viewport) ──
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.set_margin_top(4)
        footer.set_margin_bottom(2)

        lbl_creator = Gtk.Label()
        lbl_creator.set_markup("<i>Github: <a href='https://github.com/atikrony'>@atikrony</a></i>")
        lbl_creator.set_halign(Gtk.Align.START)
        footer.pack_start(lbl_creator, False, False, 0)

        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda _: self._close_modal())
        footer.pack_end(btn_close, False, False, 0)

        main_vbox.pack_end(footer, False, False, 0)

        self._modal_dialog = dialog
        self._update_modal_labels()
        dialog.show_all()

    # ── Appearance callbacks ──────────────────────────────

    def _on_font_set(self, font_btn):
        desc = font_btn.get_font_desc()
        if desc:
            fam = desc.get_family()
            if fam:
                self.font_family = fam
            self._save_settings()
            self._refresh_icon()

    def _on_font_size_changed(self, spin):
        self.font_size = int(spin.get_value())
        self._save_settings()
        self._refresh_icon()

    def _on_color_up_set(self, col_btn):
        rgba = col_btn.get_rgba()
        self.color_up = [rgba.red, rgba.green, rgba.blue, rgba.alpha]
        self._save_settings()
        self._refresh_icon()

    def _on_color_dn_set(self, col_btn):
        rgba = col_btn.get_rgba()
        self.color_down = [rgba.red, rgba.green, rgba.blue, rgba.alpha]
        self._save_settings()
        self._refresh_icon()

    def _on_analytics_toggled(self, check_btn):
        self.analytics_enabled = check_btn.get_active()
        self._save_settings()

    def _update_modal_labels(self):
        """Update live text in modal if open."""
        if not self._modal_dialog or not self._live_labels:
            return

        unit_label = UNITS.get(self.unit_key, UNITS["Mb/s"])["label"]
        up_str = format_speed(self.current_up_bps, self.unit_key)
        dn_str = format_speed(self.current_down_bps, self.unit_key)

        r_u, g_u, b_u, _ = self.color_up
        r_d, g_d, b_d, _ = self.color_down
        hex_u = f"#{int(r_u*255):02x}{int(g_u*255):02x}{int(b_u*255):02x}"
        hex_d = f"#{int(r_d*255):02x}{int(g_d*255):02x}{int(b_d*255):02x}"

        self._live_labels["speed_up"].set_markup(f"<b>Upload:</b>   <span color='{hex_u}' weight='bold'>{up_str} {unit_label}</span>")
        self._live_labels["speed_dn"].set_markup(f"<b>Download:</b> <span color='{hex_d}' weight='bold'>{dn_str} {unit_label}</span>")

        self._live_labels["today_up"].set_markup(f"<b>Upload:</b>   {auto_format_total(self.daily_up)}")
        self._live_labels["today_dn"].set_markup(f"<b>Download:</b> {auto_format_total(self.daily_down)}")
        self._live_labels["today_tot"].set_markup(f"<b>Total:</b>    <span color='#27ae60' weight='bold'>{auto_format_total(self.daily_up + self.daily_down)}</span>")

    def _on_modal_close(self, widget, event):
        self._close_modal()
        return True

    def _close_modal(self):
        if self._modal_dialog:
            self._modal_dialog.destroy()
            self._modal_dialog = None
            self._live_labels.clear()

    def _on_unit_changed(self, combo, categories):
        """Handle unit combo box change."""
        text = combo.get_active_text()
        if text is None or text.startswith("──"):
            return  # Category header, ignore

        # Map display text back to unit key
        for _cat_name, unit_keys in categories:
            for uk in unit_keys:
                info = UNITS[uk]
                if f"  {info['long']} ({info['label']})" == text:
                    self.unit_key = uk
                    self._save_settings()
                    self._refresh_icon()
                    return

    # ── Update loop ───────────────────────────────────────

    def _update(self):
        """Calculate speed and update the indicator icon."""
        now = time.monotonic()
        dt = now - self.prev_time
        if dt <= 0:
            return True

        rx, tx = self._read_bytes()

        down_bytes = max(0, rx - self.prev_rx)
        up_bytes = max(0, tx - self.prev_tx)

        # Handle counter reset (e.g. interface bounce)
        if down_bytes > 10 * 1024**3 or up_bytes > 10 * 1024**3:
            down_bytes = 0
            up_bytes = 0

        down_bps = down_bytes / dt
        up_bps = up_bytes / dt

        # Instantaneous speeds for accurate matching with browser speed tests
        self.current_up_bps = up_bps
        self.current_down_bps = down_bps

        # Day rollover check
        today = date.today().isoformat()
        if today != self.today:
            self._save_daily_totals()
            self.today = today
            self.daily_up = 0
            self.daily_down = 0
            # Daily active user ping
            self._ping_analytics(path="/app-active", title="NetSpeed Active")

        # Accumulate daily totals
        self.daily_up += up_bytes
        self.daily_down += down_bytes

        # Accumulate monthly totals
        self._update_monthly(up_bytes, down_bytes)

        self.prev_rx = rx
        self.prev_tx = tx
        self.prev_time = now

        # Re-render icon with updated speed
        up_text = format_speed(up_bps, self.unit_key)
        dn_text = format_speed(down_bps, self.unit_key)
        name, path = self._render_text_icon(up_text, dn_text)
        tooltip = self._get_tooltip_text()

        if USE_XAPP:
            self.status_icon.set_icon_name(path)
            self.status_icon.set_tooltip_text(tooltip)
        else:
            self.indicator.set_icon_full(name, tooltip)

        # Update menu usage label
        self.menu_item_usage.set_label(self._get_tooltip_text(single_line=True))

        # Live update modal if currently open
        self._update_modal_labels()

        # Save totals to disk every ~30 seconds
        self._save_counter += 1
        if self._save_counter >= 30:
            self._save_counter = 0
            self._save_daily_totals()
            self._save_monthly_history()

        return True

    def _quit(self, _widget):
        self._save_daily_totals()
        self._save_monthly_history()
        Gtk.main_quit()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    NetSpeedIndicator()
    Gtk.main()


if __name__ == "__main__":
    main()
