#!/usr/bin/env python3
"""
AwesomeBrowse 2  (2.1.2-Renovo, first GA release)
A clean, themeable, Chromium-based browser built on Qt WebEngine.

    pip install -r requirements.txt   # PyQt6, PyQt6-WebEngine, psutil (QtMultimedia is included with PyQt6)
    python awesomebrowse_2.1.2_renovo.py [url ...] [--private] [--profile ID] [--safe-mode]
"""
from __future__ import annotations

import copy
import io
import json
import math
import mimetypes
import os
import random
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from string import Template
from html import escape as html_escape
from urllib.parse import quote_plus

from PyQt6.QtCore import (QBuffer, QByteArray, QCoreApplication, QEasingCurve, QEvent, QEventLoop, QFile, QIODevice,
                          QMarginsF, QObject, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, QStandardPaths,
                          QStringListModel, Qt, QThread, QTimer, QUrl, QVariantAnimation, pyqtSignal,
                          pyqtSlot)
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QFontMetrics, QIcon, QKeySequence,
                         QLinearGradient, QMovie, QPageLayout, QPageSize, QPainter, QPainterPath, QPalette, QPen,
                         QPixmap, QTextCursor, QPolygonF, QShortcut)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtNetwork import QAuthenticator, QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtPrintSupport import QPrintPreviewWidget, QPrinter, QPrinterInfo
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import (QWebEngineContextMenuRequest, QWebEngineDownloadRequest,
                                   QWebEngineNotification, QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
                                   QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor,
                                   QWebEngineUrlRequestJob, QWebEngineUrlScheme,
                                   QWebEngineUrlSchemeHandler)
from PyQt6.QtWebEngineWidgets import QWebEngineView
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget
except ImportError:  # Static wallpapers still work when Qt Multimedia is unavailable.
    QAudioOutput = QMediaPlayer = QVideoWidget = None
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QCompleter, QDialog,
                             QCheckBox, QDockWidget, QFileDialog, QFrame, QGraphicsBlurEffect,
                             QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                             QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget, QTabBar,
                             QToolButton, QVBoxLayout, QWidget, QWidgetAction)

APP_NAME = "AwesomeBrowse 2"
SPACE_EDITION = os.environ.get("AWESOMEBROWSE_EDITION", "stable").strip().lower() == "space"
APP_VERSION = "2.1.2-Renovo"
SCHEME = "awesome"
NEWTAB = "awesome://newtab"

# ═════════════════════════════════════════════════════════════════════════════
#  Static data
# ═════════════════════════════════════════════════════════════════════════════

ENGINES = [
    ("google", "Google", "https://www.google.com/search?q=%s"),
    ("duckduckgo", "DuckDuckGo", "https://duckduckgo.com/?q=%s"),
    ("bing", "Bing", "https://www.bing.com/search?q=%s"),
    ("brave", "Brave Search", "https://search.brave.com/search?q=%s"),
    ("ecosia", "Ecosia", "https://www.ecosia.org/search?q=%s"),
    ("startpage", "Startpage", "https://www.startpage.com/do/search?q=%s"),
    ("yahoo", "Yahoo", "https://search.yahoo.com/search?p=%s"),
]
ENGINE_BY_ID = {e[0]: e for e in ENGINES}

AVATAR_COLORS = ["#5b8cff", "#9b6bff", "#e5589f", "#f0883e", "#e8b13a", "#3fb97f", "#2bb5c7", "#8a93a6"]

DEFAULT_WIDGETS = [
    ("YouTube", "https://www.youtube.com"), ("GitHub", "https://github.com"),
    ("Reddit", "https://www.reddit.com"), ("Wikipedia", "https://www.wikipedia.org"),
    ("Gmail", "https://mail.google.com"), ("Maps", "https://maps.google.com"),
]
if SPACE_EDITION:
    DEFAULT_WIDGETS.insert(0, ("AwesomeSpace", "awesome://space"))

TRACKER_DOMAINS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com",
    "google-analytics.com", "googletagservices.com", "adnxs.com", "taboola.com", "outbrain.com",
    "scorecardresearch.com", "criteo.com", "criteo.net", "pubmatic.com", "rubiconproject.com",
    "amazon-adsystem.com", "moatads.com", "adsrvr.org", "openx.net", "casalemedia.com",
    "quantserve.com", "hotjar.com", "mixpanel.com", "segment.io", "fullstory.com",
)

TRACKER_SET = frozenset(TRACKER_DOMAINS)


def is_tracker_host(host: str) -> bool:
    while host:
        if host in TRACKER_SET:
            return True
        host = host.partition(".")[2]
    return False


ACCOUNT_SERVICES = [
    ("google", "Google", "https://accounts.google.com/"), ("github", "GitHub", "https://github.com/login"),
    ("microsoft", "Microsoft", "https://login.live.com/"), ("discord", "Discord", "https://discord.com/login"),
    ("reddit", "Reddit", "https://www.reddit.com/login"), ("x", "X", "https://x.com/i/flow/login"),
    ("spotify", "Spotify", "https://accounts.spotify.com/login"), ("twitch", "Twitch", "https://www.twitch.tv/login"),
    ("apple", "Apple", "https://appleid.apple.com/sign-in"), ("custom", "Other site", ""),
]


def _lum(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(a: str, b: str, t: float) -> str:
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _on_color(accent: str) -> str:
    return "#0b0f1a" if _lum(accent) > 150 else "#ffffff"


def _theme(label, kind, bg, surface, surface2, text, sub, accent, border, hover, wall) -> dict:
    return dict(label=label, kind=kind, bg=bg, surface=surface, surface2=surface2, text=text, sub=sub,
                accent=accent, on_accent=_on_color(accent), border=border, hover=hover, wall=wall)


# key: (label, kind, bg, surface, surface2, text, sub, accent, border, hover, wallpaper(style, c1, c2, c3))
THEMES = {
    # originals (keys kept so existing profiles keep working)
    "dark": _theme("Dark", "dark", "#141416", "#1f1f23", "#2a2a30", "#ececf1", "#9b9ba8", "#8ab4ff", "#33333b", "#2d2d34",
                   ("ridges", "#3b4a8c", "#1d2250", "#8ab4ff")),
    "light": _theme("Light", "light", "#dfe3ea", "#fbfbfd", "#eceef3", "#1b1d22", "#666c78", "#2f6bff", "#d3d7df", "#e6e9f0",
                    ("ridges", "#7fa6ff", "#2f6bff", "#ffe2b8")),
    "midnight": _theme("Midnight blue", "dark", "#070b17", "#0e1630", "#16224a", "#e4ebff", "#8795bd", "#5ea0ff", "#1f2d5a", "#1a2851",
                       ("orbits", "#5ea0ff", "#7a5cff", "#1fd1ff")),
    "cream": _theme("Cream", "light", "#e6dcc4", "#f9f3e4", "#efe6d0", "#3a3224", "#85795f", "#b4692a", "#d8cbae", "#ebe1c8",
                    ("ridges", "#e0b27a", "#b4692a", "#fff0cf")),
    # more dark
    "graphite": _theme("Graphite", "dark", "#161819", "#202325", "#2b2f32", "#e6e8ea", "#98a0a6", "#7fd1b9", "#343a3e", "#2f3438",
                       ("ridges", "#2f4650", "#1b252b", "#7fd1b9")),
    "nord": _theme("Nord", "dark", "#242933", "#2e3440", "#3b4252", "#eceff4", "#9aa5b8", "#88c0d0", "#434c5e", "#3b4252",
                   ("waves", "#88c0d0", "#5e81ac", "#eceff4")),
    "dracula": _theme("Dracula", "dark", "#1e1f29", "#282a36", "#343746", "#f8f8f2", "#9aa0c0", "#bd93f9", "#44475a", "#3a3d4f",
                      ("blobs", "#bd93f9", "#ff79c6", "#8be9fd")),
    "tokyo": _theme("Tokyo night", "dark", "#16161e", "#1a1b26", "#24283b", "#c0caf5", "#7f8bb3", "#7aa2f7", "#2f334d", "#292e42",
                    ("mesh", "#7aa2f7", "#bb9af7", "#f7768e")),
    "gruvbox": _theme("Gruvbox", "dark", "#1d2021", "#282828", "#3c3836", "#ebdbb2", "#a89984", "#fabd2f", "#504945", "#3c3836",
                      ("ridges", "#d65d0e", "#cc241d", "#fabd2f")),
    "mocha": _theme("Mocha", "dark", "#11111b", "#1e1e2e", "#313244", "#cdd6f4", "#9399b2", "#cba6f7", "#45475a", "#313244",
                    ("blobs", "#cba6f7", "#f5c2e7", "#89b4fa")),
    "rosepine": _theme("Rosé pine", "dark", "#191724", "#1f1d2e", "#26233a", "#e0def4", "#908caa", "#ebbcba", "#403d52", "#2a2740",
                       ("orbits", "#eb6f92", "#c4a7e7", "#31748f")),
    "everforest": _theme("Everforest", "dark", "#232a2e", "#2d353b", "#343f44", "#d3c6aa", "#9da9a0", "#a7c080", "#475258", "#3a464c",
                         ("ridges", "#3f6b4f", "#83c092", "#d3c6aa")),
    "ayu": _theme("Ayu mirage", "dark", "#151a23", "#1f2430", "#2a3040", "#cbccc6", "#8a919e", "#ffcc66", "#343b4c", "#2a3040",
                  ("waves", "#ffcc66", "#73d0ff", "#f28779")),
    "abyss": _theme("Abyss", "dark", "#000000", "#0b0b0d", "#17171b", "#e8e8ee", "#8a8a96", "#ff5c7a", "#1f1f26", "#17171b",
                    ("mesh", "#ff5c7a", "#7a5cff", "#00d1ff")),
    "crimson": _theme("Crimson", "dark", "#1a0e11", "#24141a", "#321c24", "#f3dde2", "#b58c96", "#ff6b81", "#4a2a34", "#3a2029",
                      ("ridges", "#b8264b", "#5a1328", "#ffb199")),
    "amethyst": _theme("Amethyst", "dark", "#140f1f", "#1d1630", "#2a2044", "#e9e1ff", "#a597cc", "#b388ff", "#3a2d5c", "#2e2450",
                       ("blobs", "#b388ff", "#ff7ac6", "#6ea8ff")),
    "deepsea": _theme("Deep sea", "dark", "#06141b", "#0b2230", "#12354a", "#dff3fb", "#86aebf", "#3dd6d0", "#1b4a63", "#164058",
                      ("waves", "#3dd6d0", "#1e88b5", "#0a4a7a")),
    "solardark": _theme("Solarized dark", "dark", "#00212b", "#002b36", "#073642", "#eee8d5", "#93a1a1", "#2aa198", "#0f4753", "#073642",
                        ("orbits", "#2aa198", "#268bd2", "#b58900")),
    # more light
    "paper": _theme("Paper", "light", "#ecebe7", "#fbfaf7", "#f1efe9", "#26231f", "#7a756b", "#c2410c", "#dedbd2", "#e8e5dc",
                    ("ridges", "#d9a066", "#c2410c", "#f3e3c7")),
    "latte": _theme("Latte", "light", "#dce0e8", "#eff1f5", "#e6e9ef", "#4c4f69", "#7c7f93", "#8839ef", "#ccd0da", "#e0e4ec",
                    ("blobs", "#8839ef", "#ea76cb", "#1e66f5")),
    "solarlight": _theme("Solarized light", "light", "#eee8d5", "#fdf6e3", "#f4eed9", "#586e75", "#93a1a1", "#268bd2", "#ded7bf", "#efe9d2",
                         ("orbits", "#268bd2", "#2aa198", "#b58900")),
    "dawn": _theme("Dawn", "light", "#f2e9e1", "#faf4ed", "#f4ede8", "#575279", "#9893a5", "#d7827e", "#dfdad9", "#efe6e0",
                   ("blobs", "#d7827e", "#907aa9", "#56949f")),
    "gruvlight": _theme("Gruvbox light", "light", "#ebdbb2", "#fbf1c7", "#f2e5bc", "#3c3836", "#7c6f64", "#b57614", "#d5c4a1", "#eddcae",
                        ("ridges", "#d79921", "#cc241d", "#98971a")),
    "sakura": _theme("Sakura", "light", "#f6e4ea", "#fff6f9", "#fbebf1", "#4a2c37", "#9a7a86", "#e0457b", "#efd2dc", "#f9e4ec",
                     ("blobs", "#f48fb1", "#e0457b", "#ffd1dc")),
    "mint": _theme("Mint", "light", "#dcece4", "#f4fbf7", "#e6f3ec", "#1f3a30", "#69877a", "#1f9d6b", "#c8e0d4", "#dff0e7",
                   ("waves", "#1f9d6b", "#7fd6b0", "#bfeedd")),
    "sky": _theme("Sky", "light", "#dbe8f5", "#f5f9fe", "#e6eff9", "#1b2f45", "#667f99", "#2a7de1", "#c5d8ec", "#deeaf7",
                  ("ridges", "#2a7de1", "#7fb5f0", "#f6d6a8")),
    "lavender": _theme("Lavender", "light", "#e6e1f2", "#f8f6fd", "#eeeaf8", "#2c2545", "#7d759b", "#7c5ce0", "#d6cfea", "#e9e4f5",
                       ("mesh", "#7c5ce0", "#c3a6ff", "#ff9ec7")),
    "sand": _theme("Sand", "light", "#e8dccb", "#f8f1e6", "#efe5d4", "#3b3125", "#8a7b66", "#c7782c", "#dccdb5", "#ebe0cc",
                   ("ridges", "#e0a96d", "#c7782c", "#8a5a2b")),
    "arctic": _theme("Arctic", "light", "#e3eaf0", "#f7fafc", "#ebf0f5", "#1d2b36", "#6b7f8f", "#00a3c4", "#cfdbe5", "#e2e9ef",
                     ("waves", "#00a3c4", "#8fd3e8", "#e6f6fb")),
}


def _with_accent(t: dict, store) -> dict:
    t = dict(t)
    acc = store.data.get("accent", "") if hasattr(store, "data") else ""
    if isinstance(acc, str) and re.match(r"^#[0-9a-fA-F]{6}$", acc):
        t["accent"], t["on_accent"] = acc, _on_color(acc)
    return t


def resolve_theme(store) -> dict:
    """The active theme for a profile, including its personal accent colour."""
    return _with_accent(THEMES.get(store["theme"], THEMES["dark"]), store)


SETTING_TYPES = {
    "name": str, "color": str, "theme": str, "search_engine": str, "startup": str, "homepage": str,
    "show_bookmarks_bar": bool, "show_home_button": bool, "keep_cookies": bool,
    "block_third_party_cookies": bool, "block_trackers": bool, "send_dnt": bool,
    "force_dark_pages": bool, "ask_download_location": bool, "zoom_default": int,
    "wallpaper": str, "wallpaper_dim": int, "wallpaper_blur": int, "show_clock": bool,
    "show_widgets": bool, "clock_24h": bool,
    "description": str, "accent": str, "avatar_emoji": str, "animations": bool, "smooth_scroll": bool,
    "lazy_restore": bool, "zoom_per_site": bool, "sidebar_open": bool, "sidebar_always_visible": bool,
    "edition": str, "mini_player": bool,
}

ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def web_vars(t: dict) -> dict:
    """CSS custom properties handed to the internal pages."""
    return {
        "bg": t["bg"], "surface": t["surface"], "surface2": t["surface2"], "text": t["text"],
        "sub": t["sub"], "accent": t["accent"], "on-accent": t["on_accent"], "border": t["border"],
        "hover": t["hover"], "accent-soft": rgba(t["accent"], 0.22),
        "glass": rgba(t["surface"], 0.74), "glass-border": rgba(t["text"], 0.16),
    }


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


# ═════════════════════════════════════════════════════════════════════════════
#  Qt styling and vector icons
# ═════════════════════════════════════════════════════════════════════════════

QSS = Template(r"""
QWidget { color: $text; font-size: 13px; }
QMainWindow, QDialog, QMessageBox, QInputDialog, QFileDialog { background: $bg; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 5px 8px; border-radius: 6px; }
#root, #chrome, #strip, #toolbar, #bookmarkbar, #browserBody, #viewhost { background: transparent; border: none; }
#toolbar { border-bottom: 1px solid $glass_border; }
#bookmarkbar { border-top: 1px solid $glass_border; }
#findbar { background: $surface; border-top: 1px solid $border; }
QToolButton { background: transparent; border: none; border-radius: 10px; }
QToolButton:hover { background: $hover; }
QToolButton:pressed { background: $border; }
QToolButton#bm { padding: 0 9px; color: $text; border-radius: 7px; }
QToolButton#tabclose { border-radius: 9px; padding: 0; margin: 0; }
QToolButton#tabclose:hover { background: $border_a; }
QToolButton::menu-indicator { image: none; }
QLineEdit { background: $surface2; border: 1px solid transparent; border-radius: 17px; padding: 0 10px;
            selection-background-color: $accent; selection-color: $on_accent; }
QLineEdit:hover { border-color: $border; }
QLineEdit:focus { border-color: $accent; background: $surface; }
QLineEdit#find, QLineEdit#field { border-radius: 9px; border-color: $border; padding: 0 12px; min-height: 36px; }
QLineEdit#address { background: $glass; border: 1px solid $glass_border; border-radius: 20px; padding: 0 15px; }
QLineEdit#address:hover { border-color: $glass_highlight; }
QLineEdit#address:focus { background: $glass; border-color: $accent; }
QTabBar { background: transparent; }
QTabBar::tab { background: $glass; color: $text; margin: 4px 3px 3px 2px; padding: 0 9px 0 11px;
               border: 1px solid $glass_border; border-radius: 14px; }
QTabBar::tab:hover:!selected { background: $surface_a; border-color: $glass_highlight; }
QTabBar::tab:selected { background: $glass; border-color: $glass_highlight; color: $text; }
#toolbar QToolButton { background: $glass; border: 1px solid $glass_border; border-radius: 17px; }
#toolbar QToolButton:hover { background: $surface_a; border-color: $glass_highlight; }
#toolbar QToolButton:pressed { background: $hover; }
QProgressBar { border: none; background: transparent; max-height: 2px; min-height: 2px; }
QProgressBar::chunk { background: $accent; }
QMenu { background: $surface; border: 1px solid $border; border-radius: 12px; padding: 6px; }
QMenu::item { padding: 7px 30px 7px 14px; border-radius: 7px; margin: 1px 0; }
QMenu::item:selected { background: $hover; }
QMenu::item:disabled { color: $sub; }
QMenu::separator { height: 1px; background: $border; margin: 5px 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QDockWidget::title { background: $surface; padding: 6px 12px; border-top: 1px solid $border; }
QPushButton { background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 9px 20px; }
QPushButton:hover { background: $hover; }
QPushButton:disabled { color: $sub; }
QPushButton[primary="true"] { background: $accent; color: $on_accent; border: none; font-weight: 600; }
QPushButton[primary="true"]:disabled { background: $border; color: $sub; }
QPushButton[ghost="true"] { background: transparent; border: none; color: $sub; }
QPushButton[ghost="true"]:hover { color: $text; }
QPushButton[choice="true"] { padding: 10px 16px; }
QPushButton[choice="true"]:checked { border: 2px solid $accent; background: $surface; font-weight: 600; }
QLabel#overlay { background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 6px 12px; }
QLabel#badge { background: $surface2; border-radius: 10px; padding: 3px 12px; color: $sub; }
QLabel#h1 { font-size: 28px; font-weight: 700; }
QLabel#lead { color: $sub; font-size: 14px; }
QLabel#muted { color: $sub; }
QComboBox { background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 7px 12px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; selection-background-color: $hover; selection-color: $text; outline: 0; }
QSpinBox { background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 4px 8px; min-height: 28px; }
QLabel#h2 { font-size: 18px; font-weight: 650; }
QLabel#bigstat { font-size: 30px; font-weight: 700; }
QLabel#sect { font-size: 13px; font-weight: 650; color: $sub; padding-top: 8px; }
#sidebar { background: transparent; }
#rail { background: $glass; border: 1px solid $glass_border; border-top-color: $glass_highlight; border-radius: 17px; }
#sidepanel { background: $glass; border: 1px solid $glass_border; border-top-color: $glass_highlight; border-radius: 17px; }
#sidepanel QLineEdit, #sidepanel QComboBox, #sidepanel QListWidget, #sidepanel QPlainTextEdit {
    background: $surface_a; border-color: $glass_border; }
#sidepanel QPushButton, #sidepanel QToolButton { background: $glass; border-color: $glass_border; }
#sidepanel QPushButton:hover, #sidepanel QToolButton:hover { background: $surface_a; }
#rail QToolButton:checked { background: $hover; }
QWidget#panelbody { background: transparent; }
QScrollArea { background: transparent; border: none; }
QSlider::groove:horizontal { height: 4px; background: $border; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { background: $accent; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:disabled { background: $border; }
QListWidget { background: $surface2; border: 1px solid $border; border-radius: 10px; padding: 4px; outline: 0; }
QListWidget::item { padding: 6px 8px; border-radius: 6px; }
QListWidget::item:selected { background: $hover; color: $text; }
QPlainTextEdit#notes { background: $surface2; border: 1px solid $border; border-radius: 10px; padding: 8px;
                       selection-background-color: $accent; selection-color: $on_accent; }
#selbar { background: $surface2; border: 1px solid $border; border-radius: 12px; }
#selbar QPushButton { padding: 4px 12px; border-radius: 8px; }
#selbar QToolButton { border-radius: 8px; }
QToolButton#sidebarReveal { background: $glass; border: 1px solid $glass_border; border-left: none;
                            border-top-right-radius: 10px; border-bottom-right-radius: 10px; }
QToolButton#sidebarReveal:hover { background: $hover; }
QWidget#sidebarHoverZone { background: transparent; }
QWidget#printHeader { background: $surface; border-bottom: 1px solid $border; }
QWidget#printFooter { background: $surface; border-top: 1px solid $border; }
QFrame#printSetup { background: $surface; border-right: 1px solid $border; }
QFrame#printStage { background: #edf0f4; border-radius: 14px; }
QFrame#printStage QLabel { color: #344054; }
QPrintPreviewWidget { background: #e9edf2; border: 1px solid #d4d9e0; border-radius: 12px; }
QLabel#printHint { color: $sub; }
QLabel#printSection { color: $sub; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QToolButton#printNav { color: #344054; background: #ffffff; border: 1px solid #d4d9e0; border-radius: 8px; }
QToolButton#printNav:hover { background: #f4f6f8; }
QFrame#printStage QPushButton { color: #344054; background: #ffffff; border-color: #d4d9e0; }
QFrame#printStage QPushButton:hover { background: #f4f6f8; }
QDialog#palette { background: transparent; }
QFrame#palettecard { background: $surface; border: 1px solid $border; border-radius: 16px; }
QFrame#downloadPopup { background: $glass; border: 1px solid $glass_highlight; border-radius: 16px; }
QFrame#downloadCard { background: $surface_a; border: 1px solid $glass_border; border-radius: 12px; }
QScrollArea#downloadScroll, QWidget#downloadRows { background: transparent; border: none; }
QLabel#downloadEmpty { color: $sub; padding: 8px 6px; }
QLabel#downloadTitle { font-size: 15px; font-weight: 650; }
QFrame#downloadPopup QToolButton { background: transparent; border: 1px solid transparent; padding: 5px 8px; }
QFrame#downloadPopup QToolButton:hover { background: $surface_a; border-color: $glass_border; }
QWidget#downloadActions QToolButton { color: $sub; padding: 4px 8px; }
QWidget#downloadActions QToolButton:hover { color: $text; }
QLabel#downloadName { font-weight: 600; }
QFrame#siteNotification { background: $glass; border: 1px solid $glass_highlight; border-radius: 15px; }
QFrame#siteNotification QLabel { background: transparent; }
QLabel#notificationTitle { font-weight: 650; }
QLabel#notificationMessage { color: $text; }
QLabel#notificationOrigin { color: $sub; font-size: 11px; }
QProgressBar#downloadProgress { border: none; background: $border; min-height: 5px; max-height: 5px; border-radius: 3px; }
QProgressBar#downloadProgress::chunk { background: $accent; border-radius: 3px; }
QLineEdit#paletteinput { border-radius: 10px; min-height: 42px; font-size: 15px; padding: 0 14px; border: 1px solid $border; background: $surface2; }
QListWidget#palettelist { background: transparent; border: none; }
QListWidget#palettelist::item { padding: 0; border-radius: 9px; }
""")

COMPLETER_QSS = Template(r"""
QListView { background: $surface; color: $text; border: 1px solid $border; border-radius: 10px;
            padding: 4px; outline: 0; font-size: 13px; }
QListView::item { padding: 7px 10px; border-radius: 6px; }
QListView::item:selected { background: $hover; color: $text; }
""")


PILL_QSS = Template(r"""
#toolbar, #bookmarkbar { background: transparent; border: none; }
QTabBar::tab { margin: 4px 3px; padding: 0 8px 0 12px; border-radius: 15px; border: 1px solid $glass_border; }
QTabBar::tab:hover:!selected { background: $surface_a; }
QTabBar::tab:selected { background: $glass; border: 1px solid $glass_highlight; }
QLineEdit { border-radius: 20px; padding: 0 16px; background: $surface; border: 1px solid $border; }
QLineEdit:hover { border-color: $accent; }
QLineEdit:focus { border-color: $accent; background: $surface; }
QToolButton { border-radius: 16px; }
QToolButton:hover { background: $surface2; }
QToolButton#bm { border-radius: 13px; }
QToolButton#tabclose { border-radius: 9px; }
QPushButton { border-radius: 15px; }
QMenu { border-radius: 18px; padding: 8px; }
QMenu::item { border-radius: 11px; padding: 8px 32px 8px 14px; }
#rail { background: $glass; border: 1px solid $glass_border; border-top-color: $glass_highlight; border-radius: 18px; }
#sidepanel { background: $glass; border: 1px solid $glass_border; border-top-color: $glass_highlight; border-radius: 18px; }
#toolbar[zen="true"] { background: $glass; border-bottom: 1px solid $glass_border; }
#strip[zen="true"] { background: $glass; border-bottom: 1px solid $glass_border; }
QTabBar#tabs[zen="true"] { background: transparent; }
QTabBar#tabs[zen="true"]::tab { background: transparent; border: 1px solid transparent; }
QTabBar#tabs[zen="true"]::tab:selected { background: $glass; border-color: $glass_border; }
QToolButton#sidebarReveal { border-radius: 0 10px 10px 0; }
#selbar { border-radius: 16px; }
QFrame#palettecard { border-radius: 22px; }
QLabel#overlay { border-radius: 14px; }
""")

LEGACY_QSS = Template(r"""
QTabBar::tab { border-top-left-radius: 4px; border-top-right-radius: 4px; }
QLineEdit { border-radius: 6px; }
QPushButton, QToolButton { border-radius: 5px; }
QMenu { border-radius: 6px; }
""")

MINI_QSS = Template(r"""
QFrame#mini { background: $surface_a; border: 1px solid $border_a; border-radius: 22px; }
QFrame#mini QLabel { background: transparent; }
QFrame#mini QToolButton { border-radius: 15px; }
""")


def build_qss(t: dict, edition: str = "nightly") -> str:
    t2 = dict(t, surface_a=rgba(t["surface"], 0.8), border_a=rgba(t["border"], 0.9),
              glass=rgba(t["surface"], 0.42), glass_border=rgba(t["text"], 0.25),
              glass_highlight=rgba(t["text"], 0.42))
    q = QSS.safe_substitute(**t2)
    if edition == "stable":
        q += PILL_QSS.safe_substitute(**t2)
    elif edition == "legacy":
        q += LEGACY_QSS.safe_substitute(**t2)
    return q + MINI_QSS.safe_substitute(**t2)


def build_palette(t: dict) -> QPalette:
    p = QPalette()
    c = QColor
    p.setColor(QPalette.ColorRole.Window, c(t["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, c(t["text"]))
    p.setColor(QPalette.ColorRole.Base, c(t["surface2"]))
    p.setColor(QPalette.ColorRole.AlternateBase, c(t["surface"]))
    p.setColor(QPalette.ColorRole.Text, c(t["text"]))
    p.setColor(QPalette.ColorRole.Button, c(t["surface2"]))
    p.setColor(QPalette.ColorRole.ButtonText, c(t["text"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, c(t["surface2"]))
    p.setColor(QPalette.ColorRole.ToolTipText, c(t["text"]))
    p.setColor(QPalette.ColorRole.Highlight, c(t["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, c(t["on_accent"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, c(t["sub"]))
    p.setColor(QPalette.ColorRole.Link, c(t["accent"]))
    p.setColor(QPalette.ColorRole.Mid, c(t["border"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c(t["sub"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c(t["sub"]))
    return p


def _draw_glyph(p: QPainter, name: str) -> None:
    """Draws a glyph on a 24x24 grid (stroke style)."""
    P = QPointF
    line = lambda a, b, c, d: p.drawLine(P(a, b), P(c, d))
    poly = lambda *pts: p.drawPolyline(QPolygonF([P(x, y) for x, y in pts]))
    if name == "back":
        line(19, 12, 5, 12); poly((12, 5), (5, 12), (12, 19))
    elif name == "forward":
        line(5, 12, 19, 12); poly((12, 5), (19, 12), (12, 19))
    elif name == "reload":
        p.drawArc(QRectF(5, 5, 14, 14), 40 * 16, 280 * 16); poly((13.2, 7.6), (17.4, 7.6), (17.4, 3.4))
    elif name in ("stop", "close"):
        k = 6 if name == "stop" else 7.5
        line(k, k, 24 - k, 24 - k); line(24 - k, k, k, 24 - k)
    elif name == "home":
        poly((4, 11), (12, 4), (20, 11)); poly((6, 9.5), (6, 20), (18, 20), (18, 9.5))
    elif name in ("star", "star_on"):
        pts = []
        for i in range(10):
            r = 8.6 if i % 2 == 0 else 3.6
            a = -math.pi / 2 + i * math.pi / 5
            pts.append(P(12 + r * math.cos(a), 12.6 + r * math.sin(a)))
        if name == "star_on":
            p.setBrush(p.pen().color())
        p.drawPolygon(QPolygonF(pts))
    elif name == "spark":
        line(12, 3, 12, 21); line(3, 12, 21, 12); line(5.5, 5.5, 18.5, 18.5); line(18.5, 5.5, 5.5, 18.5)
    elif name == "menu":
        line(4, 6.5, 20, 6.5); line(4, 12, 20, 12); line(4, 17.5, 20, 17.5)
    elif name == "plus":
        line(12, 5, 12, 19); line(5, 12, 19, 12)
    elif name == "minus":
        line(5, 12, 19, 12)
    elif name == "lock":
        p.drawRoundedRect(QRectF(6, 11, 12, 9), 2, 2); p.drawArc(QRectF(8.5, 4, 7, 8), 0, 180 * 16)
        line(8.5, 8, 8.5, 11); line(15.5, 8, 15.5, 11)
    elif name == "warn":
        p.drawPolygon(QPolygonF([P(12, 4), P(21, 20), P(3, 20)])); line(12, 10, 12, 14); line(12, 17, 12, 17.1)
    elif name == "globe":
        p.drawEllipse(QRectF(3, 3, 18, 18)); p.drawEllipse(QRectF(8, 3, 8, 18)); line(3, 12, 21, 12)
    elif name == "download":
        line(12, 4, 12, 15); poly((7, 11), (12, 16), (17, 11)); line(5, 20, 19, 20)
    elif name == "settings":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for a in range(0, 360, 45):
            r1, r2 = math.radians(a), math.radians(a)
            line(12 + 5.5 * math.cos(r1), 12 + 5.5 * math.sin(r1),
                 12 + 9 * math.cos(r2), 12 + 9 * math.sin(r2))
        p.drawEllipse(QRectF(10, 10, 4, 4))
    elif name == "fullscreen":
        poly((4, 9), (4, 4), (9, 4)); poly((15, 4), (20, 4), (20, 9))
        poly((20, 15), (20, 20), (15, 20)); poly((9, 20), (4, 20), (4, 15))
    elif name == "search":
        p.drawEllipse(QRectF(5, 5, 12, 12)); line(15.5, 15.5, 20, 20)
    elif name == "up":
        poly((6, 15), (12, 9), (18, 15))
    elif name == "down":
        poly((6, 9), (12, 15), (18, 9))
    elif name == "eyeoff":
        p.drawEllipse(QRectF(3, 7.5, 18, 9)); p.drawEllipse(QRectF(9.5, 9.5, 5, 5)); line(4, 20, 20, 4)
    elif name == "bookmark":
        poly((7, 4), (17, 4), (17, 20), (12, 15.5), (7, 20), (7, 4))
    elif name == "sidebar":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3); line(9, 4, 9, 20)
    elif name == "gauge":
        p.drawArc(QRectF(3, 6, 18, 18), 0, 180 * 16); line(3, 15, 21, 15); line(12, 15, 16, 10)
    elif name == "layers":
        poly((12, 4), (21, 9), (12, 14), (3, 9), (12, 4)); poly((3, 13), (12, 18), (21, 13))
    elif name == "note":
        p.drawRoundedRect(QRectF(5, 3.5, 14, 17), 2, 2); line(8.5, 9, 15.5, 9); line(8.5, 13, 15.5, 13); line(8.5, 17, 12, 17)
    elif name == "group":
        p.drawRoundedRect(QRectF(3, 9, 18, 11), 3, 3); p.drawRoundedRect(QRectF(3, 4, 8, 3), 1.5, 1.5)
    elif name == "puzzle":
        p.drawRoundedRect(QRectF(4, 9, 16, 11), 2, 2); p.drawEllipse(QRectF(9, 3.5, 6, 6))
    elif name == "bolt":
        p.drawPolygon(QPolygonF([P(13, 3), P(5, 13.5), P(11, 13.5), P(10, 21), P(19, 10), P(13, 10)]))
    elif name == "panel":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3); line(15, 4, 15, 20)
    elif name == "chev_left":
        poly((15, 6), (9, 12), (15, 18))
    elif name == "chev_right":
        poly((9, 6), (15, 12), (9, 18))
    elif name == "music":
        p.drawEllipse(QRectF(3.5, 15, 5.5, 5)); line(9, 17.5, 9, 5); poly((9, 5), (19.5, 3), (19.5, 14)); p.drawEllipse(QRectF(14.5, 12, 5.5, 5))
    elif name == "play":
        p.setBrush(p.pen().color()); p.drawPolygon(QPolygonF([P(8, 5), P(19, 12), P(8, 19)]))
    elif name == "pause":
        p.setBrush(p.pen().color()); p.drawRoundedRect(QRectF(6.5, 5, 3.6, 14), 1.2, 1.2); p.drawRoundedRect(QRectF(13.9, 5, 3.6, 14), 1.2, 1.2)
    elif name == "next":
        p.setBrush(p.pen().color()); p.drawPolygon(QPolygonF([P(6, 5.5), P(15.5, 12), P(6, 18.5)])); line(18.5, 5.5, 18.5, 18.5)
    elif name == "prev":
        p.setBrush(p.pen().color()); p.drawPolygon(QPolygonF([P(18, 5.5), P(8.5, 12), P(18, 18.5)])); line(5.5, 5.5, 5.5, 18.5)
    elif name == "sleep":
        p.drawArc(QRectF(5, 4, 15, 15), 60 * 16, 250 * 16); line(14, 7, 18, 7); line(18, 7, 14, 11); line(14, 11, 18, 11)


ICON_COLORS = {   # the stable edition gives every icon its own bright colour
    "back": "#4f9dff", "forward": "#4f9dff", "reload": "#34c98b", "stop": "#ff6b6b", "home": "#ff9f43", "star": "#ffc542",
    "star_on": "#ffc542", "menu": "#a78bfa", "plus": "#ff6bb5", "lock": "#34c98b", "warn": "#ffb020", "globe": "#38bdf8",
    "download": "#38bdf8", "fullscreen": "#60a5fa", "search": "#60a5fa", "up": "#60a5fa", "down": "#60a5fa",
    "bookmark": "#f472b6", "sidebar": "#818cf8", "spark": "#d8b4fe", "gauge": "#34d399", "layers": "#f59e0b", "note": "#fbbf24",
    "group": "#fb7185", "puzzle": "#c084fc", "bolt": "#facc15", "panel": "#60a5fa",
    "music": "#ff5c7a", "play": "#ff5c7a", "pause": "#ff5c7a", "next": "#c084fc", "prev": "#c084fc",
    "sleep": "#a78bfa", "eyeoff": "#9ca3af",
}


def make_icon(name: str, color: str, disabled: str | None = None, size: int = 20) -> QIcon:
    icon = QIcon()
    for mode, col in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, rgba_qcolor(disabled or color, 0.45))):
        pm = QPixmap(size * 2, size * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(size / 24, size / 24)
        pen = QPen(QColor(col) if isinstance(col, str) else col, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        _draw_glyph(p, name)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def rgba_qcolor(hex_color: str, alpha: float) -> QColor:
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c


def logo_pixmap(size: int = 128) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 128, size / 128)
    accent = QColor("#8ab4ff")
    pen = QPen(accent, 9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawArc(QRectF(27, 27, 74, 74), 40 * 16, 285 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(accent)
    p.drawEllipse(QRectF(92, 28, 13, 13))
    p.end()
    return pm


def avatar_pixmap(name: str, color: str, size: int, image: str | None = None) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    photo = QPixmap(image) if image and os.path.isfile(image) else QPixmap()
    if not photo.isNull():
        side = min(photo.width(), photo.height())
        photo = photo.copy((photo.width() - side) // 2, (photo.height() - side) // 2, side, side)
        clip = QPainterPath()
        clip.addEllipse(QRectF(0, 0, size, size))
        p.setClipPath(clip)
        p.drawPixmap(QRectF(0, 0, size, size), photo, QRectF(photo.rect()))
        p.end()
        return pm
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(0, 0, size, size))
    p.setPen(QColor("#ffffff"))
    f = p.font()
    f.setPixelSize(int(size * 0.46))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, (name.strip()[:1] or "?").upper())
    p.end()
    return pm


# ═════════════════════════════════════════════════════════════════════════════
#  Premade wallpapers (generated SVG, no asset files)
# ═════════════════════════════════════════════════════════════════════════════

def _svg(defs: str, body: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" '
            f'preserveAspectRatio="xMidYMid slice"><defs>{defs}</defs>{body}</svg>')


def _lin(gid: str, stops, x2=0, y2=1) -> str:
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>'


def _blur(gid: str, dev: int) -> str:
    return (f'<filter id="{gid}" x="-50%" y="-50%" width="200%" height="200%">'
            f'<feGaussianBlur stdDeviation="{dev}"/></filter>')


def _stars(rng: random.Random, n: int, height: int = 700) -> str:
    out = []
    for _ in range(n):
        out.append(f'<circle cx="{rng.randint(0, 1920)}" cy="{rng.randint(0, height)}" '
                   f'r="{rng.uniform(0.5, 1.7):.1f}" fill="#fff" fill-opacity="{rng.uniform(0.25, 0.9):.2f}"/>')
    return "".join(out)


def _ridge(rng: random.Random, y: float, amp: float, color: str, opacity: float = 1.0) -> str:
    freqs = (1.3, 2.9, 5.7)
    phases = [rng.uniform(0, 6.28) for _ in freqs]
    pts = []
    for i in range(97):
        t = i / 96 * 6.2832
        off = sum(math.sin(t * f + ph) * amp / (k + 1) for k, (f, ph) in enumerate(zip(freqs, phases)))
        pts.append(f"{1920 * i / 96:.0f},{y + off:.0f}")
    return f'<polygon points="{" ".join(pts)} 1920,1080 0,1080" fill="{color}" fill-opacity="{opacity}"/>'


def _wall_aurora() -> str:
    r = random.Random(11)
    defs = _lin("s", [(0, "#04060f"), (0.55, "#0a1830"), (1, "#0f2f3f")]) + _blur("b", 80)
    body = ('<rect width="1920" height="1080" fill="url(#s)"/>' + _stars(r, 150, 640) +
            '<g filter="url(#b)"><ellipse cx="640" cy="340" rx="520" ry="150" fill="#2dffa0" fill-opacity=".45" transform="rotate(-8 640 340)"/>'
            '<ellipse cx="1180" cy="290" rx="480" ry="130" fill="#7a5cff" fill-opacity=".5" transform="rotate(6 1180 290)"/>'
            '<ellipse cx="1500" cy="430" rx="360" ry="110" fill="#2fd3ff" fill-opacity=".35"/></g>' +
            _ridge(r, 850, 80, "#06101c") + _ridge(r, 950, 55, "#03070e"))
    return _svg(defs, body)


def _wall_dunes() -> str:
    r = random.Random(5)
    defs = _lin("s", [(0, "#241046"), (0.45, "#7b2d5f"), (0.75, "#f4845f"), (1, "#f9c97c")]) + _blur("b", 40)
    body = ('<rect width="1920" height="1080" fill="url(#s)"/>'
            '<circle cx="1380" cy="600" r="150" fill="#ffe3a8" fill-opacity=".85" filter="url(#b)"/>' +
            _ridge(r, 700, 60, "#c8553d", .95) + _ridge(r, 790, 80, "#a13d4a") +
            _ridge(r, 880, 70, "#6b2a4b") + _ridge(r, 975, 50, "#3b1d45"))
    return _svg(defs, body)


def _wall_ocean() -> str:
    r = random.Random(3)
    defs = _lin("s", [(0, "#021b3a"), (0.6, "#0a4a7a"), (1, "#1e88b5")]) + _blur("b", 60)
    body = ('<rect width="1920" height="1080" fill="url(#s)"/>'
            '<circle cx="520" cy="250" r="110" fill="#dff3ff" fill-opacity=".5" filter="url(#b)"/>' + _stars(r, 60, 400))
    for i, (y, c, o) in enumerate([(560, "#1c78a8", .55), (660, "#0e5c8f", .8), (760, "#0a4673", .9),
                                   (860, "#06335a", .95), (960, "#031f3d", 1)]):
        body += _ridge(r, y, 26 + i * 4, c, o)
    return _svg(defs, body)


def _wall_alpine() -> str:
    r = random.Random(8)
    defs = _lin("s", [(0, "#141e30"), (0.6, "#35577d"), (1, "#f0a98b")]) + _blur("b", 50)
    body = ('<rect width="1920" height="1080" fill="url(#s)"/>' + _stars(r, 70, 380) +
            _ridge(r, 560, 150, "#6f8db0", .9) + '<rect y="640" width="1920" height="200" fill="#fff" fill-opacity=".07" filter="url(#b)"/>' +
            _ridge(r, 720, 140, "#46648a") + _ridge(r, 840, 120, "#2a4262") + _ridge(r, 950, 90, "#14233a"))
    return _svg(defs, body)


def _wall_nebula() -> str:
    r = random.Random(21)
    defs = _blur("b", 110)
    body = ('<rect width="1920" height="1080" fill="#07030f"/><g filter="url(#b)">'
            '<ellipse cx="520" cy="360" rx="420" ry="260" fill="#ff2d95" fill-opacity=".5"/>'
            '<ellipse cx="1060" cy="620" rx="520" ry="300" fill="#6a11cb" fill-opacity=".65"/>'
            '<ellipse cx="1500" cy="300" rx="400" ry="250" fill="#2575fc" fill-opacity=".5"/>'
            '<ellipse cx="900" cy="900" rx="360" ry="180" fill="#00d2ff" fill-opacity=".3"/></g>' + _stars(r, 320, 1080))
    return _svg(defs, body)


def _wall_forest() -> str:
    r = random.Random(14)
    defs = _lin("s", [(0, "#0f2d23"), (0.55, "#1d5a45"), (1, "#8fc9a0")]) + _blur("b", 45)
    body = ('<rect width="1920" height="1080" fill="url(#s)"/>'
            '<circle cx="1500" cy="330" r="120" fill="#f3ffd8" fill-opacity=".55" filter="url(#b)"/>' +
            _ridge(r, 620, 110, "#3f8f6a", .8) + _ridge(r, 740, 100, "#2f7d5b") +
            _ridge(r, 860, 90, "#236449") + _ridge(r, 960, 70, "#0d2f23"))
    return _svg(defs, body)


def _wall_slate() -> str:
    defs = _lin("s", [(0, "#1c1f26"), (0.5, "#2b2f3a"), (1, "#111318")], 1, 1) + _blur("b", 120)
    body = ('<rect width="1920" height="1080" fill="url(#s)"/>'
            '<circle cx="1400" cy="260" r="360" fill="#6d7a99" fill-opacity=".22" filter="url(#b)"/>')
    return _svg(defs, body)


WALLPAPERS = [("aurora", "Aurora", _wall_aurora), ("dunes", "Dunes", _wall_dunes), ("ocean", "Ocean", _wall_ocean),
              ("alpine", "Alpine", _wall_alpine), ("nebula", "Nebula", _wall_nebula),
              ("forest", "Forest", _wall_forest), ("slate", "Slate", _wall_slate)]
_WALL_CACHE: dict[str, bytes] = {}


def _wall_for_theme(key: str) -> str:
    """A graphic wallpaper painted from the theme's own palette."""
    t = THEMES[key]
    style, c1, c2, c3 = t["wall"]
    dark = t["kind"] == "dark"
    bg = t["bg"]
    rng = random.Random(sum(ord(c) for c in key) * 7)
    top = _mix(bg, "#000000", 0.28) if dark else _mix(c3, "#ffffff", 0.55)
    bot = _mix(c1, bg, 0.6) if dark else _mix(c1, "#ffffff", 0.7)
    if style == "blobs":
        base = _mix(bg, "#000000", 0.18) if dark else _mix(bg, "#ffffff", 0.35)
        op = ".6" if dark else ".7"
        body = (f'<rect width="1920" height="1080" fill="{base}"/><g filter="url(#b)">'
                f'<ellipse cx="520" cy="360" rx="470" ry="290" fill="{c1}" fill-opacity="{op}"/>'
                f'<ellipse cx="1180" cy="660" rx="560" ry="320" fill="{c2}" fill-opacity="{op}"/>'
                f'<ellipse cx="1560" cy="260" rx="430" ry="260" fill="{c3}" fill-opacity="{op}"/>'
                f'<ellipse cx="760" cy="960" rx="420" ry="200" fill="{c3}" fill-opacity=".35"/></g>')
        if dark:
            body += _stars(rng, 120, 1080)
        return _svg(_blur("b", 120), body)
    if style == "mesh":
        cols, rows = 13, 7
        pts = [[(x * 1920 / (cols - 1) + (rng.uniform(-45, 45) if 0 < x < cols - 1 else 0),
                 y * 1080 / (rows - 1) + (rng.uniform(-45, 45) if 0 < y < rows - 1 else 0))
                for x in range(cols)] for y in range(rows)]

        def col(px, py):
            u, v = px / 1920, py / 1080
            c = _mix(_mix(c1, c2, u), c3, max(0.0, v - 0.2) * 0.8)
            c = _mix(c, bg, 0.5 if dark else 0.0) if dark else _mix(c, "#ffffff", 0.28)
            return _mix(c, "#ffffff" if rng.random() > 0.5 else "#000000", rng.uniform(0.0, 0.10))
        polys = []
        for y in range(rows - 1):
            for x in range(cols - 1):
                a, b, c, d = pts[y][x], pts[y][x + 1], pts[y + 1][x + 1], pts[y + 1][x]
                for tri in ((a, b, c), (a, c, d)):
                    cx = sum(p[0] for p in tri) / 3
                    cy = sum(p[1] for p in tri) / 3
                    pts_s = " ".join(f"{p[0]:.0f},{p[1]:.0f}" for p in tri)
                    colr = col(cx, cy)
                    polys.append(f'<polygon points="{pts_s}" fill="{colr}" stroke="{colr}" stroke-width="1"/>')
        return _svg("", "".join(polys))
    if style == "orbits":
        defs = _lin("s", [(0, top), (1, bot)], 1, 1) + _blur("b", 90)
        body = f'<rect width="1920" height="1080" fill="url(#s)"/><circle cx="1350" cy="480" r="330" fill="{c1}" fill-opacity=".28" filter="url(#b)"/>'
        for i in range(7):
            colr = (c1, c2, c3)[i % 3]
            body += f'<circle cx="1350" cy="480" r="{150 + i * 100}" fill="none" stroke="{colr}" stroke-opacity="{0.34 - i * 0.03:.2f}" stroke-width="2"/>'
        for i in range(9):
            ang = rng.uniform(0, 6.283)
            rr = 150 + rng.randint(0, 6) * 100
            colr = (c1, c2, c3)[i % 3]
            body += (f'<circle cx="{1350 + rr * math.cos(ang):.0f}" cy="{480 + rr * math.sin(ang):.0f}" '
                     f'r="{rng.randint(5, 15)}" fill="{colr}" fill-opacity=".9"/>')
        if dark:
            body += _stars(rng, 90, 1080)
        return _svg(defs, body)
    # ridges / waves share a sky + layered silhouettes
    defs = _lin("s", [(0, top), (1, bot)]) + _blur("b", 55)
    body = f'<rect width="1920" height="1080" fill="url(#s)"/>'
    if dark:
        body += _stars(rng, 110, 520)
    body += (f'<circle cx="{rng.randint(1100, 1700)}" cy="{rng.randint(240, 400)}" r="{rng.randint(90, 150)}" '
             f'fill="{c3}" fill-opacity="{.5 if dark else .7}" filter="url(#b)"/>')
    waves = style == "waves"
    for i in range(5 if waves else 4):
        f = i / (4 if waves else 3)
        far = _mix(c2, bg if dark else "#ffffff", 0.55)
        near = _mix(bg, "#000000", 0.45) if dark else _mix(c2, bg, 0.4)
        colr = _mix(far, near, f)
        y = (560 + i * 95) if waves else (590 + i * 105)
        body += _ridge(rng, y, (26 + i * 4) if waves else (120 - i * 20), colr, 0.96)
    return _svg(defs, body)


def theme_wallpaper_svg(key: str) -> bytes | None:
    if key not in THEMES:
        return None
    ck = "theme/" + key
    if ck not in _WALL_CACHE:
        _WALL_CACHE[ck] = _wall_for_theme(key).encode("utf-8")
    return _WALL_CACHE[ck]


def wallpaper_svg(wid: str) -> bytes | None:
    if wid not in _WALL_CACHE:
        for key, _, fn in WALLPAPERS:
            if key == wid:
                _WALL_CACHE[wid] = fn().encode("utf-8")
    return _WALL_CACHE.get(wid)


def valid_wallpaper(store, value: str) -> bool:
    if value == "auto" or value in {w[0] for w in WALLPAPERS}:
        return True
    if value.startswith("theme:"):
        return value[6:] in THEMES
    return value.startswith("user:") and value[5:] in store["user_wallpapers"]


# ═════════════════════════════════════════════════════════════════════════════
#  Profile storage
# ═════════════════════════════════════════════════════════════════════════════

def default_config(name: str, color: str, theme: str, engine: str) -> dict:
    return {
        "name": name, "color": color, "theme": theme, "search_engine": engine,
        "startup": "newtab", "homepage": "",
        "show_bookmarks_bar": False, "show_home_button": True, "zoom_default": 100,
        "keep_cookies": True, "block_third_party_cookies": False, "block_trackers": True,
        "send_dnt": True, "force_dark_pages": False,
        "ask_download_location": False, "download_dir": str(Path.home() / "Downloads"),
        "wallpaper": "auto", "wallpaper_dim": 18, "wallpaper_blur": 0, "user_wallpapers": [],
        "accent": "", "description": "", "avatar_emoji": "", "accounts": [],
        "animations": True, "smooth_scroll": True, "lazy_restore": True, "zoom_per_site": True,
        "sidebar_open": False, "sidebar_always_visible": False, "sidebar_panel": "perf", "notes": "", "web_panels": [], "workspaces": [],
        "sidebar_order": ["perf", "work", "notes", "web", "music", "ai"],
        "sidebar_panels": ["perf", "work", "notes", "web", "music", "ai"],
        "ai_provider": "chatgpt",
        "zoom_by_host": {}, "extensions": [], "session_groups": {},
        "avatar_image": "", "edition": "stable", "mini_player": False,
        "show_clock": True, "show_widgets": True, "clock_24h": True,
        "widgets": [{"id": uuid.uuid4().hex[:8], "name": n, "url": u} for n, u in DEFAULT_WIDGETS],
        "bookmarks": [], "history": [], "downloads": [], "session": [],
    }


class ProfileStore:
    """One profile's settings and data, persisted as JSON next to its web data."""

    def __init__(self, pid: str, root: Path):
        self.id = pid
        self.dir = root / "profiles" / pid
        self.path = self.dir / "config.json"
        self.data: dict = {}
        for sub in ("webdata", "cache", "wallpapers"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.flush)
        self.load()

    def load(self) -> None:
        base = default_config("User", AVATAR_COLORS[0], "dark", "google")
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        self.data = {**base, **loaded}
        try:
            ui_version = int(loaded.get("renovo_ui_version", 0) or 0)
        except (TypeError, ValueError):
            ui_version = 0
        if ui_version < 1:
            self.data["show_bookmarks_bar"] = False
            self.data["renovo_ui_version"] = 1
            self.save()
    def __getitem__(self, key):
        return self.data[key]

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def save(self) -> None:
        self._timer.start()

    def flush(self) -> None:
        self._timer.stop()
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    @property
    def search_template(self) -> str:
        return ENGINE_BY_ID.get(self.data["search_engine"], ENGINES[0])[2]


def smart_url(text: str, template: str) -> QUrl:
    t = text.strip()
    if not t:
        return QUrl(NEWTAB)
    if re.match(r"^(https?|file|ftp|awesome|view-source|about|data|blob):", t, re.I):
        return QUrl("about:blank") if t.lower() == "about:blank" else QUrl.fromUserInput(t)
    if " " not in t and re.match(r"^(localhost|(\d{1,3}\.){3}\d{1,3}|[\w-]+(\.[\w-]+)+)(:\d+)?([/?#].*)?$", t):
        local = t.startswith("localhost") or re.match(r"^\d{1,3}(\.\d{1,3}){3}", t)
        return QUrl(("http://" if local else "https://") + t)
    return QUrl(template.replace("%s", quote_plus(t)))


# ═════════════════════════════════════════════════════════════════════════════
#  Internal pages (awesome://...)
# ═════════════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════════════
#  Pure logic (no Qt): extension helpers, memory policy
# ═════════════════════════════════════════════════════════════════════════════


# ── Chrome extension helpers ────────────────────────────────────────────────

def match_pattern_regex(pat: str) -> str | None:
    """Chrome match pattern -> regex source that works in both Python and JavaScript."""
    if pat == "<all_urls>":
        return r"^(?:https?|ftp|file)://.*$"
    m = re.match(r"^(\*|https?|file|ftp)://([^/]*)(/.*)$", pat)
    if not m:
        return None
    scheme, host, path = m.groups()
    sch = "https?" if scheme == "*" else re.escape(scheme)
    if scheme == "file":
        host_re = ""
    else:
        if host == "*":
            host_re = r"[^/]+"
        elif host.startswith("*."):
            host_re = r"(?:[^/]+\.)?" + re.escape(host[2:])
        else:
            host_re = re.escape(host)
        host_re += r"(?::\d+)?"
    path_re = ".*".join(re.escape(p) for p in path.split("*"))
    return f"^{sch}://{host_re}{path_re}$"


def crx_zip_bytes(data: bytes) -> bytes:
    """Strip the CRX2/CRX3 header and return the embedded zip archive."""
    if data[:4] == b"Cr24":
        ver = int.from_bytes(data[4:8], "little")
        if ver == 3:
            return data[12 + int.from_bytes(data[8:12], "little"):]
        if ver == 2:
            pk, sg = int.from_bytes(data[8:12], "little"), int.from_bytes(data[12:16], "little")
            return data[16 + pk + sg:]
        raise ValueError("Unsupported CRX version")
    if data[:2] == b"PK":
        return data
    raise ValueError("This isn't a CRX or ZIP file")


def folder_extension_id(path: str) -> str:
    import hashlib
    h = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in h)


# ── memory limiter policy ───────────────────────────────────────────────────

LIMIT_MIN_MB = 1024          # below this the browser UI + one tab can't fit
LIMIT_STEP_MB = 128


def clamp_limit(mb: float, total_mb: float = 0) -> int:
    hi = max(2048, int(total_mb * 0.9)) if total_mb else 65536
    return int(max(LIMIT_MIN_MB, min(hi, round(mb / LIMIT_STEP_MB) * LIMIT_STEP_MB)))


class LimiterPolicy:
    """Decides *when* to free memory. It only ever asks for one small, reversible
    action at a time (sleep one tab), waits between actions, caps how many it
    takes per minute, and gives up gracefully when nothing is left to free."""

    def __init__(self, cooldown: float = 6.0, max_per_minute: int = 6):
        self.cooldown, self.max_per_minute = cooldown, max_per_minute
        self.next_ok = 0.0
        self.stuck_until = 0.0
        self.actions: list[float] = []

    def decide(self, used: float, limit: float, now: float, has_candidates: bool, aggressive: bool = False) -> str:
        self.actions = [t for t in self.actions if now - t < 60]
        if used <= limit * (0.95 if aggressive else 1.0):
            self.stuck_until = 0.0
            return "ok"
        if now < self.stuck_until:
            return "stuck"
        if now < self.next_ok or len(self.actions) >= self.max_per_minute:
            return "wait"
        if not has_candidates:
            self.stuck_until = now + 45
            return "stuck"
        return "reduce"

    def acted(self, now: float) -> None:
        self.next_ok = now + self.cooldown
        self.actions.append(now)


def process_tree_memory_mb() -> tuple[float, bool]:
    """Memory of this process and its children in MB, plus whether it's accurate."""
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil:
        total = 0
        try:
            me = psutil.Process()
            procs = [me] + me.children(recursive=True)
        except Exception:
            return 0.0, False
        for p in procs:
            try:
                mi = p.memory_full_info()
                total += getattr(mi, "pss", None) or getattr(mi, "uss", None) or mi.rss
            except Exception:
                continue
        return total / 1048576, True
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1048576, False
    except Exception:
        return 0.0, False


def system_memory_mb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / 1048576
    except Exception:
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1048576
        except Exception:
            return 0.0


TRACKING_EXACT = {"fbclid", "gclid", "dclid", "msclkid", "mc_eid", "mc_cid", "igshid", "yclid", "_hsenc", "_hsmi", "ref_src"}


def strip_tracking(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    parts = urlsplit(url)
    if not parts.query:
        return url
    keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not (k.lower().startswith("utm_") or k.lower() in TRACKING_EXACT)]
    return urlunsplit(parts._replace(query=urlencode(keep)))


def chromium_flags(ram: dict, safe: bool) -> str:
    flags = ["--enable-gpu-rasterization", "--enable-zero-copy"]
    if ram.get("hard_cap") and not safe:
        flags.append(f"--js-flags=--max-old-space-size={max(512, int(ram.get('limit_mb', 4096)) // 6)}")
    return " ".join(flags)



BASE_CSS = r"""
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{font:14px/1.5 "Segoe UI Variable Text","Segoe UI",Inter,system-ui,-apple-system,"Noto Sans",Roboto,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
button,input,select{font:inherit;color:inherit}
.btn{height:34px;padding:0 16px;border-radius:9px;border:1px solid var(--border);background:var(--surface2);cursor:pointer;transition:background .15s}
.btn:hover{background:var(--hover)}
.btn.primary{background:var(--accent);color:var(--on-accent);border-color:transparent;font-weight:600}
.btn.primary:hover{filter:brightness(1.08)}
.btn.danger{color:#ff6b6b;border-color:rgba(255,107,107,.4);background:transparent}
.text,select{height:36px;border-radius:9px;border:1px solid var(--border);background:var(--surface2);padding:0 12px;outline:none}
.text:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.switch{position:relative;width:42px;height:24px;flex:none;display:inline-block}
.switch input{opacity:0;position:absolute;inset:0;margin:0;cursor:pointer;z-index:1;width:100%;height:100%}
.switch span{position:absolute;inset:0;border-radius:12px;background:var(--border);transition:background .2s}
.switch span:before{content:"";position:absolute;width:18px;height:18px;left:3px;top:3px;border-radius:50%;background:#fff;transition:transform .2s;box-shadow:0 1px 3px rgba(0,0,0,.3)}
.switch input:checked+span{background:var(--accent)}
.switch input:checked+span:before{transform:translateX(18px)}
input[type=range]{accent-color:var(--accent);width:100%}
::-webkit-scrollbar{width:10px}::-webkit-scrollbar-thumb{background:var(--border);border-radius:5px;border:2px solid transparent;background-clip:padding-box}
"""

NEWTAB_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>New tab</title>
<style>/*__ROOT__*/
/*__BASE__*/
html,body{background:transparent!important}
body{overflow:hidden}
.wall{display:none!important}
.veil{display:none!important}
.scroll{position:fixed;inset:0;overflow:auto;z-index:1}
.chip{position:fixed;top:18px;left:20px;z-index:3;display:flex;align-items:center;gap:10px;padding:5px 16px 5px 5px;border-radius:999px;background:var(--glass);backdrop-filter:blur(16px);border:1px solid var(--glass-border);color:var(--text);font-weight:500}
.chip:hover{border-color:var(--accent)}
.av{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:700;font-size:13px}
main{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:84px 24px 110px;gap:30px}
#hero{text-align:center}
#clock{font-size:96px;font-weight:200;letter-spacing:-.03em;color:#fff;text-shadow:0 2px 36px rgba(0,0,0,.4);line-height:1}
#greet{font-size:20px;color:rgba(255,255,255,.9);text-shadow:0 1px 14px rgba(0,0,0,.5);margin-top:10px}
.search{position:relative;width:min(680px,92vw);height:58px;border-radius:29px;display:flex;align-items:center;gap:4px;padding:0 8px 0 6px;background:var(--glass);border:1px solid var(--glass-border);backdrop-filter:blur(24px) saturate(1.3);box-shadow:0 12px 44px rgba(0,0,0,.28);transition:box-shadow .2s,border-color .2s}
.search:focus-within{border-color:var(--accent);box-shadow:0 12px 44px rgba(0,0,0,.34),0 0 0 4px var(--accent-soft)}
.search input{flex:1;height:100%;border:0;outline:0;background:transparent;font-size:17px;color:var(--text);padding:0 8px;min-width:0}
.search input::placeholder{color:var(--sub)}
.eng{height:42px;padding:0 12px;border-radius:21px;border:0;background:transparent;cursor:pointer;color:var(--sub);display:flex;align-items:center;gap:6px;font-size:13px}
.eng:hover{background:var(--hover);color:var(--text)}
.go{width:42px;height:42px;border-radius:50%;border:0;background:var(--accent);color:var(--on-accent);cursor:pointer;display:grid;place-items:center}
.go:hover{filter:brightness(1.1)}
#engmenu{position:absolute;top:64px;left:0;min-width:200px;padding:6px;border-radius:14px;background:var(--surface);border:1px solid var(--border);box-shadow:0 16px 48px rgba(0,0,0,.4);display:none;z-index:6}
#engmenu.open{display:block}
#engmenu button{display:flex;width:100%;align-items:center;justify-content:space-between;border:0;background:transparent;padding:9px 12px;border-radius:8px;cursor:pointer;text-align:left}
#engmenu button:hover{background:var(--hover)}
#engmenu button.on{color:var(--accent);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,96px);gap:22px 18px;justify-content:center;width:min(920px,94vw)}
.tile{position:relative;width:96px;display:flex;flex-direction:column;align-items:center;gap:9px;color:#fff;transition:transform .15s}
.tile:hover{transform:translateY(-3px)}
.tile.drag{opacity:.35}
.ico{width:64px;height:64px;border-radius:19px;background:var(--accent-soft);border:1px solid var(--glass-border);backdrop-filter:blur(18px);display:grid;place-items:center;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.25)}
.ico img{width:34px;height:34px;border-radius:8px}
.ico b{font-size:24px;font-weight:700;color:var(--accent)}
.lbl{font-size:12.5px;max-width:96px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-shadow:0 1px 8px rgba(0,0,0,.7)}
.tools{position:absolute;top:-7px;right:0;display:none;gap:4px}
.tile:hover .tools{display:flex}
.tool{width:22px;height:22px;border-radius:50%;border:0;background:rgba(0,0,0,.7);color:#fff;cursor:pointer;display:grid;place-items:center;font-size:12px;line-height:1}
.tool:hover{background:#000}
button.add{border:0;background:transparent;cursor:pointer;font:inherit}
.add .ico{background:transparent;border:1.5px dashed rgba(255,255,255,.5);box-shadow:none;color:#fff;font-size:26px;font-weight:300}
.fab{position:fixed;right:22px;bottom:22px;z-index:4;height:44px;padding:0 18px;border-radius:22px;display:flex;align-items:center;gap:8px;background:var(--glass);backdrop-filter:blur(16px);border:1px solid var(--glass-border);color:var(--text);cursor:pointer}
.fab:hover{border-color:var(--accent)}
#panel{position:fixed;top:0;right:0;bottom:0;width:372px;max-width:100vw;transform:translateX(102%);transition:transform .28s cubic-bezier(.2,.8,.2,1);background:var(--surface);border-left:1px solid var(--border);z-index:8;padding:22px;overflow:auto;box-shadow:-20px 0 60px rgba(0,0,0,.35)}
#panel.open{transform:none}
#panel header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
#panel h2{margin:0;font-size:19px}
#panel h4{margin:22px 0 10px;font-size:13px;color:var(--sub);font-weight:600}
.x{width:30px;height:30px;border-radius:8px;border:0;background:transparent;cursor:pointer;font-size:20px;color:var(--sub);line-height:1}
.x:hover{background:var(--hover);color:var(--text)}
.wps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.wp{position:relative;aspect-ratio:16/10;border-radius:10px;background-size:cover;background-position:center;cursor:pointer;border:2px solid transparent;outline:1px solid var(--border);outline-offset:-1px}
.wp.sel{border-color:var(--accent)}
.wp .x{position:absolute;top:2px;right:2px;width:20px;height:20px;font-size:14px;background:rgba(0,0,0,.6);color:#fff;display:none;border-radius:50%}
.wp:hover .x{display:block}
.wp.imp{display:grid;place-items:center;border:1.5px dashed var(--border);color:var(--sub);font-size:12px;text-align:center;background:transparent}
.wp.imp:hover{border-color:var(--accent);color:var(--accent)}
.ctl{margin:12px 0}.ctl label{display:flex;justify-content:space-between;color:var(--sub);margin-bottom:6px}
.line{display:flex;align-items:center;justify-content:space-between;padding:9px 0}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(4px);z-index:9;display:none;place-items:center}
#modal.open{display:grid}
.dlg{width:min(400px,92vw);background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:24px;box-shadow:0 24px 80px rgba(0,0,0,.5)}
.dlg h3{margin:0 0 16px;font-size:18px}
.dlg label{display:block;color:var(--sub);margin:12px 0 6px}
.dlg .text{width:100%}
.dlg .acts{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}
.err{color:#ff6b6b;font-size:12.5px;min-height:18px;margin-top:6px}
@keyframes rise{from{opacity:0;transform:translateY(18px) scale(.98)}to{opacity:1;transform:none}}
@keyframes drift{from{opacity:0;transform:scale(1.06)}to{opacity:1;transform:scale(1)}}
.rise{animation:rise .7s cubic-bezier(.2,.8,.2,1) both}
.tile.enter{animation:rise .6s cubic-bezier(.2,.8,.2,1) both}
.wall{animation:drift 1.1s ease-out both}
.ico{transition:transform .18s cubic-bezier(.2,.8,.2,1),box-shadow .18s}.tile:hover .ico{transform:scale(1.06);box-shadow:0 14px 30px rgba(0,0,0,.35)}
.chip,.fab,.search{transition:transform .15s,border-color .2s,box-shadow .2s}.fab:hover{transform:translateY(-2px)}
body.noanim *,body.noanim *:before{animation:none!important;transition:none!important}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:640px){#clock{font-size:64px}}
@media print{
 html,body{height:auto!important;overflow:visible!important;background:#fff!important;color:#17191d!important}
 .wall,.veil,.chip,.fab,#panel,#modal,.tools,.eng,#engmenu,.go{display:none!important}
 .scroll{position:static;overflow:visible}
 main{min-height:0;padding:16px 18px;gap:18px}
 #clock,#greet,.lbl,.tile{color:#17191d!important;text-shadow:none!important}
 #clock{font-size:42px}
 #greet{font-size:14px}
 .search{width:100%;max-width:none;background:#fff;border:1px solid #d1d5db;box-shadow:none;backdrop-filter:none}
 .search input{color:#17191d}
 .grid{width:100%;grid-template-columns:repeat(5,minmax(64px,1fr));gap:12px 8px}
 .ico{background:#f1f3f5;border:1px solid #d6d9de;box-shadow:none;backdrop-filter:none}
 .ico img{max-width:28px;max-height:28px}
}
</style></head><body>
<div class="wall" id="wall"></div><div class="veil"></div>
<a class="chip" href="awesome://settings/profile" title="Profile settings"><span class="av" id="av"></span><span id="pname"></span></a>
<div class="scroll"><main>
  <section id="hero" class="rise"><div id="clock"></div><div id="greet"></div></section>
  <form class="search rise" id="sf" autocomplete="off" style="animation-delay:.12s">
    <button type="button" class="eng" id="engbtn"><span id="engname"></span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></button>
    <input id="q" type="text" placeholder="Search the web or type an address" spellcheck="false" autofocus>
    <button class="go" type="submit" title="Search"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
    <div id="engmenu"></div>
  </form>
  <section class="grid" id="grid"></section>
</main></div>
<button class="fab" id="fab"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></svg>Customize</button>
<aside id="panel">
  <header><h2>Customize this page</h2><button class="x" id="pclose">&times;</button></header>
  <h4>Wallpaper</h4><div class="wps" id="wps"></div>
  <div class="ctl"><label>Dim<span id="dimv"></span></label><input type="range" id="dim" min="0" max="80"></div>
  <div class="ctl"><label>Blur<span id="blurv"></span></label><input type="range" id="blur" min="0" max="24"></div>
  <h4>Layout</h4>
  <div class="line"><span>Show clock</span><label class="switch"><input type="checkbox" id="tclock"><span></span></label></div>
  <div class="line"><span>24-hour time</span><label class="switch"><input type="checkbox" id="t24"><span></span></label></div>
  <div class="line"><span>Show shortcuts</span><label class="switch"><input type="checkbox" id="twid"><span></span></label></div>
</aside>
<div id="modal"><form class="dlg" id="mf" autocomplete="off"><h3 id="mt">Add shortcut</h3>
  <label for="mn">Name</label><input class="text" id="mn" maxlength="30" placeholder="Wikipedia">
  <label for="mu">Website</label><input class="text" id="mu" placeholder="wikipedia.org">
  <div class="err" id="merr"></div>
  <div class="acts"><button type="button" class="btn" id="mcancel">Cancel</button><button class="btn primary" type="submit">Save</button></div></form></div>
<script>__QWC__</script>
<script>
const S=__STATE__;
let bridge=null;const queue=[];
function ready(f){bridge?f():queue.push(f)}
if(window.qt&&window.QWebChannel){new QWebChannel(qt.webChannelTransport,c=>{bridge=c.objects.bridge;queue.splice(0).forEach(f=>f())})}
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function set(k,v){S[k]=v;ready(()=>bridge.setSetting(k,JSON.stringify(v)))}
function wpUrl(id){if(id==='auto')return 'awesome://wallpaper/theme/'+S.theme+'.svg';if(id.startsWith('theme:'))return 'awesome://wallpaper/theme/'+id.slice(6)+'.svg';return id.startsWith('user:')?'awesome://wallpaper/user/'+encodeURIComponent(id.slice(5)):'awesome://wallpaper/'+id+'.svg'}
const isVid=id=>id.startsWith('user:')&&/\.(mp4|webm|m4v|mov|ogv)$/i.test(id);
function paintWall(){const w=$('#wall');w.style.filter='none';w.style.backgroundImage='none';w.innerHTML='';$('.veil').style.opacity=0}
function tick(){const d=new Date(),g=d.getHours();let h=g;const m=String(d.getMinutes()).padStart(2,'0');
  h=S.clock_24h?String(h).padStart(2,'0'):(h%12||12);$('#clock').textContent=h+':'+m;
  $('#greet').textContent=(g<5?'Good night':g<12?'Good morning':g<18?'Good afternoon':'Good evening')+', '+S.name}
function layout(){$('#hero').style.display=S.show_clock?'':'none';$('#grid').style.display=S.show_widgets?'':'none'}
const eng=()=>S.engines.find(e=>e.id===S.search_engine)||S.engines[0];
function looksUrl(t){return /^(https?|file|awesome):\/\//i.test(t)||(!/\s/.test(t)&&(/^[^\s\/]+\.[a-z]{2,}([\/?#:].*)?$/i.test(t)||/^localhost(:\d+)?([\/?#].*)?$/i.test(t)))}
function go(t){t=t.trim();if(!t)return;let u;if(looksUrl(t))u=/^[a-z]+:\/\//i.test(t)?t:'https://'+t;else u=eng().url.replace('%s',encodeURIComponent(t));location.href=u}
$('#sf').onsubmit=e=>{e.preventDefault();go($('#q').value)};
function paintEng(){$('#engname').textContent=eng().label;
  $('#engmenu').innerHTML=S.engines.map(e=>`<button type="button" data-id="${e.id}" class="${e.id===S.search_engine?'on':''}">${esc(e.label)}${e.id===S.search_engine?'<span>&#10003;</span>':''}</button>`).join('');
  $('#engmenu').querySelectorAll('button').forEach(b=>b.onclick=()=>{set('search_engine',b.dataset.id);paintEng();$('#engmenu').classList.remove('open');$('#q').focus()})}
$('#engbtn').onclick=e=>{e.stopPropagation();$('#engmenu').classList.toggle('open')};
document.addEventListener('click',()=>$('#engmenu').classList.remove('open'));
function host(u){try{return new URL(u).hostname}catch(e){return u}}
function renderGrid(){const g=$('#grid');const first=!renderGrid.done;renderGrid.done=true;
  g.innerHTML=S.widgets.map((w,n)=>{const h=host(w.url),l=(w.name||h).trim();
    return `<a class="tile${first?' enter':''}" style="animation-delay:${220+n*45}ms" draggable="true" data-id="${w.id}" href="${esc(w.url)}"><span class="ico"><img alt="" src="https://icons.duckduckgo.com/ip3/${esc(h)}.ico" onerror="this.replaceWith(Object.assign(document.createElement('b'),{textContent:'${((l.match(/[A-Za-z0-9]/)||['?'])[0]).toUpperCase()}'}))"></span><span class="lbl">${esc(l)}</span><span class="tools"><button class="tool" data-a="edit" title="Edit">&#9998;</button><button class="tool" data-a="del" title="Remove">&times;</button></span></a>`}).join('')
   +`<button class="tile add" id="addw"><span class="ico">+</span><span class="lbl">Add shortcut</span></button>`;
  g.querySelectorAll('.tile[data-id]').forEach(t=>{
    t.querySelectorAll('.tool').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();const id=t.dataset.id;b.dataset.a==='del'?delWidget(id):openModal(id)});
    t.ondragstart=e=>{dragId=t.dataset.id;t.classList.add('drag');e.dataTransfer.effectAllowed='move'};
    t.ondragend=()=>{t.classList.remove('drag');dragId=null};
    t.ondragover=e=>{e.preventDefault();e.dataTransfer.dropEffect='move'};
    t.ondrop=e=>{e.preventDefault();e.stopPropagation();if(!dragId||dragId===t.dataset.id)return;const a=S.widgets.findIndex(w=>w.id===dragId),b=S.widgets.findIndex(w=>w.id===t.dataset.id);if(a<0||b<0)return;const [m]=S.widgets.splice(a,1);S.widgets.splice(b,0,m);dragId=null;renderGrid();saveWidgets()}});
  $('#addw').onclick=()=>openModal(null)}
let dragId=null,editId=null;
function saveWidgets(){ready(()=>bridge.saveWidgets(JSON.stringify(S.widgets)))}
function delWidget(id){S.widgets=S.widgets.filter(w=>w.id!==id);renderGrid();saveWidgets()}
function openModal(id){editId=id;const w=S.widgets.find(x=>x.id===id);$('#mt').textContent=w?'Edit shortcut':'Add shortcut';$('#mn').value=w?w.name:'';$('#mu').value=w?w.url:'';$('#merr').textContent='';$('#modal').classList.add('open');setTimeout(()=>$('#mn').focus(),30)}
function closeModal(){$('#modal').classList.remove('open');$('#q').focus()}
$('#mcancel').onclick=closeModal;
$('#modal').onmousedown=e=>{if(e.target.id==='modal')closeModal()};
$('#mf').onsubmit=e=>{e.preventDefault();let u=$('#mu').value.trim(),n=$('#mn').value.trim();
  if(!u){$('#merr').textContent='Enter a website address.';return}
  if(!/^[a-z][a-z0-9+.-]*:\/\//i.test(u))u='https://'+u;
  try{const p=new URL(u);if(!/^https?:$/.test(p.protocol)||!p.hostname.includes('.')&&p.hostname!=='localhost')throw 0;n=n||p.hostname.replace(/^www\./,'')}catch(x){$('#merr').textContent='That doesn\u2019t look like a valid website address.';return}
  if(editId){const w=S.widgets.find(x=>x.id===editId);w.name=n;w.url=u}else S.widgets.push({id:Math.random().toString(36).slice(2,10),name:n,url:u});
  renderGrid();saveWidgets();closeModal()};
function renderWps(){const el=$('#wps');
  const items=[{id:'auto',label:'Match my theme',user:false}].concat(S.premade.map(p=>({id:p.id,label:p.label,user:false})),S.theme_walls.map(p=>({id:p.id,label:p.label+' theme',user:false})),S.user_wallpapers.map(f=>({id:'user:'+f,label:'Imported',user:true})));
  el.innerHTML=items.map(i=>`<div class="wp ${S.wallpaper===i.id?'sel':''}" data-id="${esc(i.id)}" title="${esc(i.label)}" style="${isVid(i.id)?'background:linear-gradient(135deg,#1b1b2a,#4b3f72);display:grid;place-items:center;color:#fff;font-size:12px':`background-image:url('${wpUrl(i.id)}')`}">${isVid(i.id)?'&#9654; Live':''}${i.user?'<button class="x" data-del="1">&times;</button>':''}</div>`).join('')+`<div class="wp imp" id="imp">Import image<br>or live video</div>`;
  el.querySelectorAll('.wp[data-id]').forEach(d=>d.onclick=e=>{if(e.target.dataset.del){const f=d.dataset.id.slice(5);ready(()=>bridge.removeWallpaper(f));S.user_wallpapers=S.user_wallpapers.filter(x=>x!==f);if(S.wallpaper===d.dataset.id){S.wallpaper='aurora';paintWall()}renderWps();return}
    set('wallpaper',d.dataset.id);paintWall();renderWps()});
  $('#imp').onclick=()=>ready(()=>bridge.pickWallpaper(r=>{if(!r)return;const o=JSON.parse(r);if(o.error){alert(o.error);return}S.wallpaper=o.wallpaper;S.user_wallpapers=o.user_wallpapers;paintWall();renderWps()}))}
function bind(id,key,fx){const el=$(id);el.checked=!!S[key];el.onchange=()=>{set(key,el.checked);fx&&fx()}}
bind('#tclock','show_clock',layout);bind('#t24','clock_24h',tick);bind('#twid','show_widgets',layout);
function slider(id,key,vid,unit){const el=$(id);el.value=S[key];$(vid).textContent=S[key]+unit;el.oninput=()=>{S[key]=+el.value;$(vid).textContent=el.value+unit;paintWall()};el.onchange=()=>set(key,+el.value)}
slider('#dim','wallpaper_dim','#dimv','%');slider('#blur','wallpaper_blur','#blurv',' px');
$('#fab').onclick=()=>$('#panel').classList.add('open');
$('#pclose').onclick=()=>$('#panel').classList.remove('open');
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('#panel').classList.remove('open');closeModal()}});
$('#av').textContent=(S.avatar_emoji||S.name[0]||'?').toUpperCase();$('#av').style.background=S.color;$('#pname').textContent=S.name;$('.chip').title=S.description||'Profile settings';if(S.has_avatar){const a=$('#av');a.textContent='';a.style.background='url(awesome://avatar/a) center/cover'}if(S.animations===false)document.body.classList.add('noanim');
paintWall();tick();setInterval(tick,5000);layout();paintEng();renderGrid();renderWps();$('#q').focus();
</script></body></html>"""

SETTINGS_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Settings</title>
<style>/*__ROOT__*/
/*__BASE__*/
.shell{display:flex;height:100%}
.side{width:264px;padding:22px 14px;border-right:1px solid var(--border);background:var(--surface);flex:none;display:flex;flex-direction:column;gap:2px}
.side h1{font-size:20px;margin:2px 12px 16px;font-weight:650}
.nav a{display:block;padding:9px 12px;border-radius:9px;color:var(--sub);cursor:pointer}
.nav a:hover{background:var(--hover);color:var(--text)}
.nav a.on{background:var(--accent-soft);color:var(--accent);font-weight:600}
.main{flex:1;overflow:auto;padding:26px 48px 90px}
.wrap{max-width:780px;margin:0 auto}
.top{display:flex;justify-content:flex-end;margin-bottom:20px}
.top .text{width:300px;border-radius:19px;height:38px;padding:0 16px}
.sec{display:none}.sec.on{display:block}
.sec>h2{margin:4px 0 16px;font-size:22px;font-weight:650}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;margin-bottom:18px;overflow:hidden}
.card>h3{margin:0;padding:16px 20px 12px;font-size:14px;font-weight:650}
.row{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:14px 20px;border-top:1px solid var(--border)}
.row .t b{font-weight:500;display:block}.row .t small{color:var(--sub);display:block;max-width:440px}
.row.col{flex-direction:column;align-items:stretch}
.profile{display:flex;gap:20px;align-items:center;padding:20px}
.big{width:72px;height:72px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:30px;font-weight:700;flex:none}
.sw{display:flex;gap:10px;flex-wrap:wrap}.sw i{width:26px;height:26px;border-radius:50%;cursor:pointer;outline-offset:2px}.sw i.on{outline:2px solid var(--text)}
.themes{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;padding:6px 20px 20px}
.tc{cursor:pointer;text-align:center}
.tc .pv{height:96px;border-radius:12px;border:1.5px solid;overflow:hidden;display:flex;flex-direction:column}
.tc.sel .pv{outline:2.5px solid var(--accent);outline-offset:2px}
.pt{height:16px;display:flex;gap:3px;padding:4px 6px 0}.pt i{width:34px;border-radius:5px 5px 0 0}
.pb{height:16px;padding:4px 8px}.pb b{display:block;height:8px;border-radius:4px}
.pc{flex:1;padding:10px;display:grid;place-items:center}.pc u{display:block;width:70%;height:12px;border-radius:6px}
.tc span{display:block;margin-top:8px;font-size:13px}.tc.sel span{color:var(--accent);font-weight:600}
.opt{display:flex;gap:12px;align-items:center;padding:12px 20px;border-top:1px solid var(--border);cursor:pointer}
.opt input{accent-color:var(--accent);width:16px;height:16px}
.plist .row .t small{max-width:none}
.pill{display:inline-block;padding:2px 10px;border-radius:10px;background:var(--accent-soft);color:var(--accent);font-size:12px;margin-left:8px}
table.sc{width:100%;border-collapse:collapse}table.sc td{padding:10px 20px;border-top:1px solid var(--border)}table.sc td:first-child{color:var(--sub);width:42%}
kbd{font:12px ui-monospace,Consolas,monospace;background:var(--surface2);border:1px solid var(--border);border-bottom-width:2px;border-radius:5px;padding:1px 7px}
#cm{position:fixed;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(4px);display:none;place-items:center;z-index:9}#cm.open{display:grid}
.dlg{width:min(560px,92vw);max-height:80vh;display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.5)}
.dlg header{display:flex;gap:12px;align-items:center;padding:18px 20px;border-bottom:1px solid var(--border)}.dlg header h3{margin:0;flex:1;font-size:17px}
.dlg .body{overflow:auto;flex:1}.dlg .body .row{padding:10px 20px}.dlg footer{padding:14px 20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;color:var(--sub)}
.empty{padding:34px;text-align:center;color:var(--sub)}
.hide{display:none!important}
.pills{display:flex;gap:8px;padding:0 20px 8px}.pills button{border:1px solid var(--border);background:transparent;border-radius:16px;padding:4px 14px;cursor:pointer}.pills button.on{background:var(--accent-soft);color:var(--accent);border-color:transparent;font-weight:600}
.themes{grid-template-columns:repeat(4,1fr)}
.av2{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:700}
</style></head><body><div class="shell">
<aside class="side"><h1>Settings</h1><nav class="nav" id="nav">
<a data-s="profile">Profile</a><a data-s="appearance">Appearance</a><a data-s="search">Search engine</a><a data-s="startup">On startup</a><a data-s="privacy">Privacy and cookies</a><a data-s="downloads">Downloads</a><a data-s="experimental">Advanced</a><a data-href="awesome://extensions">Extensions</a><a data-s="about">About</a></nav></aside>
<div class="main"><div class="wrap">
<div class="top"><input class="text" id="find" placeholder="Search settings" autocomplete="off"></div>

<section class="sec" data-s="profile"><h2>Profile</h2>
 <div class="card" style="overflow:hidden"><div id="bn" style="height:76px"></div><div class="profile" style="margin-top:-38px;align-items:flex-end"><div class="big" id="big" style="border:4px solid var(--surface)"></div><div style="flex:1;padding-bottom:4px">
   <div style="display:flex;gap:10px"><input class="text" id="pname" data-key="name" maxlength="40" style="flex:1;max-width:300px" placeholder="Your name"><input class="text" data-key="avatar_emoji" maxlength="4" style="width:70px;text-align:center" placeholder="&#128512;" title="Optional emoji for your avatar"></div></div></div>
   <div class="row col" style="border-top:0"><div class="t"><b>About this profile</b><small>A short description. It shows when you hover your avatar and on your profile list.</small></div><textarea class="text" data-key="description" maxlength="280" rows="3" style="height:auto;padding:10px 12px;resize:vertical" placeholder="Work, study, side projects, shared with the family"></textarea></div>
   <div class="row"><div class="t"><b>Avatar colour</b></div><div class="sw" id="sw"></div></div></div>
 <div class="card"><h3>Accent colour</h3><div class="row"><div class="t"><b>Profile accent</b><small>Replaces the theme's accent in this profile only: buttons, selection, focus rings.</small></div><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:flex-end"><div class="sw" id="acc"></div><input type="color" id="accpick" style="width:34px;height:34px;border:0;background:none;padding:0;cursor:pointer"></div></div></div>
 <div class="card"><h3>Linked accounts</h3><div id="alist"></div>
  <div class="row col"><div class="t"><b>Add an account</b><small>Keeps a one-click sign-in for this profile. Your actual logins live in this profile's cookies, so you stay signed in between sessions.</small></div>
   <div style="display:flex;gap:10px;flex-wrap:wrap"><select id="asvc" style="min-width:140px"></select><input class="text" id="alabel" placeholder="you@example.com or username" style="flex:1;min-width:180px"><input class="text" id="aurl" placeholder="https://site.com/login" style="flex:1;min-width:180px;display:none"><button class="btn primary" id="aadd">Add</button></div></div></div>
 <div class="card plist"><h3>Profiles on this device</h3><div id="plist"></div>
  <div class="row"><div class="t"><b>Add a profile</b><small>Each profile has its own bookmarks, history, cookies and look.</small></div><button class="btn" id="addp">Add profile</button></div>
  <div class="row"><div class="t"><b>Delete this profile</b><small>Removes this profile&rsquo;s bookmarks, history, cookies and sign-ins from this device.</small></div><button class="btn danger" id="delp">Delete profile</button></div></div>
</section>

<section class="sec" data-s="appearance"><h2>Appearance</h2>
 <div class="card"><h3>Theme</h3><div class="pills" id="tfilter"><button data-f="all" class="on">All</button><button data-f="dark">Dark</button><button data-f="light">Light</button></div><div class="themes" id="themes"></div></div>
 <div class="card"><h3>Toolbar</h3>
  <div class="row"><div class="t"><b>Show bookmarks bar</b></div><label class="switch"><input type="checkbox" data-key="show_bookmarks_bar"><span></span></label></div>
  <div class="row"><div class="t"><b>Show home button</b></div><label class="switch"><input type="checkbox" data-key="show_home_button"><span></span></label></div></div>
 <div class="card"><h3>Web content</h3>
  <div class="row"><div class="t"><b>Default page zoom</b></div><select data-key="zoom_default" data-int="1"><option>75</option><option>90</option><option>100</option><option>110</option><option>125</option><option>150</option><option>175</option><option>200</option></select></div>
  <div class="row"><div class="t"><b>Dark mode for websites</b><small>Applies a dark rendering to pages that don&rsquo;t offer one. Reopen tabs to apply.</small></div><label class="switch"><input type="checkbox" data-key="force_dark_pages"><span></span></label></div></div>
</section>

<section class="sec" data-s="search"><h2>Search engine</h2>
 <div class="card"><div class="row"><div class="t"><b>Search engine</b><small>Used by the address bar and the new tab page.</small></div><select id="eng" data-key="search_engine"></select></div></div>
</section>

<section class="sec" data-s="startup"><h2>On startup</h2>
 <div class="card">
  <label class="opt"><input type="radio" name="st" value="newtab" data-key="startup"><span>Open the new tab page</span></label>
  <label class="opt"><input type="radio" name="st" value="restore" data-key="startup"><span>Continue where I left off</span></label>
  <label class="opt"><input type="radio" name="st" value="custom" data-key="startup"><span>Open a specific page</span></label>
  <div class="row"><div class="t"><b>Home page</b><small>Used for startup and the home button. Leave blank for the new tab page.</small></div><input class="text" data-key="homepage" style="width:300px" placeholder="https://"></div></div>
</section>

<section class="sec" data-s="privacy"><h2>Privacy and cookies</h2>
 <div class="card"><h3>Cookies and sign-ins</h3>
  <div class="row"><div class="t"><b>Stay signed in</b><small>Saves cookies between sessions so sites remember you. Takes effect after restarting the browser.</small></div><label class="switch"><input type="checkbox" data-key="keep_cookies"><span></span></label></div>
  <div class="row"><div class="t"><b>Block third-party cookies</b><small>Stops other sites from tracking you with cookies. Some embedded content may stop working.</small></div><label class="switch"><input type="checkbox" data-key="block_third_party_cookies"><span></span></label></div>
  <div class="row"><div class="t"><b>See all cookies and site data</b><small>Review and remove cookies by site.</small></div><button class="btn" id="cookies">Manage cookies</button></div></div>
 <div class="card"><h3>Protection</h3>
  <div class="row"><div class="t"><b>Block ads and trackers</b><small>Blocks requests to well-known advertising and tracking domains.</small></div><label class="switch"><input type="checkbox" data-key="block_trackers"><span></span></label></div>
  <div class="row"><div class="t"><b>Send &ldquo;Do Not Track&rdquo; request</b></div><label class="switch"><input type="checkbox" data-key="send_dnt"><span></span></label></div></div>
 <div class="card"><h3>Site permissions</h3><p class="muted">When a site requests notifications, your microphone, or your camera, AwesomeBrowse asks before access is granted. Choose Allow or Block in the site prompt.</p></div>
 <div class="card"><h3>Clear browsing data</h3>
  <label class="opt"><input type="checkbox" id="c_history" checked><span>Browsing history</span></label>
  <label class="opt"><input type="checkbox" id="c_cookies" checked><span>Cookies and site data <span class="pill">signs you out</span></span></label>
  <label class="opt"><input type="checkbox" id="c_cache" checked><span>Cached images and files</span></label>
  <div class="row"><div class="t"><small id="cstat"></small></div><button class="btn primary" id="clear">Clear data</button></div></div>
</section>

<section class="sec" data-s="downloads"><h2>Downloads</h2>
 <div class="card"><div class="row"><div class="t"><b>Location</b><small id="dldir"></small></div><button class="btn" id="chdir">Change</button></div>
 <div class="row"><div class="t"><b>Ask where to save each file</b></div><label class="switch"><input type="checkbox" data-key="ask_download_location"><span></span></label></div></div>
</section>

<section class="sec" data-s="experimental"><h2>Advanced</h2>
 <div class="card"><h3>Interface and features</h3>
  <div class="row"><div class="t"><b>Interface style</b><small>Renovo uses floating tabs and the current layout. Classic keeps the earlier 2.1 layout. Legacy uses the classic 2.0 interface without the sidebar.</small></div><select data-key="edition"><option value="stable">2.1.2-Renovo</option><option value="nightly">Classic 2.1</option><option value="legacy">Legacy 2.0</option></select></div>
  <div class="row"><div class="t"><b>Animations</b><small>Tab open and close, tab switching, panels and the new tab page. Turn off for a flatter, snappier feel.</small></div><label class="switch"><input type="checkbox" data-key="animations"><span></span></label></div>
  <div class="row"><div class="t"><b>Smooth scrolling</b><small>Takes effect on the next page load.</small></div><label class="switch"><input type="checkbox" data-key="smooth_scroll"><span></span></label></div>
  <div class="row"><div class="t"><b>Load restored tabs on demand</b><small>After a restart, tabs load only when you open them. Much faster startup and lower memory.</small></div><label class="switch"><input type="checkbox" data-key="lazy_restore"><span></span></label></div>
  <div class="row"><div class="t"><b>Remember zoom for each site</b></div><label class="switch"><input type="checkbox" data-key="zoom_per_site"><span></span></label></div>
  <div class="row"><div class="t"><b>Open the sidebar at startup</b><small>Press Ctrl+B, or hover the left edge of the page.</small></div><label class="switch"><input type="checkbox" data-key="sidebar_open"><span></span></label></div>
  <div class="row"><div class="t"><b>Keep sidebar visible</b><small>Pin it open in every window for this profile.</small></div><label class="switch"><input type="checkbox" data-key="sidebar_always_visible"><span></span></label></div></div>
</section>

<section class="sec" data-s="about"><h2>About AwesomeBrowse 2</h2>
 <div class="card"><table class="sc" id="about"></table></div>
 <div class="card"><h3>Keyboard shortcuts</h3><table class="sc">
 <tr><td>New tab / close tab / reopen</td><td><kbd>Ctrl</kbd> <kbd>T</kbd> &nbsp; <kbd>Ctrl</kbd> <kbd>W</kbd> &nbsp; <kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>T</kbd></td></tr>
 <tr><td>Address bar</td><td><kbd>Ctrl</kbd> <kbd>L</kbd></td></tr>
 <tr><td>Find in page</td><td><kbd>Ctrl</kbd> <kbd>F</kbd></td></tr>
 <tr><td>Bookmark this page</td><td><kbd>Ctrl</kbd> <kbd>D</kbd></td></tr>
 <tr><td>Toggle sidebar / customize panels</td><td><kbd>Ctrl</kbd> <kbd>B</kbd></td></tr>
 <tr><td>Zen mode</td><td><kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>Z</kbd> or <kbd>Esc</kbd></td></tr>
 <tr><td>Print preview</td><td><kbd>Ctrl</kbd> <kbd>P</kbd></td></tr>
 <tr><td>Full screen</td><td><kbd>F11</kbd></td></tr>
 <tr><td>Developer tools / view source</td><td><kbd>F12</kbd> &nbsp; <kbd>Ctrl</kbd> <kbd>U</kbd></td></tr>
 <tr><td>Private window</td><td><kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>N</kbd></td></tr>
 <tr><td>History / downloads</td><td><kbd>Ctrl</kbd> <kbd>H</kbd> &nbsp; <kbd>Ctrl</kbd> <kbd>J</kbd></td></tr></table></div>
</section>
</div></div></div>
<div id="cm"><div class="dlg"><header><h3>Cookies and site data</h3><input class="text" id="cq" placeholder="Filter sites" style="width:200px"><button class="btn" id="cmx">Close</button></header>
<div class="body" id="cbody"></div><footer><span id="ctotal"></span><button class="btn danger" id="cdelall">Remove all</button></footer></div></div>
<script>__QWC__</script>
<script>
const S=__STATE__,TH=__THEMES__;
let bridge=null;const queue=[];
function ready(f){bridge?f():queue.push(f)}
if(window.qt&&window.QWebChannel){new QWebChannel(qt.webChannelTransport,c=>{bridge=c.objects.bridge;queue.splice(0).forEach(f=>f())})}
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function save(k,v){S[k]=v;ready(()=>bridge.setSetting(k,JSON.stringify(v)))}
const onAcc=h=>{const r=parseInt(h.slice(1,3),16),g=parseInt(h.slice(3,5),16),b=parseInt(h.slice(5,7),16);return(.2126*r+.7152*g+.0722*b)>150?'#0b0f1a':'#ffffff'};
const hexA=(h,a)=>'rgba('+parseInt(h.slice(1,3),16)+','+parseInt(h.slice(3,5),16)+','+parseInt(h.slice(5,7),16)+','+a+')';
function applyTheme(n){const t=Object.assign({},TH[n]);if(S.accent){t.accent=S.accent;t['on-accent']=onAcc(S.accent);t['accent-soft']=hexA(S.accent,.22)}for(const k in t)document.documentElement.style.setProperty('--'+k,t[k])}
function show(sec){$$('.sec').forEach(s=>s.classList.toggle('on',s.dataset.s===sec));$$('#nav a').forEach(a=>a.classList.toggle('on',a.dataset.s===sec));history.replaceState(null,'','awesome://settings/'+sec)}
$$('#nav a').forEach(a=>a.onclick=()=>{if(a.dataset.href){location.href=a.dataset.href;return}$('#find').value='';filter('');show(a.dataset.s)});
$$('[data-key]').forEach(el=>{const k=el.dataset.key;
  if(el.type==='checkbox'){el.checked=!!S[k];el.onchange=()=>save(k,el.checked)}
  else if(el.type==='radio'){el.checked=S[k]===el.value;el.onchange=()=>{if(el.checked)save(k,el.value)}}
  else if(el.tagName==='SELECT'){el.value=String(S[k]);el.onchange=()=>save(k,el.dataset.int?+el.value:el.value)}
  else{el.value=S[k];el.oninput=()=>{if(k==='avatar_emoji'){S.avatar_emoji=el.value;paintAv()}};el.onchange=()=>{save(k,el.value);paintAv()}}});
function paintAv(){const b=$('#big');b.textContent=(S.avatar_emoji||S.name[0]||'?').toUpperCase();b.style.background=S.color;$('#bn').style.background='linear-gradient(120deg,'+S.color+',var(--accent))'}
$('#pname').oninput=()=>{S.name=$('#pname').value||'?';paintAv()};
$('#sw').innerHTML=S.colors.map(c=>`<i data-c="${c}" style="background:${c}" class="${c===S.color?'on':''}"></i>`).join('');
$$('#sw i').forEach(i=>i.onclick=()=>{save('color',i.dataset.c);$$('#sw i').forEach(x=>x.classList.toggle('on',x===i));paintAv()});
paintAv();
const ACC=['','#5b8cff','#9b6bff','#e5589f','#f0883e','#e8b13a','#3fb97f','#2bb5c7'];
function paintAcc(){$('#acc').innerHTML=ACC.map(c=>`<i data-c="${c}" title="${c||'Theme default'}" style="background:${c||'conic-gradient(var(--accent),var(--surface2),var(--accent))'}" class="${(S.accent||'')===c?'on':''}"></i>`).join('');
  $$('#acc i').forEach(i=>i.onclick=()=>setAccent(i.dataset.c))}
function setAccent(c){S.accent=c;save('accent',c);applyTheme(S.theme);paintAcc();paintAv();paintThemes();if(c)$('#accpick').value=c}
$('#accpick').value=S.accent||'#5b8cff';$('#accpick').onchange=e=>setAccent(e.target.value);paintAcc();
function paintAccounts(){const L=$('#alist');L.innerHTML=S.accounts.length?S.accounts.map(a=>`<div class="row"><div style="display:flex;gap:14px;align-items:center"><span class="av2" style="background:hsl(${[...a.service].reduce((h,c)=>(h*31+c.charCodeAt(0))%360,0)},50%,45%)">${esc(a.service[0].toUpperCase())}</span><div class="t"><b>${esc(a.service)}</b><small>${esc(a.label)}</small></div></div><div style="display:flex;gap:8px"><button class="btn" data-open="${a.id}">Sign in</button><button class="btn danger" data-del="${a.id}">Remove</button></div></div>`).join(''):'<div class="empty" style="padding:18px">No accounts linked yet.</div>';
  $$('[data-open]',L).forEach(b=>b.onclick=()=>ready(()=>bridge.openAccount(b.dataset.open)));
  $$('[data-del]',L).forEach(b=>b.onclick=()=>{S.accounts=S.accounts.filter(a=>a.id!==b.dataset.del);ready(()=>bridge.saveAccounts(JSON.stringify(S.accounts)));paintAccounts()})}
$('#asvc').innerHTML=S.services.map(x=>`<option value="${x.id}">${esc(x.label)}</option>`).join('');
$('#asvc').onchange=()=>{$('#aurl').style.display=$('#asvc').value==='custom'?'':'none'};
$('#aadd').onclick=()=>{const svc=S.services.find(x=>x.id===$('#asvc').value);let url=svc.url||$('#aurl').value.trim();const label=$('#alabel').value.trim();if(!url||!label)return;
  if(!/^https?:\/\//i.test(url))url='https://'+url;let name=svc.label;if(svc.id==='custom'){try{name=new URL(url).hostname.replace(/^www\./,'')}catch(e){return}}
  S.accounts.push({id:Math.random().toString(36).slice(2,10),service:name,label,url});ready(()=>bridge.saveAccounts(JSON.stringify(S.accounts)));$('#alabel').value='';$('#aurl').value='';paintAccounts()};
paintAccounts();
$('#eng').innerHTML=S.engines.map(e=>`<option value="${e.id}">${esc(e.label)}</option>`).join('');$('#eng').value=S.search_engine;
let tf='all';
function paintThemes(){$('#themes').innerHTML=S.theme_order.filter(k=>tf==='all'||S.theme_kinds[k]===tf).map(k=>{const t=TH[k];return `<div class="tc ${S.theme===k?'sel':''}" data-k="${k}"><div class="pv" style="background:${t.bg};border-color:${t.border}"><div class="pt"><i style="background:${t.surface}"></i><i style="background:${t.hover}"></i></div><div class="pb" style="background:${t.surface}"><b style="background:${t.surface2}"></b></div><div class="pc" style="background:linear-gradient(135deg,${t.accent},${t.bg})"><u style="background:${t.glass}"></u></div></div><span>${S.theme_labels[k]}</span></div>`}).join('');
  $$('.tc').forEach(c=>c.onclick=()=>{S.theme=c.dataset.k;applyTheme(S.theme);save('theme',S.theme);paintThemes()})}
$$('#tfilter button').forEach(b=>b.onclick=()=>{tf=b.dataset.f;$$('#tfilter button').forEach(x=>x.classList.toggle('on',x===b));paintThemes()});
paintThemes();
function paintProfiles(){$('#plist').innerHTML=S.profiles.map(p=>`<div class="row"><div style="display:flex;gap:14px;align-items:center"><span class="av" style="width:34px;height:34px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:700;background:${p.color}">${esc((p.name[0]||'?').toUpperCase())}</span><div class="t"><b>${esc(p.name)}${p.current?'<span class="pill">This profile</span>':''}</b>${p.description?`<small>${esc(p.description)}</small>`:''}</div></div>${p.current?'':`<button class="btn" data-o="${p.id}">Open</button>`}</div>`).join('');
  $$('[data-o]').forEach(b=>b.onclick=()=>ready(()=>bridge.openProfile(b.dataset.o)))}
paintProfiles();
$('#addp').onclick=()=>ready(()=>bridge.newProfile());
$('#delp').onclick=()=>ready(()=>bridge.deleteProfile());
$('#dldir').textContent=S.download_dir;
$('#chdir').onclick=()=>ready(()=>bridge.chooseDownloadDir(r=>{if(r){S.download_dir=r;$('#dldir').textContent=r}}));
$('#about').innerHTML=S.about.map(r=>`<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join('');
$('#clear').onclick=()=>{const o={history:$('#c_history').checked,cookies:$('#c_cookies').checked,cache:$('#c_cache').checked};
  ready(()=>bridge.clearData(JSON.stringify(o),r=>{$('#cstat').textContent='Cleared.';setTimeout(()=>$('#cstat').textContent='',3000)}))};
let cookies=[];
function paintCookies(){const q=$('#cq').value.toLowerCase();const list=cookies.filter(c=>c.domain.includes(q));
  $('#cbody').innerHTML=list.length?list.map(c=>`<div class="row"><div class="t"><b>${esc(c.domain)}</b><small>${c.count} cookie${c.count>1?'s':''}</small></div><button class="btn" data-d="${esc(c.domain)}">Remove</button></div>`).join(''):'<div class="empty">No cookies stored.</div>';
  $('#ctotal').textContent=cookies.reduce((a,c)=>a+c.count,0)+' cookies from '+cookies.length+' sites';
  $$('#cbody [data-d]').forEach(b=>b.onclick=()=>ready(()=>{bridge.deleteCookies(b.dataset.d);cookies=cookies.filter(c=>c.domain!==b.dataset.d);paintCookies()}))}
$('#cookies').onclick=()=>ready(()=>bridge.getCookies(r=>{cookies=JSON.parse(r);$('#cq').value='';paintCookies();$('#cm').classList.add('open')}));
$('#cq').oninput=paintCookies;$('#cmx').onclick=()=>$('#cm').classList.remove('open');
$('#cm').onmousedown=e=>{if(e.target.id==='cm')$('#cm').classList.remove('open')};
$('#cdelall').onclick=()=>ready(()=>{bridge.deleteCookies('');cookies=[];paintCookies()});
function filter(q){q=q.trim().toLowerCase();
  if(!q){$$('.row,.card,.opt').forEach(e=>e.classList.remove('hide'));show(($$('#nav a.on')[0]||$('#nav a')).dataset.s);return}
  $$('.sec').forEach(s=>{let any=false;$$('.card',s).forEach(c=>{let n=0;$$('.row,.opt,.themes,.profile,tr',c).forEach(r=>{const m=r.textContent.toLowerCase().includes(q)||c.firstElementChild.textContent.toLowerCase().includes(q);r.classList.toggle('hide',!m&&!r.classList.contains('themes')&&!r.classList.contains('profile'));if(m)n++});c.classList.toggle('hide',!n);if(n)any=true});s.classList.toggle('on',any)});
  $$('#nav a').forEach(a=>a.classList.remove('on'))}
$('#find').oninput=e=>filter(e.target.value);
show(S.section&&$(`.sec[data-s="${S.section}"]`)?S.section:'profile');
</script></body></html>"""

EXT_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Extensions</title>
<style>/*__ROOT__*/
/*__BASE__*/
.wrap{max-width:880px;margin:0 auto;padding:34px 28px 90px}
.head{display:flex;align-items:center;gap:16px;margin-bottom:6px}.head h1{margin:0;font-size:26px;font-weight:650;flex:1}
.lead{color:var(--sub);margin:0 0 22px;max-width:640px}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.bar .text{flex:1;min-width:240px}
#msg{min-height:22px;color:var(--sub);margin-bottom:14px}#msg.ok{color:#3fb97f}#msg.bad{color:#ff6b6b}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:10px;animation:rise .45s cubic-bezier(.2,.8,.2,1) both}
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.top{display:flex;gap:14px;align-items:flex-start}
.ic{width:46px;height:46px;border-radius:12px;background:var(--surface2);display:grid;place-items:center;font-weight:700;overflow:hidden;flex:none;font-size:20px}.ic img{width:34px;height:34px;object-fit:contain}
.top .m{flex:1;min-width:0}.top b{font-size:15px}.top small{color:var(--sub);margin-left:6px}
.desc{color:var(--sub);font-size:13px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:2px 0 0}
.tags{display:flex;gap:6px;flex-wrap:wrap}.tag{font-size:12px;padding:2px 10px;border-radius:10px;background:var(--surface2);color:var(--sub)}.tag.good{background:var(--accent-soft);color:var(--accent)}.tag.warn{background:rgba(229,160,58,.18);color:#e5a03a}
.acts{display:flex;gap:8px;flex-wrap:wrap}.acts .btn{height:30px;padding:0 12px;font-size:13px}
.perm{display:none;font-size:12.5px;color:var(--sub);border-top:1px solid var(--border);padding-top:10px;line-height:1.7;word-break:break-word}.perm.open{display:block}
.empty{padding:60px 20px;text-align:center;color:var(--sub);border:1.5px dashed var(--border);border-radius:16px}
.note{margin-top:28px;padding:18px 20px;border:1px solid var(--border);border-radius:14px;background:var(--surface);color:var(--sub);font-size:13.5px}
.note b{color:var(--text)}
</style></head><body><div class="wrap">
<div class="head"><h1>Extensions</h1></div>
<p class="lead">Add Chrome extensions to this profile. They run in an isolated layer, separate from the sites they change.</p>
<div class="bar"><button class="btn primary" id="unpacked">Load unpacked folder</button><button class="btn" id="file">Install .crx or .zip</button></div>
<div class="bar"><input class="text" id="store" placeholder="Chrome Web Store link or extension ID"><button class="btn" id="storego">Install from store</button></div>
<div id="msg"></div>
<div class="grid" id="list"></div>
<div class="note"><b>What works.</b> Extensions that change or add to pages (content scripts and styles), plus options pages and simple popups, with <code>chrome.storage</code>, <code>chrome.runtime</code> and <code>chrome.i18n</code> available.
<b>What doesn't.</b> Anything that depends on a background service worker, <code>webRequest</code> blocking, native messaging or other browser-level APIs. Those extensions can install, but that part stays idle.
Extensions are off in private windows. Reload open tabs after turning one on or off.</div>
</div>
<script>__QWC__</script>
<script>
const S=__STATE__;
let bridge=null;const queue=[];
function ready(f){bridge?f():queue.push(f)}
if(window.qt&&window.QWebChannel){new QWebChannel(qt.webChannelTransport,c=>{bridge=c.objects.bridge;queue.splice(0).forEach(f=>f())})}
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function say(t,cls){const m=$('#msg');m.textContent=t;m.className=cls||''}
function render(){const L=$('#list');
  if(S.private){L.innerHTML='<div class="empty" style="grid-column:1/-1">Extensions are turned off in private windows.</div>';return}
  if(!S.extensions.length){L.innerHTML='<div class="empty" style="grid-column:1/-1">Nothing installed yet. Load an unpacked folder, pick a .crx file, or paste a Web Store link.</div>';return}
  L.innerHTML=S.extensions.map((e,n)=>`<div class="card" style="animation-delay:${n*50}ms" data-id="${e.id}">
   <div class="top"><div class="ic">${e.icon_url?`<img src="${esc(e.icon_url)}" onerror="this.replaceWith(document.createTextNode('${esc((e.name[0]||'?').toUpperCase())}'))">`:esc((e.name[0]||'?').toUpperCase())}</div>
   <div class="m"><b>${esc(e.name)}</b><small>${esc(e.version)}</small><p class="desc">${esc(e.description||'No description')}</p></div>
   <label class="switch"><input type="checkbox" ${e.enabled?'checked':''} data-a="on"><span></span></label></div>
   <div class="tags">${e.content?`<span class="tag good">${e.content} content script${e.content>1?'s':''}</span>`:''}${e.popup?'<span class="tag good">Popup</span>':''}${e.options?'<span class="tag">Options page</span>':''}${e.background?'<span class="tag warn">Background part not supported</span>':''}<span class="tag">Manifest V${e.mv}</span></div>
   <div class="acts">${e.options?'<button class="btn" data-a="opts">Options</button>':''}<button class="btn" data-a="more">Details</button><button class="btn danger" data-a="rm">Remove</button></div>
   <div class="perm"><b>Permissions:</b> ${esc(e.permissions.join(', ')||'none')}<br><b>Sites:</b> ${esc(e.hosts.join(', ')||'only where its content scripts match')}<br><b>ID:</b> ${e.id}</div></div>`).join('');
  $$('.card').forEach(c=>{const id=c.dataset.id;
    c.querySelector('[data-a=on]').onchange=ev=>{ready(()=>bridge.setExtensionEnabled(id,ev.target.checked));S.extensions.find(x=>x.id===id).enabled=ev.target.checked;say('Reload open tabs to apply the change.')};
    const o=c.querySelector('[data-a=opts]');if(o)o.onclick=()=>ready(()=>bridge.openExtensionOptions(id));
    c.querySelector('[data-a=more]').onclick=()=>c.querySelector('.perm').classList.toggle('open');
    c.querySelector('[data-a=rm]').onclick=()=>{if(confirm('Remove this extension?'))ready(()=>bridge.removeExtension(id))}})}
function result(r){if(!r)return;const o=JSON.parse(r);if(!o.msg)return;say(o.msg,o.ok?'ok':'bad')}
$('#unpacked').onclick=()=>ready(()=>bridge.installUnpacked(result));
$('#file').onclick=()=>ready(()=>bridge.installFile(result));
$('#storego').onclick=()=>{const v=$('#store').value.trim();if(!v)return;say('Contacting the Chrome Web Store\u2026');ready(()=>bridge.installStore(v))};
$('#store').onkeydown=e=>{if(e.key==='Enter')$('#storego').click()};
render();
</script></body></html>"""


LIB_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>/*__ROOT__*/
/*__BASE__*/
.wrap{max-width:860px;margin:0 auto;padding:34px 28px 90px}
.head{display:flex;align-items:center;gap:16px;margin-bottom:22px}.head h1{margin:0;font-size:24px;font-weight:650;flex:1}
.head .text{width:300px;border-radius:19px;height:38px;padding:0 16px}
.day{margin:26px 0 8px;font-size:14px;font-weight:650;color:var(--sub)}
.list{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden}
.item{display:flex;align-items:center;gap:14px;padding:11px 16px;border-top:1px solid var(--border)}
.item:first-child{border-top:0}.item:hover{background:var(--hover)}
.item .tm{color:var(--sub);width:64px;flex:none;font-size:13px}
.fav{width:30px;height:30px;border-radius:8px;display:grid;place-items:center;font-weight:700;color:#fff;font-size:13px;flex:none}
.item .m{flex:1;min-width:0}.item .m a{display:block;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}.item .m small{display:block;color:var(--sub);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rm{width:30px;height:30px;border-radius:8px;border:0;background:transparent;color:var(--sub);cursor:pointer;font-size:18px;opacity:0}.item:hover .rm{opacity:1}.rm:hover{background:var(--border);color:var(--text)}
.empty{padding:70px 20px;text-align:center;color:var(--sub)}
.prog{height:5px;border-radius:3px;background:var(--border);overflow:hidden;margin-top:7px}.prog i{display:block;height:100%;background:var(--accent);transition:width .3s}
.acts{display:flex;gap:8px}.acts .btn{height:30px;padding:0 12px;font-size:13px}
</style></head><body><div class="wrap">
<div class="head"><h1>__TITLE__</h1><input class="text" id="q" placeholder="Search" autocomplete="off"><a class="btn" href="awesome://settings/privacy" style="display:none" id="clr">Clear browsing data</a></div>
<div id="out"></div></div>
<script>__QWC__</script>
<script>
const S=__STATE__,PAGE=S.page;
let bridge=null;const queue=[];
function ready(f){bridge?f():queue.push(f)}
if(window.qt&&window.QWebChannel){new QWebChannel(qt.webChannelTransport,c=>{bridge=c.objects.bridge;queue.splice(0).forEach(f=>f())})}
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function hue(s){let h=0;for(const c of s)h=(h*31+c.charCodeAt(0))%360;return h}
function host(u){try{return new URL(u).hostname.replace(/^www\./,'')}catch(e){return u}}
const fav=u=>{const h=host(u);return `<span class="fav" style="background:hsl(${hue(h)},50%,45%)">${esc((h[0]||'?').toUpperCase())}</span>`};
function dayLabel(ts){const d=new Date(ts*1000),t=new Date();const a=new Date(d.getFullYear(),d.getMonth(),d.getDate()),b=new Date(t.getFullYear(),t.getMonth(),t.getDate());const n=Math.round((b-a)/864e5);
  return n===0?'Today':n===1?'Yesterday':d.toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric',year:d.getFullYear()!==t.getFullYear()?'numeric':undefined})}
function size(n){if(!n)return '';const u=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<3){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]}
function render(){const q=$('#q').value.toLowerCase();let h='';
  if(PAGE==='history'){const items=S.history.filter(x=>(x.title+x.url).toLowerCase().includes(q));
    if(!items.length){$('#out').innerHTML='<div class="empty">'+(q?'No matching history.':'Pages you visit will show up here.')+'</div>';return}
    let day='',open=false;for(const x of items){const l=dayLabel(x.time);if(l!==day){if(open)h+='</div>';h+=`<div class="day">${l}</div><div class="list">`;day=l;open=true}
      h+=`<div class="item" data-t="${x.time}"><span class="tm">${new Date(x.time*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</span>${fav(x.url)}<div class="m"><a href="${esc(x.url)}">${esc(x.title||x.url)}</a><small>${esc(x.url)}</small></div><button class="rm" title="Remove from history">&times;</button></div>`}
    $('#out').innerHTML=h+'</div>';
    document.querySelectorAll('.item .rm').forEach(b=>b.onclick=()=>{const it=b.closest('.item');const t=+it.dataset.t;S.history=S.history.filter(x=>x.time!==t);ready(()=>bridge.removeHistory(JSON.stringify([t])));render()})}
  else if(PAGE==='bookmarks'){const items=S.bookmarks.filter(x=>(x.title+x.url).toLowerCase().includes(q));
    if(!items.length){$('#out').innerHTML='<div class="empty">'+(q?'No matching bookmarks.':'Press Ctrl+D on any page to bookmark it.')+'</div>';return}
    $('#out').innerHTML='<div class="list">'+items.map(x=>`<div class="item" data-u="${esc(x.url)}">${fav(x.url)}<div class="m"><a href="${esc(x.url)}">${esc(x.title||x.url)}</a><small>${esc(x.url)}</small></div><button class="rm" title="Remove bookmark">&times;</button></div>`).join('')+'</div>';
    document.querySelectorAll('.item .rm').forEach(b=>b.onclick=()=>{const u=b.closest('.item').dataset.u;S.bookmarks=S.bookmarks.filter(x=>x.url!==u);ready(()=>bridge.removeBookmark(u));render()})}
  else{const items=S.downloads.filter(x=>x.name.toLowerCase().includes(q));
    if(!items.length){$('#out').innerHTML='<div class="empty">Files you download will show up here.</div>';return}
    $('#out').innerHTML='<div class="list">'+items.map(x=>{const pct=x.total>0?Math.round(x.received/x.total*100):0;
      const st=x.state==='progress'?`${size(x.received)}${x.total?' of '+size(x.total):''}`:x.state==='done'?(x.exists?size(x.total||x.received):'File moved or deleted'):x.state==='cancelled'?'Cancelled':'Failed';
      return `<div class="item" data-id="${x.id}">${fav(x.url||x.name)}<div class="m"><a href="#" data-a="open" style="pointer-events:${x.state==='done'&&x.exists?'auto':'none'}">${esc(x.name)}</a><small>${esc(st)}</small>${x.state==='progress'?`<div class="prog"><i style="width:${pct}%"></i></div>`:''}</div>
      <div class="acts">${x.state==='progress'?'<button class="btn" data-a="cancel">Cancel</button>':x.state==='done'&&x.exists?'<button class="btn" data-a="show">Show in folder</button>':''}<button class="rm" style="opacity:1" data-a="rm" title="Remove from list">&times;</button></div></div>`}).join('')+'</div>';
    document.querySelectorAll('[data-a]').forEach(b=>b.onclick=e=>{e.preventDefault();const id=b.closest('.item').dataset.id,a=b.dataset.a;
      ready(()=>{a==='open'?bridge.openDownload(id):a==='show'?bridge.showDownload(id):a==='cancel'?bridge.cancelDownload(id):bridge.removeDownload(id);setTimeout(poll,150)})})}}
function poll(){if(PAGE!=='downloads'||!bridge)return;bridge.getDownloads(r=>{S.downloads=JSON.parse(r);render()})}
$('#q').oninput=render;
if(PAGE==='history')$('#clr').style.display='';
render();if(PAGE==='downloads'){setInterval(poll,900);ready(poll)}
</script></body></html>"""


# ═════════════════════════════════════════════════════════════════════════════
#  Browser engine pieces: contexts, scheme handler, bridge, downloads, cookies
# ═════════════════════════════════════════════════════════════════════════════

_QWC_CACHE: list[str] = []


def qwebchannel_js() -> str:
    if not _QWC_CACHE:
        f = QFile(":/qtwebchannel/qwebchannel.js")
        text = ""
        if f.open(QIODevice.OpenModeFlag.ReadOnly):
            text = bytes(f.readAll()).decode("utf-8", "replace")
            f.close()
        _QWC_CACHE.append(text)
    return _QWC_CACHE[0]


def render_template(tpl: str, store: ProfileStore, state: dict, title: str = "") -> bytes:
    root = ":root{" + ";".join(f"--{k}:{v}" for k, v in web_vars(resolve_theme(store)).items()) + "}"
    themes = safe_json({k: web_vars(_with_accent(v, store)) for k, v in THEMES.items()})
    html = (tpl.replace("/*__BASE__*/", BASE_CSS).replace("/*__ROOT__*/", root)
            .replace("__TITLE__", title).replace("__THEMES__", themes)
            .replace("__QWC__", qwebchannel_js()).replace("__STATE__", safe_json(state)))
    return html.encode("utf-8")


class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, store: ProfileStore):
        super().__init__()
        self.store = store

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        data = self.store.data
        if data.get("block_trackers"):
            host = info.requestUrl().host()
            main = info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame
            if host and not main and is_tracker_host(host):
                info.block(True)
                return
        if data.get("send_dnt"):
            info.setHttpHeader(QByteArray(b"DNT"), QByteArray(b"1"))


class CookieJar(QObject):
    """Mirrors the profile's cookie store so settings can list and remove cookies."""

    def __init__(self, profile: QWebEngineProfile, store: ProfileStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.cookies: dict = {}
        self.cs = profile.cookieStore()
        self.cs.cookieAdded.connect(self._added)
        self.cs.cookieRemoved.connect(self._removed)
        self.cs.setCookieFilter(self._filter)
        self.cs.loadAllCookies()

    @staticmethod
    def _key(c):
        return (c.domain(), bytes(c.name()).decode("utf-8", "replace"), c.path())

    def _added(self, c):
        self.cookies[self._key(c)] = c

    def _removed(self, c):
        self.cookies.pop(self._key(c), None)

    def _filter(self, request) -> bool:
        if not self.store.data.get("block_third_party_cookies"):
            return True
        return not getattr(request, "thirdParty", False)

    def summary(self) -> list[dict]:
        counts: dict[str, int] = {}
        for (domain, _, _) in self.cookies:
            d = domain.lstrip(".")
            counts[d] = counts.get(d, 0) + 1
        return [{"domain": d, "count": n} for d, n in sorted(counts.items())]

    def delete_domain(self, domain: str) -> None:
        for key, cookie in list(self.cookies.items()):
            if key[0].lstrip(".") == domain:
                self.cs.deleteCookie(cookie)

    def delete_all(self) -> None:
        self.cs.deleteAllCookies()
        self.cookies.clear()


class DownloadManager(QObject):
    changed = pyqtSignal()
    finishedItem = pyqtSignal(str)

    def __init__(self, ctx: "Context"):
        super().__init__(ctx)
        self.ctx = ctx
        self.live: dict[str, dict] = {}
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(220)
        self._progress_timer.timeout.connect(self.changed.emit)
        ctx.profile.downloadRequested.connect(self.on_request)

    @staticmethod
    def _unique(directory: str, name: str) -> str:
        base, ext = os.path.splitext(name)
        candidate, n = name, 1
        while os.path.exists(os.path.join(directory, candidate)):
            candidate = f"{base} ({n}){ext}"
            n += 1
        return candidate

    def on_request(self, req: QWebEngineDownloadRequest) -> None:
        store = self.ctx.store
        if not req.isSavePageDownload():
            name = req.suggestedFileName() or req.downloadFileName() or "download"
            directory = store["download_dir"]
            os.makedirs(directory, exist_ok=True)
            if store["ask_download_location"]:
                path, _ = QFileDialog.getSaveFileName(QApplication.activeWindow(), "Save file",
                                                      os.path.join(directory, name))
                if not path:
                    req.cancel()
                    return
                directory, name = os.path.split(path)
            else:
                name = self._unique(directory, name)
            req.setDownloadDirectory(directory)
            req.setDownloadFileName(name)
        req.accept()
        uid = uuid.uuid4().hex
        now = time.time()
        rec = {"id": uid, "name": req.downloadFileName(), "url": req.url().toString(),
               "path": os.path.join(req.downloadDirectory(), req.downloadFileName()),
               "time": now, "state": "progress", "received": 0, "total": 0,
               "elapsed": 0.0, "speed": 0.0, "_started_mono": time.monotonic(),
               "_last_sample_mono": time.monotonic(), "_last_sample_bytes": 0, "req": req}
        self.live[uid] = rec
        req.receivedBytesChanged.connect(lambda r=rec, q=req: self._progress(r, q))
        if hasattr(req, "totalBytesChanged"):
            req.totalBytesChanged.connect(lambda r=rec, q=req: self._progress(r, q))
        req.stateChanged.connect(lambda st, r=rec: self._state(r, st))
        self.changed.emit()

    def _progress(self, rec, req) -> None:
        received = max(0, req.receivedBytes())
        rec["received"], rec["total"] = received, max(0, req.totalBytes())
        now = time.monotonic()
        rec["elapsed"] = max(0.0, now - rec["_started_mono"])
        interval = now - rec["_last_sample_mono"]
        if interval >= 0.2:
            rec["speed"] = max(0.0, received - rec["_last_sample_bytes"]) / interval
            rec["_last_sample_mono"], rec["_last_sample_bytes"] = now, received
        if not self._progress_timer.isActive():
            self._progress_timer.start()

    def _state(self, rec, state) -> None:
        S = QWebEngineDownloadRequest.DownloadState
        if state == S.DownloadInProgress:
            return
        rec["state"] = {S.DownloadCompleted: "done", S.DownloadCancelled: "cancelled"}.get(state, "failed")
        rec["received"] = rec["req"].receivedBytes()
        rec["total"] = max(rec["total"], rec["req"].totalBytes())
        rec["elapsed"] = max(0.0, time.monotonic() - rec["_started_mono"])
        rec["speed"] = 0.0
        self.live.pop(rec["id"], None)
        if not self.ctx.private:
            saved = {k: v for k, v in rec.items() if k != "req" and not k.startswith("_")}
            self.ctx.store.data["downloads"].insert(0, saved)
            del self.ctx.store.data["downloads"][100:]
            self.ctx.store.save()
        else:
            self.ctx.private_done.insert(0, {k: v for k, v in rec.items() if k != "req" and not k.startswith("_")})
        self.finishedItem.emit(rec["id"])
        self.changed.emit()

    def records(self) -> list[dict]:
        out = []
        now, monotonic_now = time.time(), time.monotonic()
        for r in self.live.values():
            item = {k: v for k, v in r.items() if k != "req" and not k.startswith("_")}
            item["elapsed"] = max(0.0, now - r.get("time", now))
            if monotonic_now - r.get("_last_sample_mono", monotonic_now) > 1.5:
                item["speed"] = 0.0
            out.append(item | {"exists": True})
        done = self.ctx.private_done if self.ctx.private else self.ctx.store["downloads"]
        for r in done:
            out.append({**r, "exists": os.path.exists(r.get("path", ""))})
        return out

    def find(self, uid: str) -> dict | None:
        return next((r for r in self.records() if r["id"] == uid), None)

    def cancel(self, uid: str) -> None:
        rec = self.live.get(uid)
        if rec:
            rec["req"].cancel()

    def remove(self, uid: str) -> None:
        self.cancel(uid)
        if not self.ctx.private:
            self.ctx.store.data["downloads"] = [r for r in self.ctx.store["downloads"] if r["id"] != uid]
            self.ctx.store.save()
        else:
            self.ctx.private_done = [r for r in self.ctx.private_done if r["id"] != uid]

    def clear(self) -> None:
        if not self.ctx.private:
            self.ctx.store.set("downloads", [])
        else:
            self.ctx.private_done.clear()


class SchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves awesome:// pages, AwesomeSpace, and wallpapers."""

    def __init__(self, ctx: "Context"):
        super().__init__(ctx)
        self.ctx = ctx

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        url = job.requestUrl()
        host, path = url.host(), url.path()
        try:
            result = self.ctx.app.serve(self.ctx, host, path, url.query())
        except Exception:  # never let an internal page crash the browser
            result = None
        if result is None:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        data, mime = result
        buf = QBuffer(job)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        if host in ("ext", "extapi"):
            try:
                job.setAdditionalResponseHeaders({QByteArray(b"Access-Control-Allow-Origin"): [QByteArray(b"*")]})
            except (TypeError, AttributeError):
                pass
        job.reply(QByteArray(mime.encode()), buf)

class Context(QObject):
    """A QtWebEngine profile plus everything attached to it."""

    def __init__(self, app: "BrowserApp", store: ProfileStore, private: bool = False):
        super().__init__(app)
        self.app, self.store, self.private = app, store, private
        self.private_done: list[dict] = []
        if private:
            self.profile = QWebEngineProfile(self)
        else:
            self.profile = QWebEngineProfile(f"ab2_{store.id}", self)
            self.profile.setPersistentStoragePath(str(store.dir / "webdata"))
            self.profile.setCachePath(str(store.dir / "cache"))
            policy = (QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies if store["keep_cookies"]
                      else QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self.profile.setPersistentCookiesPolicy(policy)
        # Use the engine's native identity consistently. Spoofing a Firefox UA
        # on Chromium while stripping Chromium client hints breaks sign-in and
        # CAPTCHA compatibility checks on some sites.
        self.chromium = (re.search(r"Chrome/([\d.]+)", self.profile.httpUserAgent()) or [None, "unknown"])[1]
        self.interceptor = RequestInterceptor(store)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.handler = SchemeHandler(self)
        self.profile.installUrlSchemeHandler(QByteArray(SCHEME.encode()), self.handler)
        if hasattr(self.profile, "setNotificationPresenter"):
            self.profile.setNotificationPresenter(self.present_notification)
        for attr, val in (("FullScreenSupportEnabled", True), ("ScrollAnimatorEnabled", bool(store["smooth_scroll"])),
                          ("JavascriptCanOpenWindows", True), ("ScreenCaptureEnabled", True),
                          ("DnsPrefetchEnabled", True), ("PdfViewerEnabled", True)):
            a = getattr(QWebEngineSettings.WebAttribute, attr, None)
            if a is not None:
                self.profile.settings().setAttribute(a, val)
        self.apply_dark_mode()
        self.cookies = CookieJar(self.profile, store, self)
        self.downloads = DownloadManager(self)
        self.extensions = None
        if not private:
            self.extensions = ExtensionManager(self)
            self.extensions.message.connect(lambda m, st=store: app.extensions_changed(st, m))

    def present_notification(self, notification: QWebEngineNotification) -> None:
        windows = [w for w in self.app.windows if getattr(w, "ctx", None) is self and not getattr(w, "_closing", False)]
        if windows:
            active = QApplication.activeWindow()
            target = active if active in windows else windows[-1]
            target.show_web_notification(notification)
        else:
            notification.close()

    def apply_scroll(self) -> None:
        a = getattr(QWebEngineSettings.WebAttribute, "ScrollAnimatorEnabled", None)
        if a is not None:
            self.profile.settings().setAttribute(a, bool(self.store["smooth_scroll"]))

    def apply_dark_mode(self) -> None:
        a = getattr(QWebEngineSettings.WebAttribute, "ForceDarkMode", None)
        if a is not None:
            self.profile.settings().setAttribute(a, bool(self.store["force_dark_pages"]))

    def clear_data(self, opts: dict) -> None:
        if opts.get("history") and not self.private:
            self.store.set("history", [])
        if opts.get("cookies"):
            self.cookies.delete_all()
        if opts.get("cache"):
            self.profile.clearHttpCache()


class Bridge(QObject):
    """JavaScript <-> Python bridge. Only answers to awesome:// pages."""

    def __init__(self, page: "WebPage", ctx: Context):
        super().__init__(page)
        self.page, self.ctx = page, ctx

    def _ok(self) -> bool:
        return self.page.url().scheme() == SCHEME

    @property
    def app(self) -> "BrowserApp":
        return self.ctx.app

    def _window(self):
        return self.page.window or QApplication.activeWindow()

    @pyqtSlot(str, str)
    def setSetting(self, key: str, raw: str) -> None:
        if not self._ok():
            return
        try:
            value = json.loads(raw)
        except ValueError:
            return
        self.app.apply_setting(self.ctx.store, key, value, self.page)

    @pyqtSlot(str)
    def saveWidgets(self, raw: str) -> None:
        if not self._ok():
            return
        try:
            items = json.loads(raw)
            clean = []
            for w in items:
                url = str(w.get("url", ""))
                if not re.match(r"^https?://", url) and not (SPACE_EDITION and url == "awesome://space"):
                    continue
                clean.append({"id": str(w["id"])[:16], "name": str(w["name"])[:40], "url": url[:2000]})
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        self.ctx.store.set("widgets", clean[:200])

    @pyqtSlot(result=str)
    def pickWallpaper(self) -> str:
        if not self._ok():
            return ""
        path, _ = QFileDialog.getOpenFileName(self._window(), "Choose a wallpaper", str(Path.home()),
                                              "Images and live wallpapers (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg *.mp4 *.webm *.m4v *.mov *.ogv)")
        if not path:
            return ""
        if os.path.getsize(path) > 150 * 1024 * 1024:
            return json.dumps({"error": "That file is over 150 MB. Use a shorter loop for a live wallpaper."})
        store = self.ctx.store
        try:
            name = uuid.uuid4().hex[:10] + Path(path).suffix.lower()
            shutil.copyfile(path, store.dir / "wallpapers" / name)
        except OSError:
            return json.dumps({"error": "copy failed"})
        store.data["user_wallpapers"].append(name)
        store.set("wallpaper", "user:" + name)
        return json.dumps({"wallpaper": "user:" + name, "user_wallpapers": store["user_wallpapers"]})

    @pyqtSlot(str)
    def removeWallpaper(self, name: str) -> None:
        store = self.ctx.store
        if not self._ok() or name not in store["user_wallpapers"]:
            return
        store.data["user_wallpapers"].remove(name)
        selected = store["wallpaper"] == "user:" + name
        if selected:
            store.data["wallpaper"] = "auto"
        store.save()
        if selected:
            for window in self.ctx.app.windows_of(store):
                window.wallpaper_layer.set_wallpaper()
        try:
            (store.dir / "wallpapers" / os.path.basename(name)).unlink()
        except OSError:
            pass

    @pyqtSlot(str, result=str)
    def clearData(self, raw: str) -> str:
        if not self._ok():
            return "{}"
        try:
            self.ctx.clear_data(json.loads(raw))
        except ValueError:
            pass
        self.app.data_changed(self.ctx.store)
        return "{}"

    @pyqtSlot(result=str)
    def getCookies(self) -> str:
        return json.dumps(self.ctx.cookies.summary()) if self._ok() else "[]"

    @pyqtSlot(str)
    def deleteCookies(self, domain: str) -> None:
        if self._ok():
            self.ctx.cookies.delete_domain(domain) if domain else self.ctx.cookies.delete_all()

    @pyqtSlot(result=str)
    def getDownloads(self) -> str:
        return json.dumps(self.ctx.downloads.records()) if self._ok() else "[]"

    @pyqtSlot(str)
    def openDownload(self, uid: str) -> None:
        rec = self.ctx.downloads.find(uid)
        if self._ok() and rec and os.path.exists(rec["path"]):
            QDesktopServices.openUrl(QUrl.fromLocalFile(rec["path"]))

    @pyqtSlot(str)
    def showDownload(self, uid: str) -> None:
        rec = self.ctx.downloads.find(uid)
        if self._ok() and rec:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(rec["path"])))

    @pyqtSlot(str)
    def cancelDownload(self, uid: str) -> None:
        if self._ok():
            self.ctx.downloads.cancel(uid)

    @pyqtSlot(str)
    def removeDownload(self, uid: str) -> None:
        if self._ok():
            self.ctx.downloads.remove(uid)

    @pyqtSlot(str)
    def removeHistory(self, raw: str) -> None:
        if not self._ok():
            return
        try:
            times = set(json.loads(raw))
        except (ValueError, TypeError):
            return
        store = self.ctx.store
        store.set("history", [h for h in store["history"] if h["time"] not in times])
        self.app.data_changed(store)

    @pyqtSlot(str)
    def removeBookmark(self, url: str) -> None:
        if not self._ok():
            return
        store = self.ctx.store
        store.set("bookmarks", [b for b in store["bookmarks"] if b["url"] != url])
        self.app.data_changed(store)

    @pyqtSlot(result=str)
    def chooseDownloadDir(self) -> str:
        if not self._ok():
            return ""
        d = QFileDialog.getExistingDirectory(self._window(), "Choose download folder", self.ctx.store["download_dir"])
        if d:
            self.ctx.store.set("download_dir", d)
        return d

    @pyqtSlot(str)
    def openProfile(self, pid: str) -> None:
        if self._ok():
            QTimer.singleShot(0, lambda: self.app.open_profile(pid))

    @pyqtSlot()
    def newProfile(self) -> None:
        if self._ok():
            QTimer.singleShot(0, self.app.add_profile)

    @pyqtSlot()
    def deleteProfile(self) -> None:
        if not self._ok():
            return
        store = self.ctx.store
        box = QMessageBox(self._window())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete profile")
        box.setText(f"Delete the profile “{store['name']}”?")
        box.setInformativeText("Its bookmarks, history, cookies and sign-ins will be permanently removed from this device.")
        box.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() == QMessageBox.StandardButton.Yes:
            QTimer.singleShot(0, lambda: self.app.delete_profile(store))

    @pyqtSlot(str)
    def saveAccounts(self, raw: str) -> None:
        if not self._ok():
            return
        try:
            clean = [{"id": str(a["id"])[:16], "service": str(a["service"])[:24], "label": str(a["label"])[:80],
                      "url": str(a["url"])[:500]} for a in json.loads(raw) if re.match(r"^https?://", str(a.get("url", "")))]
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        self.ctx.store.set("accounts", clean[:30])

    @pyqtSlot(str)
    def openAccount(self, aid: str) -> None:
        acc = next((a for a in self.ctx.store["accounts"] if a["id"] == aid), None)
        w = self.page.window
        if self._ok() and acc and w:
            QTimer.singleShot(0, lambda: w.open_url(acc["url"]))

    def _ext(self):
        return self.ctx.extensions if self._ok() else None

    @pyqtSlot(result=str)
    def installUnpacked(self) -> str:
        ext = self._ext()
        if not ext:
            return json.dumps({"ok": False, "msg": "Extensions aren't available in private windows."})
        d = QFileDialog.getExistingDirectory(self._window(), "Choose an unpacked extension folder", str(Path.home()))
        if not d:
            return "{}"
        ok, msg = ext.install_dir(Path(d))
        self.app.extensions_changed(self.ctx.store, msg)
        return json.dumps({"ok": ok, "msg": msg})

    @pyqtSlot(result=str)
    def installFile(self) -> str:
        ext = self._ext()
        if not ext:
            return json.dumps({"ok": False, "msg": "Extensions aren't available in private windows."})
        f, _ = QFileDialog.getOpenFileName(self._window(), "Choose an extension package", str(Path.home()),
                                           "Chrome extensions (*.crx *.zip)")
        if not f:
            return "{}"
        ok, msg = ext.install_archive(f)
        self.app.extensions_changed(self.ctx.store, msg)
        return json.dumps({"ok": ok, "msg": msg})

    @pyqtSlot(str)
    def installStore(self, ref: str) -> None:
        ext = self._ext()
        if ext:
            ext.install_store(ref)

    @pyqtSlot(str, bool)
    def setExtensionEnabled(self, ext_id: str, on: bool) -> None:
        ext = self._ext()
        if ext:
            ext.set_enabled(ext_id, on)

    @pyqtSlot(str)
    def removeExtension(self, ext_id: str) -> None:
        ext = self._ext()
        if ext:
            ext.remove(ext_id)

    @pyqtSlot(str)
    def openExtensionOptions(self, ext_id: str) -> None:
        ext, w = self._ext(), self.page.window
        rec = ext.get(ext_id) if ext else None
        if rec and rec["options"] and w:
            QTimer.singleShot(0, lambda: w.open_url(f"{SCHEME}://ext/{ext_id}/{rec['options']}"))


# ═════════════════════════════════════════════════════════════════════════════
#  Website permission prompt
# ═════════════════════════════════════════════════════════════════════════════

class WebPermissionDialog(QDialog):
    DETAILS = {
        "Notifications": ("Notifications", "Let this site show alerts from AwesomeBrowse."),
        "MediaAudioCapture": ("Microphone", "Let this site access your microphone."),
        "MediaVideoCapture": ("Camera", "Let this site access your webcam."),
        "MediaAudioVideoCapture": ("Camera and microphone", "Let this site access your webcam and microphone."),
        "Geolocation": ("Location", "Let this site access your approximate location."),
        "DesktopVideoCapture": ("Screen sharing", "Let this site capture your screen."),
        "DesktopAudioVideoCapture": ("Screen and audio sharing", "Let this site capture your screen and system audio."),
    }

    def __init__(self, parent, origin: QUrl, permission_name: str):
        super().__init__(parent)
        label, description = self.DETAILS.get(permission_name, (WebPage._nice(permission_name).capitalize(),
                                                                 "Let this site use the requested feature."))
        host = origin.host() or origin.toString()
        self.setWindowTitle("Site permission")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        heading = QLabel(f"Allow {label.lower()}?")
        heading.setObjectName("h2")
        site = QLabel(host)
        site.setObjectName("muted")
        site.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail = QLabel(description)
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(site)
        layout.addWidget(detail)
        layout.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        deny = QPushButton("Block")
        allow = QPushButton("Allow")
        allow.setProperty("primary", True)
        allow.setDefault(True)
        deny.clicked.connect(self.reject)
        allow.clicked.connect(self.accept)
        buttons.addWidget(deny)
        buttons.addWidget(allow)
        layout.addLayout(buttons)


# ═════════════════════════════════════════════════════════════════════════════
#  Pages and views
# ═════════════════════════════════════════════════════════════════════════════

class WebPage(QWebEnginePage):
    def __init__(self, ctx: Context, window: "MainWindow | None", parent=None):
        super().__init__(ctx.profile, parent)
        self.ctx, self.window = ctx, window
        self.channel = QWebChannel(self)
        self.bridge = Bridge(self, ctx)
        self.channel.registerObject("bridge", self.bridge)
        self._chan_on = False      # the bridge is only attached while an awesome:// page is showing
        self._last_crash = 0.0
        self.renderProcessTerminated.connect(self._crashed)
        if ctx.extensions:
            ctx.extensions.apply_to_page(self)
        self.authenticationRequired.connect(self._auth)
        self.certificateError.connect(self._cert)
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(self._permission)
        else:
            self.featurePermissionRequested.connect(self._feature)
        self._granted: set = set()

    def createWindow(self, wtype):
        if not self.window:
            return None
        bg = wtype == QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        view = self.window.add_tab(None, background=bg, after_current=True, blank=True)
        return view.page()

    def acceptNavigationRequest(self, url: QUrl, ntype, is_main: bool) -> bool:
        if url.scheme() in ("mailto", "tel", "magnet", "sms", "callto"):
            QDesktopServices.openUrl(url)
            return False
        if is_main:
            want = url.scheme() == SCHEME
            if want and url.host() == "newtab":
                self.setBackgroundColor(QColor(0, 0, 0, 0))
            else:
                self.setBackgroundColor(QColor(255, 255, 255))
            if want != self._chan_on:
                try:
                    self.setWebChannel(self.channel if want else None)
                except TypeError:
                    pass
                self._chan_on = want
        return super().acceptNavigationRequest(url, ntype, is_main)

    def _crashed(self, status, _code) -> None:
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            return
        now = time.time()
        if now - self._last_crash < 20:      # don't loop if a page keeps crashing
            return
        self._last_crash = now
        if self.window:
            self.window.toast("A tab ran out of memory or crashed, so it was reloaded")
        QTimer.singleShot(400, lambda: self.triggerAction(QWebEnginePage.WebAction.Reload))

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:  # keep stdout quiet
        pass

    def _auth(self, url: QUrl, auth: QAuthenticator) -> None:
        dlg = QDialog(self.window)
        dlg.setWindowTitle("Sign in")
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        lbl = QLabel(f"{url.host()} requires a username and password.")
        lbl.setWordWrap(True)
        user, pw = QLineEdit(), QLineEdit()
        for f, ph in ((user, "Username"), (pw, "Password")):
            f.setObjectName("field")
            f.setPlaceholderText(ph)
        pw.setEchoMode(QLineEdit.EchoMode.Password)
        row = QHBoxLayout()
        cancel, ok = QPushButton("Cancel"), QPushButton("Sign in")
        ok.setProperty("primary", True)
        cancel.clicked.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        for w in (lbl, user, pw):
            lay.addWidget(w)
        lay.addLayout(row)
        if dlg.exec():
            auth.setUser(user.text())
            auth.setPassword(pw.text())

    def _cert(self, error) -> None:
        error.defer()
        QTimer.singleShot(0, lambda: self._cert_ask(error))

    def _cert_ask(self, error) -> None:
        if not error.isOverridable():
            error.rejectCertificate()
            return
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Your connection isn’t private")
        box.setText(f"The certificate for {error.url().host()} can’t be verified.")
        box.setInformativeText(error.description())
        go = box.addButton("Continue anyway", QMessageBox.ButtonRole.DestructiveRole)
        back = box.addButton("Go back", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(back)
        box.exec()
        error.acceptCertificate() if box.clickedButton() is go else error.rejectCertificate()

    @staticmethod
    def _nice(name: str) -> str:
        known = {
            "Notifications": "notifications", "MediaAudioCapture": "microphone",
            "MediaVideoCapture": "camera", "MediaAudioVideoCapture": "camera and microphone",
            "Geolocation": "location", "DesktopVideoCapture": "screen sharing",
            "DesktopAudioVideoCapture": "screen and audio sharing",
        }
        return known.get(name, re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower())

    def _ask(self, origin: QUrl, permission_name: str) -> bool:
        if self.window is None:
            return False
        dialog = WebPermissionDialog(self.window, origin, permission_name)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _permission(self, perm) -> None:
        name = perm.permissionType().name
        perm.grant() if self._ask(perm.origin(), name) else perm.deny()

    def _feature(self, origin: QUrl, feature) -> None:
        key = (origin.host(), feature)
        P = QWebEnginePage.PermissionPolicy
        if key in self._granted or self._ask(origin, feature.name):
            self._granted.add(key)
            self.setFeaturePermission(origin, feature, P.PermissionGrantedByUser)
        else:
            self.setFeaturePermission(origin, feature, P.PermissionDeniedByUser)


class WebView(QWebEngineView):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.win = window
        self.pinned = False
        self.page_title = ""
        self.group: str | None = None
        self.key = 0
        self.last_active = time.time()
        self.protect_until = 0.0
        self.sleeping = False
        self.sleep_url: QUrl | None = None
        self.pending_url: str | None = None      # restored tabs load when first opened
        self.loading = False
        self.closing = False
        self.setPage(WebPage(window.ctx, window, self))

    def contextMenuEvent(self, ev) -> None:
        self.win.show_context_menu(self, ev.globalPos())


# ═════════════════════════════════════════════════════════════════════════════
#  Chrome widgets
# ═════════════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════════════
#  Motion and small controls
# ═════════════════════════════════════════════════════════════════════════════

GROUP_COLORS = ["#8ab4f8", "#f28b82", "#fdd663", "#81c995", "#ff8bcb", "#78d9ec", "#fcad70", "#d7aefb"]
SLEEP_CHOICES = [("Off", 0), ("5 minutes", 5), ("10 minutes", 10), ("15 minutes", 15), ("30 minutes", 30), ("1 hour", 60)]


def fmt_mb(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{int(mb)} MB"


class Toggle(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on, self._pos = checked, 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, v) -> None:
        self._pos = float(v)
        self.update()

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, on: bool, animate: bool = False) -> None:
        if on == self._on:
            return
        self._on = on
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(1.0 if on else 0.0)
            self._anim.start()
        else:
            self._pos = 1.0 if on else 0.0
            self.update()

    def mousePressEvent(self, _e) -> None:
        self.setChecked(not self._on, True)
        self.toggled.emit(self._on)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        off = self.palette().color(QPalette.ColorRole.Mid)
        on = self.palette().color(QPalette.ColorRole.Highlight)
        mix = lambda a, b: round(a + (b - a) * self._pos)
        track = QColor(mix(off.red(), on.red()), mix(off.green(), on.green()), mix(off.blue(), on.blue()))
        if not self.isEnabled():
            track.setAlpha(110)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        p.fillPath(path, track)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(3 + 18 * self._pos, 3, 16, 16))


class Spark(QWidget):
    CAP = 60

    def __init__(self):
        super().__init__()
        self.values: list[float] = []
        self.limit: float | None = None
        self.setMinimumHeight(74)
        self.setMaximumHeight(74)

    def set_data(self, values: list[float], limit: float | None) -> None:
        self.values, self.limit = values[-self.CAP:], limit
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 6, 0, -4)
        pal = self.palette()
        acc, sub = pal.color(QPalette.ColorRole.Highlight), pal.color(QPalette.ColorRole.PlaceholderText)
        top = max(max(self.values, default=0), self.limit or 0, 1) * 1.15
        base = QColor(sub)
        base.setAlpha(70)
        p.setPen(QPen(base, 1))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        if len(self.values) > 1:
            step = r.width() / (self.CAP - 1)
            n = len(self.values)
            pts = [QPointF(r.right() - (n - 1 - i) * step, r.bottom() - v / top * r.height())
                   for i, v in enumerate(self.values)]
            path = QPainterPath(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            fill = QPainterPath(path)
            fill.lineTo(pts[-1].x(), r.bottom())
            fill.lineTo(pts[0].x(), r.bottom())
            fill.closeSubpath()
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            c1, c2 = QColor(acc), QColor(acc)
            c1.setAlpha(120)
            c2.setAlpha(8)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.fillPath(fill, g)
            p.setPen(QPen(acc, 1.8))
            p.drawPath(path)
        if self.limit:
            y = r.bottom() - self.limit / top * r.height()
            pen = QPen(QColor("#e5a03a"), 1.2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))


class ContentArea(QStackedWidget):
    """Holds the active tab view. `flash` fades a veil away to
    soften tab switches without touching the web content itself."""

    def __init__(self):
        super().__init__()
        self.curtain = QWidget(self)
        self.curtain.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.curtain.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.curtain.hide()
        self.fx = QGraphicsOpacityEffect(self.curtain)
        self.curtain.setGraphicsEffect(self.fx)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.finished.connect(self.curtain.hide)

    def set_color(self, color: str) -> None:
        self.curtain.setStyleSheet(f"background: {color};")

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.curtain.setGeometry(self.rect())

    def flash(self, strength: float = 0.6, ms: int = 210) -> None:
        self.anim.stop()
        self.curtain.setGeometry(self.rect())
        self.curtain.show()
        self.curtain.raise_()
        self.anim.setDuration(ms)
        self.anim.setStartValue(strength)
        self.anim.setEndValue(0.0)
        self.anim.start()


class FormDialog(QDialog):
    def __init__(self, parent, title: str, fields: list, ok: str = "Save"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(8)
        head = QLabel(title)
        head.setObjectName("h2")
        lay.addWidget(head)
        self.edits: list[QLineEdit] = []
        for label, default, placeholder in fields:
            lab = QLabel(label)
            lab.setObjectName("muted")
            e = QLineEdit(default)
            e.setObjectName("field")
            e.setPlaceholderText(placeholder)
            lay.addWidget(lab)
            lay.addWidget(e)
            self.edits.append(e)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel, go = QPushButton("Cancel"), QPushButton(ok)
        go.setProperty("primary", True)
        go.setDefault(True)
        cancel.clicked.connect(self.reject)
        go.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(go)
        lay.addSpacing(8)
        lay.addLayout(row)
        if self.edits:
            self.edits[0].setFocus()

    def values(self) -> list[str]:
        return [e.text().strip() for e in self.edits]


class GroupDialog(QDialog):
    def __init__(self, parent, name: str = "", color: str | None = None, title: str = "New tab group"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(400)
        self.color = color or GROUP_COLORS[0]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        head = QLabel(title)
        head.setObjectName("h2")
        lay.addWidget(head)
        hint = QLabel("Name the group and choose a color to identify its tabs.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.name = QLineEdit(name)
        self.name.setObjectName("field")
        self.name.setPlaceholderText("Name this group, like Research or Sprint 12")
        self.name.setMaxLength(24)
        lay.addWidget(self.name)
        sw = QHBoxLayout()
        sw.setSpacing(2)
        self.swatches: list[Swatch] = []
        for c in GROUP_COLORS:
            s = Swatch(c)
            s.setToolTip(f"Group color {c}")
            s.on = c == self.color
            s.clicked.connect(self._pick)
            self.swatches.append(s)
            sw.addWidget(s)
        sw.addStretch(1)
        lay.addLayout(sw)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel, go = QPushButton("Cancel"), QPushButton("Save")
        go.setProperty("primary", True)
        go.setDefault(True)
        cancel.clicked.connect(self.reject)
        go.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(go)
        lay.addSpacing(6)
        lay.addLayout(row)
        self.name.setFocus()
        self.name.selectAll()

    def _pick(self, c: str) -> None:
        self.color = c
        for s in self.swatches:
            s.on = s.color == c
            s.update()

    def values(self) -> tuple[str, str]:
        return self.name.text().strip(), self.color


# ═════════════════════════════════════════════════════════════════════════════
#  Print interface
# ═════════════════════════════════════════════════════════════════════════════

class PrintPreviewDialog(QDialog):
    def __init__(self, owner: "MainWindow", printer: QPrinter, title: str):
        super().__init__(owner)
        self.owner, self.printer = owner, printer
        self.setObjectName("printInterface")
        self.setWindowTitle("Print")
        self.setMinimumSize(920, 620)
        self.resize(1180, 780)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("printHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 14, 22, 14)
        hl.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(owner.app.logo_icon.pixmap(24, 24))
        hl.addWidget(mark)
        heading = QVBoxLayout()
        heading.setSpacing(1)
        title_label = QLabel("Print page")
        title_label.setStyleSheet("font-size:16px;font-weight:650")
        self.subtitle = QLabel(title or "Web page")
        self.subtitle.setObjectName("printHint")
        self.subtitle.setMaximumWidth(520)
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        heading.addWidget(title_label)
        heading.addWidget(self.subtitle)
        hl.addLayout(heading, 1)
        root.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        setup = QFrame()
        setup.setObjectName("printSetup")
        setup.setFixedWidth(258)
        form = QVBoxLayout(setup)
        form.setContentsMargins(17, 18, 17, 16)
        form.setSpacing(8)
        section = QLabel("PAGE SETUP")
        section.setObjectName("printSection")
        form.addWidget(section)

        self.printer_choice = QComboBox()
        self.printer_names = list(QPrinterInfo.availablePrinterNames())
        default_printer = QPrinterInfo.defaultPrinterName()
        if self.printer_names:
            for printer_name in self.printer_names:
                suffix = " · Default" if printer_name == default_printer else ""
                self.printer_choice.addItem(printer_name + suffix, printer_name)
            selected = self.printer_choice.findData(default_printer)
            self.printer_choice.setCurrentIndex(selected if selected >= 0 else 0)
            self.printer.setPrinterName(self.printer_choice.currentData())
        else:
            self.printer_choice.addItem("No printers found", "")
            self.printer_choice.setEnabled(False)
        form.addWidget(QLabel("Printer"))
        form.addWidget(self.printer_choice)

        self.paper = QComboBox()
        for label, page_id in (("A4", QPageSize.PageSizeId.A4), ("Letter", QPageSize.PageSizeId.Letter),
                               ("A3", QPageSize.PageSizeId.A3), ("A5", QPageSize.PageSizeId.A5),
                               ("Legal", QPageSize.PageSizeId.Legal)):
            self.paper.addItem(label, page_id)
        form.addWidget(QLabel("Paper size"))
        form.addWidget(self.paper)

        self.orientation = QComboBox()
        self.orientation.addItem("Portrait", QPageLayout.Orientation.Portrait)
        self.orientation.addItem("Landscape", QPageLayout.Orientation.Landscape)
        form.addWidget(QLabel("Orientation"))
        form.addWidget(self.orientation)

        self.margins = QComboBox()
        for label, size in (("Default · 12 mm", 12), ("Narrow · 6 mm", 6),
                            ("Wide · 20 mm", 20), ("None", 0)):
            self.margins.addItem(label, size)
        form.addWidget(QLabel("Margins"))
        form.addWidget(self.margins)

        self.color = QComboBox()
        self.color.addItem("Color", QPrinter.ColorMode.Color)
        self.color.addItem("Grayscale", QPrinter.ColorMode.GrayScale)
        form.addWidget(QLabel("Output"))
        form.addWidget(self.color)

        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.copies.setValue(1)
        form.addWidget(QLabel("Copies"))
        form.addWidget(self.copies)
        form.addStretch(1)
        setup_hint = QLabel("Preview updates with your settings.")
        setup_hint.setObjectName("printHint")
        setup_hint.setWordWrap(True)
        form.addWidget(setup_hint, 0)
        body_layout.addWidget(setup)

        stage = QFrame()
        stage.setObjectName("printStage")
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(18, 16, 18, 18)
        stage_layout.setSpacing(12)
        nav = QHBoxLayout()
        preview_title = QLabel("PREVIEW")
        preview_title.setObjectName("printSection")
        nav.addWidget(preview_title)
        nav.addStretch(1)
        self.previous = QToolButton()
        self.previous.setObjectName("printNav")
        self.previous.setText("‹")
        self.previous.setFixedSize(32, 30)
        self.previous.setToolTip("Previous page")
        self.page_number = QSpinBox()
        self.page_number.setRange(1, 1)
        self.page_number.setFixedWidth(62)
        self.page_total = QLabel("of 0 pages")
        self.page_total.setObjectName("printHint")
        self.next = QToolButton()
        self.next.setObjectName("printNav")
        self.next.setText("›")
        self.next.setFixedSize(32, 30)
        self.next.setToolTip("Next page")
        nav.addWidget(self.previous)
        nav.addWidget(self.page_number)
        nav.addWidget(self.page_total)
        nav.addWidget(self.next)
        nav.addSpacing(12)
        zoom_out = QToolButton()
        zoom_out.setObjectName("printNav")
        zoom_out.setText("−")
        zoom_out.setFixedSize(32, 30)
        zoom_out.setToolTip("Zoom out")
        fit = QPushButton("Fit page")
        fit.setFixedHeight(30)
        fit.setToolTip("Fit the full page in the preview")
        fit_width = QPushButton("Fit width")
        fit_width.setFixedHeight(30)
        fit_width.setToolTip("Fit the page width in the preview")
        zoom_in = QToolButton()
        zoom_in.setObjectName("printNav")
        zoom_in.setText("+")
        zoom_in.setFixedSize(32, 30)
        zoom_in.setToolTip("Zoom in")
        nav.addWidget(zoom_out)
        nav.addWidget(fit)
        nav.addWidget(fit_width)
        nav.addWidget(zoom_in)
        stage_layout.addLayout(nav)

        self.preview = QPrintPreviewWidget(printer, stage)
        self.preview.setObjectName("printPreview")
        self.preview.setMinimumSize(500, 420)
        self.preview.setSinglePageViewMode()
        preview_palette = QPalette(self.preview.palette())
        preview_palette.setColor(QPalette.ColorRole.Window, QColor("#e9edf2"))
        preview_palette.setColor(QPalette.ColorRole.Base, QColor("#e9edf2"))
        preview_palette.setColor(QPalette.ColorRole.Dark, QColor("#d4d9e0"))
        self.preview.setPalette(preview_palette)
        self.preview.setAutoFillBackground(True)
        self.preview.paintRequested.connect(owner._print_document)
        self.preview.previewChanged.connect(self.refresh_page_controls)
        stage_layout.addWidget(self.preview, 1)
        body_layout.addWidget(stage, 1)
        root.addWidget(body, 1)
        self._preview_initialized = False

        footer = QWidget()
        footer.setObjectName("printFooter")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(20, 12, 20, 12)
        footer_hint = QLabel("Send to a printer or save a PDF.")
        footer_hint.setObjectName("printHint")
        actions.addWidget(footer_hint, 1)
        cancel = QPushButton("Cancel")
        self.pdf_button = QPushButton("Save as PDF")
        actions.addWidget(self.pdf_button)
        self.print_button = QPushButton("Print")
        self.print_button.setProperty("primary", True)
        self.print_button.setMinimumWidth(112)
        self.print_button.setEnabled(bool(self.printer_names))
        actions.addWidget(cancel)
        actions.addWidget(self.print_button)
        root.addWidget(footer)

        self.paper.currentIndexChanged.connect(self.update_printer_settings)
        self.printer_choice.currentIndexChanged.connect(self.select_printer)
        self.orientation.currentIndexChanged.connect(self.update_printer_settings)
        self.margins.currentIndexChanged.connect(self.update_printer_settings)
        self.color.currentIndexChanged.connect(self.update_printer_settings)
        self.copies.valueChanged.connect(self.update_printer_settings)
        self.page_number.valueChanged.connect(self.preview.setCurrentPage)
        self.previous.clicked.connect(lambda: self.preview.setCurrentPage(max(1, self.preview.currentPage() - 1)))
        self.next.clicked.connect(lambda: self.preview.setCurrentPage(
            min(max(1, self.preview.pageCount()), self.preview.currentPage() + 1)))
        zoom_out.clicked.connect(self.preview.zoomOut)
        zoom_in.clicked.connect(self.preview.zoomIn)
        fit.clicked.connect(self.preview.fitInView)
        fit_width.clicked.connect(self.preview.fitToWidth)
        cancel.clicked.connect(self.reject)
        self.print_button.clicked.connect(self.print_to_device)
        self.pdf_button.clicked.connect(self.save_pdf)
        self.select_printer()
        self.update_printer_settings()
        QTimer.singleShot(0, self.initialize_preview)

    def initialize_preview(self) -> None:
        # Fit after the dialog has been shown and layouts have assigned the
        # preview its final viewport size. Fitting at construction time uses a
        # zero-sized viewport and can leave the first page awkwardly scaled.
        if not self.preview.isVisible():
            QTimer.singleShot(50, self.initialize_preview)
            return
        self.preview.fitInView()
        self.preview.updatePreview()
        self._preview_initialized = True
        self.refresh_page_controls()

    def update_printer_settings(self, *_args) -> None:
        self.printer.setPageSize(QPageSize(self.paper.currentData()))
        self.preview.setOrientation(self.orientation.currentData())
        margin = float(self.margins.currentData())
        self.printer.setFullPage(margin == 0)
        self.printer.setPageMargins(QMarginsF(margin, margin, margin, margin), QPageLayout.Unit.Millimeter)
        self.printer.setColorMode(self.color.currentData())
        self.printer.setCopyCount(self.copies.value())
        if self._preview_initialized:
            self.preview.updatePreview()
            QTimer.singleShot(0, self.refresh_page_controls)

    def select_printer(self, *_args) -> None:
        name = self.printer_choice.currentData()
        if not name:
            return
        self.printer.setPrinterName(name)
        info = QPrinterInfo.printerInfo(name)
        if not info.isNull() and info.defaultPageSize().isValid():
            page_index = self.paper.findData(info.defaultPageSize().id())
            if page_index >= 0:
                self.paper.setCurrentIndex(page_index)
        self.update_printer_settings()

    def refresh_page_controls(self) -> None:
        count = self.preview.pageCount()
        current = max(1, self.preview.currentPage())
        self.page_number.blockSignals(True)
        self.page_number.setRange(1, max(1, count))
        self.page_number.setValue(min(current, max(1, count)))
        self.page_number.blockSignals(False)
        self.page_total.setText(f"of {count} page{'s' if count != 1 else ''}" if count else "Preparing preview…")
        self.previous.setEnabled(count > 1 and current > 1)
        self.next.setEnabled(count > 1 and current < count)

    def print_to_device(self) -> None:
        self.print_button.setEnabled(False)
        self.print_button.setText("Printing…")
        QApplication.processEvents()
        if self.owner._print_document(self.printer):
            self.accept()
        else:
            self.print_button.setEnabled(True)
            self.print_button.setText("Print")

    def save_pdf(self) -> None:
        default_name = re.sub(r'[\\/:*?"<>|]+', "_", self.subtitle.text() or "Web page") + ".pdf"
        initial = os.path.join(self.owner.store["download_dir"], default_name)
        path, _ = QFileDialog.getSaveFileName(self, "Save print output as PDF", initial, "PDF files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self.printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        self.printer.setOutputFileName(path)
        QApplication.processEvents()
        ok = self.owner._print_document(self.printer)
        self.printer.setOutputFileName("")
        self.printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
        if ok:
            self.owner.toast(f"Saved PDF: {os.path.basename(path)}")
            self.accept()
        else:
            QMessageBox.warning(self, "PDF export failed", "The page could not be rendered as a PDF.")


# ═════════════════════════════════════════════════════════════════════════════
#  Tab bar with groups, multi-select and animated tabs
# ═════════════════════════════════════════════════════════════════════════════

class ChipItem:
    """Stands in for a tab group's label in the tab bar."""
    __slots__ = ("gid",)

    def __init__(self, gid: str):
        self.gid = gid


class TabBar(QTabBar):
    newTabRequested = pyqtSignal()
    chipClicked = pyqtSignal(str)
    tabModClick = pyqtSignal(int, object)
    plainClick = pyqtSignal()
    PIN_W = 46

    def __init__(self):
        super().__init__()
        self.setExpanding(False)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setUsesScrollButtons(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setSelectionBehaviorOnRemove(QTabBar.SelectionBehavior.SelectPreviousTab)
        self.setIconSize(QSize(16, 16))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.available = 900
        self.h = 36
        self.pill = False
        self.factors: dict[int, float] = {}
        self.provider = None          # callable(index) -> dict, supplied by the window
        self._anims: dict[int, QVariantAnimation] = {}
        self._pinned = self._regular = 0
        self._chips_w = 0

    def meta(self, i: int) -> dict:
        d = self.tabData(i) if 0 <= i < self.count() else None
        return d if isinstance(d, dict) else {}

    def _chip_width(self, i: int) -> int:
        info = self.provider(i) if self.provider else {}
        metrics = QFontMetrics(self.font())
        return metrics.horizontalAdvance(info.get("label", "")) + metrics.horizontalAdvance(str(info.get("count", 0))) + 50

    def _recount(self) -> None:
        self._pinned = self._regular = self._chips_w = 0
        for i in range(self.count()):
            if not self.isTabVisible(i):
                continue
            m = self.meta(i)
            if m.get("chip"):
                self._chips_w += self._chip_width(i)
            elif m.get("pinned"):
                self._pinned += 1
            else:
                self._regular += 1

    def tabSizeHint(self, i: int) -> QSize:
        m = self.meta(i)
        f = self.factors.get(m.get("key"), 1.0)
        if m.get("chip"):
            return QSize(max(24, int(self._chip_width(i) * f)), self.h)
        if m.get("pinned"):
            return QSize(max(8, int(self.PIN_W * f)), self.h)
        free = self.available - self._pinned * self.PIN_W - self._chips_w
        w = free // max(1, self._regular)
        return QSize(max(8, int(max(44, min(240, w)) * f)), self.h)

    def relayout(self) -> None:
        self._recount()
        if self.count():
            self.setTabText(0, self.tabText(0))
        self.updateGeometry()
        self.update()

    def animate(self, key: int, start: float, end: float, ms: int = 190, done=None) -> None:
        old = self._anims.pop(key, None)
        if old:
            old.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def step(v) -> None:
            self.factors[key] = max(0.03, float(v))
            self.relayout()

        def fin() -> None:
            self._anims.pop(key, None)
            if end >= 1.0:
                self.factors.pop(key, None)
            self.relayout()
            if done:
                done()
        anim.valueChanged.connect(step)
        anim.finished.connect(fin)
        self._anims[key] = anim
        self.factors[key] = max(0.03, float(start))
        anim.start()

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if not self.provider:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(self.count()):
            if not self.isTabVisible(i):
                continue
            info = self.provider(i)
            r = self.tabRect(i)
            if info.get("kind") == "chip":
                rr = QRectF(r).adjusted(3, 6, -3, -6)
                path = QPainterPath()
                path.addRoundedRect(rr, rr.height() / 2, rr.height() / 2)
                color = QColor(info["color"])
                tint = QColor(color)
                tint.setAlpha(48)
                border = QColor(color)
                border.setAlpha(140)
                p.fillPath(path, tint)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(border, 1))
                p.drawPath(path)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawEllipse(QRectF(rr.left() + 8, rr.center().y() - 3.5, 7, 7))
                p.setPen(QColor(info["fg"]))
                f = p.font()
                f.setPixelSize(11)
                f.setBold(True)
                p.setFont(f)
                label_rect = rr.adjusted(20, 0, -24, 0)
                p.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           p.fontMetrics().elidedText(info["label"], Qt.TextElideMode.ElideRight,
                                                      max(10, int(label_rect.width()))))
                count_rect = QRectF(rr.right() - 21, rr.center().y() - 8, 16, 16)
                count_bg = QColor(color)
                count_bg.setAlpha(70)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(count_bg)
                p.drawEllipse(count_rect)
                p.setPen(QColor(info["fg"]))
                count_font = p.font()
                count_font.setPixelSize(9)
                count_font.setBold(True)
                p.setFont(count_font)
                p.drawText(count_rect, Qt.AlignmentFlag.AlignCenter, str(info.get("count", "")))
                continue
            if info.get("color"):
                bar = QPainterPath()
                if self.pill:
                    bar.addRoundedRect(QRectF(r.left() + 16, r.bottom() - 9, max(4, r.width() - 32), 3), 1.5, 1.5)
                else:
                    bar.addRoundedRect(QRectF(r.left() + 8, r.top() + 6, max(4, r.width() - 16), 3), 1.5, 1.5)
                p.fillPath(bar, QColor(info["color"]))
            if info.get("selected"):
                p.setPen(QPen(QColor(info["accent"]), 1.8))
                p.setBrush(Qt.BrushStyle.NoBrush)
                if self.pill:
                    p.drawRoundedRect(QRectF(r).adjusted(3, 5, -3, -5), 15, 15)
                else:
                    p.drawRoundedRect(QRectF(r).adjusted(2, 6, -2, -1), 9, 9)

    def mousePressEvent(self, e) -> None:
        i = self.tabAt(e.position().toPoint())
        if e.button() == Qt.MouseButton.LeftButton and i >= 0:
            m = self.meta(i)
            if m.get("chip"):
                self.chipClicked.emit(m["chip"])
                return
            mods = e.modifiers()
            if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                self.tabModClick.emit(i, mods)
                return
            self.plainClick.emit()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.MiddleButton:
            i = self.tabAt(e.position().toPoint())
            if i >= 0 and not self.meta(i).get("chip"):
                self.tabCloseRequested.emit(i)
                return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if self.tabAt(e.position().toPoint()) < 0:
            self.newTabRequested.emit()
        else:
            super().mouseDoubleClickEvent(e)


class AddressBar(QLineEdit):
    escaped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Search or enter address")
        self.setFixedHeight(34)
        self.candidates: list[str] = []       # frecency-ordered sites, used for inline completion
        self._last_len = 0
        self.textEdited.connect(self._inline)

    def _inline(self, text: str) -> None:
        grew = len(text) > self._last_len
        self._last_len = len(text)
        if not grew or len(text) < 2 or " " in text:
            return
        low = text.lower()
        for c in self.candidates:
            if len(c) > len(text) and c.lower().startswith(low):
                self.blockSignals(True)
                self.setText(text + c[len(text):])
                self.setCursorPosition(len(text))
                self.cursorForward(True, len(c) - len(text))
                self.blockSignals(False)
                return

    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        if e.reason() != Qt.FocusReason.PopupFocusReason:
            QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(e)


def style_popup(menu: QMenu) -> QMenu:
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return menu


def add_action(menu: QMenu, text: str, slot=None, shortcut: str = "", enabled: bool = True,
               checkable: bool = False, checked: bool = False) -> QAction:
    act = QAction(text + ("\t" + shortcut if shortcut else ""), menu)
    act.setEnabled(enabled)
    if checkable:
        act.setCheckable(True)
        act.setChecked(checked)
    if slot:
        act.triggered.connect(lambda _=False, s=slot: s())
    menu.addAction(act)
    return act


class ZoomRow(QWidget):
    def __init__(self, win: "MainWindow", menu: QMenu):
        super().__init__(menu)
        self.win, self.menu = win, menu
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 4, 6, 4)
        lay.setSpacing(2)
        lay.addWidget(QLabel("Zoom"))
        lay.addStretch(1)
        for name, delta in (("minus", -1),):
            lay.addWidget(self._btn(name, lambda d=delta: self._step(d), "Zoom out"))
        self.value = QLabel("100%")
        self.value.setFixedWidth(50)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.value)
        lay.addWidget(self._btn("plus", lambda: self._step(1), "Zoom in"))
        lay.addSpacing(8)
        lay.addWidget(self._btn("fullscreen", self._fullscreen, "Full screen (F11)"))
        self.refresh()

    def _btn(self, icon: str, fn, tip: str) -> QToolButton:
        b = QToolButton()
        b.setIcon(self.win.ic(icon))
        b.setIconSize(QSize(16, 16))
        b.setFixedSize(30, 30)
        b.setToolTip(tip)
        b.clicked.connect(lambda: fn())
        return b

    def refresh(self) -> None:
        v = self.win.current_view()
        self.value.setText(f"{round((v.zoomFactor() if v else 1) * 100)}%")

    def _step(self, d: int) -> None:
        self.win.zoom_step(d)
        self.refresh()

    def _fullscreen(self) -> None:
        self.menu.close()
        QTimer.singleShot(60, self.win.toggle_fullscreen)


# ═════════════════════════════════════════════════════════════════════════════
#  Left sidebar: memory, workspaces, notes, web panels
# ═════════════════════════════════════════════════════════════════════════════

class _Panel(QScrollArea):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("panelbody")
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(16, 16, 16, 20)
        self.lay.setSpacing(10)
        self.setWidget(self.body)
        self.viewport().setAutoFillBackground(False)

    def title(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("h2")
        self.lay.addWidget(lab)
        return lab

    def section(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("sect")
        self.lay.addWidget(lab)
        return lab

    def note(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("muted")
        lab.setWordWrap(True)
        self.lay.addWidget(lab)
        return lab

    def row(self, label: str, widget: QWidget) -> None:
        h = QHBoxLayout()
        lab = QLabel(label)
        lab.setWordWrap(True)
        h.addWidget(lab, 1)
        h.addWidget(widget)
        self.lay.addLayout(h)

    @staticmethod
    def button(text: str, fn, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setProperty("primary", primary)
        b.clicked.connect(lambda: fn())
        return b

    def refresh(self) -> None:
        pass


class PerfPanel(_Panel):
    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.gov = win.app.governor
        self._loading = True
        self._last_tabs = None
        self.title("Memory")
        self.big = QLabel("0 MB")
        self.big.setObjectName("bigstat")
        self.lay.addWidget(self.big)
        self.sub = self.note("")
        self.spark = Spark()
        self.lay.addWidget(self.spark)
        self.status = self.note("")

        self.section("Limiter")
        self.t_enabled = Toggle()
        self.row("Keep AwesomeBrowse under a memory limit", self.t_enabled)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        total = self.gov.total_mb
        self.slider.setRange(LIMIT_MIN_MB, clamp_limit(1e9, total))
        self.slider.setSingleStep(LIMIT_STEP_MB)
        self.slider.setPageStep(512)
        self.limit_label = QLabel()
        self.limit_label.setMinimumWidth(58)
        h = QHBoxLayout()
        h.addWidget(self.slider, 1)
        h.addWidget(self.limit_label)
        self.lay.addLayout(h)
        self.note(f"The lowest limit is {fmt_mb(LIMIT_MIN_MB)}. Below that the browser itself wouldn't fit.")
        self.mode = QComboBox()
        self.mode.addItems(["Balanced", "Aggressive"])
        self.row("Mode", self.mode)
        self.note("Balanced sleeps the tab you haven't used for longest. Aggressive also sleeps pinned tabs and acts a little earlier.")
        self.sleep = QComboBox()
        for label, _m in SLEEP_CHOICES:
            self.sleep.addItem(label)
        self.row("Sleep idle tabs after", self.sleep)
        self.t_hard = Toggle()
        self.row("Hard heap cap per tab", self.t_hard)
        self.hard_note = self.note("Also caps each tab's JavaScript memory. Takes effect after a restart. A tab that hits the cap "
                                   "reloads on its own; the browser keeps running.")
        self.free_btn = self.button("Free memory now", self._free, True)
        self.lay.addWidget(self.free_btn)

        self.section("Tabs in this window")
        self.tabs = QListWidget()
        self.tabs.setMinimumHeight(170)
        self.lay.addWidget(self.tabs)
        row = QHBoxLayout()
        row.addWidget(self.button("Sleep tab", self._sleep_sel))
        row.addWidget(self.button("Wake tab", self._wake_sel))
        self.lay.addLayout(row)
        self.lay.addStretch(1)

        self._commit = QTimer(self)
        self._commit.setSingleShot(True)
        self._commit.setInterval(350)
        self._commit.timeout.connect(self._push)
        self.t_enabled.toggled.connect(lambda _v: self._changed())
        self.t_hard.toggled.connect(lambda _v: self._changed())
        self.slider.valueChanged.connect(self._slider)
        self.mode.currentIndexChanged.connect(lambda _i: self._changed())
        self.sleep.currentIndexChanged.connect(lambda _i: self._changed())
        self.tabs.itemDoubleClicked.connect(self._toggle_item)
        self._loading = False
        self.on_update()

    def _slider(self, v: int) -> None:
        snapped = clamp_limit(v, self.gov.total_mb)
        self.limit_label.setText(fmt_mb(snapped))
        if not self._loading:
            self._changed()

    def _changed(self) -> None:
        if not self._loading:
            self._commit.start()

    def _push(self) -> None:
        self.gov.set_config(enabled=self.t_enabled.isChecked(), limit_mb=self.slider.value(),
                            mode="aggressive" if self.mode.currentIndex() else "balanced",
                            sleep_min=SLEEP_CHOICES[self.sleep.currentIndex()][1],
                            hard_cap=self.t_hard.isChecked())

    def on_update(self) -> None:
        g, cfg = self.gov, self.gov.cfg
        if not self._commit.isActive() and not self.slider.isSliderDown():   # don't fight a change that's about to be saved
            self._loading = True
            self.t_enabled.setChecked(bool(cfg["enabled"]))
            self.t_hard.setChecked(bool(cfg["hard_cap"]))
            self.slider.setValue(int(cfg["limit_mb"]))
            self.limit_label.setText(fmt_mb(cfg["limit_mb"]))
            self.mode.setCurrentIndex(1 if cfg["mode"] == "aggressive" else 0)
            idx = next((i for i, (_l, m) in enumerate(SLEEP_CHOICES) if m == cfg["sleep_min"]), 0)
            self.sleep.setCurrentIndex(idx)
            self._loading = False
        self.slider.setEnabled(bool(cfg["enabled"]))
        self.big.setText(fmt_mb(g.used))
        if cfg["enabled"]:
            pct = int(g.used / max(1, cfg["limit_mb"]) * 100)
            line = f"{pct}% of your {fmt_mb(cfg['limit_mb'])} limit"
        else:
            line = f"Limiter is off. This computer has {fmt_mb(g.total_mb)}." if g.total_mb else "Limiter is off."
        if not g.accurate:
            line += " Numbers are approximate. Install psutil for exact figures."
        if g.safe_mode:
            line += " Safe mode: the hard cap is ignored this session."
        self.sub.setText(line)
        self.spark.set_data(g.history, cfg["limit_mb"] if cfg["enabled"] else None)
        self.status.setText(g.status)
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        win = self.win
        rows = []
        for v in win.tab_views():
            state = "Sleeping" if v.sleeping else ("Visible" if win.is_visible_view(v) else "Active")
            rows.append((id(v), state, v.page_title or v.url().host() or "New tab"))
        if rows == self._last_tabs:
            return
        self._last_tabs = rows
        cur = self.tabs.currentRow()
        self.tabs.clear()
        for v in win.tab_views():
            state = "Sleeping" if v.sleeping else ("Visible" if win.is_visible_view(v) else "Active")
            it = QListWidgetItem(f"{state}   {(v.page_title or v.url().host() or 'New tab')[:38]}")
            it.setData(Qt.ItemDataRole.UserRole, v)
            self.tabs.addItem(it)
        if 0 <= cur < self.tabs.count():
            self.tabs.setCurrentRow(cur)

    def _selected(self):
        it = self.tabs.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _toggle_item(self, it) -> None:
        v = it.data(Qt.ItemDataRole.UserRole)
        if v:
            self.win.wake_view(v) if v.sleeping else self.win.sleep_view(v, force=True)
            self._last_tabs = None
            self.refresh()

    def _sleep_sel(self) -> None:
        v = self._selected()
        if v:
            self.win.sleep_view(v, force=True)
            self._last_tabs = None
            self.refresh()

    def _wake_sel(self) -> None:
        v = self._selected()
        if v:
            self.win.wake_view(v)
            self._last_tabs = None
            self.refresh()

    def _free(self) -> None:
        n = self.gov.free_now()
        self.win.toast(f"Put {n} tab{'s' if n != 1 else ''} to sleep" if n else "Nothing to free: only visible tabs are open")
        self._last_tabs = None
        self.on_update()


class WorkPanel(_Panel):
    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.title("Workspace")
        self.section("Tab groups")
        self.groups = QListWidget()
        self.groups.setMinimumHeight(110)
        self.groups.itemClicked.connect(lambda it: win.focus_group(it.data(Qt.ItemDataRole.UserRole)))
        self.lay.addWidget(self.groups)
        self.note("Ctrl+click or Shift+click tabs to select several, then group them.")
        row = QHBoxLayout()
        row.addWidget(self.button("Group selected", win.group_selected))
        row.addWidget(self.button("Group this tab", win.group_current))
        self.lay.addLayout(row)

        self.section("Saved workspaces")
        self.spaces = QListWidget()
        self.spaces.setMinimumHeight(110)
        self.lay.addWidget(self.spaces)
        row = QHBoxLayout()
        row.addWidget(self.button("Save current", win.save_workspace))
        row.addWidget(self.button("Restore", self._restore))
        row.addWidget(self.button("Delete", self._delete))
        self.lay.addLayout(row)
        self.lay.addStretch(1)
        self.refresh()

    def _restore(self) -> None:
        r = self.spaces.currentRow()
        if r >= 0:
            self.win.restore_workspace(r)

    def _delete(self) -> None:
        r = self.spaces.currentRow()
        if r >= 0:
            self.win.delete_workspace(r)

    def refresh(self) -> None:
        win = self.win
        self.groups.clear()
        for gid, g in win.groups.items():
            n = sum(1 for v in win.tab_views() if v.group == gid)
            pm = QPixmap(14, 14)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor(g["color"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(1, 1, 12, 12)
            p.end()
            it = QListWidgetItem(QIcon(pm), f"{g['name'] or 'Unnamed'}   ({n})")
            it.setData(Qt.ItemDataRole.UserRole, gid)
            self.groups.addItem(it)
        self.spaces.clear()
        for w in win.store["workspaces"]:
            self.spaces.addItem(f"{w['name']}   ({len(w['tabs'])} tabs)")


class NotesPanel(_Panel):
    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.title("Notes")
        self.edit = QPlainTextEdit()
        self.edit.setObjectName("notes")
        self.edit.setPlaceholderText("Jot things down while you browse. Notes stay with this profile.")
        self.edit.setPlainText(win.store["notes"])
        self.edit.setMinimumHeight(320)
        self.lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        row.addWidget(self.button("Add page link", self._link))
        row.addWidget(self.button("Copy all", lambda: QApplication.clipboard().setText(self.edit.toPlainText())))
        self.lay.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(lambda: win.store.set("notes", self.edit.toPlainText()))
        self.edit.textChanged.connect(self._timer.start)

    def _link(self) -> None:
        v = self.win.current_view()
        if v and v.url().scheme() in ("http", "https"):
            self.edit.appendPlainText(f"{v.title() or v.url().host()}\n{v.url().toString()}\n")


class WebPanels(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.views: dict[str, QWebEngineView] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 14, 12, 12)
        v.setSpacing(8)
        t = QLabel("Web panels")
        t.setObjectName("h2")
        v.addWidget(t)
        head = QHBoxLayout()
        self.combo = QComboBox()
        head.addWidget(self.combo, 1)
        self._btns = []
        for icon, tip, fn in (("plus", "Add a web panel", self.add), ("reload", "Reload panel", self.reload),
                              ("globe", "Open in a tab", self.open_tab), ("close", "Remove panel", self.remove)):
            b = QToolButton()
            b.setFixedSize(30, 30)
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, f=fn: f())
            head.addWidget(b)
            self._btns.append((b, icon))
        v.addLayout(head)
        self.stack = QStackedWidget()
        self.empty = QLabel("Keep a site one click away: chat, music, a calendar.\nPress + to add one.")
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.empty)
        v.addWidget(self.stack, 1)
        self.refresh_icons()
        self.combo.currentIndexChanged.connect(self.select)

    def refresh_icons(self) -> None:
        for b, icon in self._btns:
            b.setIcon(self.win.ic(icon))

    def activate(self) -> None:
        panels = self.win.store["web_panels"]
        self.combo.blockSignals(True)
        cur = self.combo.currentIndex()
        self.combo.clear()
        self.combo.addItems([p["name"] for p in panels])
        self.combo.setCurrentIndex(cur if 0 <= cur < len(panels) else 0)
        self.combo.blockSignals(False)
        self.select(self.combo.currentIndex())

    def select(self, i: int) -> None:
        panels = self.win.store["web_panels"]
        if not (0 <= i < len(panels)):
            self.stack.setCurrentWidget(self.empty)
            return
        p = panels[i]
        if p["id"] not in self.views:
            view = QWebEngineView()
            view.setPage(WebPage(self.win.ctx, self.win, view))
            view.setZoomFactor(0.8)
            view.load(QUrl(p["url"]))
            self.views[p["id"]] = view
            self.stack.addWidget(view)
        self.stack.setCurrentWidget(self.views[p["id"]])

    def _current(self):
        i = self.combo.currentIndex()
        panels = self.win.store["web_panels"]
        return (i, panels[i]) if 0 <= i < len(panels) else (-1, None)

    def add(self) -> None:
        dlg = FormDialog(self.win, "Add a web panel", [("Name", "", "Calendar"), ("Website", "", "calendar.google.com")], "Add")
        if not dlg.exec():
            return
        name, url = dlg.values()
        if not url:
            return
        if not re.match(r"^https?://", url):
            url = "https://" + url
        panel = {"id": uuid.uuid4().hex[:8], "name": name or QUrl(url).host(), "url": url}
        self.win.store["web_panels"].append(panel)
        self.win.store.save()
        self.activate()
        self.combo.setCurrentIndex(self.combo.count() - 1)

    def reload(self) -> None:
        _i, p = self._current()
        if p and p["id"] in self.views:
            self.views[p["id"]].reload()

    def open_tab(self) -> None:
        _i, p = self._current()
        if p:
            self.win.open_url(p["url"])

    def remove(self) -> None:
        i, p = self._current()
        if not p:
            return
        view = self.views.pop(p["id"], None)
        if view:
            self.stack.removeWidget(view)
            view.deleteLater()
        del self.win.store["web_panels"][i]
        self.win.store.save()
        self.activate()


SIDEBAR_PANEL_INFO = {
    "perf": ("gauge", "Memory and performance", "Memory"),
    "work": ("layers", "Tab groups and workspaces", "Workspace"),
    "notes": ("note", "Notes", "Notes"),
    "web": ("panel", "Web panels", "Web panels"),
    "music": ("music", "YouTube Music player", "Music"),
    "ai": ("spark", "AI companion", "AI companion"),
}


class SidebarCustomizeDialog(QDialog):
    """Choose which sidebar panels are shown and the order of their buttons."""

    def __init__(self, order: list[str], enabled: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize sidebar")
        self.setMinimumWidth(360)
        self.setMinimumHeight(390)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        title = QLabel("Sidebar panels")
        title.setObjectName("h2")
        lay.addWidget(title)
        hint = QLabel("Select the panels you want and arrange them with the arrows.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.items = QListWidget()
        self.items.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.items.setDefaultDropAction(Qt.DropAction.MoveAction)
        for key in order:
            if key not in SIDEBAR_PANEL_INFO:
                continue
            _icon, tip, label = SIDEBAR_PANEL_INFO[key]
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            item.setCheckState(Qt.CheckState.Checked if key in enabled else Qt.CheckState.Unchecked)
            item.setToolTip(tip)
            self.items.addItem(item)
        lay.addWidget(self.items, 1)
        moves = QHBoxLayout()
        self.up = QPushButton("Move up")
        self.down = QPushButton("Move down")
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        moves.addWidget(self.up)
        moves.addWidget(self.down)
        moves.addStretch(1)
        lay.addLayout(moves)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        apply = QPushButton("Apply")
        apply.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        apply.clicked.connect(self._accept_if_valid)
        actions.addWidget(cancel)
        actions.addWidget(apply)
        lay.addLayout(actions)

    def _move(self, direction: int) -> None:
        row = self.items.currentRow()
        target = row + direction
        if row < 0 or not 0 <= target < self.items.count():
            return
        item = self.items.takeItem(row)
        self.items.insertItem(target, item)
        self.items.setCurrentRow(target)

    def _accept_if_valid(self) -> None:
        if not any(self.items.item(i).checkState() == Qt.CheckState.Checked for i in range(self.items.count())):
            QMessageBox.information(self, "Keep one panel", "Choose at least one sidebar panel.")
            return
        self.accept()

    def values(self) -> tuple[list[str], list[str]]:
        order, enabled = [], []
        for i in range(self.items.count()):
            item = self.items.item(i)
            key = item.data(Qt.ItemDataRole.UserRole)
            order.append(key)
            if item.checkState() == Qt.CheckState.Checked:
                enabled.append(key)
        return order, enabled


class AICompanionPanel(QWidget):
    PROVIDERS = (
        ("anthropic", "Claude", "https://claude.ai/new"),
        ("gemini", "Gemini", "https://gemini.google.com/app"),
        ("chatgpt", "ChatGPT", "https://chatgpt.com/"),
    )

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.loaded_provider = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.provider = QComboBox()
        for key, label, _url in self.PROVIDERS:
            self.provider.addItem(label, key)
        saved = win.store["ai_provider"]
        idx = self.provider.findData(saved)
        self.provider.setCurrentIndex(idx if idx >= 0 else 2)
        title = QLabel("AI companion")
        title.setObjectName("h2")
        lay.addWidget(title)
        head.addWidget(self.provider, 1)
        for text, tip, fn in (("↻", "Reload AI companion", self.reload),
                              ("↗", "Open AI companion in a tab", self.open_tab)):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.setFixedSize(30, 30)
            button.clicked.connect(fn)
            head.addWidget(button)
        lay.addLayout(head)
        self.view = QWebEngineView()
        self.view.setPage(WebPage(win.ctx, win, self.view))
        lay.addWidget(self.view, 1)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.activate()

    def _current(self):
        return next((item for item in self.PROVIDERS if item[0] == self.provider.currentData()), self.PROVIDERS[-1])

    def activate(self) -> None:
        key, _label, url = self._current()
        if key != self.loaded_provider:
            self.loaded_provider = key
            self.view.load(QUrl(url))

    def _provider_changed(self, _index: int) -> None:
        key, _label, url = self._current()
        self.win.store.set("ai_provider", key)
        self.loaded_provider = key
        self.view.load(QUrl(url))

    def reload(self) -> None:
        self.view.reload()

    def open_tab(self) -> None:
        self.win.open_url(self._current()[2])


class Sidebar(QWidget):
    PANEL_W = 322

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.setObjectName("sidebar")
        self.is_open = False
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.rail = QWidget()
        self.rail.setObjectName("rail")
        self.rail.setFixedWidth(46)
        rl = QVBoxLayout(self.rail)
        self.rail_layout = rl
        rl.setContentsMargins(5, 8, 5, 8)
        rl.setSpacing(4)
        self._icons: list = []
        self.toggle_btn = self._rail_button("sidebar", "Hide the sidebar (Ctrl+B)", self.toggle)
        rl.addWidget(self.toggle_btn)
        rl.addSpacing(6)
        self.buttons: dict[str, QToolButton] = {}
        self.panels: dict[str, QWidget] = {}
        self.order = [k for k in win.store["sidebar_order"] if k in SIDEBAR_PANEL_INFO]
        self.order += [k for k in SIDEBAR_PANEL_INFO if k not in self.order]
        self.enabled = {k for k in win.store["sidebar_panels"] if k in SIDEBAR_PANEL_INFO}
        if not self.enabled:
            self.enabled = set(self.order)
        for key in self.order:
            icon, tip, _label = SIDEBAR_PANEL_INFO[key]
            b = self._rail_button(icon, tip, lambda k=key: self.show_panel(k))
            b.setCheckable(True)
            rl.addWidget(b)
            self.buttons[key] = b
        rl.addStretch(1)
        self.customize_btn = self._rail_button("spark", "Customize sidebar", self.customize)
        rl.addWidget(self.customize_btn)
        self.rail.setVisible(False)
        h.addWidget(self.rail)

        self.panel = QWidget()
        self.panel.setObjectName("sidepanel")
        self.panel.setMaximumWidth(0)
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        pl.addWidget(self.stack)
        self.perf, self.work, self.notes, self.web = PerfPanel(win), WorkPanel(win), NotesPanel(win), WebPanels(win)
        self.music = MusicPanel(win)
        self.ai = AICompanionPanel(win)
        for key, w in (("perf", self.perf), ("work", self.work), ("notes", self.notes), ("web", self.web),
                       ("music", self.music), ("ai", self.ai)):
            self.panels[key] = w
            self.stack.addWidget(w)
        h.addWidget(self.panel)
        self.current = win.store["sidebar_panel"] if win.store["sidebar_panel"] in self.enabled else next(iter(self.enabled))
        self.stack.setCurrentWidget(self.panels[self.current])
        self._anim = QPropertyAnimation(self.panel, b"maximumWidth", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setDuration(220)
        self._anim.finished.connect(self._anim_done)
        self.refresh_icons()
        self._apply_buttons()

    def _rail_button(self, icon: str, tip: str, fn) -> QToolButton:
        b = QToolButton()
        b.setFixedSize(36, 36)
        b.setIconSize(QSize(19, 19))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False: fn())
        self._icons.append((b, icon))
        return b

    def refresh_icons(self) -> None:
        icon_color = resolve_theme(self.win.store)["sub"]
        for b, icon in self._icons:
            b.setIcon(self.win.ic(icon, icon_color))
        self.web.refresh_icons()
        self.music.refresh_icons()

    def _apply_buttons(self) -> None:
        for key, button in self.buttons.items():
            self.rail_layout.removeWidget(button)
            button.setVisible(key in self.enabled)
        for index, key in enumerate(self.order, start=2):
            if key in self.buttons:
                self.rail_layout.insertWidget(index, self.buttons[key])
        self._mark()

    def customize(self) -> None:
        dlg = SidebarCustomizeDialog(self.order, list(self.enabled), self.win)
        if not dlg.exec():
            return
        self.order, enabled = dlg.values()
        self.enabled = set(enabled)
        self.win.store.set("sidebar_order", self.order)
        self.win.store.set("sidebar_panels", [k for k in self.order if k in self.enabled])
        if self.current not in self.enabled:
            self.current = next(k for k in self.order if k in self.enabled)
            self.stack.setCurrentWidget(self.panels[self.current])
        self._apply_buttons()
        if self.is_open:
            self._on_show()

    def _mark(self) -> None:
        for k, b in self.buttons.items():
            b.setChecked(self.is_open and k == self.current)

    def toggle(self) -> None:
        self.set_open(not self.is_open)

    def set_open(self, on: bool, animate: bool = True) -> None:
        if on == self.is_open:
            return
        if not on and self.win.store["sidebar_always_visible"]:
            return
        self.is_open = on
        self.win.store.set("sidebar_open", on)
        self.win.update_sidebar_reveal()
        self._anim.stop()
        self.panel.setMinimumWidth(0)
        if on:
            self.rail.setVisible(True)
            self._on_show()
        if animate and self.win.anim_on():
            self._anim.setStartValue(self.panel.maximumWidth())
            self._anim.setEndValue(self.PANEL_W if on else 0)
            self._anim.start()
        else:
            self.panel.setMaximumWidth(self.PANEL_W if on else 0)
            self._anim_done()
        self._mark()

    def _anim_done(self) -> None:
        self.panel.setMinimumWidth(self.PANEL_W if self.is_open else 0)
        self.rail.setVisible(self.is_open)
        self.win.update_sidebar_reveal()

    def show_panel(self, key: str) -> None:
        if key not in self.enabled:
            return
        if self.is_open and key == self.current:
            self.set_open(False)
            return
        self.current = key
        self.win.store.set("sidebar_panel", key)
        self.stack.setCurrentWidget(self.panels[key])
        if not self.is_open:
            self.set_open(True)
        else:
            self._on_show()
        self._mark()

    def _on_show(self) -> None:
        w = self.panels[self.current]
        if self.current == "web":
            self.web.activate()
        elif self.current == "music":
            self.music.activate()
        elif self.current == "ai":
            self.ai.activate()
        elif hasattr(w, "refresh"):
            w.refresh()


# ═════════════════════════════════════════════════════════════════════════════
#  YouTube Music player (sidebar panel + pinnable mini player)
# ═════════════════════════════════════════════════════════════════════════════

YTM_URL = "https://music.youtube.com"
YTM_STATE_JS = r"""(function(){var q=function(s){return document.querySelector(s)};
var t=q('ytmusic-player-bar .title'),b=q('ytmusic-player-bar .byline'),v=q('video');
return JSON.stringify({title:t?t.textContent.trim():'',artist:b?b.textContent.split('\u2022')[0].trim():'',playing:v?!v.paused:false})})()"""
YTM_BUTTONS = {"play": "#play-pause-button", "next": ".next-button", "prev": ".previous-button"}


class MusicPanel(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.view: QWebEngineView | None = None
        self.state: dict = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 14, 12, 12)
        v.setSpacing(8)
        t = QLabel("Music")
        t.setObjectName("h2")
        v.addWidget(t)
        self.hint = QLabel("YouTube Music. Sign in once and it stays signed in for this profile.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)
        self.holder = QVBoxLayout()
        v.addLayout(self.holder, 1)
        row = QHBoxLayout()
        self._btns = []
        for icon, which in (("prev", "prev"), ("play", "play"), ("next", "next")):
            b = QToolButton()
            b.setFixedSize(36, 36)
            b.setIconSize(QSize(18, 18))
            b.clicked.connect(lambda _=False, w=which: self.control(w))
            row.addWidget(b)
            self._btns.append((b, icon))
        row.addStretch(1)
        lab = QLabel("Pin mini player")
        self.pin = Toggle(bool(win.store["mini_player"]))
        self.pin.toggled.connect(lambda on: win.app.apply_setting(win.store, "mini_player", bool(on)))
        row.addWidget(lab)
        row.addWidget(self.pin)
        v.addLayout(row)
        self.poll = QTimer(self)
        self.poll.setInterval(2000)
        self.poll.timeout.connect(self.poll_state)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        for b, icon in self._btns:
            b.setIcon(self.win.ic(icon))

    def activate(self) -> None:
        self.pin.setChecked(bool(self.win.store["mini_player"]))
        if self.view is None:
            self.view = QWebEngineView()
            self.view.setPage(WebPage(self.win.ctx, self.win, self.view))
            self.view.setZoomFactor(0.8)
            self.view.load(QUrl(YTM_URL))
            self.holder.addWidget(self.view)
            self.poll.start()
        self.win.mini.refresh_visibility()

    def poll_state(self) -> None:
        if self.view is not None:
            self.view.page().runJavaScript(YTM_STATE_JS, self._got)

    def _got(self, raw) -> None:
        try:
            self.state = json.loads(raw) if isinstance(raw, str) else {}
        except ValueError:
            return
        self.win.mini.update_state(self.state)

    def control(self, which: str) -> None:
        if self.view is None:
            self.activate()
            return
        js = (f"(function(){{var b=document.querySelector('ytmusic-player-bar {YTM_BUTTONS[which]}');if(b)b.click()}})()")
        self.view.page().runJavaScript(js)
        QTimer.singleShot(400, self.poll_state)


class MiniPlayer(QFrame):
    """A small translucent player pinned to the bottom-left of the page."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win.viewhost)
        self.win = win
        self.setObjectName("mini")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedSize(318, 60)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 8, 8)
        h.setSpacing(6)
        self.note = QLabel()
        self.note.setFixedSize(24, 24)
        h.addWidget(self.note)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel("Nothing playing")
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.artist = QLabel("")
        self.artist.setObjectName("muted")
        col.addWidget(self.title)
        col.addWidget(self.artist)
        h.addLayout(col, 1)
        self._btns = []
        for icon, which in (("prev", "prev"), ("play", "play"), ("next", "next"), ("close", None)):
            b = QToolButton()
            b.setFixedSize(30, 30)
            b.setIconSize(QSize(16, 16))
            if which:
                b.clicked.connect(lambda _=False, w=which: win.sidebar.music.control(w))
            else:
                b.setToolTip("Unpin mini player")
                b.clicked.connect(lambda _=False: win.app.apply_setting(win.store, "mini_player", False))
            h.addWidget(b)
            self._btns.append((b, icon, which))
        self.playing = False
        self.hide()

    def refresh_icons(self) -> None:
        self.note.setPixmap(self.win.ic("music").pixmap(22, 22))
        for b, icon, which in self._btns:
            name = ("pause" if self.playing else "play") if which == "play" else icon
            b.setIcon(self.win.ic(name))

    def update_state(self, st: dict) -> None:
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(st.get("title") or "Nothing playing", Qt.TextElideMode.ElideRight, 170))
        self.artist.setText(fm.elidedText(st.get("artist") or "", Qt.TextElideMode.ElideRight, 170))
        was = self.playing
        self.playing = bool(st.get("playing"))
        if was != self.playing:
            self.refresh_icons()

    def refresh_visibility(self) -> None:
        w = self.win
        on = (bool(w.store["mini_player"]) and w.sidebar.music.view is not None and w.edition() != "legacy"
              and not (w._focus_mode or w._fs))
        self.setVisible(on)
        if on:
            self.refresh_icons()
            self.reposition()

    def reposition(self) -> None:
        p = self.parentWidget()
        if p is not None:
            self.move(16, max(8, p.height() - self.height() - 46))
            self.raise_()


class SiteNotificationPopup(QFrame):
    """A small browser notification with the WebEngine click and close callbacks."""

    def __init__(self, parent: QWidget, notification: QWebEngineNotification, on_done, animate: bool = True):
        super().__init__(parent)
        self.notification = notification
        self.on_done = on_done
        self._animate = bool(animate)
        self._finishing = False
        self.setObjectName("siteNotification")
        self.setFixedSize(356, 112)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        self._show_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._show_anim.setDuration(160)
        self._show_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 12, 12)
        row.setSpacing(10)
        icon = QLabel()
        icon.setFixedSize(32, 32)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        image = notification.icon()
        if not image.isNull():
            icon.setPixmap(QPixmap.fromImage(image).scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.SmoothTransformation))
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        title = QLabel(notification.title() or notification.origin().host() or "Website notification")
        title.setObjectName("notificationTitle")
        title.setWordWrap(False)
        title.setMaximumWidth(250)
        message = QLabel(notification.message())
        message.setObjectName("notificationMessage")
        message.setWordWrap(True)
        message.setMaximumHeight(45)
        origin = QLabel(notification.origin().host())
        origin.setObjectName("notificationOrigin")
        for label in (title, message, origin):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_column.addWidget(title)
        text_column.addWidget(message)
        text_column.addWidget(origin)
        row.addLayout(text_column, 1)
        close = QToolButton()
        close.setText("×")
        close.setFixedSize(26, 26)
        close.setToolTip("Dismiss notification")
        close.clicked.connect(self.dismiss)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(9000)
        self.timer.timeout.connect(self.dismiss)
        notification.closed.connect(self._closed_by_site)

    def show_notification(self) -> None:
        self._opacity.setOpacity(0.0 if self._animate else 1.0)
        self.show()
        self.raise_()
        if self._animate:
            self._show_anim.setStartValue(0.0)
            self._show_anim.setEndValue(1.0)
            self._show_anim.start()
        self.notification.show()
        self.timer.start()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.notification.click()
            self.dismiss()
        super().mouseReleaseEvent(event)

    def _closed_by_site(self) -> None:
        if self._finishing:
            return
        self._finishing = True
        self.timer.stop()
        self.hide()
        self.on_done(self)
        self.deleteLater()

    def dismiss(self) -> None:
        if self._finishing:
            return
        self._finishing = True
        self.timer.stop()
        self.notification.close()
        self.hide()
        self.on_done(self)
        self.deleteLater()


class DownloadsPopup(QFrame):
    """A compact, live download list anchored to the browser's top-right corner."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win.centralWidget())
        self.win = win
        self.auto_hide = False
        self.dismissed_active = False
        self.setObjectName("downloadPopup")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(372)
        self.setMaximumHeight(440)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        self._show_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._show_anim.setDuration(150)
        self._show_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._render_signature = None
        self._rows_by_id: dict[str, QFrame] = {}
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._hide_if_idle)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self.refresh)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("Downloads")
        title.setObjectName("downloadTitle")
        head.addWidget(title, 1)
        self.clear_btn = QToolButton()
        self.clear_btn.setText("Clear")
        self.clear_btn.setToolTip("Clear completed downloads")
        self.clear_btn.clicked.connect(self.clear_completed)
        head.addWidget(self.clear_btn)
        self.all_btn = QToolButton()
        self.all_btn.setText("All downloads")
        self.all_btn.clicked.connect(self.open_all)
        head.addWidget(self.all_btn)
        self.close_btn = QToolButton()
        self.close_btn.setText("×")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Close downloads")
        self.close_btn.clicked.connect(self.toggle)
        head.addWidget(self.close_btn)
        lay.addLayout(head)
        self.empty = QLabel("No downloads yet")
        self.empty.setObjectName("downloadEmpty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("downloadScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setMinimumHeight(0)
        self.scroll.viewport().setAutoFillBackground(False)
        self.rows = QWidget()
        self.rows.setObjectName("downloadRows")
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(7)
        self.scroll.setWidget(self.rows)
        lay.addWidget(self.scroll)
        self.setMinimumHeight(0)
        self.scroll.hide()
        self.refresh()
        self.hide()

    @staticmethod
    def _size(value: float) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        value = max(0.0, float(value or 0))
        index = 0
        while value >= 1024 and index < len(units) - 1:
            value /= 1024
            index += 1
        return f"{value:.1f} {units[index]}" if index else f"{int(value)} B"

    @staticmethod
    def _duration(value: float) -> str:
        seconds = max(0, int(value or 0))
        return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"

    def refresh(self) -> None:
        all_records = sorted(self.win.ctx.downloads.records(), key=lambda row: row.get("time", 0), reverse=True)
        records = all_records[:8]
        completed = any(row.get("state") != "progress" for row in all_records)
        self.clear_btn.setVisible(completed)
        self.clear_btn.setEnabled(completed)
        self.empty.setVisible(not records)
        self.scroll.setVisible(bool(records))
        signature = tuple((row.get("id", ""), row.get("state", "failed")) for row in records)
        if signature != self._render_signature:
            while self.rows_layout.count():
                item = self.rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._rows_by_id.clear()
            for record in records:
                row = self._row(record)
                self._rows_by_id[record.get("id", "")] = row
                self.rows_layout.addWidget(row)
            self.rows_layout.addStretch(1)
            self._render_signature = signature
        else:
            for record in records:
                row = self._rows_by_id.get(record.get("id", ""))
                if row is not None:
                    self._update_row(row, record)
        self.adjustSize()
        self.reposition()
        if self.isVisible() and any(r.get("state") == "progress" for r in all_records):
            self.refresh_timer.start()
        elif not any(r.get("state") == "progress" for r in all_records):
            self.refresh_timer.stop()

    def _row(self, record: dict) -> QWidget:
        card = QFrame()
        card.setObjectName("downloadCard")
        card._download_state = record.get("state", "failed")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(11, 9, 11, 9)
        lay.setSpacing(5)
        name = QLabel()
        name.setObjectName("downloadName")
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name.setWordWrap(False)
        name.setMinimumWidth(0)
        card._name_label = name
        lay.addWidget(name)
        details = QLabel()
        details.setObjectName("muted")
        card._details_label = details
        lay.addWidget(details)
        card._progress_bar = None
        if card._download_state == "progress":
            progress = QProgressBar()
            progress.setObjectName("downloadProgress")
            progress.setTextVisible(False)
            progress.setMaximumHeight(5)
            card._progress_bar = progress
            lay.addWidget(progress)
        actions = QWidget(card)
        actions.setObjectName("downloadActions")
        action_row = QHBoxLayout(actions)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(4)
        action_row.addStretch(1)
        uid = record.get("id", "")
        state = card._download_state
        if state == "progress":
            cancel = QToolButton()
            cancel.setText("Cancel")
            cancel.clicked.connect(lambda _=False, i=uid: self.win.ctx.downloads.cancel(i))
            action_row.addWidget(cancel)
        elif state == "done" and record.get("exists"):
            open_file = QToolButton()
            open_file.setText("Open")
            open_file.clicked.connect(lambda _=False, i=uid: self.open_file(i))
            folder = QToolButton()
            folder.setText("Show in folder")
            folder.clicked.connect(lambda _=False, i=uid: self.show_folder(i))
            action_row.addWidget(open_file)
            action_row.addWidget(folder)
        else:
            remove = QToolButton()
            remove.setText("Remove")
            remove.clicked.connect(lambda _=False, i=uid: self.remove_record(i))
            action_row.addWidget(remove)
        lay.addWidget(actions)
        self._update_row(card, record)
        return card

    def _update_row(self, card: QFrame, record: dict) -> None:
        full_name = record.get("name") or "Download"
        card._name_label.setText(QFontMetrics(card._name_label.font()).elidedText(
            full_name, Qt.TextElideMode.ElideMiddle, max(120, self.width() - 68)))
        card._name_label.setToolTip(full_name)
        state = record.get("state", "failed")
        received, total = record.get("received", 0), record.get("total", 0)
        if state == "progress":
            meta = self._size(received)
            if total:
                meta += f" of {self._size(total)}"
            meta += f"  ·  {self._size(record.get('speed', 0))}/s  ·  {self._duration(record.get('elapsed', 0))}"
        elif state == "done":
            meta = f"Downloaded  ·  {self._size(total or received)}"
        elif state == "cancelled":
            meta = "Cancelled"
        else:
            meta = "Download failed"
        card._details_label.setText(meta)
        progress = card._progress_bar
        if progress is not None:
            if total:
                progress.setRange(0, 100)
                progress.setValue(min(100, int(received * 100 / total)))
            else:
                progress.setRange(0, 0)

    def open_file(self, uid: str) -> None:
        record = self.win.ctx.downloads.find(uid)
        if record and os.path.exists(record.get("path", "")):
            QDesktopServices.openUrl(QUrl.fromLocalFile(record["path"]))

    def show_folder(self, uid: str) -> None:
        record = self.win.ctx.downloads.find(uid)
        if record:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(record["path"])))

    def clear_completed(self) -> None:
        for record in self.win.ctx.downloads.records():
            if record.get("state") != "progress":
                self.win.ctx.downloads.remove(record["id"])
        self.refresh()

    def remove_record(self, uid: str) -> None:
        self.win.ctx.downloads.remove(uid)
        self.refresh()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent:
            self.setMaximumHeight(min(440, max(120, parent.height() - 106)))
            self.adjustSize()
            self.move(max(8, parent.width() - self.width() - 12), 94)

    def _present(self) -> None:
        self.show()
        self.raise_()
        self._opacity.setOpacity(0.0 if self.win.anim_on() else 1.0)
        if self.win.anim_on():
            self._show_anim.stop()
            self._show_anim.setStartValue(0.0)
            self._show_anim.setEndValue(1.0)
            self._show_anim.start()

    def toggle(self) -> None:
        self.hide_timer.stop()
        if self.isVisible():
            self.dismissed_active = any(r.get("state") == "progress" for r in self.win.ctx.downloads.records())
            self.refresh_timer.stop()
            self.hide()
            return
        self.auto_hide = False
        self.dismissed_active = False
        self.refresh()
        self.reposition()
        self._present()
        if any(r.get("state") == "progress" for r in self.win.ctx.downloads.records()):
            self.refresh_timer.start()

    def show_for_activity(self) -> None:
        self.auto_hide = True
        self.hide_timer.stop()
        self.refresh()
        self.reposition()
        self._present()
        self.refresh_timer.start()

    def open_all(self) -> None:
        self.hide_timer.stop()
        self.refresh_timer.stop()
        self.dismissed_active = any(r.get("state") == "progress" for r in self.win.ctx.downloads.records())
        self.hide()
        self.auto_hide = False
        self.win.open_internal("downloads")

    def _hide_if_idle(self) -> None:
        active = any(r.get("state") == "progress" for r in self.win.ctx.downloads.records())
        if self.auto_hide and not active:
            self.hide()
            self.refresh_timer.stop()
            self.auto_hide = False
            self.dismissed_active = False


# ═════════════════════════════════════════════════════════════════════════════
#  Command palette
# ═════════════════════════════════════════════════════════════════════════════

class CommandPalette(QDialog):
    def __init__(self, win: "MainWindow"):
        super().__init__(win, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.win = win
        self.setObjectName("palette")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(660)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("palettecard")
        outer.addWidget(card)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("paletteinput")
        self.input.setPlaceholderText("Type a command, tab, bookmark or address")
        self.input.textChanged.connect(self.refilter)
        self.input.installEventFilter(self)
        self.list = QListWidget()
        self.list.setObjectName("palettelist")
        self.list.setMaximumHeight(380)
        self.list.itemActivated.connect(self._run_item)
        self.list.itemClicked.connect(self._run_item)
        v.addWidget(self.input)
        v.addWidget(self.list)
        self.entries: list[dict] = []
        self.shown: list[dict] = []

    def open_palette(self) -> None:
        self.entries = self.win.palette_entries()
        self.input.clear()
        self.refilter()
        g = self.win.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 90)
        self.setWindowOpacity(0.0 if self.win.anim_on() else 1.0)
        self.show()
        self.input.setFocus()
        if self.win.anim_on():
            a = QPropertyAnimation(self, b"windowOpacity", self)
            a.setDuration(140)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.start()
            self._fade = a

    def eventFilter(self, obj, ev) -> bool:
        if obj is self.input and ev.type() == QEvent.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                n = self.list.count()
                if n:
                    row = self.list.currentRow() + (1 if k == Qt.Key.Key_Down else -1)
                    self.list.setCurrentRow(max(0, min(n - 1, row)))
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                it = self.list.currentItem()
                if it:
                    self._run_item(it)
                return True
        return super().eventFilter(obj, ev)

    def refilter(self) -> None:
        q = self.input.text().strip().lower()
        tokens = q.split()
        scored = []
        for order, e in enumerate(self.entries):
            hay = e["hay"]
            if all(t in hay for t in tokens):
                pos = sum(hay.find(t) for t in tokens)
                scored.append((pos + (0 if e.get("cmd") else 40) + order * 0.001, e))
        scored.sort(key=lambda x: x[0])
        self.shown = [e for _s, e in scored[:40]]
        extra = self.win.palette_query_entries(self.input.text().strip()) if q else []
        self.shown = extra + self.shown
        self.list.clear()
        sub = self.win.theme()["sub"]
        for e in self.shown:
            it = QListWidgetItem()
            it.setSizeHint(QSize(0, 50))
            self.list.addItem(it)
            lab = QLabel(f"<div style='font-weight:600'>{html_escape(e['title'])}</div>"
                         f"<div style='color:{sub}; font-size:11px'>{html_escape(e['sub'])}</div>")
            lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lab.setContentsMargins(6, 3, 6, 3)
            self.list.setItemWidget(it, lab)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.setVisible(bool(self.shown))

    def _run_item(self, item) -> None:
        row = self.list.row(item)
        if 0 <= row < len(self.shown):
            fn = self.shown[row]["fn"]
            self.close()
            QTimer.singleShot(30, fn)


# ═════════════════════════════════════════════════════════════════════════════
#  Memory governor
# ═════════════════════════════════════════════════════════════════════════════

RAM_DEFAULTS = {"enabled": False, "limit_mb": 4096, "mode": "balanced", "sleep_min": 0, "hard_cap": False}


class MemoryThread(QThread):
    sample = pyqtSignal(float, bool)

    def __init__(self, interval_ms: int = 3000):
        super().__init__()
        self.interval = interval_ms
        self._stop = False

    def run(self) -> None:
        while not self._stop:
            try:
                mb, ok = process_tree_memory_mb()
                self.sample.emit(mb, ok)
            except Exception:
                pass
            self.msleep(self.interval)

    def stop(self) -> None:
        self._stop = True
        self.wait(2500)


class ResourceGovernor(QObject):
    """Keeps memory under a user-chosen limit by sleeping idle tabs, one at a
    time, and never anything the person is looking at. It cannot crash the app:
    it only puts background tabs to sleep, which reload when you open them."""
    updated = pyqtSignal()

    def __init__(self, app: "BrowserApp", safe_mode: bool):
        super().__init__(app)
        self.app, self.safe_mode = app, safe_mode
        self.total_mb = system_memory_mb()
        cfg = {**RAM_DEFAULTS, **(app.state.get("ram") or {})}
        cfg["limit_mb"] = clamp_limit(float(cfg["limit_mb"]), self.total_mb)
        if cfg["mode"] not in ("balanced", "aggressive"):
            cfg["mode"] = "balanced"
        if cfg["sleep_min"] not in {m for _l, m in SLEEP_CHOICES}:
            cfg["sleep_min"] = 0
        self.cfg = cfg
        app.state["ram"] = cfg
        self.policy = LimiterPolicy()
        self.used, self.accurate = 0.0, True
        self.history: list[float] = []
        self.status = "Watching memory use."
        self.thread = MemoryThread()
        self.thread.sample.connect(self.on_sample)
        self.thread.start()
        app.qapp.aboutToQuit.connect(self.thread.stop)
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(30000)
        self.idle_timer.timeout.connect(self.sweep_idle)
        self.idle_timer.start()

    def set_config(self, **kw) -> None:
        cfg = self.cfg
        if "limit_mb" in kw:
            kw["limit_mb"] = clamp_limit(float(kw["limit_mb"]), self.total_mb)
        cfg.update({k: v for k, v in kw.items() if k in RAM_DEFAULTS})
        self.app.save_state()
        self.policy = LimiterPolicy()
        self.status = "Limiter is on." if cfg["enabled"] else "Limiter is off."
        self.updated.emit()

    def _windows(self):
        return [w for w in self.app.windows if not getattr(w, "_closing", False)]

    def candidates(self, aggressive: bool) -> list:
        now = time.time()
        out = []
        for w in self._windows():
            for v in w.tab_views():
                if w.can_sleep(v, aggressive) and now >= v.protect_until:
                    out.append((v.last_active, v, w))
        out.sort(key=lambda t: t[0])
        return [(v, w) for _t, v, w in out]

    def on_sample(self, mb: float, ok: bool) -> None:
        self.used, self.accurate = mb, ok
        self.history.append(mb)
        del self.history[:-Spark.CAP]
        try:
            self.enforce()
        except Exception:
            self.status = "Limiter paused after an unexpected error."
            self.cfg["enabled"] = False
        self.updated.emit()

    def enforce(self) -> None:
        cfg = self.cfg
        if not cfg["enabled"]:
            return
        aggressive = cfg["mode"] == "aggressive"
        now = time.time()
        cands = self.candidates(aggressive)
        verdict = self.policy.decide(self.used, cfg["limit_mb"], now, bool(cands), aggressive)
        if verdict == "ok":
            self.status = f"Within your {fmt_mb(cfg['limit_mb'])} limit."
        elif verdict == "wait":
            self.status = "Over the limit. Giving the last change time to take effect."
        elif verdict == "stuck":
            self.status = ("Over the limit, but every remaining tab is one you're using. "
                           "Raise the limit or close a tab. Nothing was closed.")
        else:
            view, win = cands[0]
            title = (view.page_title or "a tab")[:32]
            win.sleep_view(view)
            self.policy.acted(now)
            self.status = f"Over the limit, so \u201c{title}\u201d went to sleep."

    def sweep_idle(self) -> None:
        mins = self.cfg["sleep_min"]
        if not mins:
            return
        now, done = time.time(), 0
        for v, w in self.candidates(False):
            if now - v.last_active > mins * 60 and done < 3:
                w.sleep_view(v)
                done += 1
        if done:
            self.updated.emit()

    def free_now(self) -> int:
        now, n = time.time(), 0
        for v, w in self.candidates(self.cfg["mode"] == "aggressive"):
            if now - v.last_active > 20 and n < 25:
                w.sleep_view(v)
                n += 1
        self.status = f"Slept {n} tab{'s' if n != 1 else ''} on request." if n else self.status
        self.updated.emit()
        return n


# ═════════════════════════════════════════════════════════════════════════════
#  Chrome extensions (content-script compatibility layer)
# ═════════════════════════════════════════════════════════════════════════════

EXT_SHIM_JS = r"""(function(){
if(window.__abExt)return;window.__abExt=true;
const E=__EXT__;
const api=(op,params)=>fetch('awesome://extapi/'+E.id+'/'+op+'?'+new URLSearchParams(Object.assign({t:E.token},params||{}))).then(r=>r.json());
const LS='__abext_'+E.id;
const lsGet=()=>{try{return JSON.parse(localStorage.getItem(LS)||'{}')}catch(e){return{}}};
const lsSet=d=>{try{localStorage.setItem(LS,JSON.stringify(d))}catch(e){}};
const pick=(all,keys)=>{if(keys==null)return all;if(typeof keys==='string')keys=[keys];const o={};
  if(Array.isArray(keys))keys.forEach(k=>{if(k in all)o[k]=all[k]});else Object.keys(keys).forEach(k=>{o[k]=(k in all)?all[k]:keys[k]});return o};
const listeners=[];
const fire=ch=>listeners.slice().forEach(f=>{try{f(ch,'local')}catch(e){}});
const load=()=>api('get').then(r=>r.data||{}).catch(()=>lsGet());
const done=(p,cb)=>{if(typeof cb==='function'){p.then(v=>cb(v));return}return p};
function area(){return{
  get(keys,cb){return done(load().then(a=>pick(a,keys)),cb)},
  set(items,cb){const ch={};Object.keys(items).forEach(k=>ch[k]={newValue:items[k]});
    return done(api('set',{d:JSON.stringify(items)}).catch(()=>{const a=lsGet();Object.assign(a,items);lsSet(a)}).then(()=>{fire(ch)}),cb)},
  remove(keys,cb){keys=[].concat(keys);return done(api('remove',{k:JSON.stringify(keys)}).catch(()=>{const a=lsGet();keys.forEach(k=>delete a[k]);lsSet(a)}).then(()=>{}),cb)},
  clear(cb){return done(api('clear').catch(()=>lsSet({})).then(()=>{}),cb)},
  getBytesInUse(k,cb){return done(load().then(a=>JSON.stringify(pick(a,k)).length),cb)}}}
const msg=(n,subs)=>{const m=E.messages[n];if(!m)return'';let t=m.message||'';[].concat(subs||[]).forEach((s,i)=>{t=t.split('$'+(i+1)).join(s)});return t};
const ev=()=>({addListener(){},removeListener(){},hasListener(){return false}});
const port=()=>({postMessage(){},disconnect(){},onMessage:ev(),onDisconnect:ev()});
const chrome={
  runtime:{id:E.id,getURL:p=>'awesome://ext/'+E.id+'/'+String(p).replace(/^\//,''),getManifest:()=>E.manifest,
    sendMessage(){const cb=[].slice.call(arguments).pop();if(typeof cb==='function')setTimeout(()=>cb(undefined),0);else return Promise.resolve(undefined)},
    connect:port,onMessage:ev(),onConnect:ev(),onInstalled:ev(),onStartup:ev(),lastError:undefined,
    openOptionsPage(){if(E.options)window.open('awesome://ext/'+E.id+'/'+E.options)}},
  extension:{getURL:p=>'awesome://ext/'+E.id+'/'+String(p).replace(/^\//,''),inIncognitoContext:false},
  storage:{local:area(),sync:area(),managed:area(),onChanged:{addListener(f){listeners.push(f)},removeListener(f){const i=listeners.indexOf(f);if(i>=0)listeners.splice(i,1)},hasListener(f){return listeners.includes(f)}}},
  i18n:{getMessage:msg,getUILanguage:()=>navigator.language},
  tabs:{query(q,cb){return done(Promise.resolve([]),cb)},create(o){window.open(o&&o.url)},sendMessage(){},onUpdated:ev(),onActivated:ev()},
  permissions:{contains(p,cb){return done(Promise.resolve(true),cb)},request(p,cb){return done(Promise.resolve(true),cb)}},
  action:{setBadgeText(){},setBadgeBackgroundColor(){},setIcon(){},setTitle(){},onClicked:ev()},
  browserAction:{setBadgeText(){},setBadgeBackgroundColor(){},setIcon(){},setTitle(){},onClicked:ev()},
  alarms:{create(){},clear(){},onAlarm:ev()},
  contextMenus:{create(){},removeAll(){},onClicked:ev()},
};
try{window.chrome=chrome;window.browser=chrome}catch(e){}
})();
"""


class ExtensionManager(QObject):
    """Installs Chrome extensions and runs their content scripts.

    Qt WebEngine can't host Chrome's full extension runtime, so this is a
    compatibility layer: manifests are read, content scripts are injected in an
    isolated world per extension, and a small `chrome.*` API is provided
    (runtime, storage, i18n and no-op stubs). Extensions that depend on
    background pages, service workers or webRequest won't run those parts."""
    message = pyqtSignal(str)

    def __init__(self, ctx: "Context"):
        super().__init__(ctx)
        self.ctx, self.store = ctx, ctx.store
        self.dir = ctx.store.dir / "extensions"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list] = {}
        self._nam = None

    # records ----------------------------------------------------------------
    def records(self) -> list[dict]:
        return self.store["extensions"]

    def get(self, ext_id: str) -> dict | None:
        return next((r for r in self.records() if r["id"] == ext_id), None)

    def _read_manifest(self, root: Path) -> dict:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8-sig"))

    @staticmethod
    def _messages(root: Path, manifest: dict) -> dict:
        loc = manifest.get("default_locale")
        for cand in filter(None, (loc, "en", "en_US")):
            f = root / "_locales" / cand / "messages.json"
            if f.is_file():
                try:
                    return {k.lower(): v for k, v in json.loads(f.read_text(encoding="utf-8-sig")).items()}
                except ValueError:
                    pass
        return {}

    def _tr(self, text, msgs: dict) -> str:
        text = str(text or "")
        m = re.fullmatch(r"__MSG_(.+)__", text)
        if m:
            return str(msgs.get(m.group(1).lower(), {}).get("message", text))
        return text

    # install / remove -------------------------------------------------------
    def install_dir(self, src: Path, ext_id: str | None = None) -> tuple[bool, str]:
        try:
            manifest = self._read_manifest(src)
        except (OSError, ValueError):
            return False, "That folder has no readable manifest.json."
        if manifest.get("manifest_version") not in (2, 3):
            return False, "Only Manifest V2 and V3 extensions are supported."
        ext_id = ext_id or folder_extension_id(str(src))
        dest = self.dir / ext_id
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", "node_modules"))
        except OSError as e:
            return False, f"Couldn't copy the extension: {e}"
        msgs = self._messages(dest, manifest)
        icons = manifest.get("icons") or (manifest.get("action") or manifest.get("browser_action") or {}).get("default_icon") or {}
        if isinstance(icons, str):
            icons = {"48": icons}
        icon = icons[max(icons, key=lambda k: int(re.sub(r"\D", "", k) or 0))] if icons else ""
        act = manifest.get("action") or manifest.get("browser_action") or {}
        old = self.get(ext_id)
        used = {r["world"] for r in self.records() if r["id"] != ext_id}
        world = old["world"] if old else next(w for w in range(10, 250) if w not in used)
        bg = manifest.get("background") or {}
        rec = {
            "id": ext_id, "name": self._tr(manifest.get("name"), msgs) or ext_id,
            "version": str(manifest.get("version", "")), "description": self._tr(manifest.get("description"), msgs),
            "enabled": old["enabled"] if old else True, "world": world, "icon": icon,
            "popup": act.get("default_popup", ""), "options": (manifest.get("options_ui") or {}).get("page")
            or manifest.get("options_page", ""),
            "permissions": [str(p) for p in (manifest.get("permissions") or [])][:40],
            "hosts": [str(h) for h in (manifest.get("host_permissions") or [])][:40],
            "content": len(manifest.get("content_scripts") or []),
            "background": bool(bg.get("service_worker") or bg.get("scripts") or bg.get("page")),
            "mv": manifest.get("manifest_version"),
        }
        recs = [r for r in self.records() if r["id"] != ext_id] + [rec]
        self.store.set("extensions", recs)
        self.invalidate()
        return True, f"Installed {rec['name']}."

    def install_archive(self, path: str) -> tuple[bool, str]:
        import tempfile
        import zipfile
        try:
            data = crx_zip_bytes(Path(path).read_bytes())
            tmp = Path(tempfile.mkdtemp(prefix="ab2ext_"))
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(tmp)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            return False, f"Couldn't open that file: {e}"
        ok, msg = self.install_dir(tmp, self._id_from_name(path))
        shutil.rmtree(tmp, ignore_errors=True)
        return ok, msg

    @staticmethod
    def _id_from_name(path: str) -> str | None:
        m = re.search(r"[a-p]{32}", Path(path).stem)
        return m.group(0) if m else None

    def install_store(self, ref: str) -> None:
        m = re.search(r"[a-p]{32}", ref or "")
        if not m:
            self.message.emit("That doesn't look like a Chrome Web Store link or extension ID.")
            return
        ext_id = m.group(0)
        ver = self.ctx.chromium if re.match(r"^\d+(\.\d+)+$", self.ctx.chromium) else "120.0.0.0"
        url = QUrl(f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion={ver}"
                   f"&acceptformat=crx2,crx3&x=id%3D{ext_id}%26installsource%3Dondemand%26uc")
        if self._nam is None:
            self._nam = QNetworkAccessManager(self)
        req = QNetworkRequest(url)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self._nam.get(req)
        reply.finished.connect(lambda r=reply, i=ext_id: self._store_done(r, i))
        self.message.emit("Downloading from the Chrome Web Store\u2026")

    def _store_done(self, reply, ext_id: str) -> None:
        import tempfile
        import zipfile
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.message.emit(f"Download failed: {reply.errorString()}")
                return
            data = bytes(reply.readAll())
            if len(data) < 100:
                self.message.emit("The store didn't return a package for that ID.")
                return
            tmp = Path(tempfile.mkdtemp(prefix="ab2ext_"))
            with zipfile.ZipFile(io.BytesIO(crx_zip_bytes(data))) as z:
                z.extractall(tmp)
            ok, msg = self.install_dir(tmp, ext_id)
            shutil.rmtree(tmp, ignore_errors=True)
            self.message.emit(msg)
        except (ValueError, OSError, zipfile.BadZipFile) as e:
            self.message.emit(f"Couldn't install: {e}")
        finally:
            reply.deleteLater()

    def remove(self, ext_id: str) -> None:
        self.store.set("extensions", [r for r in self.records() if r["id"] != ext_id])
        shutil.rmtree(self.dir / ext_id, ignore_errors=True)
        self.invalidate()

    def set_enabled(self, ext_id: str, on: bool) -> None:
        r = self.get(ext_id)
        if r:
            r["enabled"] = bool(on)
            self.store.save()
            self.invalidate()

    # serving ----------------------------------------------------------------
    def serve(self, ext_id: str, rel: str):
        if not re.fullmatch(r"[a-p]{32}", ext_id) or not self.get(ext_id):
            return None
        root = (self.dir / ext_id).resolve()
        f = (root / rel.lstrip("/")).resolve()
        if root not in f.parents or not f.is_file() or f.name.startswith("__"):
            return None
        mt = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if f.suffix in (".js", ".mjs"):
            mt = "text/javascript"
        return f.read_bytes(), mt

    def api(self, ext_id: str, op: str, params: dict) -> bytes:
        if params.get("t") != self.ctx.app.ext_token or not re.fullmatch(r"[a-p]{32}", ext_id) or not self.get(ext_id):
            return b'{"ok":false}'
        f = self.dir / ext_id / "__storage.json"
        try:
            data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except (OSError, ValueError):
            data = {}
        try:
            if op == "set":
                data.update(json.loads(params.get("d", "{}")))
            elif op == "remove":
                for k in json.loads(params.get("k", "[]")):
                    data.pop(k, None)
            elif op == "clear":
                data = {}
            if op != "get":
                blob = json.dumps(data)
                if len(blob) > 2_000_000:
                    return b'{"ok":false}'
                f.write_text(blob, encoding="utf-8")
        except (OSError, ValueError, TypeError, AttributeError):
            return b'{"ok":false}'
        return json.dumps({"ok": True, "data": data}).encode("utf-8")

    # injection --------------------------------------------------------------
    def invalidate(self) -> None:
        self._cache.clear()
        self.refresh_pages()

    def refresh_pages(self) -> None:
        for w in self.ctx.app.windows:
            if w.ctx is self.ctx:
                for v in w.tab_views():
                    self.apply_to_page(v.page())

    def _read(self, root: Path, rel: str) -> str:
        try:
            return (root / rel).read_text(encoding="utf-8-sig")
        except OSError:
            return ""

    def _shim(self, rec: dict, manifest: dict, root: Path) -> str:
        info = {"id": rec["id"], "manifest": {k: manifest.get(k) for k in ("name", "version", "manifest_version", "description")},
                "messages": self._messages(root, manifest), "options": rec.get("options", ""),
                "token": self.ctx.app.ext_token}
        return EXT_SHIM_JS.replace("__EXT__", safe_json(info))

    def _build(self, rec: dict) -> list:
        root = self.dir / rec["id"]
        try:
            manifest = self._read_manifest(root)
        except (OSError, ValueError):
            return []
        shim = self._shim(rec, manifest, root)
        IP = QWebEngineScript.InjectionPoint
        scripts = []
        page_script = QWebEngineScript()
        page_script.setName(f"ab-ext-{rec['id']}-page")
        page_script.setWorldId(0)
        page_script.setInjectionPoint(IP.DocumentCreation)
        page_script.setRunsOnSubFrames(True)
        page_script.setSourceCode(f"if(location.href.indexOf('awesome://ext/{rec['id']}/')===0){{{shim}}}")
        scripts.append(page_script)
        for n, cs in enumerate(manifest.get("content_scripts") or []):
            inc = [r for r in (match_pattern_regex(m) for m in cs.get("matches", [])) if r]
            exc = [r for r in (match_pattern_regex(m) for m in cs.get("exclude_matches", [])) if r]
            if not inc:
                continue
            js = "\n;\n".join(self._read(root, f) for f in cs.get("js", []))
            css = "\n".join(self._read(root, f) for f in cs.get("css", []))
            css_js = (f"(function(){{var s=document.createElement('style');s.textContent={json.dumps(css)};"
                      f"(document.head||document.documentElement).appendChild(s)}})();") if css else ""
            test = (f"(function(){{var u=location.href.split('#')[0];var I={json.dumps(inc)},X={json.dumps(exc)};"
                    f"return I.some(function(r){{return new RegExp(r).test(u)}})&&!X.some(function(r){{return new RegExp(r).test(u)}})}})()")
            main_world = cs.get("world") == "MAIN"
            code = ("" if main_world else shim) + f"\nif({test}){{\n{css_js}\n{js}\n}}"
            sc = QWebEngineScript()
            sc.setName(f"ab-ext-{rec['id']}-{n}")
            sc.setWorldId(0 if main_world else int(rec["world"]))
            sc.setInjectionPoint({"document_start": IP.DocumentCreation, "document_end": IP.DocumentReady}.get(
                cs.get("run_at"), IP.Deferred))
            sc.setRunsOnSubFrames(bool(cs.get("all_frames")))
            sc.setSourceCode(code)
            scripts.append(sc)
        return scripts

    def apply_to_page(self, page: QWebEnginePage) -> None:
        if self.ctx.private:
            return
        coll = page.scripts()
        for s in coll.toList():
            if s.name().startswith("ab-ext-"):
                coll.remove(s)
        for rec in self.records():
            if not rec["enabled"]:
                continue
            if rec["id"] not in self._cache:
                self._cache[rec["id"]] = self._build(rec)
            for s in self._cache[rec["id"]]:
                coll.insert(s)


class ExtPopup(QDialog):
    def __init__(self, win: "MainWindow", rec: dict):
        super().__init__(win, Qt.WindowType.Popup)
        self.setFixedSize(400, 580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView()
        self.view.setPage(WebPage(win.ctx, win, self.view))
        self.view.load(QUrl(f"{SCHEME}://ext/{rec['id']}/{rec['popup']}"))
        lay.addWidget(self.view)


READER_JS = r"""(function(){
if(document.documentElement.getAttribute('data-ab-reader')){location.reload();return}
var root=document.querySelector('article')||document.querySelector('[role=main]')||document.querySelector('main');
if(!root){var best=null,bs=0;document.querySelectorAll('div,section').forEach(function(el){var n=0;
  el.querySelectorAll(':scope > p').forEach(function(p){n+=p.textContent.length});if(n>bs){bs=n;best=el}});root=best||document.body}
var esc=function(t){return t.replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})};
var parts=[];
root.querySelectorAll('h1,h2,h3,p,li,pre,blockquote,img').forEach(function(el){
  if(el.closest('nav,header,footer,aside,form,figure figcaption'))return;
  var tag=el.tagName.toLowerCase();
  if(tag==='img'){if((el.naturalWidth||el.width)>240)parts.push('<img src="'+el.currentSrc+'">');return}
  var t=el.textContent.trim();if(t.length<2)return;
  if(tag==='li')parts.push('<p>\u2022 '+esc(t)+'</p>');else parts.push('<'+tag+'>'+esc(t)+'</'+tag+'>')});
if(parts.length<3)return;
var title=(document.querySelector('h1')||{}).textContent||document.title;
document.querySelectorAll('link[rel=stylesheet],style').forEach(function(n){n.remove()});
document.documentElement.setAttribute('data-ab-reader','1');
document.body.innerHTML='<article><h1>'+esc(title.trim())+'</h1>'+parts.filter(function(p){return p.indexOf('<h1>')!==0}).join('')+'</article>';
var st=document.createElement('style');
st.textContent='html{background:__BG__}body{margin:0;color:__FG__;font:19px/1.75 Georgia,"Iowan Old Style",serif}article{max-width:700px;margin:0 auto;padding:64px 24px 120px}h1{font:700 38px/1.2 system-ui,sans-serif;margin:0 0 28px}h2,h3{font-family:system-ui,sans-serif;margin:36px 0 8px}p{margin:0 0 1.1em}img{max-width:100%;height:auto;border-radius:10px;margin:18px 0}pre{overflow:auto;background:rgba(127,127,127,.15);padding:14px;border-radius:8px;font-size:15px}blockquote{margin:1em 0;padding-left:18px;border-left:3px solid __ACC__;color:__SUB__}';
document.head.appendChild(st);window.scrollTo(0,0)})();"""


class WallpaperLayer(QWidget):
    """A click-through wallpaper surface behind the whole browser window."""

    VIDEO_SUFFIXES = {".mp4", ".webm", ".m4v", ".mov", ".ogv"}

    def __init__(self, store: ProfileStore, parent: QWidget):
        super().__init__(parent)
        self.store = store
        self._cache_key = ""
        self._pixmap = QPixmap()
        self._previous = QPixmap()
        self._fade = 1.0
        self._scaled: dict[tuple[int, int, int], QPixmap] = {}
        self._movie = None
        self._video = None
        self._video_dim = None
        self._player = None
        self._audio = None
        self._blur = None
        self.setObjectName("wallpaperLayer")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(220)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._fade_changed)
        self.set_wallpaper(animate=False)

    def _fade_changed(self, value) -> None:
        self._fade = float(value)
        self.update()

    @staticmethod
    def _pixmap_from_svg(data: bytes) -> QPixmap:
        renderer = QSvgRenderer(QByteArray(data))
        if not renderer.isValid():
            return QPixmap()
        pixmap = QPixmap(1920, 1080)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(pixmap.rect()))
        painter.end()
        return pixmap

    def _fallback_pixmap(self) -> QPixmap:
        data = theme_wallpaper_svg(self.store["theme"])
        if data:
            return self._pixmap_from_svg(data)
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(THEMES.get(self.store["theme"], THEMES["dark"])["bg"]))
        return pixmap

    def _load_pixmap(self, value: str) -> QPixmap:
        if value == "auto":
            data = theme_wallpaper_svg(self.store["theme"])
            return self._pixmap_from_svg(data) if data else QPixmap()
        if value.startswith("theme:"):
            data = theme_wallpaper_svg(value[6:])
            return self._pixmap_from_svg(data) if data else QPixmap()
        if value.startswith("user:"):
            name = os.path.basename(value[5:])
            if name not in self.store["user_wallpapers"]:
                return QPixmap()
            path = self.store.dir / "wallpapers" / name
            if path.suffix.lower() == ".svg":
                try:
                    return self._pixmap_from_svg(path.read_bytes())
                except OSError:
                    return QPixmap()
            return QPixmap(str(path))
        data = wallpaper_svg(value)
        return self._pixmap_from_svg(data) if data else QPixmap()

    def _stop_media(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if self._player is not None:
            self._player.stop()
            self._player.deleteLater()
            self._player = None
            self._audio = None
        if self._video is not None:
            self._video.hide()

    def _start_media(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix == ".gif":
            movie = QMovie(str(path))
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            if not movie.isValid():
                return False
            movie.frameChanged.connect(lambda: self._movie_frame(movie))
            self._movie = movie
            movie.start()
            return True
        if suffix not in self.VIDEO_SUFFIXES or QMediaPlayer is None:
            return False
        if self._video is None:
            self._video = QVideoWidget(self)
            self._video.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._video.setGeometry(self.rect())
            if hasattr(self._video, "setAspectRatioMode"):
                self._video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            self._video_dim = QWidget(self._video)
            self._video_dim.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._video_dim.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self._video_dim.setGeometry(self._video.rect())
            self._video_dim.raise_()
        audio = QAudioOutput(self)
        audio.setVolume(0.0)
        player = QMediaPlayer(self)
        player.setAudioOutput(audio)
        player.setVideoOutput(self._video)
        if hasattr(player, "setLoops"):
            player.setLoops(QMediaPlayer.Loops.Infinite)
        player.setSource(QUrl.fromLocalFile(str(path)))
        self._audio, self._player = audio, player
        self._video.show()
        self._video.lower()
        player.play()
        return True

    def _movie_frame(self, movie) -> None:
        if movie is self._movie:
            self._pixmap = movie.currentPixmap()
            self._scaled.clear()
            self.update()

    def set_wallpaper(self, animate: bool = True) -> None:
        value = self.store["wallpaper"]
        key = value + (":" + self.store["theme"] if value == "auto" else "")
        if key == self._cache_key:
            self.update_effects()
            return
        self._animation.stop()
        self._stop_media()
        self._previous = self._pixmap
        self._cache_key = key
        self._pixmap = self._load_pixmap(value)
        if self._pixmap.isNull():
            self._pixmap = self._fallback_pixmap()
        if value.startswith("user:"):
            path = self.store.dir / "wallpapers" / os.path.basename(value[5:])
            if path.is_file():
                self._start_media(path)
        self._scaled.clear()
        self._fade = 0.0 if animate and not self._previous.isNull() else 1.0
        if self._fade == 0.0:
            self._animation.start()
        else:
            self._previous = QPixmap()
        self.update_effects()
        self.update()

    def update_effects(self) -> None:
        blur = max(0, min(24, int(self.store["wallpaper_blur"])))
        dim = max(0, min(80, int(self.store["wallpaper_dim"])))
        if self._video_dim is not None:
            self._video_dim.setStyleSheet(f"background: rgba(0, 0, 0, {dim / 100:.2f});")
            self._video_dim.setGeometry(self._video.rect())
            self._video_dim.raise_()
        if blur and self._blur is None:
            self._blur = QGraphicsBlurEffect(self)
            self._blur.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
            self.setGraphicsEffect(self._blur)
        if self._blur is not None:
            self._blur.setBlurRadius(blur)
            if not blur:
                self.setGraphicsEffect(None)
                self._blur.deleteLater()
                self._blur = None
        self.update()

    def resizeEvent(self, event) -> None:
        if self._video is not None:
            self._video.setGeometry(self.rect())
            if self._video_dim is not None:
                self._video_dim.setGeometry(self._video.rect())
                self._video_dim.raise_()
        self._scaled.clear()
        super().resizeEvent(event)

    def _scaled_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return QPixmap()
        key = (self.width(), self.height(), hash(pixmap.cacheKey()))
        if key not in self._scaled:
            self._scaled[key] = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                              Qt.TransformationMode.SmoothTransformation)
        return self._scaled[key]

    def paintEvent(self, _event) -> None:
        if self._player is not None and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for pixmap, opacity in ((self._previous, 1.0 - self._fade), (self._pixmap, self._fade)):
            if pixmap.isNull() or opacity <= 0:
                continue
            scaled = self._scaled_pixmap(pixmap)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.setOpacity(opacity)
            painter.drawPixmap(x, y, scaled)
        painter.setOpacity(1.0)
        dim = max(0, min(80, int(self.store["wallpaper_dim"])))
        if dim:
            painter.fillRect(self.rect(), QColor(0, 0, 0, round(dim * 2.55)))
        painter.end()


class SidebarHoverZone(QWidget):
    hoverChanged = pyqtSignal(bool)

    def enterEvent(self, event) -> None:
        self.hoverChanged.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hoverChanged.emit(False)
        super().leaveEvent(event)


class SidebarRevealButton(QToolButton):
    hoverChanged = pyqtSignal(bool)

    def enterEvent(self, event) -> None:
        self.hoverChanged.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hoverChanged.emit(False)
        super().leaveEvent(event)


# ═════════════════════════════════════════════════════════════════════════════
#  Main window
# ═════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self, app: "BrowserApp", store: ProfileStore, ctx: Context, private: bool = False):
        super().__init__()
        self.app, self.store, self.ctx, self.private = app, store, ctx, private
        self.closed_tabs: list[tuple[str, bool]] = []
        self._icon_cache: dict = {}
        self._icon_buttons: list = []
        self._printer = None
        self._print_view = None
        self._print_loop = None
        self._print_result = None
        self._fs = False
        self._focus_mode = False
        self._was_max = False
        self._dev_view = None
        self._dev_target = None
        self._dev_page = None
        self._closing = False
        self._moving = False
        self._key_seq = 0
        self._anchor = None
        self._palette = None
        self._popup = None
        self._site_notifications: list[SiteNotificationPopup] = []
        self.tab_items: list = []                 # WebView or ChipItem, same order as the tab bar
        self.groups: dict[str, dict] = {}
        self.selected: set = set()
        self._current: WebView | None = None
        self.setWindowIcon(app.logo_icon)
        self.resize(1320, 860)
        self.setMinimumSize(640, 420)
        self._build_ui()
        self.download_popup = DownloadsPopup(self)
        self._build_shortcuts()
        ctx.downloads.finishedItem.connect(self._download_done)
        ctx.downloads.changed.connect(self._downloads_changed)
        app.governor.updated.connect(self.sidebar.perf.on_update)
        self.apply_theme()
        self.refresh_bookmarks_bar()
        self.refresh_extension_button()
        if store["sidebar_open"] or store["sidebar_always_visible"]:
            self.sidebar.set_open(True, animate=False)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.wallpaper_layer = WallpaperLayer(self.store, root)
        self.wallpaper_layer.setGeometry(root.rect())
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.chrome = QWidget()
        self.chrome.setObjectName("chrome")
        cl = QVBoxLayout(self.chrome)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # tab strip
        self.strip = QWidget()
        self.strip.setObjectName("strip")
        self.strip.setFixedHeight(40)
        sl = QHBoxLayout(self.strip)
        sl.setContentsMargins(10, 4, 10, 0)
        sl.setSpacing(4)
        self.tabbar = TabBar()
        self.tabbar.setObjectName("tabs")
        self.tabbar.provider = self.tab_info
        sl.addWidget(self.tabbar, 0, Qt.AlignmentFlag.AlignBottom)
        self.plus = self.tool_button("plus", "New tab (Ctrl+T)", self.new_tab, 30)
        sl.addWidget(self.plus, 0, Qt.AlignmentFlag.AlignVCenter)
        self.selbar = QWidget()
        self.selbar.setObjectName("selbar")
        sb = QHBoxLayout(self.selbar)
        sb.setContentsMargins(10, 2, 4, 2)
        sb.setSpacing(4)
        self.sel_label = QLabel("")
        sb.addWidget(self.sel_label)
        for text, fn in (("Group", self.group_selected), ("Close", self.close_selected)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, f=fn: f())
            sb.addWidget(b)
        sb.addWidget(self.tool_button("close", "Clear selection", self.clear_selection, 24))
        sl.addWidget(self.selbar, 0, Qt.AlignmentFlag.AlignVCenter)
        self.selbar.hide()
        sl.addStretch(1)
        if self.private:
            badge = QLabel("  Private  ")
            badge.setObjectName("badge")
            sl.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        cl.addWidget(self.strip)

        # toolbar
        self.toolbar = QWidget()
        self.toolbar.setObjectName("toolbar")
        self.toolbar.setFixedHeight(48)
        tl = QHBoxLayout(self.toolbar)
        tl.setContentsMargins(10, 0, 10, 0)
        tl.setSpacing(2)
        self.back_btn = self.tool_button("back", "Back (Alt+Left). Right-click for history", self.go_back)
        self.fwd_btn = self.tool_button("forward", "Forward (Alt+Right). Right-click for history", self.go_forward)
        self.reload_btn = self.tool_button("reload", "Reload (Ctrl+R)", self.reload_or_stop)
        self.home_btn = self.tool_button("home", "Home (Alt+Home)", self.go_home)
        for b, fwd in ((self.back_btn, False), (self.fwd_btn, True)):
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _p, bt=b, f=fwd: self.nav_history_menu(bt, f))
        for b in (self.back_btn, self.fwd_btn, self.reload_btn, self.home_btn):
            tl.addWidget(b)
        tl.addSpacing(6)
        self.address = AddressBar()
        self.address.setObjectName("address")
        self.sec_action = self.address.addAction(self.ic("globe"), QLineEdit.ActionPosition.LeadingPosition)
        self.star_action = self.address.addAction(self.ic("star"), QLineEdit.ActionPosition.TrailingPosition)
        self.star_action.setToolTip("Bookmark this page (Ctrl+D)")
        self.star_action.triggered.connect(self.toggle_bookmark)
        self.address.returnPressed.connect(self.on_address_enter)
        self.address.escaped.connect(self.on_address_escape)
        self.completer_model = QStringListModel(self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setMaxVisibleItems(8)
        self.completer.activated.connect(lambda text: self.navigate(text))
        self.address.setCompleter(self.completer)
        tl.addWidget(self.address, 1)
        tl.addSpacing(6)
        self.ext_btn = self.tool_button("puzzle", "Extensions", self.show_extensions_menu)
        self.dl_btn = self.tool_button("download", "Downloads", self.toggle_downloads_popup)
        self.settings_btn = self.tool_button("settings", "Settings (Ctrl+,)", lambda: self.open_internal("settings"))
        self.profile_btn = QToolButton()
        self.profile_btn.setFixedSize(34, 34)
        self.profile_btn.setIconSize(QSize(26, 26))
        self.profile_btn.setToolTip("Profiles")
        self.profile_btn.clicked.connect(self.show_profile_menu)
        self.menu_btn = self.tool_button("menu", "Menu", self.show_main_menu)
        for b in (self.ext_btn, self.dl_btn, self.settings_btn, self.profile_btn, self.menu_btn):
            tl.addWidget(b)
        cl.addWidget(self.toolbar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        cl.addWidget(self.progress)

        self.bmbar = QWidget()
        self.bmbar.setObjectName("bookmarkbar")
        self.bmbar.setFixedHeight(34)
        self.bm_layout = QHBoxLayout(self.bmbar)
        self.bm_layout.setContentsMargins(10, 3, 10, 3)
        self.bm_layout.setSpacing(2)
        cl.addWidget(self.bmbar)
        lay.addWidget(self.chrome)

        # sidebar + web content
        body = QWidget()
        body.setObjectName("browserBody")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.viewhost = QWidget()
        self.viewhost.setObjectName("viewhost")
        vl = QVBoxLayout(self.viewhost)
        vl.setContentsMargins(0, 0, 0, 0)
        self.content = ContentArea()
        self.stack = QStackedWidget()
        self.content.addWidget(self.stack)
        vl.addWidget(self.content)
        self.sidebar = Sidebar(self)
        bl.addWidget(self.sidebar)
        bl.addWidget(self.viewhost, 1)
        lay.addWidget(body, 1)
        self.sidebar_hover_zone = SidebarHoverZone(self.viewhost)
        self.sidebar_hover_zone.setObjectName("sidebarHoverZone")
        self.sidebar_hover_zone.setFixedSize(12, 126)
        self.sidebar_hover_zone.setMouseTracking(True)
        self.sidebar_hover_zone.hoverChanged.connect(self._sidebar_hover_changed)
        self.sidebar_reveal = SidebarRevealButton(self.viewhost)
        self.sidebar_reveal.setObjectName("sidebarReveal")
        self.sidebar_reveal.setFixedSize(34, 64)
        self.sidebar_reveal.setIconSize(QSize(18, 18))
        self.sidebar_reveal.setIcon(self.ic("sidebar"))
        self.sidebar_reveal.setToolTip("Open sidebar (Ctrl+B)")
        self.sidebar_reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_reveal.clicked.connect(lambda _=False: self.sidebar.toggle())
        self.sidebar_reveal.hoverChanged.connect(self._sidebar_hover_changed)
        self.sidebar_hide_timer = QTimer(self)
        self.sidebar_hide_timer.setSingleShot(True)
        self.sidebar_hide_timer.setInterval(420)
        self.sidebar_hide_timer.timeout.connect(self._hide_sidebar_reveal)
        self.sidebar_reveal_animation = QPropertyAnimation(self.sidebar_reveal, b"pos", self)
        self.sidebar_reveal_animation.setDuration(160)
        self.sidebar_reveal_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._icon_buttons.append((self.sidebar_reveal, "sidebar"))
        self.sidebar_hover_zone.raise_()
        self.sidebar_reveal.raise_()
        self.update_sidebar_reveal()
        self.link_label = QLabel(self.viewhost)
        self.link_label.setObjectName("overlay")
        self.link_label.hide()
        self.toast_label = QLabel(self.viewhost)
        self.toast_label.setObjectName("overlay")
        self.toast_label.hide()
        self.toast_fx = QGraphicsOpacityEffect(self.toast_label)
        self.toast_label.setGraphicsEffect(self.toast_fx)
        self.mini = MiniPlayer(self)
        self.toast_anim = QPropertyAnimation(self.toast_fx, b"opacity", self)
        self.toast_anim.finished.connect(self._toast_faded)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self._toast_out)

        # find bar
        self.findbar = QWidget()
        self.findbar.setObjectName("findbar")
        fl = QHBoxLayout(self.findbar)
        fl.setContentsMargins(14, 8, 14, 8)
        fl.setSpacing(6)
        self.find_input = QLineEdit()
        self.find_input.setObjectName("find")
        self.find_input.setPlaceholderText("Find in page")
        self.find_input.setFixedWidth(280)
        self.find_input.textChanged.connect(lambda: self.do_find(True))
        self.find_input.returnPressed.connect(lambda: self.do_find(True))
        self.find_count = QLabel("")
        self.find_count.setObjectName("muted")
        fl.addWidget(self.find_input)
        fl.addWidget(self.find_count)
        fl.addWidget(self.tool_button("up", "Previous (Shift+Enter)", lambda: self.do_find(False), 30))
        fl.addWidget(self.tool_button("down", "Next (Enter)", lambda: self.do_find(True), 30))
        fl.addStretch(1)
        fl.addWidget(self.tool_button("close", "Close (Esc)", self.close_find, 30))
        lay.addWidget(self.findbar)
        self.findbar.hide()
        self.wallpaper_layer.lower()
        QShortcut(QKeySequence("Esc"), self.findbar, activated=self.close_find,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Shift+Return"), self.find_input, activated=lambda: self.do_find(False),
                  context=Qt.ShortcutContext.WidgetShortcut)

        # developer tools dock
        self.devdock = QDockWidget("Developer tools", self)
        self.devdock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.devview = QWebEngineView()
        self.devdock.setWidget(self.devview)
        self.devdock.setMinimumHeight(260)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.devdock)
        self.devdock.hide()
        self.devdock.visibilityChanged.connect(self._dev_visibility)

        self.tabbar.currentChanged.connect(self.on_tab_changed)
        self.tabbar.tabMoved.connect(self.on_tab_moved)
        self.tabbar.tabCloseRequested.connect(self.close_tab)
        self.tabbar.newTabRequested.connect(self.new_tab)
        self.tabbar.customContextMenuRequested.connect(self.tab_context_menu)
        self.tabbar.chipClicked.connect(self.toggle_collapse)
        self.tabbar.tabModClick.connect(self.tab_mod_click)
        self.tabbar.plainClick.connect(self.clear_selection)

    def tool_button(self, icon: str, tip: str, slot, size: int = 34) -> QToolButton:
        b = QToolButton()
        b.setFixedSize(size, size)
        b.setIconSize(QSize(18, 18))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: slot())
        self._icon_buttons.append((b, icon))
        return b

    def tab_close_button(self, view: WebView) -> QToolButton:
        button = QToolButton()
        button.setObjectName("tabclose")
        button.setFixedSize(20, 20)
        button.setIconSize(QSize(14, 14))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setAutoRaise(True)
        button.setIcon(self.ic("close", self.theme()["sub"]))
        button.setToolTip("Close tab")
        button.clicked.connect(lambda _=False, v=view: self.close_tab(self.index_of(v)))
        return button

    def _build_shortcuts(self) -> None:
        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)
        sc("Ctrl+T", self.new_tab)
        sc("Ctrl+W", lambda: self.close_tab(self.tabbar.currentIndex()))
        sc("Ctrl+Shift+T", self.reopen_tab)
        sc("Ctrl+N", lambda: self.app.open_window(self.store))
        sc("Ctrl+Shift+N", lambda: self.app.open_window(self.store, private=True))
        for s in ("Ctrl+L", "Alt+D", "F6"):
            sc(s, self.focus_address)
        for s in ("Ctrl+R", "F5"):
            sc(s, lambda: self.current_view() and self.current_view().reload())
        for s in ("Ctrl+Shift+R", "Ctrl+F5"):
            sc(s, lambda: self.current_view() and self.current_view().page().triggerAction(
                QWebEnginePage.WebAction.ReloadAndBypassCache))
        sc("Alt+Left", self.go_back)
        sc("Alt+Right", self.go_forward)
        sc("Alt+Home", self.go_home)
        sc("Ctrl+D", self.toggle_bookmark)
        sc("Ctrl+Shift+B", self.toggle_bookmarks_bar)
        sc("Ctrl+H", lambda: self.open_internal("history"))
        sc("Ctrl+J", lambda: self.open_internal("downloads"))
        sc("Ctrl+Shift+O", lambda: self.open_internal("bookmarks"))
        sc("Ctrl+,", lambda: self.open_internal("settings"))
        sc("Ctrl+Shift+Delete", lambda: self.open_internal("settings/privacy"))
        sc("Ctrl+F", self.open_find)
        sc("Ctrl+P", self.print_page)
        sc("Ctrl+S", self.save_page)
        sc("Ctrl+U", self.view_source)
        sc("F12", lambda: self.open_devtools(self.current_view()))
        sc("Ctrl+Shift+I", lambda: self.open_devtools(self.current_view()))
        sc("F11", self.toggle_fullscreen)
        for s in ("Ctrl++", "Ctrl+="):
            sc(s, lambda: self.zoom_step(1))
        sc("Ctrl+-", lambda: self.zoom_step(-1))
        sc("Ctrl+0", lambda: self.zoom_set(1.0))
        sc("Ctrl+Tab", lambda: self.cycle_tab(1))
        sc("Ctrl+PgDown", lambda: self.cycle_tab(1))
        sc("Ctrl+Shift+Tab", lambda: self.cycle_tab(-1))
        sc("Ctrl+PgUp", lambda: self.cycle_tab(-1))
        for i in range(1, 9):
            sc(f"Ctrl+{i}", lambda i=i: self.select_tab(i - 1))
            sc(f"Alt+{i}", lambda i=i: self.select_tab(i - 1))
        sc("Ctrl+9", lambda: self.select_tab(-1))
        # 2.1 nightly
        for s in ("Ctrl+K", "Ctrl+Shift+P"):
            sc(s, self.open_palette)
        sc("Ctrl+B", self.sidebar.toggle)
        sc("Ctrl+Shift+G", self.group_current)
        sc("Ctrl+Alt+R", self.reader_mode)
        sc("Ctrl+Shift+F", self.toggle_zen)
        sc("Ctrl+Shift+Z", self.toggle_zen)
        sc("Ctrl+Shift+S", self.screenshot)
        self.esc_fullscreen = QShortcut(QKeySequence("Esc"), self, activated=self._leave_hidden_chrome)
        self.esc_fullscreen.setEnabled(False)

    def ic(self, name: str, color: str | None = None) -> QIcon:
        t = resolve_theme(self.store)
        stable = self.store["edition"] == "stable"
        key = (name, color, self.store["theme"], stable)
        if key not in self._icon_cache:
            col = color or (ICON_COLORS.get(name) if stable else None) or t["text"]
            self._icon_cache[key] = make_icon(name, col, t["sub"])
        return self._icon_cache[key]

    def edition(self) -> str:
        return self.store["edition"]

    def apply_edition(self) -> None:
        ed = self.edition()
        stable, legacy = ed == "stable", ed == "legacy"
        self.tabbar.pill = stable
        self.tabbar.h = 40 if stable else 36
        self.strip.setFixedHeight(46 if stable else 40)
        self.toolbar.setFixedHeight(54 if stable else 48)
        self.address.setFixedHeight(40 if stable else 34)
        self.refresh_extension_button()
        self.sidebar.setVisible(not legacy and not (self._fs or self._focus_mode))
        self.update_sidebar_reveal()
        self.mini.refresh_icons()
        self.mini.refresh_visibility()
        self.tabbar.relayout()
        if self._fs or self._focus_mode:
            self._apply_chrome_visibility()

    def apply_theme(self) -> None:
        t = resolve_theme(self.store)
        self._icon_cache.clear()
        self.setPalette(build_palette(t))
        self.setStyleSheet(build_qss(t, self.store["edition"]))
        self.content.set_color(t["bg"])
        self.completer.popup().setStyleSheet(COMPLETER_QSS.safe_substitute(**t))
        for b, name in self._icon_buttons:
            b.setIcon(self.ic(name))
        self.refresh_profile_button()
        for i in range(self.tabbar.count()):
            btn = self.tabbar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if isinstance(btn, QToolButton):
                btn.setIcon(self.ic("close", t["sub"]))
            v = self.view_at(i)
            if v and v.url().scheme() == SCHEME:
                self.tabbar.setTabIcon(i, self.app.logo_icon)
        self.sidebar.refresh_icons()
        if self._palette is not None:
            self._palette.deleteLater()
            self._palette = None
        self.apply_edition()
        self.update_toolbar()
        self.refresh_bookmarks_bar()
        self.wallpaper_layer.set_wallpaper()

    def theme(self) -> dict:
        return resolve_theme(self.store)

    def anim_on(self) -> bool:
        return bool(self.store["animations"]) and self.store["edition"] != "legacy"

    def refresh_profile_button(self) -> None:
        img = str(self.store.dir / self.store["avatar_image"]) if self.store["avatar_image"] else None
        self.profile_btn.setIcon(QIcon(avatar_pixmap(self.store["avatar_emoji"] or self.store["name"], self.store["color"], 28, img)))
        tip = self.store["name"] + (f"\n{self.store['description']}" if self.store["description"] else "")
        self.profile_btn.setToolTip(tip)
        self.home_btn.setVisible(bool(self.store["show_home_button"]) and not self._focus_mode and not self._fs)

    def on_setting_changed(self, key: str, sender) -> None:
        if key in ("theme", "accent"):
            self.apply_theme()
            for v in self.tab_views():
                if v.url().scheme() == SCHEME and v.page() is not sender:
                    v.reload()
        elif key == "edition":
            self.apply_theme()
        elif key == "mini_player":
            self.mini.refresh_visibility()
        elif key == "show_bookmarks_bar":
            self.refresh_bookmarks_bar()
        elif key in ("show_home_button", "name", "color", "avatar_emoji", "description"):
            self.refresh_profile_button()
        elif key == "force_dark_pages":
            self.ctx.apply_dark_mode()
        elif key == "smooth_scroll":
            self.ctx.apply_scroll()
        elif key == "keep_cookies":
            self.toast("Restart AwesomeBrowse 2 to apply the cookie change")
        elif key in ("wallpaper", "wallpaper_dim", "wallpaper_blur"):
            self.wallpaper_layer.set_wallpaper()
        elif key == "sidebar_always_visible":
            if self.store[key]:
                self.sidebar.set_open(True)
            self.update_sidebar_reveal()

    def current_view(self) -> WebView | None:
        return self._current

    def tab_views(self) -> list:
        return [x for x in self.tab_items if isinstance(x, WebView)]

    def index_of(self, item) -> int:
        for i, x in enumerate(self.tab_items):
            if x is item:
                return i
        return -1

    def is_visible_view(self, v) -> bool:
        return v is self._current

    def view_at(self, i: int):
        x = self.tab_items[i] if 0 <= i < len(self.tab_items) else None
        return x if isinstance(x, WebView) else None

    def add_tab(self, url, background: bool = False, after_current: bool = False, blank: bool = False,
                pinned: bool = False, group: str | None = None, lazy: bool = False, lazy_title: str | None = None) -> WebView:
        view = WebView(self)
        self._key_seq += 1
        view.key = self._key_seq
        view.setZoomFactor(self.store["zoom_default"] / 100)
        page = view.page()
        view.titleChanged.connect(lambda t, v=view: self._title_changed(v, t))
        view.iconChanged.connect(lambda _i, v=view: self._icon_changed(v))
        view.urlChanged.connect(lambda u, v=view: self._url_changed(v, u))
        view.loadStarted.connect(lambda v=view: self._load_started(v))
        view.loadProgress.connect(lambda p, v=view: self._load_progress(v, p))
        view.loadFinished.connect(lambda ok, v=view: self._load_finished(v, ok))
        view.printRequested.connect(self.print_page)
        page.linkHovered.connect(self.show_link)
        page.fullScreenRequested.connect(self._html_fullscreen)
        page.windowCloseRequested.connect(lambda v=view: self.close_tab(self.index_of(v)))
        page.recentlyAudibleChanged.connect(lambda _a, v=view: self._refresh_tab_label(v))
        page.findTextFinished.connect(lambda r, v=view: self._find_result(v, r))

        n = len(self.tab_items)
        npinned = sum(1 for x in self.tab_items if isinstance(x, WebView) and x.pinned)
        idx = n
        cur = self.index_of(self._current) if self._current else -1
        if after_current and cur >= 0:
            idx = max(cur + 1, npinned)
            if group is None and self._current.group and not pinned:
                group = self._current.group          # tabs opened from a grouped tab stay in that group
        if pinned:
            idx, group = npinned, None
        if group and group in self.groups:
            idx = self._group_insert_index(group, idx)
            self.groups[group]["collapsed"] = False
            self._apply_collapse(group)
        view.group = group if group in self.groups else None
        if lazy and url:                       # decided before the tab exists, so a first tab still loads when selected
            view.pending_url = url
            view.page_title = lazy_title or QUrl(url).host() or "New tab"

        self._moving = True
        self.tab_items.insert(idx, view)
        self.stack.addWidget(view)
        if self.anim_on():
            self.tabbar.factors[view.key] = 0.03
        self.tabbar.insertTab(idx, self.app.logo_icon, "New tab")
        self.tabbar.setTabData(idx, {"key": view.key, "pinned": False, "chip": None})
        btn = self.tab_close_button(view)
        self.tabbar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, btn)
        self._moving = False
        if pinned:
            self.set_pinned(view, True)
        if self.anim_on():
            self.tabbar.animate(view.key, 0.03, 1.0, 200)
        else:
            self.tabbar.relayout()
        if view.pending_url:
            self._refresh_tab_label(view)
        elif not blank:
            view.load(QUrl(url) if url else QUrl(NEWTAB))
        if not background:
            view.fresh = True
            self.tabbar.setCurrentIndex(self.index_of(view))
            view.setFocus()
        self._groups_changed()
        return view

    def new_tab(self) -> None:
        self.add_tab(None, after_current=False).setFocus()

    def new_tab(self) -> None:
        v = self.add_tab(None, after_current=False)
        v.setFocus()

    def open_url(self, url: str, new_tab: bool = True) -> None:
        if new_tab or not self.current_view():
            self.add_tab(url)
        else:
            self.current_view().load(QUrl(url))

    def open_internal(self, path: str) -> None:
        url = f"{SCHEME}://{path}"
        v = self.current_view()
        if v and v.url().toString().rstrip("/") == NEWTAB:
            v.load(QUrl(url))
        else:
            self.add_tab(url)

    def close_tab(self, i: int) -> None:
        view = self.view_at(i)
        if view is None or view.closing:
            return
        if len(self.tab_views()) == 1:
            self.close()
            return
        view.closing = True
        self.selected.discard(view)
        if self.anim_on() and self.tabbar.isTabVisible(i):
            btn = self.tabbar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if btn:
                btn.hide()
            self.tabbar.animate(view.key, 1.0, 0.03, 150, done=lambda v=view: self._finish_close(v))
        else:
            self._finish_close(view)

    def _finish_close(self, view: WebView) -> None:
        i = self.index_of(view)
        if i < 0:
            return
        url = view.url()
        if url.isValid() and url.toString().rstrip("/") != NEWTAB and not self.private:
            self.closed_tabs.append((url.toString(), view.pinned))
            del self.closed_tabs[:-20]
        if self._dev_target is view:
            self.devdock.hide()
        if self._current is view:
            self._current = None
        self._moving = True
        self.tab_items.pop(i)
        self.tabbar.factors.pop(view.key, None)
        self.tabbar.removeTab(i)
        self._moving = False
        if view.group and not any(v.group == view.group for v in self.tab_views() if v is not view):
            view.group = None
        self.stack.removeWidget(view)
        view.deleteLater()
        self._drop_empty_groups()
        self.update_selbar()
        self.tabbar.relayout()
        self._groups_changed()
        if self._current is None:
            cur = self.view_at(self.tabbar.currentIndex())
            if cur is not None:
                self.on_tab_changed(self.tabbar.currentIndex())

    def reopen_tab(self) -> None:
        if self.closed_tabs:
            url, pinned = self.closed_tabs.pop()
            self.add_tab(url, pinned=pinned)

    def reopen_tab(self) -> None:
        if self.closed_tabs:
            url, pinned = self.closed_tabs.pop()
            self.add_tab(url, pinned=pinned)

    def on_tab_changed(self, i: int) -> None:
        item = self.tab_items[i] if 0 <= i < len(self.tab_items) else None
        if item is None:
            return
        if isinstance(item, ChipItem):                  # never rest on a group label
            self._select_near(i)
            return
        view = item
        if view is self._current:
            return
        now = time.time()
        if self._current is not None:
            self._current.last_active = now
        self._current = view
        view.last_active = now
        if view.sleeping:
            self.wake_view(view)
        if view.pending_url:
            url, view.pending_url = view.pending_url, None
            view.load(QUrl(url))
        if self._dev_target is not None and self._dev_target is not view:
            self.devdock.hide()
        self.close_find()
        self.show_view(view, strong=getattr(view, "fresh", False))
        view.fresh = False
        self.update_toolbar(force_address=True)
        self.update_window_title()
        self.progress.setValue(0 if not view.loading else max(8, self.progress.value()))
        if not self.address.hasFocus() or view.url().toString().rstrip("/") == NEWTAB:
            view.setFocus()
        self.sidebar.perf.refresh() if self.sidebar.is_open and self.sidebar.current == "perf" else None
        self.tabbar.update()

    def _select_near(self, i: int) -> None:
        n = len(self.tab_items)
        for step in range(1, n + 1):
            for j in (i + step, i - step):
                if 0 <= j < n and isinstance(self.tab_items[j], WebView) and self.tabbar.isTabVisible(j):
                    self.tabbar.setCurrentIndex(j)
                    return

    def show_view(self, view: WebView, strong: bool = False) -> None:
        if self.stack.indexOf(view) < 0:
            self.stack.addWidget(view)
        self.stack.setCurrentWidget(view)
        self.content.setCurrentWidget(self.stack)
        if self.anim_on():
            self.content.flash(0.96 if strong else 0.5, 280 if strong else 200)

    def on_tab_moved(self, frm: int, to: int) -> None:
        if not (0 <= frm < len(self.tab_items)):
            return
        item = self.tab_items.pop(frm)
        self.tab_items.insert(to, item)
        if not self._moving and isinstance(item, WebView) and not item.pinned:
            self._infer_group(item)
        self.tabbar.update()

    def select_tab(self, n: int) -> None:
        shown = [i for i, x in enumerate(self.tab_items) if isinstance(x, WebView) and self.tabbar.isTabVisible(i)]
        if shown:
            self.tabbar.setCurrentIndex(shown[-1] if n < 0 else shown[min(n, len(shown) - 1)])

    def cycle_tab(self, d: int) -> None:
        n, i = len(self.tab_items), self.tabbar.currentIndex()
        for step in range(1, n + 1):
            j = (i + d * step) % n
            if isinstance(self.tab_items[j], WebView) and self.tabbar.isTabVisible(j):
                self.tabbar.setCurrentIndex(j)
                return

    def set_pinned(self, view: WebView, pinned: bool) -> None:
        i = self.index_of(view)
        if i < 0:
            return
        if pinned and view.group:
            self.remove_from_group(view)
            i = self.index_of(view)
        view.pinned = pinned
        meta = dict(self.tabbar.meta(i))
        meta["pinned"] = pinned
        self.tabbar.setTabData(i, meta)
        old = self.tabbar.tabButton(i, QTabBar.ButtonPosition.RightSide)
        if pinned:
            self.tabbar.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
            if old:
                old.hide()
                old.deleteLater()
        else:
            btn = self.tab_close_button(view)
            self.tabbar.setTabButton(i, QTabBar.ButtonPosition.RightSide, btn)
        others = sum(1 for x in self.tab_items if isinstance(x, WebView) and x.pinned and x is not view)
        dest = others if pinned else others
        if i != dest:
            self._moving = True
            self.tabbar.moveTab(i, dest)
            self._moving = False
        self._refresh_tab_label(view)
        self.tabbar.relayout()

    def _refresh_tab_label(self, view: WebView) -> None:
        i = self.index_of(view)
        if i < 0:
            return
        title = view.page_title or "New tab"
        page = view.page()
        prefix = ""
        if view.sleeping:
            prefix = "\u25cb "
        elif page.isAudioMuted():
            prefix = "(muted) "
        elif page.recentlyAudible():
            prefix = "\u266a "
        self.tabbar.setTabText(i, "" if view.pinned else prefix + title)
        tip = prefix + title + ("\nSleeping to save memory. Click to wake it." if view.sleeping else "")
        self.tabbar.setTabToolTip(i, tip)

    def _title_changed(self, view: WebView, title: str) -> None:
        if view.url().scheme() == SCHEME and view.url().host() == "newtab":
            title = "New tab"
        view.page_title = title or view.url().host() or "New tab"
        self._refresh_tab_label(view)
        if view is self._current:
            self.update_window_title()

    def _icon_changed(self, view: WebView) -> None:
        i = self.index_of(view)
        if i < 0:
            return
        if view.url().scheme() == SCHEME:
            self.tabbar.setTabIcon(i, self.app.logo_icon)
        else:
            icon = view.icon()
            self.tabbar.setTabIcon(i, icon if not icon.isNull() else self.ic("globe"))

    def _url_changed(self, view: WebView, url: QUrl) -> None:
        i = self.index_of(view)
        if url.scheme() == SCHEME and i >= 0:
            self.tabbar.setTabIcon(i, self.app.logo_icon)
            if not view.page_title or view.page_title == "New tab":
                view.page_title = {"newtab": "New tab"}.get(url.host(), url.host().capitalize())
                self._refresh_tab_label(view)
        if view is self._current:
            self.update_toolbar(force_address=not self.address.hasFocus())

    def _load_started(self, view: WebView) -> None:
        view.loading = True
        if view is self.current_view():
            self.reload_btn.setIcon(self.ic("stop"))
            self.progress.setValue(8)

    def _load_progress(self, view: WebView, p: int) -> None:
        if view is self.current_view():
            self.progress.setValue(max(p, 8))

    def _load_finished(self, view: WebView, ok: bool) -> None:
        view.loading = False
        if view is self._current:
            self.reload_btn.setIcon(self.ic("reload"))
            self.progress.setValue(0)
            self.update_toolbar()
        url = view.url()
        if ok and self.store["zoom_per_site"] and url.scheme() in ("http", "https") and url.host():
            z = self.store["zoom_by_host"].get(url.host())
            if z and abs(view.zoomFactor() - z) > 0.001:
                view.setZoomFactor(z)
        if ok and not self.private and url.scheme() in ("http", "https"):
            self.record_history(view.title(), url.toString())

    def update_window_title(self) -> None:
        v = self.current_view()
        title = v.page_title if v else ""
        self.setWindowTitle(f"{title} - {APP_NAME}" + (" (Private)" if self.private else "") if title else APP_NAME)

    # ── toolbar state ───────────────────────────────────────────────────────
    @staticmethod
    def display_url(url: QUrl) -> str:
        s = url.toString()
        if url.scheme() == SCHEME and url.host() == "newtab":
            return ""
        return s

    def update_toolbar(self, force_address: bool = False) -> None:
        v = self.current_view()
        if not v:
            return
        h = v.history()
        self.back_btn.setEnabled(h.canGoBack())
        self.fwd_btn.setEnabled(h.canGoForward())
        loading = getattr(v, "loading", False)
        self.reload_btn.setIcon(self.ic("stop" if loading else "reload"))
        url = v.url()
        if force_address or not self.address.hasFocus():
            self.address.setText(self.display_url(url))
            self.address.setCursorPosition(0)
        scheme = url.scheme()
        if scheme == "https":
            self.sec_action.setIcon(self.ic("lock", resolve_theme(self.store)["sub"]))
            self.sec_action.setToolTip("Connection is secure")
        elif scheme == "http":
            self.sec_action.setIcon(self.ic("warn", "#e5a03a"))
            self.sec_action.setToolTip("Not secure")
        elif scheme == SCHEME:
            self.sec_action.setIcon(self.app.logo_icon)
            self.sec_action.setToolTip("AwesomeBrowse page")
        else:
            self.sec_action.setIcon(self.ic("globe"))
            self.sec_action.setToolTip("")
        if self._focus_mode and not self._fs:
            self.sec_action.setIcon(self.app.logo_icon)
            self.sec_action.setToolTip("AwesomeBrowse Zen")
        marked = self.is_bookmarked(url.toString())
        self.star_action.setIcon(self.ic("star_on", resolve_theme(self.store)["accent"]) if marked else self.ic("star"))
        self.star_action.setVisible(not self._focus_mode and scheme in ("http", "https", "file"))

    # ── navigation ──────────────────────────────────────────────────────────
    def focus_address(self) -> None:
        self.address.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.address.selectAll()

    def on_address_enter(self) -> None:
        self.navigate(self.address.text())

    def on_address_escape(self) -> None:
        v = self.current_view()
        self.update_toolbar(force_address=True)
        if v:
            v.setFocus()

    def navigate(self, text: str) -> None:
        v = self.current_view() or self.add_tab(None)
        url = smart_url(text, self.store.search_template)
        v.load(url)
        v.setFocus()

    def go_back(self) -> None:
        v = self.current_view()
        v and v.back()

    def go_forward(self) -> None:
        v = self.current_view()
        v and v.forward()

    def reload_or_stop(self) -> None:
        v = self.current_view()
        if v:
            v.stop() if getattr(v, "loading", False) else v.reload()

    def go_home(self) -> None:
        v = self.current_view()
        if v:
            home = self.store["homepage"].strip()
            v.load(smart_url(home, self.store.search_template) if home else QUrl(NEWTAB))

    def nav_history_menu(self, button: QToolButton, forward: bool) -> None:
        v = self.current_view()
        if not v:
            return
        h = v.history()
        items = h.forwardItems(12) if forward else list(reversed(h.backItems(12)))
        if not items:
            return
        m = self.make_menu()
        for item in items:
            add_action(m, (item.title() or item.url().toString())[:60], lambda it=item: h.goToItem(it))
        m.exec(button.mapToGlobal(button.rect().bottomLeft()))

    # ── history & bookmarks ─────────────────────────────────────────────────
    def record_history(self, title: str, url: str) -> None:
        hist = self.store["history"]
        if hist and hist[0]["url"] == url:
            hist[0]["title"] = title or hist[0]["title"]
        else:
            hist.insert(0, {"title": title or url, "url": url, "time": time.time()})
            del hist[5000:]
        self.store.save()

    def is_bookmarked(self, url: str) -> bool:
        return any(b["url"] == url for b in self.store["bookmarks"])

    def toggle_bookmark(self) -> None:
        v = self.current_view()
        if not v or v.url().scheme() not in ("http", "https", "file"):
            return
        url = v.url().toString()
        if self.is_bookmarked(url):
            self.store.set("bookmarks", [b for b in self.store["bookmarks"] if b["url"] != url])
            self.toast("Bookmark removed")
        else:
            self.store["bookmarks"].append({"title": v.title() or url, "url": url})
            self.store.save()
            self.toast("Bookmarked")
        self.app.data_changed(self.store)

    def toggle_bookmarks_bar(self) -> None:
        self.app.apply_setting(self.store, "show_bookmarks_bar", not self.store["show_bookmarks_bar"])

    def refresh_bookmarks_bar(self) -> None:
        while self.bm_layout.count():
            item = self.bm_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        marks = self.store["bookmarks"]
        show_bar = bool(self.store["show_bookmarks_bar"]) and not self._focus_mode and not self._fs
        self.bmbar.setVisible(show_bar)
        if not show_bar:
            return
        avail = max(200, self.width() - 80)
        used, overflow = 0, []
        fm = QFontMetrics(self.font())
        for b in marks:
            text = fm.elidedText(b["title"] or b["url"], Qt.TextElideMode.ElideRight, 150)
            w = fm.horizontalAdvance(text) + 42
            if overflow or used + w > avail:
                overflow.append(b)
                continue
            used += w + 2
            btn = QToolButton()
            btn.setObjectName("bm")
            btn.setText(text)
            btn.setIcon(self.ic("globe"))
            btn.setIconSize(QSize(14, 14))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setFixedHeight(26)
            btn.setToolTip(b["url"])
            btn.clicked.connect(lambda _=False, u=b["url"]: self.open_url(u, new_tab=False))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda _p, bk=b, bt=btn: self.bookmark_menu(bk, bt))
            self.bm_layout.addWidget(btn)
        if overflow:
            more = QToolButton()
            more.setObjectName("bm")
            more.setText("\u00bb")
            more.setFixedHeight(26)
            more.clicked.connect(lambda _=False, o=overflow, m=more: self._overflow_menu(o, m))
            self.bm_layout.addWidget(more)
        if not marks:
            hint = QLabel("Bookmarks you add appear here. Press Ctrl+D on any page.")
            hint.setObjectName("muted")
            self.bm_layout.addWidget(hint)
        self.bm_layout.addStretch(1)

    def _overflow_menu(self, items, button) -> None:
        m = self.make_menu()
        for b in items:
            add_action(m, (b["title"] or b["url"])[:60], lambda u=b["url"]: self.open_url(u, new_tab=False))
        m.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def bookmark_menu(self, bk: dict, button: QToolButton) -> None:
        m = self.make_menu()
        add_action(m, "Open in new tab", lambda: self.open_url(bk["url"]))
        add_action(m, "Open in new window", lambda: self.app.open_window(self.store, urls=[bk["url"]]))
        m.addSeparator()
        add_action(m, "Rename\u2026", lambda: self._rename_bookmark(bk))
        add_action(m, "Delete", lambda: self._delete_bookmark(bk))
        m.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _rename_bookmark(self, bk: dict) -> None:
        text, ok = QInputDialog.getText(self, "Rename bookmark", "Name", text=bk["title"])
        if ok and text.strip():
            bk["title"] = text.strip()
            self.store.save()
            self.app.data_changed(self.store)

    def _delete_bookmark(self, bk: dict) -> None:
        self.store.set("bookmarks", [b for b in self.store["bookmarks"] if b is not bk])
        self.app.data_changed(self.store)

    def refresh_completions(self) -> None:
        """Suggestions ranked by how often and how recently you visit them, plus your past searches."""
        from urllib.parse import parse_qs, urlsplit
        now, score, hosts = time.time(), {}, {}
        search_hosts = ("google.", "duckduckgo.", "bing.", "search.brave.", "ecosia.", "startpage.", "search.yahoo.")
        for h in self.store["history"][:3000]:
            u = h["url"]
            w = 1.0 / (1.0 + (now - h["time"]) / 86400 / 7)
            try:
                parts = urlsplit(u)
            except ValueError:
                continue
            host = (parts.hostname or "").removeprefix("www.")
            if any(host.startswith(x) or x in host for x in search_hosts):
                q = (parse_qs(parts.query).get("q") or parse_qs(parts.query).get("p") or [""])[0].strip()
                if q:
                    score[q] = score.get(q, 0) + w * 1.2
                continue
            score[u] = score.get(u, 0) + w
            if host:
                hosts[host] = hosts.get(host, 0) + w
        for b in self.store["bookmarks"]:
            score[b["url"]] = score.get(b["url"], 0) + 3
            try:
                host = (urlsplit(b["url"]).hostname or "").removeprefix("www.")
            except ValueError:
                host = ""
            if host:
                hosts[host] = hosts.get(host, 0) + 3
        for host, w in hosts.items():
            score[host] = score.get(host, 0) + w * 1.5
        ranked = sorted(score, key=score.get, reverse=True)[:1500]
        self.completer_model.setStringList(ranked)
        self.address.candidates = sorted(hosts, key=hosts.get, reverse=True)[:400]

    def make_menu(self, parent=None) -> QMenu:
        return style_popup(QMenu(parent or self))

    def show_main_menu(self) -> None:
        m = self.make_menu()
        add_action(m, "New tab", self.new_tab, "Ctrl+T")
        add_action(m, "New window", lambda: self.app.open_window(self.store), "Ctrl+N")
        add_action(m, "New private window", lambda: self.app.open_window(self.store, private=True), "Ctrl+Shift+N")
        m.addSeparator()
        zoom = ZoomRow(self, m)
        wa = QWidgetAction(m)
        wa.setDefaultWidget(zoom)
        m.addAction(wa)
        m.addSeparator()
        add_action(m, "Command palette\u2026", self.open_palette, "Ctrl+K")
        add_action(m, "Sidebar", self.sidebar.toggle, "Ctrl+B", checkable=True, checked=self.sidebar.is_open)
        add_action(m, "Customize sidebar\u2026", self.sidebar.customize)
        ws = style_popup(m.addMenu("Tabs and workspaces"))
        add_action(ws, "Group this tab\u2026", self.group_current, "Ctrl+Shift+G")
        add_action(ws, "Group selected tabs\u2026", self.group_selected, enabled=len(self.selected) >= 2)
        ws.addSeparator()
        add_action(ws, "Save workspace\u2026", self.save_workspace)
        add_action(m, "Extensions", lambda: self.open_internal("extensions"))
        m.addSeparator()
        bm = style_popup(m.addMenu("Bookmarks"))
        add_action(bm, "Bookmark this tab", self.toggle_bookmark, "Ctrl+D")
        add_action(bm, "Show bookmarks bar", self.toggle_bookmarks_bar, "Ctrl+Shift+B", checkable=True,
                   checked=bool(self.store["show_bookmarks_bar"]))
        add_action(bm, "Manage bookmarks", lambda: self.open_internal("bookmarks"), "Ctrl+Shift+O")
        if self.store["bookmarks"]:
            bm.addSeparator()
            for b in self.store["bookmarks"][:15]:
                add_action(bm, (b["title"] or b["url"])[:50], lambda u=b["url"]: self.open_url(u))
        add_action(m, "History", lambda: self.open_internal("history"), "Ctrl+H")
        add_action(m, "Downloads", lambda: self.open_internal("downloads"), "Ctrl+J")
        m.addSeparator()
        add_action(m, "Find in page\u2026", self.open_find, "Ctrl+F")
        add_action(m, "Print\u2026", self.print_page, "Ctrl+P")
        add_action(m, "Save page as\u2026", self.save_page, "Ctrl+S")
        tools = style_popup(m.addMenu("More tools"))
        add_action(tools, "Reader mode", self.reader_mode, "Ctrl+Alt+R")
        add_action(tools, "Zen mode", self.toggle_zen, "Ctrl+Shift+Z")
        add_action(tools, "Take screenshot", self.screenshot, "Ctrl+Shift+S")
        add_action(tools, "Copy link without tracking", self.copy_clean_url)
        tools.addSeparator()
        add_action(tools, "Developer tools", lambda: self.open_devtools(self.current_view()), "F12")
        add_action(tools, "View page source", self.view_source, "Ctrl+U")
        add_action(tools, "Save page as PDF\u2026", self.save_pdf)
        v = self.current_view()
        if v:
            add_action(tools, "Unmute tab" if v.page().isAudioMuted() else "Mute tab", self.toggle_mute)
        tools.addSeparator()
        add_action(tools, "Clear browsing data\u2026", lambda: self.open_internal("settings/privacy"), "Ctrl+Shift+Del")
        m.addSeparator()
        add_action(m, "Settings", lambda: self.open_internal("settings"), "Ctrl+,")
        add_action(m, f"About {APP_NAME}", lambda: self.open_internal("settings/about"))
        m.addSeparator()
        add_action(m, "Exit", self.app.quit_all)
        m.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomRight()) - QPoint(m.sizeHint().width(), -2))

    def show_profile_menu(self) -> None:
        m = self.make_menu()
        head = QAction(f"Signed in as {self.store['name']}" if not self.private else "Private window", m)
        head.setEnabled(False)
        m.addAction(head)
        m.addSeparator()
        for s in self.app.list_profiles():
            add_action(m, s["name"], lambda pid=s.id: self.app.open_profile(pid), checkable=True,
                       checked=(s.id == self.store.id))
        m.addSeparator()
        add_action(m, "Add profile\u2026", self.app.add_profile)
        add_action(m, "Manage profile", lambda: self.open_internal("settings/profile"))
        m.exec(self.profile_btn.mapToGlobal(QPoint(self.profile_btn.width() - m.sizeHint().width(),
                                                    self.profile_btn.height() + 2)))

    def tab_context_menu(self, pos) -> None:
        i = self.tabbar.tabAt(pos)
        item = self.tab_items[i] if 0 <= i < len(self.tab_items) else None
        m = self.make_menu()
        if isinstance(item, ChipItem):
            gid, g = item.gid, self.groups.get(item.gid, {})
            add_action(m, "Rename or recolor group\u2026", lambda: self.edit_group(gid))
            add_action(m, "Expand group" if g.get("collapsed") else "Collapse group", lambda: self.toggle_collapse(gid))
            add_action(m, "New tab in group", lambda: self.add_tab(None, group=gid))
            add_action(m, "Copy all addresses", lambda: self._copy("\n".join(v.url().toString() for v in self.group_views(gid)),
                                                                     "Copied the group's addresses"))
            m.addSeparator()
            add_action(m, "Ungroup", lambda: self.ungroup(gid))
            add_action(m, "Close group", lambda: self.close_group(gid))
            m.exec(self.tabbar.mapToGlobal(pos))
            return
        add_action(m, "New tab", self.new_tab)
        if isinstance(item, WebView):
            v = item
            m.addSeparator()
            add_action(m, "Reload", lambda: v.reload())
            add_action(m, "Duplicate", lambda: self.add_tab(v.url().toString(), after_current=True))
            add_action(m, "Unpin tab" if v.pinned else "Pin tab", lambda: self.set_pinned(v, not v.pinned))
            add_action(m, "Unmute tab" if v.page().isAudioMuted() else "Mute tab",
                       lambda: (v.page().setAudioMuted(not v.page().isAudioMuted()), self._refresh_tab_label(v)))
            if self.can_sleep(v, True) or v.sleeping:
                add_action(m, "Wake tab" if v.sleeping else "Sleep tab",
                           lambda: self.wake_view(v) if v.sleeping else self.sleep_view(v, force=True))
            m.addSeparator()
            if len(self.selected) >= 2 and v in self.selected:
                add_action(m, f"Group {len(self.selected)} selected tabs\u2026", self.group_selected)
            else:
                sub = style_popup(m.addMenu("Add to group"))
                for gid, g in self.groups.items():
                    add_action(sub, g["name"] or "Unnamed group", lambda gid=gid: self.add_to_group(v, gid),
                               checkable=True, checked=(v.group == gid), enabled=not v.pinned)
                if self.groups:
                    sub.addSeparator()
                add_action(sub, "New group\u2026", lambda: self._group_dialog([v]), enabled=not v.pinned)
                if v.group:
                    add_action(m, "Remove from group", lambda: self.remove_from_group(v))
            m.addSeparator()
            add_action(m, "Close tab", lambda: self.close_tab(self.index_of(v)))
            add_action(m, "Close other tabs", lambda: self._close_others(v))
            add_action(m, "Close tabs to the right", lambda: self._close_right(v))
        add_action(m, "Reopen closed tab", self.reopen_tab, "Ctrl+Shift+T", enabled=bool(self.closed_tabs))
        m.exec(self.tabbar.mapToGlobal(pos))

    def _close_others(self, keep: WebView) -> None:
        for v in self.tab_views():
            if v is not keep and not v.pinned:
                self.close_tab(self.index_of(v))

    def _close_right(self, ref: WebView) -> None:
        start = self.index_of(ref) + 1
        for x in list(self.tab_items[start:]):
            if isinstance(x, WebView) and not x.pinned:
                self.close_tab(self.index_of(x))

    def show_context_menu(self, view: WebView, gpos) -> None:
        d = view.lastContextMenuRequest()
        page = view.page()
        WA = QWebEnginePage.WebAction
        MT = QWebEngineContextMenuRequest.MediaType
        trig = lambda a: (lambda: page.triggerAction(a))
        m = self.make_menu(view)
        link = d.linkUrl()
        has_link = link.isValid() and not link.isEmpty()
        media = d.mediaType()
        selected = d.selectedText().strip()
        editable = d.isContentEditable()
        sections = 0

        def sep():
            nonlocal sections
            if sections:
                m.addSeparator()
            sections += 1

        if has_link:
            sep()
            add_action(m, "Open link in new tab", lambda: self.add_tab(link.toString(), after_current=True))
            add_action(m, "Open link in new window", lambda: self.app.open_window(self.store, urls=[link.toString()]))
            add_action(m, "Open link in private window",
                       lambda: self.app.open_window(self.store, private=True, urls=[link.toString()]))
            add_action(m, "Copy link address", lambda: QApplication.clipboard().setText(link.toString()))
            add_action(m, "Copy link without tracking", lambda: self._copy(strip_tracking(link.toString()), "Copied clean link"))
            add_action(m, "Save link as\u2026", trig(WA.DownloadLinkToDisk))
        if media == MT.MediaTypeImage:
            sep()
            add_action(m, "Open image in new tab", lambda: self.add_tab(d.mediaUrl().toString(), after_current=True))
            add_action(m, "Save image as\u2026", trig(WA.DownloadImageToDisk))
            add_action(m, "Copy image", trig(WA.CopyImageToClipboard))
            add_action(m, "Copy image address", trig(WA.CopyImageUrlToClipboard))
        elif media in (MT.MediaTypeVideo, MT.MediaTypeAudio):
            sep()
            kind = "video" if media == MT.MediaTypeVideo else "audio"
            add_action(m, f"Open {kind} in new tab", lambda: self.add_tab(d.mediaUrl().toString(), after_current=True))
            add_action(m, f"Save {kind} as\u2026", trig(WA.DownloadMediaToDisk))
            add_action(m, f"Copy {kind} address", trig(WA.CopyMediaUrlToClipboard))
        if editable:
            sep()
            add_action(m, "Undo", trig(WA.Undo), "Ctrl+Z")
            add_action(m, "Redo", trig(WA.Redo), "Ctrl+Shift+Z")
            m.addSeparator()
            add_action(m, "Cut", trig(WA.Cut), "Ctrl+X", enabled=bool(selected))
            add_action(m, "Copy", trig(WA.Copy), "Ctrl+C", enabled=bool(selected))
            add_action(m, "Paste", trig(WA.Paste), "Ctrl+V")
            add_action(m, "Paste as plain text", trig(WA.PasteAndMatchStyle), "Ctrl+Shift+V")
            add_action(m, "Select all", trig(WA.SelectAll), "Ctrl+A")
        elif selected:
            sep()
            add_action(m, "Copy", trig(WA.Copy), "Ctrl+C")
            label = selected if len(selected) <= 28 else selected[:27] + "\u2026"
            eng = ENGINE_BY_ID.get(self.store["search_engine"], ENGINES[0])[1]
            add_action(m, f"Search {eng} for \u201c{label}\u201d",
                       lambda: self.add_tab(self.store.search_template.replace("%s", quote_plus(selected)),
                                            after_current=True))
        if not (has_link or media != MT.MediaTypeNone or editable or selected):
            sep()
            h = view.history()
            add_action(m, "Back", self.go_back, "Alt+Left", enabled=h.canGoBack())
            add_action(m, "Forward", self.go_forward, "Alt+Right", enabled=h.canGoForward())
            add_action(m, "Reload", lambda: view.reload(), "Ctrl+R")
            m.addSeparator()
            add_action(m, "Save as\u2026", self.save_page, "Ctrl+S")
            add_action(m, "Print\u2026", self.print_page, "Ctrl+P")
            if view.url().scheme() in ("http", "https", "file"):
                add_action(m, "Remove bookmark" if self.is_bookmarked(view.url().toString()) else "Bookmark this page",
                           self.toggle_bookmark, "Ctrl+D")
            add_action(m, "Select all", trig(WA.SelectAll), "Ctrl+A")
        sep()
        add_action(m, "Reader mode", self.reader_mode, "Ctrl+Alt+R")
        add_action(m, "View page source", self.view_source, "Ctrl+U")
        add_action(m, "Inspect", lambda: self.open_devtools(view, inspect=True), "Ctrl+Shift+I")
        m.exec(gpos)

    # ── page tools ──────────────────────────────────────────────────────────
    def view_source(self) -> None:
        v = self.current_view()
        if v and v.url().isValid():
            self.add_tab("view-source:" + v.url().toString(), after_current=True)


    # ── tab bar information ────────────────────────────────────────────────
    def tab_info(self, i: int) -> dict:
        item = self.tab_items[i] if 0 <= i < len(self.tab_items) else None
        t = self.theme()
        if isinstance(item, ChipItem):
            g = self.groups.get(item.gid, {})
            n = sum(1 for v in self.tab_views() if v.group == item.gid)
            label = g.get("name") or "Group"
            col = g.get("color", "#8ab4f8")
            return {"kind": "chip", "color": col, "fg": t["text"], "label": label, "count": n}
        if isinstance(item, WebView):
            col = self.groups[item.group]["color"] if item.group in self.groups else None
            return {"kind": "tab", "color": col,
                    "selected": item in self.selected, "accent": t["accent"]}
        return {}

    @staticmethod
    def _item_group(item):
        if isinstance(item, ChipItem):
            return item.gid
        return item.group if isinstance(item, WebView) else None

    def chip_index(self, gid: str) -> int:
        for i, x in enumerate(self.tab_items):
            if isinstance(x, ChipItem) and x.gid == gid:
                return i
        return -1

    def group_views(self, gid: str) -> list:
        return [v for v in self.tab_views() if v.group == gid]

    def _groups_changed(self) -> None:
        self.tabbar.relayout()
        self.sidebar.work.refresh()

    # ── tab groups ──────────────────────────────────────────────────────────
    def _group_insert_index(self, gid: str, idx: int) -> int:
        c = self.chip_index(gid)
        if c < 0:
            return idx
        members = [self.index_of(v) for v in self.group_views(gid)]
        last = max(members) if members else c
        return max(c + 1, min(idx, last + 1))

    def _insert_chip(self, gid: str, index: int) -> None:
        self._moving = True
        self._key_seq += 1
        self.tab_items.insert(index, ChipItem(gid))
        self.tabbar.insertTab(index, "")
        self.tabbar.setTabData(index, {"key": self._key_seq, "pinned": False, "chip": gid})
        self.tabbar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        self.tabbar.setTabToolTip(index, "Click to collapse or expand. Right-click for more.")
        self._moving = False

    def _remove_chip(self, gid: str) -> None:
        i = self.chip_index(gid)
        if i >= 0:
            self._moving = True
            self.tab_items.pop(i)
            self.tabbar.removeTab(i)
            self._moving = False

    def _drop_empty_groups(self) -> None:
        used = {v.group for v in self.tab_views() if v.group}
        for gid in [g for g in self.groups if g not in used]:
            self._remove_chip(gid)
            self.groups.pop(gid, None)

    def create_group(self, views: list, name: str, color: str) -> str:
        chosen = set(views)
        views = [v for v in self.tab_views() if v in chosen and not v.pinned]
        if not views:
            return ""
        for v in views:
            v.group = None
        self._drop_empty_groups()
        gid = uuid.uuid4().hex[:8]
        self.groups[gid] = {"name": name, "color": color, "collapsed": False}
        first = self.index_of(views[0])
        self._insert_chip(gid, first)
        views[0].group = gid
        target = first + 2
        self._moving = True
        for v in views[1:]:
            i = self.index_of(v)
            if i != target:
                self.tabbar.moveTab(i, target)
            v.group = gid
            target += 1
        self._moving = False
        self._groups_changed()
        return gid

    def _group_dialog(self, views: list) -> None:
        color = GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)]
        dlg = GroupDialog(self, "", color)
        if dlg.exec():
            name, col = dlg.values()
            self.create_group(views, name, col)
        self.clear_selection()

    def group_selected(self) -> None:
        views = [v for v in self.tab_views() if v in self.selected and not v.pinned]
        if views:
            self._group_dialog(views)
        else:
            self.group_current()

    def group_current(self) -> None:
        v = self._current
        if v is None:
            return
        if v.pinned:
            self.toast("Unpin this tab first. Pinned tabs can't be grouped")
        elif v.group:
            self.edit_group(v.group)
        else:
            self._group_dialog([v])

    def edit_group(self, gid: str) -> None:
        g = self.groups.get(gid)
        if not g:
            return
        dlg = GroupDialog(self, g["name"], g["color"], "Edit tab group")
        if dlg.exec():
            g["name"], g["color"] = dlg.values()
            self._groups_changed()

    def ungroup(self, gid: str) -> None:
        for v in self.group_views(gid):
            v.group = None
        self._drop_empty_groups()
        self._groups_changed()

    def close_group(self, gid: str) -> None:
        views = self.group_views(gid)
        if len(views) >= len(self.tab_views()):
            self.toast("That's every open tab. Close the window instead")
            return
        for v in views:
            self.close_tab(self.index_of(v))

    def toggle_collapse(self, gid: str) -> None:
        g = self.groups.get(gid)
        if g:
            g["collapsed"] = not g["collapsed"]
            self._apply_collapse(gid)

    def _apply_collapse(self, gid: str) -> None:
        g = self.groups.get(gid)
        if not g:
            return
        col = bool(g["collapsed"])
        cur_hidden = False
        for i, x in enumerate(self.tab_items):
            if isinstance(x, WebView) and x.group == gid:
                self.tabbar.setTabVisible(i, not col)
                cur_hidden = cur_hidden or (col and x is self._current)
        if cur_hidden and not self._select_outside(gid):
            g["collapsed"] = False
            for i, x in enumerate(self.tab_items):
                if isinstance(x, WebView) and x.group == gid:
                    self.tabbar.setTabVisible(i, True)
            self.toast("This group has the only open tab, so it stays expanded")
        self._groups_changed()

    def _select_outside(self, gid: str) -> bool:
        c = self.chip_index(gid)
        n = len(self.tab_items)
        for step in range(1, n + 1):
            for j in (c + step, c - step):
                if 0 <= j < n:
                    x = self.tab_items[j]
                    if isinstance(x, WebView) and x.group != gid and self.tabbar.isTabVisible(j):
                        self.tabbar.setCurrentIndex(j)
                        return True
        return False

    def focus_group(self, gid: str) -> None:
        g = self.groups.get(gid)
        views = self.group_views(gid)
        if g and views:
            if g["collapsed"]:
                g["collapsed"] = False
                self._apply_collapse(gid)
            self.select_view(views[0])

    def select_view(self, v) -> None:
        i = self.index_of(v)
        if i < 0:
            return
        if v.group in self.groups and self.groups[v.group]["collapsed"]:
            self.groups[v.group]["collapsed"] = False
            self._apply_collapse(v.group)
        self.tabbar.setCurrentIndex(i)

    def add_to_group(self, view: WebView, gid: str) -> None:
        if view.pinned or gid not in self.groups or view.group == gid:
            return
        old = view.group
        view.group = gid
        i = self.index_of(view)
        last = max(self.index_of(v) for v in self.group_views(gid) if v is not view) if len(self.group_views(gid)) > 1 else self.chip_index(gid)
        self._moving = True
        self.tabbar.moveTab(i, last if i < last else last + 1)
        self._moving = False
        if old:
            self._drop_empty_groups()
        self.groups[gid]["collapsed"] = False
        self._apply_collapse(gid)

    def remove_from_group(self, view: WebView) -> None:
        gid = view.group
        if not gid:
            return
        view.group = None
        others = [self.index_of(v) for v in self.group_views(gid)]
        if others:
            dest, i = max(others), self.index_of(view)
            self._moving = True
            self.tabbar.moveTab(i, dest if i < dest else dest + 1)
            self._moving = False
        self._drop_empty_groups()
        self._groups_changed()

    def _infer_group(self, view: WebView) -> None:
        """After a drag: a tab dropped inside a group joins it; dragged past either end it leaves."""
        i = self.index_of(view)
        new = None
        for gid in self.groups:
            c = self.chip_index(gid)
            others = [self.index_of(v) for v in self.group_views(gid) if v is not view]
            if c < 0:
                continue
            if not others:
                if view.group == gid and i > c:
                    new = gid
                    break
                continue
            last = max(others)
            if view.group == gid and c < i <= last + 1:
                new = gid
                break
            if view.group != gid and c < i < last:
                new = gid
                break
        if new != view.group:
            view.group = new
            if new:
                self.groups[new]["collapsed"] = False
                self._apply_collapse(new)
            self._drop_empty_groups()
        self._groups_changed()

    # ── multi-select ────────────────────────────────────────────────────────
    def tab_mod_click(self, i: int, mods) -> None:
        item = self.tab_items[i] if 0 <= i < len(self.tab_items) else None
        if not isinstance(item, WebView):
            return
        if not self.selected and self._current is not None:
            self.selected.add(self._current)
            self._anchor = self._current
        if (mods & Qt.KeyboardModifier.ShiftModifier) and self._anchor is not None:
            a, b = sorted((self.index_of(self._anchor), i))
            for j in range(a, b + 1):
                x = self.tab_items[j]
                if isinstance(x, WebView) and self.tabbar.isTabVisible(j):
                    self.selected.add(x)
        else:
            if item in self.selected:
                self.selected.discard(item)
            else:
                self.selected.add(item)
            self._anchor = item
        self.update_selbar()

    def update_selbar(self) -> None:
        n = len(self.selected)
        if n >= 2:
            self.sel_label.setText(f"{n} tabs selected")
            self.selbar.show()
        else:
            self.selected.clear()
            self.selbar.hide()
        self._update_tab_width()
        self.tabbar.update()

    def _update_tab_width(self) -> None:
        extra = self.selbar.sizeHint().width() if self.selbar.isVisible() else 0
        self.tabbar.available = max(200, self.width() - 160 - extra)
        self.tabbar.relayout()

    def clear_selection(self) -> None:
        if self.selected:
            self.selected.clear()
            self._anchor = None
            self.update_selbar()

    def close_selected(self) -> None:
        views = [v for v in self.tab_views() if v in self.selected]
        if len(views) >= len(self.tab_views()):
            self.toast("That's every open tab. Close the window instead")
            return
        self.clear_selection()
        for v in views:
            self.close_tab(self.index_of(v))

    # ── sleeping tabs ───────────────────────────────────────────────────────
    def can_sleep(self, v: WebView, aggressive: bool = False) -> bool:
        try:
            if v.sleeping or v.loading or v.closing or self.is_visible_view(v):
                return False
            if v.pinned and not aggressive:
                return False
            u = v.url()
            if not u.isValid() or u.isEmpty() or u.scheme() == SCHEME:
                return False
            return not v.page().recentlyAudible()
        except RuntimeError:
            return False

    def sleep_view(self, v: WebView, force: bool = False) -> None:
        if v.sleeping:
            return
        if self.is_visible_view(v):
            if force:
                self.toast("A tab that's on screen can't sleep")
            return
        if not force and not self.can_sleep(v, True):
            return
        v.sleep_url = v.url()
        try:
            v.page().setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
        except Exception:
            return
        v.sleeping = True
        self._refresh_tab_label(v)

    def wake_view(self, v: WebView) -> None:
        if not v.sleeping:
            return
        v.sleeping = False
        v.last_active = time.time()
        v.protect_until = time.time() + 90
        try:
            v.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except Exception:
            pass
        u = v.sleep_url
        if u is not None and u.isValid():
            QTimer.singleShot(900, lambda: self._ensure_loaded(v, u))
        self._refresh_tab_label(v)

    @staticmethod
    def _ensure_loaded(v: WebView, u: QUrl) -> None:
        try:
            if v.url().isEmpty() or v.url().toString() == "about:blank":
                v.load(u)
        except RuntimeError:
            pass

    def sleep_current_tab(self) -> None:
        v = self._current
        if v is None:
            return
        others = [x for x in self.tab_views() if x is not v and not x.closing]
        if not others:
            self.toast("This is the only tab, so it stays awake")
            return
        self.select_view(others[0] if self.index_of(others[0]) > self.index_of(v) else others[-1])
        self.sleep_view(v, force=True)

    # ── sessions and workspaces ─────────────────────────────────────────────
    def snapshot(self) -> dict:
        tabs = []
        for v in self.tab_views():
            url = v.pending_url or (v.sleep_url.toString() if v.sleeping and v.sleep_url else v.url().toString())
            if not url or url.rstrip("/") == NEWTAB or url == "about:blank":
                continue
            tabs.append({"url": url, "title": v.page_title, "pinned": v.pinned, "group": v.group})
        used = {t["group"] for t in tabs if t["group"]}
        groups = {g: dict(self.groups[g]) for g in used if g in self.groups}
        return {"tabs": tabs, "groups": groups}

    def restore_tabs(self, items: list, groups: dict, lazy: bool = True) -> list:
        views, gmap = [], {}
        for it in items:
            if not isinstance(it, dict) or not it.get("url"):
                views.append(None)
                continue
            gid, ng = it.get("group"), None
            if gid and gid in groups:
                if gid not in gmap:
                    g = groups[gid]
                    ng = uuid.uuid4().hex[:8]
                    self.groups[ng] = {"name": str(g.get("name", ""))[:24],
                                       "color": g.get("color") if g.get("color") in GROUP_COLORS else GROUP_COLORS[0],
                                       "collapsed": False}
                    gmap[gid] = ng
                    self._insert_chip(ng, len(self.tab_items))
                ng = gmap[gid]
            views.append(self.add_tab(it["url"], background=True, pinned=bool(it.get("pinned")), group=ng,
                                      lazy=lazy, lazy_title=it.get("title")))
        for gid, g in groups.items():
            if g.get("collapsed") and gid in gmap:
                self.groups[gmap[gid]]["collapsed"] = True
                self._apply_collapse(gmap[gid])
        return views

    def restore_session(self, session: list, groups: dict) -> None:
        views = self.restore_tabs(session, groups, lazy=bool(self.store["lazy_restore"]))
        first = next((v for v in views if v is not None), None)
        if first is None:
            self.add_tab(None)
        else:
            self.tabbar.setCurrentIndex(self.index_of(first))

    def save_workspace(self) -> None:
        snap = self.snapshot()
        if not snap["tabs"]:
            self.toast("Open a few pages first")
            return
        dlg = FormDialog(self, "Save workspace", [("Name", "", "Research sprint")], "Save")
        if dlg.exec():
            name = dlg.values()[0] or time.strftime("Workspace %d %b %H:%M")
            self.store["workspaces"].append({"name": name[:40], **snap})
            self.store.save()
            self.sidebar.work.refresh()
            self.toast(f"Saved \u201c{name[:40]}\u201d")

    def restore_workspace(self, r: int) -> None:
        if not (0 <= r < len(self.store["workspaces"])):
            return
        w = self.store["workspaces"][r]
        views = self.restore_tabs(w["tabs"], w.get("groups", {}), lazy=True)
        first = next((v for v in views if v is not None), None)
        if first is not None:
            self.tabbar.setCurrentIndex(self.index_of(first))
        self.toast(f"Opened \u201c{w['name']}\u201d")

    def delete_workspace(self, r: int) -> None:
        if 0 <= r < len(self.store["workspaces"]):
            del self.store["workspaces"][r]
            self.store.save()
            self.sidebar.work.refresh()

    # ── command palette ─────────────────────────────────────────────────────
    def open_palette(self) -> None:
        if self._palette is None:
            self._palette = CommandPalette(self)
        self._palette.open_palette()

    def open_sidebar_panel(self, key: str) -> None:
        if key not in self.sidebar.enabled:
            self.sidebar.customize()
            return
        if not (self.sidebar.is_open and self.sidebar.current == key):
            self.sidebar.show_panel(key)

    def palette_entries(self) -> list:
        def cmd(title, sub, fn, extra=""):
            return {"title": title, "sub": sub, "fn": fn, "hay": f"{title} {sub} {extra}".lower(), "cmd": True}
        v = self._current
        cmds = [
            cmd("New tab", "Ctrl+T", self.new_tab), cmd("New window", "Ctrl+N", lambda: self.app.open_window(self.store)),
            cmd("New private window", "Ctrl+Shift+N", lambda: self.app.open_window(self.store, private=True), "incognito"),
            cmd("Group this tab", "Ctrl+Shift+G", self.group_current, "tab group collection"),
            cmd("Group selected tabs", "Ctrl+click tabs to select several", self.group_selected),
            cmd("Save workspace", "Remember these tabs and groups", self.save_workspace, "session"),
            cmd("Toggle sidebar", "Ctrl+B", self.sidebar.toggle),
            cmd("Customize sidebar", "Choose panels and change their order", self.sidebar.customize),
            cmd("Memory and performance", "Sidebar. RAM limiter", lambda: self.open_sidebar_panel("perf"), "ram limit sleep"),
            cmd("Free memory now", "Sleep tabs you aren't using", lambda: self.sidebar.perf._free(), "ram"),
            cmd("Notes", "Sidebar scratchpad", lambda: self.open_sidebar_panel("notes")),
            cmd("Web panels", "Sidebar. Pinned sites", lambda: self.open_sidebar_panel("web")),
            cmd("Music player", "Sidebar. YouTube Music with a pinnable mini player", lambda: self.open_sidebar_panel("music"), "youtube song"),
            cmd("AI companion", "Choose Claude, Gemini or ChatGPT", lambda: self.open_sidebar_panel("ai"), "assistant chat"),
            cmd("Workspace panel", "Sidebar. Groups and saved workspaces", lambda: self.open_sidebar_panel("work")),
            cmd("Reader mode", "Ctrl+Alt+R", self.reader_mode, "clean article"),
            cmd("Zen mode", "Ctrl+Shift+Z. Keep tabs and a full-width search bar", self.toggle_zen, "focus distraction free"),
            cmd("Take screenshot", "Ctrl+Shift+S. Saved and copied", self.screenshot),
            cmd("Copy link without tracking", "Strips utm_ and click IDs", self.copy_clean_url),
            cmd("Sleep this tab", "Free its memory", self.sleep_current_tab),
            cmd("Bookmark this page", "Ctrl+D", self.toggle_bookmark), cmd("History", "Ctrl+H", lambda: self.open_internal("history")),
            cmd("Downloads", "Ctrl+J", lambda: self.open_internal("downloads")),
            cmd("Bookmarks", "Ctrl+Shift+O", lambda: self.open_internal("bookmarks")),
            cmd("Settings", "Ctrl+,", lambda: self.open_internal("settings")),
            cmd("Extensions", "Install and manage", lambda: self.open_internal("extensions"), "chrome addon"),
            cmd("Clear browsing data", "Ctrl+Shift+Del", lambda: self.open_internal("settings/privacy"), "cookies cache"),
            cmd("Developer tools", "F12", lambda: self.open_devtools(self.current_view()), "inspect"),
            cmd("View page source", "Ctrl+U", self.view_source), cmd("Find in page", "Ctrl+F", self.open_find),
            cmd("Print", "Ctrl+P", self.print_page), cmd("Full screen", "F11", self.toggle_fullscreen),
            cmd("Reload", "Ctrl+R", lambda: v and v.reload()), cmd("Reopen closed tab", "Ctrl+Shift+T", self.reopen_tab),
            cmd("Show or hide bookmarks bar", "Ctrl+Shift+B", self.toggle_bookmarks_bar),
            cmd("Mute or unmute tab", "", self.toggle_mute), cmd("Pin or unpin tab", "", lambda: v and self.set_pinned(v, not v.pinned)),
            cmd("Duplicate tab", "", lambda: v and self.add_tab(v.url().toString(), after_current=True)),
        ]
        for key, t in THEMES.items():
            cmds.append(cmd(f"Theme: {t['label']}", f"{t['kind'].capitalize()} theme",
                            lambda k=key: self.app.apply_setting(self.store, "theme", k), "colour color appearance"))
        out = cmds
        for tv in self.tab_views():
            title = tv.page_title or tv.url().host() or "New tab"
            out.append({"title": f"Switch to {title}", "sub": tv.pending_url or tv.url().toString(),
                        "fn": lambda x=tv: self.select_view(x), "hay": f"{title} {tv.url().toString()} tab".lower()})
        for b in self.store["bookmarks"][:300]:
            out.append({"title": b["title"] or b["url"], "sub": "Bookmark  " + b["url"], "fn": lambda u=b["url"]: self.open_url(u),
                        "hay": f"{b['title']} {b['url']} bookmark".lower()})
        for h in self.store["history"][:150]:
            out.append({"title": h["title"] or h["url"], "sub": "History  " + h["url"], "fn": lambda u=h["url"]: self.open_url(u),
                        "hay": f"{h['title']} {h['url']} history".lower()})
        return out

    def palette_query_entries(self, text: str) -> list:
        eng = ENGINE_BY_ID.get(self.store["search_engine"], ENGINES[0])[1]
        out = []
        url = smart_url(text, self.store.search_template)
        if not url.toString().startswith(self.store.search_template.split("%s")[0]) or " " not in text and "." in text:
            out.append({"title": f"Go to {text}", "sub": url.toString(), "fn": lambda u=text: self.open_url(smart_url(u, self.store.search_template).toString()),
                        "hay": ""})
        out.append({"title": f"Search {eng} for \u201c{text}\u201d", "sub": "Opens in a new tab",
                    "fn": lambda q=text: self.open_url(self.store.search_template.replace("%s", quote_plus(q))), "hay": ""})
        return out

    # ── page tools ──────────────────────────────────────────────────────────
    def _copy(self, text: str, msg: str) -> None:
        QApplication.clipboard().setText(text)
        self.toast(msg)

    def copy_clean_url(self) -> None:
        v = self._current
        if v is not None:
            self._copy(strip_tracking(v.url().toString()), "Copied link without tracking")

    def reader_mode(self) -> None:
        v = self._current
        if v is None or v.url().scheme() not in ("http", "https"):
            self.toast("Reader mode works on web pages")
            return
        t = self.theme()
        js = (READER_JS.replace("__BG__", t["bg"]).replace("__FG__", t["text"]).replace("__SUB__", t["sub"])
              .replace("__ACC__", t["accent"]))
        v.page().runJavaScript(js)

    def screenshot(self) -> None:
        v = self._current
        if v is None:
            return
        pm = v.grab()
        if pm.isNull():
            self.toast("Couldn't capture this page")
            return
        folder = Path(self.store["download_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("AwesomeBrowse %Y-%m-%d %H.%M.%S.png")
        pm.save(str(path))
        QApplication.clipboard().setPixmap(pm)
        self.toast("Screenshot saved and copied")

    # ── extensions ──────────────────────────────────────────────────────────
    def refresh_extension_button(self) -> None:
        self.ext_btn.setVisible(self.ctx.extensions is not None and self.edition() != "legacy"
                                and not self._focus_mode and not self._fs)

    def show_extensions_menu(self) -> None:
        m = self.make_menu()
        ext = self.ctx.extensions
        if ext is None:
            add_action(m, "Extensions are off in private windows", enabled=False)
        else:
            recs = ext.records()
            if not recs:
                add_action(m, "No extensions installed yet", enabled=False)
            for r in recs:
                sub = style_popup(m.addMenu(r["name"] + ("" if r["enabled"] else " (off)")))
                if r["popup"] and r["enabled"]:
                    add_action(sub, "Open popup", lambda r=r: self.open_ext_popup(r))
                if r["options"]:
                    add_action(sub, "Options", lambda r=r: self.open_url(f"{SCHEME}://ext/{r['id']}/{r['options']}"))
                add_action(sub, "Turn off" if r["enabled"] else "Turn on",
                           lambda r=r: (ext.set_enabled(r["id"], not r["enabled"]), self.toast("Reload open tabs to apply the change")))
                add_action(sub, "Remove", lambda r=r: self._remove_ext(r))
            m.addSeparator()
            add_action(m, "Manage extensions", lambda: self.open_internal("extensions"))
        m.exec(self.ext_btn.mapToGlobal(QPoint(0, self.ext_btn.height() + 2)))

    def _remove_ext(self, rec: dict) -> None:
        if QMessageBox.question(self, "Remove extension", f"Remove {rec['name']}?") == QMessageBox.StandardButton.Yes:
            self.ctx.extensions.remove(rec["id"])
            self.app.extensions_changed(self.store, f"Removed {rec['name']}")

    def open_ext_popup(self, rec: dict) -> None:
        self._popup = ExtPopup(self, rec)
        self._popup.move(self.ext_btn.mapToGlobal(QPoint(self.ext_btn.width() - 400, self.ext_btn.height() + 4)))
        self._popup.show()

    def open_devtools(self, view: WebView | None, inspect: bool = False) -> None:
        if view is None:
            return
        old = self._dev_page
        dev_page = QWebEnginePage(self.ctx.profile, self.devview)
        self.devview.setPage(dev_page)
        self._dev_page = dev_page
        if old is not None:
            old.deleteLater()
        self._dev_target = view
        view.page().setDevToolsPage(dev_page)
        self.devdock.show()
        view.page().triggerAction(QWebEnginePage.WebAction.InspectElement)

    def _dev_visibility(self, visible: bool) -> None:
        if not visible and self._dev_target is not None:
            try:
                self._dev_target.page().setDevToolsPage(None)
            except (RuntimeError, TypeError):
                pass
            self._dev_target = None

    def open_find(self) -> None:
        self.findbar.show()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def close_find(self) -> None:
        if not self.findbar.isVisible():
            return
        self.findbar.hide()
        v = self.current_view()
        if v:
            v.findText("")
            v.setFocus()
        self.find_count.setText("")

    def do_find(self, forward: bool) -> None:
        v = self.current_view()
        if not v:
            return
        text = self.find_input.text()
        if not text:
            v.findText("")
            self.find_count.setText("")
            return
        flags = QWebEnginePage.FindFlag(0) if forward else QWebEnginePage.FindFlag.FindBackward
        v.findText(text, flags)

    def _find_result(self, view: WebView, result) -> None:
        if view is self.current_view() and self.find_input.text():
            n = result.numberOfMatches()
            self.find_count.setText(f"{result.activeMatchOrdinal()} of {n}" if n else "No matches")

    def print_page(self) -> None:
        v = self.current_view()
        if not v:
            return
        self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._printer.setResolution(300)
        self._printer.setDocName(v.page_title or "Web page")
        self._print_view = v
        preview = PrintPreviewDialog(self, self._printer, v.page_title or "Web page")
        try:
            preview.exec()
        finally:
            self._print_view = None
            self._printer = None

    def _print_document(self, printer) -> bool:
        view = self._print_view
        if not view:
            return False
        loop = QEventLoop(self)
        self._print_loop = loop
        self._print_result = None
        view.printFinished.connect(self._print_finished)
        view.print(printer)
        if self._print_result is None:
            loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        try:
            view.printFinished.disconnect(self._print_finished)
        except TypeError:
            pass
        result = self._print_result
        self._print_loop = None
        self._print_result = None
        if result is False:
            painter = QPainter()
            if painter.begin(printer):
                painter.drawText(QPointF(24, 40), "Could not generate the print preview.")
                painter.end()
            self.toast("Could not render the print preview")
        return result is True

    def _print_finished(self, success: bool) -> None:
        self._print_result = bool(success)
        if self._print_loop is not None:
            self._print_loop.quit()

    def save_pdf(self) -> None:
        v = self.current_view()
        if not v:
            return
        name = re.sub(r'[\\/:*?"<>|]+', "_", v.title() or "page") + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save as PDF", os.path.join(self.store["download_dir"], name),
                                              "PDF (*.pdf)")
        if path:
            def finished(filename, ok):
                try:
                    v.pdfPrintingFinished.disconnect(finished)
                except TypeError:
                    pass
                self.toast(f"Saved PDF: {os.path.basename(filename)}" if ok else "Saving PDF failed")
            v.pdfPrintingFinished.connect(finished)
            v.printToPdf(path)

    def save_page(self) -> None:
        v = self.current_view()
        if not v:
            return
        name = re.sub(r'[\\/:*?"<>|]+', "_", v.title() or "page") + ".html"
        path, _ = QFileDialog.getSaveFileName(self, "Save page as", os.path.join(self.store["download_dir"], name),
                                              "Web page, complete (*.html)")
        if path:
            v.page().save(path, QWebEngineDownloadRequest.SavePageFormat.CompleteHtmlSaveFormat)

    def toggle_mute(self) -> None:
        v = self.current_view()
        if v:
            v.page().setAudioMuted(not v.page().isAudioMuted())
            self._refresh_tab_label(v)

    def _download_done(self, uid: str) -> None:
        rec = self.ctx.downloads.find(uid)
        if rec and rec["state"] == "done":
            self.toast(f"Downloaded {rec['name']}")

    def toggle_downloads_popup(self) -> None:
        self.download_popup.toggle()

    def _downloads_changed(self) -> None:
        popup = self.download_popup
        popup.refresh()
        active = any(r.get("state") == "progress" for r in self.ctx.downloads.records())
        if self._fs or self._focus_mode:
            popup.dismissed_active = active
            return
        if active:
            popup.hide_timer.stop()
            if not popup.isVisible() and not popup.dismissed_active:
                popup.show_for_activity()
        else:
            popup.dismissed_active = False
            if popup.isVisible() and popup.auto_hide:
                popup.hide_timer.start(3600)

    def show_web_notification(self, notification: QWebEngineNotification) -> None:
        popup = SiteNotificationPopup(self.centralWidget(), notification, self._remove_site_notification,
                                      animate=self.anim_on())
        self._site_notifications.append(popup)
        popup.show_notification()
        self._position_site_notifications()

    def _remove_site_notification(self, popup: SiteNotificationPopup) -> None:
        if popup in self._site_notifications:
            self._site_notifications.remove(popup)
        self._position_site_notifications()

    def _position_site_notifications(self) -> None:
        parent = self.centralWidget()
        if parent is None:
            return
        visible = [n for n in self._site_notifications if n.isVisible()]
        for index, popup in enumerate(visible):
            x = max(12, parent.width() - popup.width() - 18)
            y = max(12, parent.height() - popup.height() - 18 - index * (popup.height() + 10))
            popup.move(x, y)
            popup.raise_()

    # ── zoom ────────────────────────────────────────────────────────────────
    def zoom_set(self, factor: float) -> None:
        v = self.current_view()
        if v:
            v.setZoomFactor(factor)
            host = v.url().host()
            if self.store["zoom_per_site"] and host and v.url().scheme() in ("http", "https"):
                z = self.store["zoom_by_host"]
                if abs(factor - 1.0) < 0.001:
                    z.pop(host, None)
                else:
                    z[host] = factor
                self.store.save()
            self.toast(f"{round(factor * 100)}%")

    def zoom_step(self, direction: int) -> None:
        v = self.current_view()
        if not v:
            return
        cur = v.zoomFactor()
        if direction > 0:
            nxt = next((z for z in ZOOM_STEPS if z > cur + 0.001), ZOOM_STEPS[-1])
        else:
            nxt = next((z for z in reversed(ZOOM_STEPS) if z < cur - 0.001), ZOOM_STEPS[0])
        self.zoom_set(nxt)

    # ── fullscreen ──────────────────────────────────────────────────────────
    def toggle_fullscreen(self) -> None:
        self.set_fullscreen(not self._fs)

    def set_fullscreen(self, on: bool) -> None:
        if on == self._fs:
            return
        self._fs = on
        if on:
            self._was_max = self.isMaximized()
            self.showFullScreen()
        else:
            v = self.current_view()
            exit_action = getattr(QWebEnginePage.WebAction, "ExitFullScreen", None)
            if v and exit_action is not None:
                v.page().triggerAction(exit_action)
            self.showMaximized() if self._was_max else self.showNormal()
        self._apply_chrome_visibility()
        v = self.current_view()
        if v:
            v.setFocus()
        if on:
            self.toast("Press F11 or Esc to exit full screen")

    def _apply_chrome_visibility(self) -> None:
        zen = self._focus_mode and not self._fs
        hidden = self._fs
        self.setProperty("zenMode", zen)
        self.chrome.setVisible(not hidden)
        self.sidebar.setVisible(not hidden and not zen and self.edition() != "legacy")
        self.strip.setProperty("zen", zen)
        self.toolbar.setProperty("zen", zen)
        self.tabbar.setProperty("zen", zen)
        self.address.setProperty("zen", zen)
        for widget in (self.strip, self.toolbar, self.tabbar, self.address):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.tabbar.pill = zen or self.edition() == "stable"
        self.tabbar.h = 36 if zen else (40 if self.edition() == "stable" else 36)
        self.strip.setFixedHeight(44 if zen else (46 if self.edition() == "stable" else 40))
        self.toolbar.setFixedHeight(66 if zen else (54 if self.edition() == "stable" else 48))
        self.address.setFixedHeight(46 if zen else (40 if self.edition() == "stable" else 34))
        self.toolbar.layout().setContentsMargins(20, 8, 20, 8) if zen else self.toolbar.layout().setContentsMargins(10, 0, 10, 0)
        self.plus.setIcon(self.ic("plus", resolve_theme(self.store)["sub"]) if zen else self.ic("plus"))
        self.bmbar.setVisible(not hidden and not zen and bool(self.store["show_bookmarks_bar"]))
        for widget in (self.back_btn, self.fwd_btn, self.reload_btn, self.home_btn,
                       self.ext_btn, self.dl_btn, self.profile_btn, self.menu_btn):
            widget.setVisible(not zen)
        if not zen:
            self.home_btn.setVisible(bool(self.store["show_home_button"]))
            self.refresh_extension_button()
        self.star_action.setVisible(not zen and self.current_view() is not None and
                                     self.current_view().url().scheme() in ("http", "https", "file"))
        self.progress.setVisible(not zen)
        self.update_sidebar_reveal()
        if hidden or zen:
            self.findbar.hide()
            self.mini.hide()
            self.link_label.hide()
            self.toast_label.hide()
            if hasattr(self, "download_popup"):
                self.download_popup.hide()
                self.download_popup.refresh_timer.stop()
                self.download_popup.dismissed_active = any(
                    r.get("state") == "progress" for r in self.ctx.downloads.records())
        if not hidden and not zen:
            self.mini.refresh_visibility()
            if hasattr(self, "download_popup"):
                self.download_popup.dismissed_active = False
                self._downloads_changed()
        self.tabbar.relayout()
        self.esc_fullscreen.setEnabled(hidden or zen)
        if not hidden:
            self.update_toolbar()

    def update_sidebar_reveal(self) -> None:
        if not hasattr(self, "sidebar_reveal") or not hasattr(self, "sidebar_hover_zone"):
            return
        enabled = (not self._fs and not self._focus_mode and self.edition() != "legacy"
                   and not self.sidebar.is_open and not self.store["sidebar_always_visible"])
        zone_h = min(136, max(40, self.viewhost.height() - 24))
        self.sidebar_hover_zone.setGeometry(0, 14, 12, zone_h)
        self.sidebar_hover_zone.setVisible(enabled)
        if not enabled:
            self.sidebar_hide_timer.stop()
            self.sidebar_reveal_animation.stop()
            self.sidebar_reveal.hide()
            self.sidebar_reveal.move(-self.sidebar_reveal.width(), 14)
            return
        if not self.sidebar_reveal.isVisible():
            self.sidebar_reveal.move(-self.sidebar_reveal.width(), 14)
        self.sidebar_hover_zone.raise_()
        self.sidebar_reveal.raise_()

    def _sidebar_hover_changed(self, on: bool) -> None:
        if on:
            self.sidebar_hide_timer.stop()
            if (self._fs or self._focus_mode or self.sidebar.is_open
                    or self.edition() == "legacy" or self.store["sidebar_always_visible"]):
                return
            self.sidebar_reveal_animation.stop()
            y = 16
            self.sidebar_reveal.move(-self.sidebar_reveal.width(), y)
            self.sidebar_reveal.show()
            self.sidebar_hover_zone.raise_()
            self.sidebar_reveal.raise_()
            self.sidebar_reveal_animation.setStartValue(self.sidebar_reveal.pos())
            self.sidebar_reveal_animation.setEndValue(QPoint(8, y))
            self.sidebar_reveal_animation.start()
        else:
            self.sidebar_hide_timer.start()

    def _hide_sidebar_reveal(self) -> None:
        if self.sidebar.is_open or not self.sidebar_reveal.isVisible():
            return
        self.sidebar_reveal_animation.stop()
        self.sidebar_reveal_animation.setStartValue(self.sidebar_reveal.pos())
        self.sidebar_reveal_animation.setEndValue(QPoint(-self.sidebar_reveal.width(), 16))
        self.sidebar_reveal_animation.finished.connect(self._finish_sidebar_reveal_hide)
        self.sidebar_reveal_animation.start()

    def _finish_sidebar_reveal_hide(self) -> None:
        if self.sidebar_reveal.x() < 0:
            self.sidebar_reveal.hide()
        try:
            self.sidebar_reveal_animation.finished.disconnect(self._finish_sidebar_reveal_hide)
        except TypeError:
            pass

    def _leave_hidden_chrome(self) -> None:
        if self._fs:
            self.set_fullscreen(False)
        if self._focus_mode:
            self.toggle_focus()

    def toggle_focus(self) -> None:
        self.toggle_zen()

    def toggle_zen(self) -> None:
        self._focus_mode = not self._focus_mode
        self._apply_chrome_visibility()

    def _html_fullscreen(self, request) -> None:
        request.accept()
        self.set_fullscreen(request.toggleOn())

    # ── overlays ────────────────────────────────────────────────────────────
    def show_link(self, url: str) -> None:
        if not url:
            self.link_label.hide()
            return
        fm = QFontMetrics(self.link_label.font())
        self.link_label.setText(fm.elidedText(url, Qt.TextElideMode.ElideMiddle, max(200, int(self.width() * 0.6))))
        self.link_label.adjustSize()
        self.link_label.move(10, self.viewhost.height() - self.link_label.height() - 10)
        self.link_label.show()
        self.link_label.raise_()

    def toast(self, text: str) -> None:
        lab = self.toast_label
        lab.setText(text)
        lab.adjustSize()
        lab.move((self.viewhost.width() - lab.width()) // 2, self.viewhost.height() - lab.height() - 26)
        lab.show()
        lab.raise_()
        self.toast_anim.stop()
        if self.anim_on():
            self.toast_anim.setDuration(170)
            self.toast_anim.setStartValue(self.toast_fx.opacity() if lab.isVisible() else 0.0)
            self.toast_anim.setEndValue(1.0)
            self.toast_anim.start()
        else:
            self.toast_fx.setOpacity(1.0)
        self.toast_timer.start(2300)

    def _toast_out(self) -> None:
        if self.anim_on():
            self.toast_anim.stop()
            self.toast_anim.setDuration(280)
            self.toast_anim.setStartValue(self.toast_fx.opacity())
            self.toast_anim.setEndValue(0.0)
            self.toast_anim.start()
        else:
            self.toast_label.hide()

    def _toast_faded(self) -> None:
        if self.toast_fx.opacity() < 0.05:
            self.toast_label.hide()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if hasattr(self, "wallpaper_layer") and self.centralWidget() is not None:
            self.wallpaper_layer.setGeometry(self.centralWidget().rect())
            self.wallpaper_layer.lower()
        self.update_sidebar_reveal()
        extra = self.selbar.sizeHint().width() if self.selbar.isVisible() else 0
        self.tabbar.available = max(200, self.width() - 160 - extra)
        self.tabbar.relayout()
        self._bm_timer = getattr(self, "_bm_timer", None)
        if self._bm_timer is None:
            self._bm_timer = QTimer(self)
            self._bm_timer.setSingleShot(True)
            self._bm_timer.timeout.connect(self.refresh_bookmarks_bar)
        self._bm_timer.start(120)
        self.mini.reposition()
        if hasattr(self, "download_popup"):
            self.download_popup.reposition()
        if hasattr(self, "_site_notifications"):
            self._position_site_notifications()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.refresh_completions()

    def closeEvent(self, e) -> None:
        self._closing = True
        for notification in list(self._site_notifications):
            notification.dismiss()
        if not self.private and len([w for w in self.app.windows_of(self.store) if not w.private]) == 1:
            snap = self.snapshot()
            self.store.set("session", snap["tabs"])
            self.store.set("session_groups", snap["groups"])
        try:
            self.app.governor.updated.disconnect(self.sidebar.perf.on_update)
        except (TypeError, RuntimeError):
            pass
        self.devdock.hide()
        for v in self.tab_views():
            v.deleteLater()
        self.app.window_closed(self)
        super().closeEvent(e)

# ═════════════════════════════════════════════════════════════════════════════
#  First-run / add-profile wizard
# ═════════════════════════════════════════════════════════════════════════════

class Swatch(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, color: str):
        super().__init__()
        self.color, self.on = color, False
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(QRectF(6, 6, 24, 24))
        if self.on:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(self.palette().color(QPalette.ColorRole.Text), 2))
            p.drawEllipse(QRectF(2, 2, 32, 32))

    def mousePressEvent(self, _e) -> None:
        self.clicked.emit(self.color)


class ThemeCard(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, key: str):
        super().__init__()
        self.key, self.on = key, False
        self.setFixedSize(160, 172)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _e) -> None:
        t = THEMES[self.key]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(6, 6, self.width() - 12, 124)
        path = QPainterPath()
        path.addRoundedRect(area, 12, 12)
        p.setClipPath(path)
        p.fillRect(area, QColor(t["bg"]))
        p.fillRect(QRectF(area.x(), area.y() + 26, area.width(), 24), QColor(t["surface"]))
        tab = QPainterPath()
        tab.addRoundedRect(QRectF(area.x() + 10, area.y() + 8, 52, 20), 6, 6)
        p.fillPath(tab, QColor(t["surface"]))
        p.fillRect(QRectF(area.x() + 70, area.y() + 10, 34, 14), QColor(t["hover"]))
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(area.x() + 28, area.y() + 32, area.width() - 56, 12), 6, 6)
        p.fillPath(pill, QColor(t["surface2"]))
        g = QLinearGradient(area.topLeft(), area.bottomRight())
        g.setColorAt(0, QColor(t["accent"]))
        g.setColorAt(1, QColor(t["bg"]))
        p.fillRect(QRectF(area.x(), area.y() + 50, area.width(), area.height() - 50), g)
        glass = QPainterPath()
        glass.addRoundedRect(QRectF(area.x() + 24, area.y() + 80, area.width() - 48, 16), 8, 8)
        p.fillPath(glass, QColor(t["surface"]))
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(t["border"]), 1))
        p.drawRoundedRect(area, 12, 12)
        if self.on:
            p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 3))
            p.drawRoundedRect(area.adjusted(-2, -2, 2, 2), 14, 14)
        p.setPen(self.palette().color(QPalette.ColorRole.Highlight if self.on else QPalette.ColorRole.Text))
        f = p.font()
        f.setBold(self.on)
        f.setPixelSize(14)
        p.setFont(f)
        p.drawText(QRectF(0, 136, self.width(), 30), Qt.AlignmentFlag.AlignCenter, t["label"])

    def mousePressEvent(self, _e) -> None:
        self.clicked.emit(self.key)


class LookPreview(QWidget):
    """A painted mock-up of the new AwesomeBrowse: floating tabs, rounded bar, sidebar, mini player."""

    def __init__(self, key: str = "dark", sparkles: bool = False, height: int = 240):
        super().__init__()
        self.key, self.sparkles = key, sparkles
        self.setFixedHeight(height)

    def set_theme(self, key: str) -> None:
        self.key = key
        self.update()

    @staticmethod
    def _pill(p: QPainter, r: QRectF, fill, border=None, radius=None) -> None:
        path = QPainterPath()
        rad = r.height() / 2 if radius is None else radius
        path.addRoundedRect(r, rad, rad)
        p.fillPath(path, QColor(fill) if isinstance(fill, str) else fill)
        if border:
            p.setPen(QPen(QColor(border), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def paintEvent(self, _e) -> None:
        t = THEMES[self.key]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        win = QRectF(W * 0.07, 8, W * 0.86, H - 16)
        self._pill(p, win, t["bg"], t["border"], 20)
        x, y = win.x() + 16, win.y() + 12
        # floating pill tabs
        for i, (w, dot) in enumerate(((128, "#4f9dff"), (104, "#34c98b"), (92, "#ff9f43"))):
            r = QRectF(x, y, w, 26)
            self._pill(p, r, t["surface"] if i == 0 else t["hover"], t["border"] if i == 0 else None)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(dot))
            p.drawEllipse(QRectF(r.x() + 10, r.y() + 8, 10, 10))
            self._pill(p, QRectF(r.x() + 26, r.y() + 10, w - 46, 6), rgba_qcolor(t["sub"], 0.5))
            x += w + 6
        p.setBrush(QColor("#ff6bb5"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(x + 4, y + 3, 20, 20))
        p.setPen(QPen(QColor("#ffffff"), 1.6))
        p.drawLine(QPointF(x + 14, y + 8), QPointF(x + 14, y + 18))
        p.drawLine(QPointF(x + 9, y + 13), QPointF(x + 19, y + 13))
        # toolbar
        ty = y + 38
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(("#4f9dff", "#34c98b", "#ff9f43")):
            p.setBrush(QColor(c))
            p.drawEllipse(QRectF(win.x() + 18 + i * 28, ty + 3, 20, 20))
        bar = QRectF(win.x() + 108, ty, win.width() - 108 - 100, 26)
        self._pill(p, bar, t["surface"], t["border"])
        p.setBrush(QColor("#34c98b"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(bar.x() + 11, bar.y() + 8, 10, 10))
        self._pill(p, QRectF(bar.x() + 30, bar.y() + 10, bar.width() * 0.4, 6), rgba_qcolor(t["sub"], 0.55))
        for i, c in enumerate(("#c084fc", "#38bdf8", "#a78bfa")):
            p.setBrush(QColor(c))
            p.drawEllipse(QRectF(bar.right() + 12 + i * 26, ty + 3, 20, 20))
        # body: sidebar rail + page
        by = ty + 38
        body = QRectF(win.x() + 14, by, win.width() - 28, win.bottom() - by - 12)
        rail = QRectF(body.x(), body.y(), 30, body.height())
        self._pill(p, rail, t["surface"], t["border"], 12)
        for i, c in enumerate(("#34d399", "#f59e0b", "#fbbf24", "#ff5c7a")):
            p.setBrush(QColor(c))
            p.setPen(Qt.PenStyle.NoPen)
            if rail.y() + 14 + i * 24 < rail.bottom() - 8:
                p.drawEllipse(QRectF(rail.x() + 9, rail.y() + 10 + i * 24, 12, 12))
        page = QRectF(body.x() + 38, body.y(), body.width() - 38, body.height())
        _style, c1, c2, c3 = t["wall"]
        g = QLinearGradient(page.topLeft(), page.bottomRight())
        g.setColorAt(0, QColor(_mix(c1, t["bg"], 0.35)))
        g.setColorAt(1, QColor(_mix(c2, t["bg"], 0.25)))
        self._pill(p, page, g, None, 14)
        self._pill(p, QRectF(page.center().x() - 40, page.y() + 12, 80, 14), QColor(255, 255, 255, 190), None, 7)
        self._pill(p, QRectF(page.center().x() - page.width() * 0.26, page.y() + 36, page.width() * 0.52, 22),
                   rgba_qcolor(t["surface"], 0.85), None)
        for i in range(5):
            self._pill(p, QRectF(page.center().x() - 100 + i * 42, page.y() + 70, 32, 32), rgba_qcolor(t["surface"], 0.7), None, 10)
        # translucent mini player
        mini = QRectF(page.x() + 10, page.bottom() - 36, 110, 26)
        self._pill(p, mini, rgba_qcolor(t["surface"], 0.78), t["border"])
        p.setBrush(QColor("#ff5c7a"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(mini.x() + 9, mini.y() + 7, 12, 12))
        self._pill(p, QRectF(mini.x() + 28, mini.y() + 8, 50, 4), rgba_qcolor(t["text"], 0.6))
        self._pill(p, QRectF(mini.x() + 28, mini.y() + 15, 34, 3), rgba_qcolor(t["sub"], 0.6))
        if self.sparkles:
            p.setBrush(QColor(t["accent"]))
            p.setPen(Qt.PenStyle.NoPen)
            for cx, cy, r in ((W * 0.04, H * 0.2, 10), (W * 0.96, H * 0.15, 13), (W * 0.93, H * 0.82, 8), (W * 0.05, H * 0.78, 12)):
                star = QPainterPath()
                star.moveTo(cx, cy - r)
                star.quadTo(cx, cy, cx + r, cy)
                star.quadTo(cx, cy, cx, cy + r)
                star.quadTo(cx, cy, cx - r, cy)
                star.quadTo(cx, cy, cx, cy - r)
                p.fillPath(star, QColor(t["accent"]))


class ThemeDot(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, key: str):
        super().__init__()
        self.key, self.on = key, False
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(THEMES[key]["label"])

    def paintEvent(self, _e) -> None:
        t = THEMES[self.key]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        circle = QPainterPath()
        circle.addEllipse(QRectF(5, 5, 24, 24))
        p.setClipPath(circle)
        p.fillRect(QRectF(5, 5, 12, 24), QColor(t["bg"]))
        p.fillRect(QRectF(17, 5, 12, 24), QColor(t["accent"]))
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(t["border"]), 1))
        p.drawEllipse(QRectF(5, 5, 24, 24))
        if self.on:
            p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 2.4))
            p.drawEllipse(QRectF(1.5, 1.5, 31, 31))

    def mousePressEvent(self, _e) -> None:
        self.clicked.emit(self.key)


class VersionCard(QPushButton):
    def __init__(self, title: str, desc: str, tag: str = ""):
        super().__init__()
        self.setCheckable(True)
        self.setProperty("choice", True)
        self.setMinimumHeight(84)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(2)
        head = QLabel(f"{title}" + (f"   {tag}" if tag else ""))
        f = head.font()
        f.setPixelSize(16)
        f.setBold(True)
        head.setFont(f)
        body = QLabel(desc)
        body.setWordWrap(True)
        body.setObjectName("muted")
        for w in (head, body):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(w)


WIZ_LINKS = [
    ("website", "Website", "https://{u}"), ("github", "GitHub", "https://github.com/{u}"), ("x", "X", "https://x.com/{u}"),
    ("youtube", "YouTube", "https://youtube.com/@{u}"), ("instagram", "Instagram", "https://instagram.com/{u}"),
    ("linkedin", "LinkedIn", "https://linkedin.com/in/{u}"), ("twitch", "Twitch", "https://twitch.tv/{u}"),
    ("reddit", "Reddit", "https://reddit.com/user/{u}"), ("spotify", "Spotify", "https://open.spotify.com/user/{u}"),
    ("discord", "Discord", "https://{u}"),
]
WIZ_EXTRA = Template(r"""
QLabel#keycap { background: $surface2; border: 1px solid $border; border-bottom-width: 2px; border-radius: 8px; padding: 3px 10px; font-weight: 600; }
QPlainTextEdit#bio { background: $surface2; border: 1px solid $border; border-radius: 12px; padding: 8px; selection-background-color: $accent; selection-color: $on_accent; }
QToolButton#avatarbtn { border-radius: 48px; }
""")


class SetupWizard(QDialog):
    """First-run slideshow, also used for 'Add profile' (which skips the intro slides)."""

    def __init__(self, first_run: bool, logo: QIcon):
        super().__init__()
        self.first_run = first_run
        self.setWindowTitle(f"{APP_NAME} setup" if first_run else "Add profile")
        self.setWindowIcon(logo)
        self.setFixedSize(900, 660)
        self.theme, self.color, self.edition = "tokyo" if first_run else "dark", AVATAR_COLORS[0], "stable"
        self.avatar_src: str | None = None
        self.link_rows: list = []
        self.result_data: dict | None = None
        self.sequence = [0, 1, 2, 3, 4] if first_run else [1, 3, 4]
        self.pos = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(46, 36, 46, 26)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        # 0 intro
        w, l = self._page()
        l.addWidget(self._h1("AwesomeBrowse has a new look!"), 0, Qt.AlignmentFlag.AlignHCenter)
        l.addWidget(self._lead("Floating tabs, rounded everything, bright icons and a smarter address bar. Let's get you set up."),
                    0, Qt.AlignmentFlag.AlignHCenter)
        l.addSpacing(10)
        self.intro_preview = LookPreview(self.theme, sparkles=True, height=330)
        l.addWidget(self.intro_preview)
        l.addStretch(1)

        # 1 profile
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        host.setObjectName("panelbody")
        outer.setWidget(host)
        outer.viewport().setAutoFillBackground(False)
        self.pages.addWidget(outer)
        l = QVBoxLayout(host)
        l.setContentsMargins(0, 0, 10, 0)
        l.setSpacing(8)
        l.addWidget(self._h1("Edit your profile"))
        l.addWidget(self._lead("Add a photo, a short bio and links to your other platforms. You can change all of it later in Settings."))
        l.addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(22)
        col0 = QVBoxLayout()
        self.avatar_btn = QToolButton()
        self.avatar_btn.setObjectName("avatarbtn")
        self.avatar_btn.setIconSize(QSize(96, 96))
        self.avatar_btn.setFixedSize(100, 100)
        self.avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.avatar_btn.setToolTip("Choose a profile picture")
        self.avatar_btn.clicked.connect(self._pick_photo)
        col0.addWidget(self.avatar_btn)
        rm = QPushButton("Remove photo")
        rm.setProperty("ghost", True)
        rm.clicked.connect(self._remove_photo)
        col0.addWidget(rm)
        row.addLayout(col0)
        col = QVBoxLayout()
        col.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("field")
        self.name_edit.setPlaceholderText("Your name")
        self.name_edit.setMaxLength(40)
        self.name_edit.textChanged.connect(self._profile_changed)
        col.addWidget(self.name_edit)
        self.bio = QPlainTextEdit()
        self.bio.setObjectName("bio")
        self.bio.setPlaceholderText("About you: what you do, what this profile is for")
        self.bio.setFixedHeight(78)
        self.bio.textChanged.connect(self._bio_changed)
        col.addWidget(self.bio)
        sw = QHBoxLayout()
        sw.setSpacing(2)
        self.swatches = []
        for c in AVATAR_COLORS:
            sw_ = Swatch(c)
            sw_.clicked.connect(self._pick_color)
            self.swatches.append(sw_)
            sw.addWidget(sw_)
        sw.addStretch(1)
        col.addLayout(sw)
        row.addLayout(col, 1)
        l.addLayout(row)
        l.addSpacing(8)
        head = QLabel("Links to your other platforms")
        head.setObjectName("sect")
        l.addWidget(head)
        self.links_box = QVBoxLayout()
        self.links_box.setSpacing(6)
        l.addLayout(self.links_box)
        self.add_link_btn = QPushButton("Add a link")
        self.add_link_btn.clicked.connect(self._add_link)
        l.addWidget(self.add_link_btn, 0, Qt.AlignmentFlag.AlignLeft)
        l.addStretch(1)

        # 2 shortcuts
        w, l = self._page()
        l.addWidget(self._h1("Organize your tabs"))
        l.addWidget(self._lead("Keep workflows organised. Here are the shortcuts worth learning."))
        l.addSpacing(14)
        for keys, text in ((["Ctrl", "click"], "Select several tabs. Add Shift to select a range."),
                           (["Ctrl", "Shift", "G"], "Group tabs, then name and colour the group."),
                           (["Click a chip"], "Collapse or expand a tab group."),
                           (["Ctrl", "K"], "Command palette: find any tab, page or command."),
                           (["Ctrl", "B"], "Show or hide the full sidebar. Customize its panels and order."),
                           (["Ctrl", "Shift", "Z"], "Zen mode: hide browser controls. Esc returns.")):
            r = QHBoxLayout()
            kc = QHBoxLayout()
            kc.setSpacing(6)
            for k in keys:
                lab = QLabel(k)
                lab.setObjectName("keycap")
                kc.addWidget(lab)
            kc.addStretch(1)
            holder = QWidget()
            holder.setFixedWidth(300)
            holder.setLayout(kc)
            r.addWidget(holder)
            r.addWidget(QLabel(text), 1)
            l.addLayout(r)
            l.addSpacing(8)
        l.addStretch(1)

        # 3 the new look
        w, l = self._page()
        l.addWidget(self._h1("Meet the new look"))
        l.addWidget(self._lead("Pick a theme to try it on. There are 29, and each comes with a matching wallpaper."))
        l.addSpacing(6)
        self.preview = LookPreview(self.theme, height=250)
        l.addWidget(self.preview)
        self.theme_name = QLabel()
        self.theme_name.setObjectName("h2")
        self.theme_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(self.theme_name)
        grid = QGridLayout()
        grid.setSpacing(2)
        self.dots = []
        order = sorted(THEMES, key=lambda k: (THEMES[k]["kind"] != "dark", list(THEMES).index(k)))
        for n, key in enumerate(order):
            d = ThemeDot(key)
            d.clicked.connect(self._pick_theme)
            self.dots.append(d)
            grid.addWidget(d, n // 15, n % 15)
        gh = QHBoxLayout()
        gh.addStretch(1)
        gh.addLayout(grid)
        gh.addStretch(1)
        l.addLayout(gh)
        l.addStretch(1)

        # 4 version
        w, l = self._page()
        l.addWidget(self._h1("Choose your interface style"))
        l.addWidget(self._lead("Choose how the browser looks. You can switch styles any time in Settings."))
        l.addSpacing(10)
        self.version_group = QButtonGroup(self)
        for key, title, desc, tag in (
                ("stable", "2.1.2-Renovo GA", "The first general release: customizable sidebar, AI companion, live download progress, print preview, "
                 "floating tabs, YouTube Music, and live wallpapers.", "Recommended"),
                ("nightly", "Classic 2.1", "The earlier AwesomeBrowse 2 look with tab groups, extensions and the memory limiter.", ""),
                ("legacy", "2.0.0 Legacy", "The classic interface, without the sidebar or animations.", "")):
            card = VersionCard(title, desc, tag)
            card.setChecked(key == "stable")
            card.clicked.connect(lambda _=False, k=key: setattr(self, "edition", k))
            self.version_group.addButton(card)
            l.addWidget(card)
        l.addStretch(1)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setProperty("ghost", True)
        self.back_btn.clicked.connect(lambda: self._go(-1))
        self.next_btn = QPushButton("Next")
        self.next_btn.setProperty("primary", True)
        self.next_btn.setMinimumWidth(150)
        self.next_btn.clicked.connect(lambda: self._go(1))
        nav.addWidget(self.back_btn)
        nav.addStretch(1)
        self.dots_label = QLabel()
        self.dots_label.setObjectName("muted")
        nav.addWidget(self.dots_label)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        self._add_link()
        self._pick_color(self.color)
        self._pick_theme(self.theme)
        self._show_page()

    # building blocks ---------------------------------------------------------
    def _page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)
        self.pages.addWidget(w)
        return w, l

    @staticmethod
    def _h1(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("h1")
        return lbl

    @staticmethod
    def _lead(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("lead")
        lbl.setWordWrap(True)
        return lbl

    # profile -----------------------------------------------------------------
    def _refresh_avatar(self) -> None:
        self.avatar_btn.setIcon(QIcon(avatar_pixmap(self.name_edit.text() or "?", self.color, 96, self.avatar_src)))

    def _profile_changed(self) -> None:
        self._refresh_avatar()
        self._update_nav()

    def _bio_changed(self) -> None:
        if len(self.bio.toPlainText()) > 280:
            self.bio.setPlainText(self.bio.toPlainText()[:280])
            self.bio.moveCursor(QTextCursor.MoveOperation.End)

    def _pick_color(self, c: str) -> None:
        self.color = c
        for sw in self.swatches:
            sw.on = sw.color == c
            sw.update()
        self._refresh_avatar()

    def _pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a profile picture", str(Path.home()),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.avatar_src = path
            self._refresh_avatar()

    def _remove_photo(self) -> None:
        self.avatar_src = None
        self._refresh_avatar()

    def _add_link(self) -> None:
        if len(self.link_rows) >= 5:
            return
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        combo = QComboBox()
        for _k, label, _t in WIZ_LINKS:
            combo.addItem(label)
        combo.setMinimumWidth(130)
        edit = QLineEdit()
        edit.setObjectName("field")
        edit.setPlaceholderText("username or link")
        rm = QToolButton()
        rm.setText("\u2715")
        rm.setToolTip("Remove link")
        h.addWidget(combo)
        h.addWidget(edit, 1)
        h.addWidget(rm)
        self.links_box.addWidget(row)
        entry = (row, combo, edit)
        self.link_rows.append(entry)
        rm.clicked.connect(lambda _=False, e=entry: self._remove_link(e))
        self.add_link_btn.setVisible(len(self.link_rows) < 5)

    def _remove_link(self, entry) -> None:
        if entry in self.link_rows:
            self.link_rows.remove(entry)
            entry[0].deleteLater()
        self.add_link_btn.setVisible(len(self.link_rows) < 5)

    def _links(self) -> list[dict]:
        out = []
        for _row, combo, edit in self.link_rows:
            v = edit.text().strip()
            if not v:
                continue
            _k, label, tpl = WIZ_LINKS[combo.currentIndex()]
            url = v if re.match(r"^https?://", v, re.I) else tpl.replace("{u}", v.lstrip("@/"))
            out.append({"id": uuid.uuid4().hex[:8], "service": label, "label": v if not v.startswith("http") else label, "url": url})
        return out

    # theme / navigation --------------------------------------------------------
    def _pick_theme(self, key: str) -> None:
        self.theme = key
        t = THEMES[key]
        self.setPalette(build_palette(t))
        self.setStyleSheet(build_qss(t, "stable") + WIZ_EXTRA.safe_substitute(**t))
        for d in self.dots:
            d.on = d.key == key
            d.update()
        self.preview.set_theme(key)
        self.intro_preview.set_theme(key)
        self.theme_name.setText(f"{t['label']}  ({t['kind']})")
        self._refresh_avatar()

    def _page_index(self) -> int:
        return self.sequence[self.pos]

    def _show_page(self) -> None:
        self.pages.setCurrentIndex(self._page_index())
        self._update_nav()

    def _go(self, d: int) -> None:
        npos = self.pos + d
        if npos >= len(self.sequence):
            self.result_data = {"name": self.name_edit.text().strip(), "color": self.color, "theme": self.theme,
                                "engine": "google", "bio": self.bio.toPlainText().strip(), "links": self._links(),
                                "avatar_src": self.avatar_src, "edition": self.edition}
            self.accept()
            return
        self.pos = max(0, npos)
        self._show_page()

    def _update_nav(self) -> None:
        n, last = len(self.sequence), self.pos == len(self.sequence) - 1
        self.back_btn.setVisible(self.pos > 0)
        self.next_btn.setText("Get started" if (self.first_run and self.pos == 0) else "Finish" if last else "Next")
        self.next_btn.setEnabled(not (self._page_index() == 1 and not self.name_edit.text().strip()))
        self.dots_label.setText("   ".join("\u25cf" if k == self.pos else "\u25cb" for k in range(n)))


# ═════════════════════════════════════════════════════════════════════════════
#  Application controller
# ═════════════════════════════════════════════════════════════════════════════

class BrowserApp(QObject):
    def __init__(self, qapp: QApplication, root: Path, safe_mode: bool = False):
        super().__init__()
        self.qapp, self.root = qapp, root
        self.ext_token = uuid.uuid4().hex
        (root / "profiles").mkdir(parents=True, exist_ok=True)
        self.state_path = root / "state.json"
        self.state = {"last": None, "trash": [], "ram": {}, "dirty": False}
        try:
            self.state.update(json.loads(self.state_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.safe_mode = safe_mode
        self.state["dirty"] = True          # cleared on a clean exit; if still set next time we start in safe mode
        self.logo_icon = QIcon(logo_pixmap(128))
        self.stores: dict[str, ProfileStore] = {}
        self.contexts: dict[str, Context] = {}
        self.windows: list[MainWindow] = []
        self._purge_trash()
        qapp.aboutToQuit.connect(self._flush_all)
        qapp.aboutToQuit.connect(self._clean_exit)
        self.governor = ResourceGovernor(self, safe_mode)
        self.governor.safe_mode = safe_mode

    # profiles ---------------------------------------------------------------
    def _purge_trash(self) -> None:
        for pid in self.state["trash"]:
            shutil.rmtree(self.root / "profiles" / pid, ignore_errors=True)
        self.state["trash"] = []
        self._save_state()

    def _save_state(self) -> None:
        try:
            self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        except OSError:
            pass

    def save_state(self) -> None:
        self._save_state()

    def _clean_exit(self) -> None:
        self.state["dirty"] = False
        self._save_state()

    def extensions_changed(self, store: ProfileStore, msg: str = "") -> None:
        for w in self.windows_of(store):
            if msg:
                w.toast(msg)
            for v in w.tab_views():
                if v.url().scheme() == SCHEME and v.url().host() == "extensions":
                    v.reload()
            w.refresh_extension_button()

    def list_profiles(self) -> list[ProfileStore]:
        out = []
        for d in sorted((self.root / "profiles").iterdir()):
            if d.is_dir() and (d / "config.json").exists() and d.name not in self.state["trash"]:
                out.append(self.store(d.name))
        return out

    def store(self, pid: str) -> ProfileStore:
        if pid not in self.stores:
            self.stores[pid] = ProfileStore(pid, self.root)
        return self.stores[pid]

    def context(self, store: ProfileStore) -> Context:
        if store.id not in self.contexts:
            self.contexts[store.id] = Context(self, store)
        return self.contexts[store.id]

    def create_profile(self, data: dict) -> ProfileStore:
        pid = uuid.uuid4().hex[:8]
        store = self.store(pid)
        store.data = default_config(data["name"], data["color"], data["theme"], data.get("engine", "google"))
        store.data["description"] = str(data.get("bio", ""))[:280]
        store.data["accounts"] = list(data.get("links", []))[:5]
        store.data["edition"] = data.get("edition", "stable")
        src = data.get("avatar_src")
        if src and os.path.isfile(src):
            name = "avatar" + (Path(src).suffix.lower() or ".png")
            try:
                shutil.copyfile(src, store.dir / name)
                store.data["avatar_image"] = name
            except OSError:
                pass
        store.flush()
        return store

    def add_profile(self) -> None:
        dlg = SetupWizard(first_run=False, logo=self.logo_icon)
        if dlg.exec() and dlg.result_data:
            self.open_window(self.create_profile(dlg.result_data))

    def delete_profile(self, store: ProfileStore) -> None:
        for w in self.windows_of(store):
            w.close()
        self.contexts.pop(store.id, None)
        self.stores.pop(store.id, None)
        self.state["trash"].append(store.id)
        if self.state["last"] == store.id:
            self.state["last"] = None
        self._save_state()
        remaining = self.list_profiles()
        if remaining:
            if not self.windows:
                self.open_window(remaining[0])
        else:
            dlg = SetupWizard(first_run=True, logo=self.logo_icon)
            if dlg.exec() and dlg.result_data:
                self.open_window(self.create_profile(dlg.result_data))
            else:
                self.qapp.quit()

    def open_profile(self, pid: str) -> None:
        mine = [w for w in self.windows if w.store.id == pid and not w.private]
        if mine:
            mine[-1].raise_()
            mine[-1].activateWindow()
        else:
            self.open_window(self.store(pid))

    # windows ----------------------------------------------------------------
    def open_window(self, store: ProfileStore, private: bool = False, urls=None, restore: bool = False):
        ctx = Context(self, store, private=True) if private else self.context(store)
        win = MainWindow(self, store, ctx, private)
        self.windows.append(win)
        self.state["last"] = store.id
        self._save_state()
        win.show()
        opened = False
        if restore and not private and store["startup"] == "restore" and store["session"]:
            win.restore_session(store["session"], store["session_groups"])
            opened = True
        elif not urls and not private and store["startup"] == "custom" and store["homepage"].strip():
            win.add_tab(smart_url(store["homepage"], store.search_template).toString())
            opened = True
        for u in urls or []:
            win.add_tab(u)
            opened = True
        if not opened:
            win.add_tab(None)
        return win

    def windows_of(self, store: ProfileStore) -> list[MainWindow]:
        return [w for w in self.windows if w.store is store]

    def window_closed(self, win: MainWindow) -> None:
        if win in self.windows:
            self.windows.remove(win)
        if win.private:
            win.ctx.deleteLater()

    def quit_all(self) -> None:
        self.qapp.closeAllWindows()

    def _flush_all(self) -> None:
        for s in self.stores.values():
            s.flush()

    def data_changed(self, store: ProfileStore) -> None:
        for w in self.windows_of(store):
            w.refresh_bookmarks_bar()
            w.update_toolbar()
            w.refresh_completions()

    # settings ---------------------------------------------------------------
    def apply_setting(self, store: ProfileStore, key: str, value, sender=None) -> None:
        kind = SETTING_TYPES.get(key)
        if kind is None or type(value) is not kind:
            return
        if key == "theme" and value not in THEMES:
            return
        if key == "search_engine" and value not in ENGINE_BY_ID:
            return
        if key == "startup" and value not in ("newtab", "restore", "custom"):
            return
        if key == "edition" and value not in ("legacy", "nightly", "stable"):
            return
        if key == "color" and value not in AVATAR_COLORS:
            return
        if key == "wallpaper" and not valid_wallpaper(store, value):
            return
        if key == "accent" and value and not re.match(r"^#[0-9a-fA-F]{6}$", value):
            return
        if key == "description":
            value = value.strip()[:280]
        if key == "avatar_emoji":
            value = value.strip()[:4]
        if key == "name":
            value = value.strip()[:40] or store["name"]
        if key == "homepage":
            value = value.strip()[:500]
        if key in ("wallpaper_dim", "wallpaper_blur"):
            value = max(0, min(80 if key == "wallpaper_dim" else 24, value))
        if key == "zoom_default":
            value = max(25, min(500, value))
        store.set(key, value)
        for w in self.windows_of(store):
            w.on_setting_changed(key, sender)

    # internal pages ---------------------------------------------------------
    def serve(self, ctx: Context, host: str, path: str, query: str = ""):
        store = ctx.store
        if host == "space":
            if not SPACE_EDITION:
                return None
            app_file = Path(__file__).resolve().parent / "awesomespace" / "index.html"
            try:
                if not app_file.is_file():
                    return None
                html = app_file.read_text(encoding="utf-8")
            except OSError:
                return None
            theme = resolve_theme(store)
            space_vars = {
                "bg": theme["bg"], "panel": theme["surface"], "panel2": theme["surface2"],
                "line": theme["border"], "text": theme["text"], "muted": theme["sub"],
                "accent": theme["accent"], "accent-soft": rgba(theme["accent"], 0.22),
                "on-accent": theme["on_accent"], "hover": theme["hover"],
            }
            space_css = ":root{" + ";".join(f"--{key}:{value}" for key, value in space_vars.items())
            space_css += f";color-scheme:{theme['kind']};}}"
            html = html.replace("/*__AWESOME_THEME__*/", space_css, 1)
            return html.encode("utf-8"), "text/html; charset=utf-8"
        if host == "about":
            host, path = "settings", "/about"
        if host == "ext":
            parts = path.lstrip("/").split("/", 1)
            return ctx.extensions.serve(parts[0], parts[1] if len(parts) > 1 else "") if ctx.extensions else None
        if host == "extapi":
            parts = path.lstrip("/").split("/", 1)
            if not ctx.extensions or len(parts) != 2:
                return None
            from urllib.parse import parse_qsl
            return ctx.extensions.api(parts[0], parts[1], dict(parse_qsl(query))), "application/json"
        if host == "wallpaper":
            if path.startswith("/user/"):
                name = os.path.basename(path[6:])
                if name not in store["user_wallpapers"]:
                    return None
                f = store.dir / "wallpapers" / name
                return f.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream"
            if path.startswith("/theme/"):
                data = theme_wallpaper_svg(path[7:].removesuffix(".svg"))
                return (data, "image/svg+xml") if data else None
            data = wallpaper_svg(path.strip("/").removesuffix(".svg"))
            return (data, "image/svg+xml") if data else None
        if host == "avatar":
            f = store.dir / store["avatar_image"] if store["avatar_image"] else None
            return (f.read_bytes(), mimetypes.guess_type(f.name)[0] or "image/png") if f and f.is_file() else None
        engines = [{"id": e[0], "label": e[1], "url": e[2]} for e in ENGINES]
        order = sorted(THEMES, key=lambda k: (THEMES[k]["kind"] != "dark", list(THEMES).index(k)))
        if host == "newtab":
            widgets = list(store["widgets"])
            if SPACE_EDITION and not any(w.get("url") == "awesome://space" for w in widgets):
                widgets.append({"id": "awesomespace", "name": "AwesomeSpace", "url": "awesome://space"})
                store.set("widgets", widgets)
            elif not SPACE_EDITION:
                clean_widgets = [w for w in widgets if w.get("url") != "awesome://space"]
                if clean_widgets != widgets:
                    store.set("widgets", clean_widgets)
            state = {k: store[k] for k in ("name", "color", "theme", "search_engine", "widgets", "wallpaper",
                                           "user_wallpapers", "wallpaper_dim", "wallpaper_blur", "show_clock",
                                           "show_widgets", "clock_24h", "description", "avatar_emoji", "animations")}
            state["has_avatar"] = bool(store["avatar_image"])
            state["engines"] = engines
            state["premade"] = [{"id": w[0], "label": w[1]} for w in WALLPAPERS]
            state["theme_walls"] = [{"id": "theme:" + k, "label": THEMES[k]["label"]} for k in order]
            return render_template(NEWTAB_HTML, store, state), "text/html"
        if host == "settings":
            skip = {"history", "bookmarks", "session", "session_groups", "widgets", "downloads", "user_wallpapers",
                    "notes", "web_panels", "workspaces", "zoom_by_host", "extensions", "sidebar_order",
                    "sidebar_panels", "ai_provider", "renovo_ui_version"}
            state = {k: v for k, v in store.data.items() if k not in skip}
            state.update(engines=engines, colors=AVATAR_COLORS, section=path.strip("/"),
                         theme_labels={k: v["label"] for k, v in THEMES.items()},
                         theme_kinds={k: v["kind"] for k, v in THEMES.items()}, theme_order=order,
                         services=[{"id": a, "label": b, "url": c} for a, b, c in ACCOUNT_SERVICES],
                         profiles=[{"id": s.id, "name": s["name"], "color": s["color"], "current": s is store,
                                    "description": s["description"]} for s in self.list_profiles()],
                         about=[["Version", APP_VERSION], ["Engine", f"Chromium {ctx.chromium}"],
                                ["Qt WebEngine", self.qt_version()], ["Profile folder", str(store.dir)],
                                ["Mode", "Private" if ctx.private else "Standard"]])
            return render_template(SETTINGS_HTML, store, state), "text/html"
        if host == "extensions":
            recs = []
            if ctx.extensions:
                for r in ctx.extensions.records():
                    recs.append({**r, "icon_url": f"{SCHEME}://ext/{r['id']}/{r['icon']}" if r["icon"] else ""})
            return render_template(EXT_HTML, store, {"extensions": recs, "private": ctx.private}), "text/html"
        if host in ("history", "bookmarks", "downloads"):
            state = {"page": host, "history": store["history"][:2000] if not ctx.private else [],
                     "bookmarks": store["bookmarks"], "downloads": ctx.downloads.records()}
            title = {"history": "History", "bookmarks": "Bookmarks", "downloads": "Downloads"}[host]
            return render_template(LIB_HTML, store, state, title), "text/html"
        return None

    @staticmethod
    def qt_version() -> str:
        from PyQt6.QtCore import QT_VERSION_STR
        return QT_VERSION_STR


# ═════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════════════

def register_scheme() -> None:
    scheme = QWebEngineUrlScheme(QByteArray(SCHEME.encode()))
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(scheme)


def main() -> int:
    QCoreApplication.setApplicationName("AwesomeBrowse2")
    QCoreApplication.setOrganizationName("AwesomeBrowse")
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    try:
        raw = json.loads((root / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    # Safe mode (--safe-mode, or the last run didn't exit cleanly) ignores the hard heap cap.
    safe = "--safe-mode" in sys.argv or bool(raw.get("dirty"))
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", chromium_flags(raw.get("ram") or {}, safe))
    register_scheme()
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    qapp = QApplication(sys.argv)
    qapp.setApplicationDisplayName(APP_NAME)
    qapp.setStyle("Fusion")

    browser = BrowserApp(qapp, root, safe_mode=safe)
    qapp.setWindowIcon(browser.logo_icon)

    args = [a for a in sys.argv[1:] if a != "--safe-mode"]
    private = "--private" in args
    wanted = args[args.index("--profile") + 1] if "--profile" in args and args.index("--profile") + 1 < len(args) else None
    urls = [a for a in args if not a.startswith("--") and a != wanted]

    profiles = browser.list_profiles()
    if not profiles:
        dlg = SetupWizard(first_run=True, logo=browser.logo_icon)
        if not dlg.exec() or not dlg.result_data:
            browser.state["dirty"] = False
            browser.save_state()
            return 0
        store = browser.create_profile(dlg.result_data)
    else:
        by_id = {p.id: p for p in profiles}
        store = by_id.get(wanted) or by_id.get(browser.state.get("last")) or profiles[0]
    browser.open_window(store, private=private, urls=urls or None, restore=True)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
