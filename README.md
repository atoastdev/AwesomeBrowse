# AwesomeBrowse 2.1.21-Renovo Hotfix

Renovo is the first GA line of AwesomeBrowse 2, built with PyQt6 and Qt WebEngine. This hotfix keeps the sidebar rail separate from its panels, adds a preview page for the upcoming extensions store, and tightens extension package handling.

## Features

- Sleek floating-tab interface with 29 themes and matching wallpapers
- Tab groups and workspaces
- Chrome extension support (content scripts, storage, i18n)
- Permission review before installing extensions, isolated extension origins and bounded safe archive extraction
- Awesome Extensions Store preview at `awesome://extensionstore` (the store itself is coming soon)
- Built-in RAM limiter with graceful degradation
- YouTube Music player in the sidebar with a pinnable mini player
- Reader mode, focus mode, command palette, notes, web panels
- Selectable Renovo install with optional AwesomeSpace new-tab widgets
- Wallpaper-backed translucent tabs, address bar, and toolbar pills
- Hover-to-open sidebar with a setting to pin it visible; bookmarks bar is hidden by default
- Live downloads pop-up with transfer progress, elapsed time, and speed
- Print preview with installed-printer selection and PDF output
- Per-site prompts for notifications, microphones, and cameras, with in-browser notification cards
- Tab group chips and brief interface animations

## System requirements

Python 3.10+, PyQt6 6.6+, PyQt6-WebEngine 6.6+, and psutil. QtMultimedia bindings are included with PyQt6; Linux users also need the Qt system libraries listed below.

Debian / Ubuntu:

    sudo apt install python3 python3-venv \
        libnss3 libasound2 libxkbcommon-x11-0 libgl1 \
        libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
        libxcb-shape0 libxcb-xinerama0 libxcb-xkb1

Fedora:

    sudo dnf install python3 python3-virtualenv \
        nss alsa-lib libxkbcommon-x11 mesa-libGL \
        xcb-util-cursor xcb-util-wm

Arch:

    sudo pacman -S python nss alsa-lib libxkbcommon xcb-util-cursor \
        xcb-util-wm gl

## Install

    git clone https://github.com/atoastdev/awesomebrowse.git
    cd awesomebrowse
    ./install.sh

The installer asks which edition to install before it creates a virtual
environment. Choose **AwesomeBrowse 2.1.21-Renovo Hotfix** or **AwesomeBrowse
2.1.21-Renovo Hotfix with AwesomeSpace**. You can also select with
`./install.sh --edition stable` or `./install.sh --edition space`. The choice
is saved in the launcher, so it stays active after installation.

Run it with:

    awesomebrowse
If that fails:

    python3 awesomebrowse_2.1.21_renovo_hotfix.py

Or with flags:

    awesomebrowse --private
    awesomebrowse --profile <id>
    awesomebrowse --safe-mode

## Uninstall

    rm ~/.local/bin/awesomebrowse
    rm ~/.local/share/applications/awesomebrowse.desktop
    rm -rf .venv

Profile data lives at ~/.local/share/AwesomeBrowse2/. Delete that folder
too if you want to remove everything.

## Known limitations

- The hard heap cap relies on Chromium flags honoured by your QtWebEngine
  build. If your distro patches QtWebEngine, the cap may be silently ignored.
- Chrome extensions are supported through a compatibility layer (content
  scripts, chrome.storage, chrome.runtime, chrome.i18n). Anything depending
  on a background service worker, webRequest blocking, or native messaging
  will install but stay idle. Review permissions before installing extensions;
  only install extensions from sources you trust. The Awesome Extensions Store
  is a placeholder, not a live catalogue.
- Tab sleeping uses Chromium's Discarded lifecycle state. A tab with unsaved
  form data can lose that data when slept.
- CAPTCHA behavior is controlled by each site. Renovo uses Qt WebEngine's native Chromium identity for compatibility and does not bypass site checks.
## Licence

GPL-3.0. See LICENSE.
README_END
