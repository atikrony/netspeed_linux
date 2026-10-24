<p align="center">
  <img src="netspeed.png" alt="NetSpeed Logo" width="128" height="128" />
</p>

# NetSpeed

NetSpeed is a lightweight Linux panel indicator for monitoring real-time
network speed. It displays upload and download throughput directly in the
system panel and keeps track of daily and monthly data usage.

![NetSpeed](https://img.shields.io/badge/platform-Linux-FCC624?logo=linux&logoColor=black)
![Python](https://img.shields.io/badge/python-3-blue?logo=python)
![License](https://img.shields.io/badge/license-see%20repository-lightgrey)

## Features

- Real-time upload and download speeds updated every second
- Compact stacked `U:` and `D:` panel display
- Support for bit and byte units, including Mbps, Kbps, Gbps, MB/s, KB/s,
  MiB/s, and more
- Automatic detection of active network interfaces
- Daily upload, download, and total usage tracking
- Monthly usage history
- Hover tooltip showing today's data usage
- Custom font family and font size
- Separate upload and download colors
- Native XApp status icon support on Linux Mint/Cinnamon
- AppIndicator3 fallback for other supported desktop environments
- Optional anonymous daily active-user analytics, which can be disabled in
  Settings
- Starts automatically when you log in

## Supported Systems

NetSpeed is designed for Debian-based Linux distributions, including:

- Ubuntu
- Debian
- Linux Mint
- Cinnamon and other GTK-based desktop environments

The application uses XApp on Cinnamon when available and otherwise uses
AppIndicator3 or Ayatana AppIndicator.

## Installation

### Install with the provided script

Clone or download this repository, then run:

```bash
chmod +x install.sh
./install.sh
```

The installer checks for required dependencies, installs missing Debian
packages, copies NetSpeed to the local user data directory, and enables
desktop autostart.

### Install the `.deb` package

The repository includes a Debian package:

```bash
sudo apt install ./netspeed_1.0.0.deb
```

To build a fresh package from the source files:

```bash
./build-deb.sh
sudo apt install ./netspeed_1.0.0.deb
```

## Dependencies

The installer manages the required packages on supported Debian-based
systems. NetSpeed requires:

- Python 3
- GTK 3
- PyGObject
- Pycairo
- XApp, AppIndicator3, or Ayatana AppIndicator

## Usage

After installation, NetSpeed starts automatically with your desktop session.
You can also launch it manually with:

```bash
netspeed
```

The panel indicator displays the current upload and download speeds. Hover
over it to see today's usage. Left-click the indicator, or select
**Settings & Usage** from the context menu, to:

- Choose the speed unit
- Change the panel font and font size
- Select upload and download colors
- View current speed and today's usage
- Review monthly usage history
- Enable or disable anonymous analytics

Right-click the indicator to open the settings window or quit NetSpeed.

## Data Storage

Local settings and usage data are stored in:

```text
~/.local/share/netspeed/
```

This includes the application settings, daily totals, and monthly usage
history. Network counters are read locally from the Linux system interfaces;
NetSpeed does not perform a speed test or send network traffic to measure
throughput.

NetSpeed optionally sends one anonymous active-user request per day to
GoatCounter (https://netspeed-linux.goatcounter.com) to help the developer understand usage. This option is enabled
by default and can be disabled from **Settings & Usage**. No network speed,
interface name, or usage totals are included in the analytics request.

<script data-goatcounter="https://netspeed-linux.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>

## Uninstallation

To remove both local and package installations:

```bash
./uninstall.sh
```

If NetSpeed was installed as a Debian package, it can also be removed with:

```bash
sudo apt remove netspeed
```

## License

See the repository for the applicable license information.
