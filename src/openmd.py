#!/usr/bin/env python3
# openmd.py - Simple Markdown previewer for MacOS, Unix, with sidebar TOC
# by Rufus Lin, 2026
# Open source: GitHub RufusLin/openmd or directly install: pip install openmd
# -------------------------------------------------
# This script is invoked by "openmd <md-file>" after "pip install openmd".
# Remote files over ssh can also be opened with a shell alias defined in ~/.zshrc:
#
#   remotemd() {
#       local remote_path="$1"
#       local filename=$(basename "$remote_path")
#       local tmp_file="/tmp/remote_preview_${filename}.md"
#
#       # Pull via the 'home' alias, then launch
#       scp "home:$remote_path" "$tmp_file" && \
#       $MD_VIEWER_PY $MD_VIEWER_SCRIPT "$tmp_file" >/dev/null 2>&1 &
#   }
#
# The script itself only opens a local file path; remote handling is performed by the
# `remotemd` alias which copies the file via SSH (scp) to a temporary location and
# then runs this script on that copy. No glob expansion or remote file fetching is
# performed inside the Python code.
# -------------------------------------------------
# Tabs are intentionally preserved — DO NOT remove the QTabWidget multi-file tab view.

__version__ = '1.4.29'

import sys, os, re, markdown, configparser, hashlib, tempfile, subprocess, threading, time, json, html, textwrap
import urllib.request
try:
    import yaml
except ImportError:
    yaml = None

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_LOGGING_RULES", "qt.webengine*=false;*.info=false;*.warning=false;*.debug=false")

# Try to import curses for file picker; fallback to simple list
try:
    import curses
except Exception:
    curses = None

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem, QPushButton,
    QDialog, QLabel, QFrame, QGraphicsOpacityEffect,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QSize, Qt, QFileSystemWatcher, QUrl, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QColor, QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile
from bs4 import BeautifulSoup

# GitHub-Modern Dark Theme (built-in defaults)
CSS = """body { 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
    line-height: 1.6; color: #c9d1d9; max-width: 900px; margin: auto; padding: 2rem; background-color: #0d1117; 
}

pre { 
    background-color: #161b22; padding: 16px; border-radius: 6px; border: 1px solid #30363d;
    overflow: auto; font-family: "SFMono-Regular", Consolas, monospace; 
}

#meta { 
    background-color: rgba(110,118,129,0.4); padding: 16px; border-radius: 6px; border: 1px solid #30363d;
    overflow: auto; font-family: "SFMono-Regular", Consolas, monospace; 
    margin-bottom: 1.5rem; white-space: pre-wrap; 
}
code { background-color: rgba(110,118,129,0.4); padding: 0.2em 0.4em; border-radius: 6px; font-size: 85%; }
table { border-collapse: collapse; width: 100%; margin: 24px 0; border: 1px solid #30363d; }
table th, table td { border: 1px solid #30363d; padding: 8px 12px; }
table tr:nth-child(even) { background-color: #161b22; }
h1 a, h2 a, h3 a, h4 a, h5 a, h6 a { color: inherit; text-decoration: none; }
"""

# Sidebar Qt stylesheet
SIDEBAR_CSS = """
QWidget#sidebarCol {
    background: #161b22;
    border-right: 1px solid #30363d;
}
QTreeWidget {
    background: #161b22;
    color: #c9d1d9;
    border: 2px solid transparent;
    font-size: 14px;
}
QTreeWidget:focus {
    border: 2px solid #58a6ff;
}
QTreeWidget::item { padding: 2px 0; }
QTreeWidget::item:hover { background: #212730; }
QTreeWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2d7dd2, stop:1 #1a5fa8);
    color: #ffffff;
    border-left: 3px solid #58a6ff;
    border-radius: 2px;
}
QTreeWidget::item:selected:!active {
    background: #30363d;
    color: #8b949e;
    border-left: 3px solid #484f58;
}
QTreeWidget::item:selected:hover { background: #2d7dd2; }

QPushButton#metaBtn, QPushButton#helpBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #4caf50, stop:0.4 #43a047, stop:0.5 #388e3c, stop:1 #2e7d32);
    border: 1px solid #1b5e20;
    border-bottom: 2px solid #003300;
    border-radius: 4px; color: white;
    font-weight: bold;
    font-size: 10px;
    padding: 0 10px;
}
QPushButton#metaBtn:hover, QPushButton#helpBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #66bb6a, stop:0.4 #4caf50, stop:0.5 #43a047, stop:1 #388e3c);
}
QPushButton#metaBtn:pressed, QPushButton#helpBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2e7d32, stop:1 #388e3c);
    border-bottom: 1px solid #003300;
}
"""

# Web view focus styling
VIEW_CSS = """
QWebEngineView {
    border: 2px solid transparent;
}
QWebEngineView:focus {
    border: 2px solid #58a6ff;
}
"""

CONFIG_PATH = os.path.expanduser('~/.openmd.config')
UPDATE_CHECK_INTERVAL = 6 * 3600  # seconds



def _load_user_css() -> str:
    """Load .openmd.css from cwd, script install dir, or home dir (first match wins).

    The user CSS is appended after the built-in CSS so any rule in .openmd.css
    overrides the matching default via normal CSS cascade.
    """
    candidates = [
        os.path.join(os.getcwd(), '.openmd.css'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.openmd.css'),
        os.path.expanduser('~/.openmd.css'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'openmd-default.css'),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except OSError:
                pass
    return ''


def _parse_themes(css_text: str) -> list[tuple[str, str]]:
    """Return up to 16 (theme_name, bg_color) tuples parsed from body.theme-xxx rules.

    Scans for patterns like:
        body.theme-foo { ... background-color: #rrggbb; ... }
    Returns themes in the order they appear in the CSS.
    Skips any block that is malformed or missing a background-color.
    Caps at 16 themes to keep the swatch bar compact.
    """
    themes = []
    seen = set()
    try:
        block_re = re.compile(
            r'body\.theme-([\w-]+)\s*\{([^}]*)\}', re.DOTALL
        )
        bg_re = re.compile(r'background-color\s*:\s*([^;]+);')
        for m in block_re.finditer(css_text):
            if len(themes) >= 16:
                break
            try:
                name = m.group(1).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                bg_match = bg_re.search(m.group(2))
                if not bg_match:
                    continue  # skip themes with no background-color
                bg = bg_match.group(1).strip()
                if not bg:
                    continue
                themes.append((name, bg))
            except Exception:
                continue  # skip malformed individual block
    except Exception:
        pass  # return whatever was collected before the error
    return themes


def _load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding='utf-8')
    if not cfg.has_section('display'):
        cfg.add_section('display')
    if not cfg.has_option('display', 'show_meta'):
        cfg.set('display', 'show_meta', 'false')
    return cfg


def _save_config(cfg: configparser.ConfigParser):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        cfg.write(f)


def _get_saved_theme(cfg: configparser.ConfigParser) -> str:
    return cfg.get('display', 'theme', fallback='')


def _set_saved_theme(cfg: configparser.ConfigParser, theme: str):
    if not cfg.has_section('display'):
        cfg.add_section('display')
    cfg.set('display', 'theme', theme)
    _save_config(cfg)


class _OpenMDPage(QWebEnginePage):
    """Custom QWebEnginePage that opens http/https links in the system browser.

    Any navigation to an external URL (http/https) is intercepted and handed
    off to QDesktopServices.openUrl() so it opens in the user's default browser.
    The Qt window itself never navigates away from the rendered markdown.
    All other schemes (data:, file:, about:) are allowed through normally.
    """
    focusSidebarRequested = Signal()

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        scheme = url.scheme()
        if scheme in ('http', 'https'):
            try:
                QDesktopServices.openUrl(url)
            except Exception:
                pass
            return False  # block in-window navigation regardless
        return True  # allow file://, data:, about:blank, anchor jumps, etc.

    def javaScriptConsoleMessage(self, level, message, line, source):
        if "FOCUS_SIDEBAR" in message:
            self.focusSidebarRequested.emit()
        super().javaScriptConsoleMessage(level, message, line, source)


class _HelpDialog(QDialog):
    """Custom help dialog that handles Escape and Return keys."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("openmd – Quick Help")
        self.setModal(True)
        self.resize(690, 520)  # 15% wider (600 * 1.15)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(event)


class _HelpPage(QWebEnginePage):
    """Page for help modal that handles the close signal via console."""
    closeRequested = Signal()

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        if url.scheme() in ('http', 'https'):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, _type, isMainFrame)

    def javaScriptConsoleMessage(self, level, message, line, source):
        if "CLOSE_DIALOG" in message:
            self.closeRequested.emit()
        super().javaScriptConsoleMessage(level, message, line, source)


class _SidebarTree(QTreeWidget):
    """QTreeWidget with custom navigation and expansion logic."""
    rightArrowPressed = Signal()
    focusChanged = Signal(bool)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focusChanged.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusChanged.emit(False)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        item = self.currentItem()

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if item:
                self.itemClicked.emit(item, 0)
            event.accept()
            return
        elif key == Qt.Key_Space:
            event.accept()
            return
        elif key == Qt.Key_Right:
            self.rightArrowPressed.emit()
            event.accept()
            return
        elif key == Qt.Key_Left:
            event.accept()
            return
        
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Per-file preview window: sidebar TOC (QTreeWidget) + QWebEngineView
# ---------------------------------------------------------------------------
# NOTE: This class renders a single markdown file with a TOC sidebar.
# The outer QTabWidget (in __main__) wraps multiple FilePreviewWidget instances
# so that multi-file tab support is preserved. DO NOT collapse these into one.
# ---------------------------------------------------------------------------

class FilePreviewWidget(QWidget):
    """A single-file preview pane: left sidebar TOC + right HTML view."""

    def __init__(self, file_path: str, shared_config: configparser.ConfigParser):
        super().__init__()
        self.file_path = file_path
        self.cfg = shared_config
        self._current_theme = _get_saved_theme(self.cfg)
        # Read meta visibility from config (default false)
        self._show_meta = self.cfg.getboolean('display', 'show_meta', fallback=False)

        # KaTeX CDN snippets
        self._katex_css = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css">'
        self._katex_script = (
            '<script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js"></script>\n'
            '<script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/contrib/auto-render.min.js"></script>\n'
            '<script>'
            'try { document.addEventListener("DOMContentLoaded",function(){'
            'if(window.renderMathInElement)renderMathInElement(document.body,{'
            'delimiters:[{left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false}]'
            '});}); } catch(e) {}'
            '</script>'
        )
        # Mermaid: triggered via loadFinished + runJavaScript
        self._mermaid_script = '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>'

        # --- Load and render markdown ---
        html_body, toc_html = self._render_markdown(file_path)
        full_html = self._build_html(html_body)

        # --- Sidebar (QTreeWidget) ---
        self.sidebar = _SidebarTree()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setIndentation(16)
        self.sidebar.itemClicked.connect(self._jump_to_section)
        self._populate_sidebar(toc_html)

        # --- Theme swatch bar at the foot of the sidebar ---
        self._swatch_bar = self._build_swatch_bar()

        # --- Sidebar column: tree + swatch bar ---
        sidebar_col = QWidget()
        sidebar_col.setObjectName("sidebarCol")
        sidebar_col.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar_col.setStyleSheet(SIDEBAR_CSS)
        
        self.sidebar_opacity = QGraphicsOpacityEffect(self)
        self.sidebar_opacity.setOpacity(1.0)
        sidebar_col.setGraphicsEffect(self.sidebar_opacity)
        self.sidebar.focusChanged.connect(lambda focused: self.sidebar_opacity.setOpacity(1.0 if focused else 0.6))
        
        sidebar_layout = QVBoxLayout(sidebar_col)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(self.sidebar)

        # --- Meta and Help buttons ---
        self.meta_btn = QPushButton("META")
        self.meta_btn.setObjectName("metaBtn")
        self.meta_btn.setFixedHeight(26)
        self.meta_btn.clicked.connect(self._toggle_meta)

        self.help_btn = QPushButton("HELP")
        self.help_btn.setObjectName("helpBtn")
        self.help_btn.setFixedHeight(26)
        self.help_btn.clicked.connect(self._show_help)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(6, 4, 6, 4)
        btn_row.setSpacing(4)
        btn_row.addWidget(self.meta_btn)
        btn_row.addWidget(self.help_btn)

        sidebar_layout.addLayout(btn_row)
        sidebar_layout.addSpacing(24)  # Spacer before swatches
        sidebar_layout.addWidget(self._swatch_bar)

        # --- Web view ---
        self.view = QWebEngineView()
        self.view.setStyleSheet(VIEW_CSS)
        
        page = _OpenMDPage(self.view)
        page.focusSidebarRequested.connect(self.sidebar.setFocus)
        self.view.setPage(page)  # intercept external links
        
        # Allow local file:// pages to load remote https:// images and
        # local files from other directories (e.g. temp cache).
        # Must be set on both the profile and the view settings to take effect.
        for settings in (
            QWebEngineProfile.defaultProfile().settings(),
            self.view.settings(),
        ):
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
        self.view.loadFinished.connect(self._on_load_finished)
        self._base_url = QUrl.fromLocalFile(
            os.path.dirname(os.path.abspath(file_path)) + os.sep
        )
        self.view.setHtml(full_html, self._base_url)

        # Now that view is initialized, connect sidebar right arrow
        self.sidebar.rightArrowPressed.connect(self._focus_view)

        # --- Live reload ---
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(self.file_path)
        self.watcher.fileChanged.connect(self._reload)

        # --- Layout: sidebar left, preview right ---
        screen_width = QApplication.primaryScreen().size().width()
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar_col)
        splitter.addWidget(self.view)
        splitter.setSizes([int(screen_width * 0.2), int(screen_width * 0.8)])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Keyboard shortcuts scoped to widgets
        # Left arrow in preview pane takes you back to the sidebar TOC
        self._shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self.view)
        self._shortcut_left.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_left.activated.connect(self.sidebar.setFocus)
        # Right arrow in preview pane is disabled to prevent accidental scrolling
        self._shortcut_right_disabled = QShortcut(QKeySequence(Qt.Key_Right), self.view)
        self._shortcut_right_disabled.setContext(Qt.WidgetWithChildrenShortcut)

    def _focus_view(self):
        """Explicitly switch focus to the web view and its document."""
        self.view.setFocus()
        self.view.page().runJavaScript("window.focus();")

    def _build_swatch_bar(self) -> QWidget:
        """Build a row of colour swatches, one per theme found in .openmd.css."""
        user_css = _load_user_css()
        self._themes = _parse_themes(user_css)  # [(name, bg_color), ...]

        bar = QWidget()
        bar.setStyleSheet("background: #0d1117; border-top: 1px solid #30363d;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        for name, bg in self._themes:
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setToolTip(name.replace('-', ' ').title())
            # Determine a border colour: slightly lighter than bg for contrast
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; border: 1px solid #555; border-radius: 3px; }}"
                f"QPushButton:hover {{ border: 2px solid #aaa; }}"
            )
            btn.clicked.connect(lambda checked, n=name: self._apply_theme(n))
            layout.addWidget(btn)

        layout.addStretch()
        return bar

    def _apply_theme(self, theme_name: str):
        """Apply a theme by setting a class on <body>."""
        self._current_theme = theme_name
        _set_saved_theme(self.cfg, theme_name)
        self.view.page().runJavaScript(
            "try { if(document.body) document.body.className = 'theme-" + theme_name + "'; } catch(e) {}"
        )

    def _populate_sidebar(self, toc_html: str):
        """Parse the TOC div from markdown-with-toc output and fill the QTreeWidget."""
        if not toc_html:
            return
        soup = BeautifulSoup(toc_html, "html.parser")
        toc_div = soup.find("div", class_="toc")
        if not toc_div:
            return
        top_ul = toc_div.find("ul", recursive=False)
        if top_ul:
            for li in top_ul.find_all("li", recursive=False):
                self._add_toc_item(li, parent_item=None)
        self.sidebar.expandAll()

    def _add_toc_item(self, node, parent_item):
        """Recursively add a <li> node (and its nested <ul> children) to the sidebar."""
        anchor_tag = node.find("a")
        if not anchor_tag:
            return
        title = anchor_tag.get_text()
        anchor_id = anchor_tag.get("name") or anchor_tag.get("href", "").lstrip("#")
        if not anchor_id:
            return

        item = QTreeWidgetItem([title])
        item.setData(0, Qt.UserRole, anchor_id)

        if parent_item is None:
            self.sidebar.addTopLevelItem(item)
        else:
            parent_item.addChild(item)

        for child_ul in node.find_all("ul", recursive=False):
            for sub_li in child_ul.find_all("li", recursive=False):
                self._add_toc_item(sub_li, item)

    def _render_markdown(self, file_path: str):
        """Read and render a markdown file; return (html_body, toc_html)."""
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                raw = fh.read()
            # Extract front-matter (YAML block between --- markers)
            yaml_str, body_md = self._extract_front_matter(raw)
            
            # STABILITY FIX: Use dedent to handle selected text fragments that carry
            # uniform indentation (common when selecting from terminal or indented blocks).
            # This prevents them from being parsed as verbatim code blocks.
            body_md = textwrap.dedent(body_md).strip()

            # Generate hidden meta HTML from YAML if yaml is available
            self._meta_html = ""
            if yaml and yaml_str:
                try:
                    data = yaml.safe_load(yaml_str)
                    pretty = yaml.dump(data, default_flow_style=False, sort_keys=False)
                    escaped = html.escape(pretty).replace('\n', '<br>')
                    visibility = 'visible' if self._show_meta else 'hidden'
                    display = 'block' if self._show_meta else 'none'
                    self._meta_html = (
                        f'<div id="meta" style="visibility:{visibility}; display:{display};">'
                        f'{escaped}</div>'
                    )
                except Exception:
                    pass
            md = markdown.Markdown(
                extensions=['toc', 'extra', 'sane_lists'],
                extension_configs={'toc': {'permalink': False, 'anchorlink': True}},
            )
            html_body = md.convert(body_md)
            toc_html = md.toc
            soup = BeautifulSoup(html_body, 'html.parser')
            for code_tag in soup.find_all('code', class_='language-mermaid'):
                pre_tag = code_tag.parent
                if pre_tag and pre_tag.name == 'pre':
                    new_pre = soup.new_tag('pre', **{'class': 'mermaid'})
                    new_pre.string = code_tag.get_text()
                    pre_tag.replace_with(new_pre)
            html_body = str(soup)
        except Exception as e:
            html_body = f"<pre>Error loading file: {e}</pre>"
            toc_html = ""
            self._meta_html = ""
        return html_body, toc_html

    def _extract_front_matter(self, raw: str) -> tuple[str, str]:
        """Return (yaml_str, body_md). If no front-matter, returns ('', raw)."""
        lines = raw.splitlines()
        if len(lines) >= 2 and lines[0].strip() == '---' and lines[1].strip() != '---':
            try:
                # We join lines starting from the first line AFTER the opening ---
                yaml_block = "\n".join(lines[1:])
                parts = yaml_block.split('---', 1)
                if len(parts) == 2 and parts[1].strip():
                    yaml_str = parts[0].strip()
                    body_md = "\n".join(parts[1].splitlines()[1:])
                    return yaml_str, body_md
            except Exception:
                pass
        return "", raw

    # Map common MIME types to file extensions for the image cache.
    _MIME_TO_EXT = {
        'image/svg+xml': '.svg',
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/gif': '.gif',
        'image/webp': '.webp',
        'image/avif': '.avif',
        'image/bmp': '.bmp',
        'image/x-icon': '.ico',
        'image/tiff': '.tiff',
    }

    def _cache_remote_images(self, html_body: str) -> str:
        """Download remote http/https images to a temp cache dir and rewrite src.

        Qt WebEngine cannot load remote images from a file:// origin even with
        LocalContentCanAccessRemoteUrls. This workaround fetches remote images
        once, caches them by URL hash in tempfile.gettempdir(), and rewrites
        the <img src> to a local file:// path so Qt can display them.

        The file extension is determined by (in order of preference):
          1. The Content-Type response header (most reliable — handles SVG badges
             and other URLs that have no file extension in the path)
          2. The URL path extension
          3. Fallback to .png
        """
        cache_dir = os.path.join(tempfile.gettempdir(), 'openmd_img_cache')
        os.makedirs(cache_dir, exist_ok=True)

        soup = BeautifulSoup(html_body, 'html.parser')
        modified = False
        for img in soup.find_all('img'):
            url = img.get('src', '')
            if not url.startswith(('http://', 'https://')):
                continue
            # Use a hash of the URL as the cache key (without extension yet)
            url_hash = hashlib.md5(url.encode()).hexdigest()

            # Check if any cached file with this hash already exists
            # (extension may vary, so glob for it)
            existing = None
            for candidate in os.listdir(cache_dir):
                if candidate.startswith(url_hash):
                    existing = os.path.join(cache_dir, candidate)
                    break

            if existing:
                img['src'] = QUrl.fromLocalFile(existing).toString()
                modified = True
                continue

            # Not cached — download and determine extension from Content-Type
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'openmd/1.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                    content_type = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()

                # Determine extension: Content-Type first, then URL path, then default
                ext = self._MIME_TO_EXT.get(content_type)
                if not ext:
                    ext = os.path.splitext(url.split('?')[0])[1]
                if not ext or len(ext) > 5:
                    ext = '.png'

                cached_path = os.path.join(cache_dir, url_hash + ext)
                with open(cached_path, 'wb') as f:
                    f.write(data)
            except Exception:
                continue  # leave src unchanged on error

            img['src'] = QUrl.fromLocalFile(cached_path).toString()
            modified = True

        return str(soup) if modified else html_body

    def _build_html(self, html_body: str) -> str:
        """Wrap rendered markdown body with CSS, Mermaid, and KaTeX.

        Qt WebEngine blocks @import url(...) inside <style> blocks when the page
        is loaded via setHtml() (no real HTTP origin). To load external fonts
        (e.g. Google Fonts), we extract @import url(...) lines from the user CSS
        and re-emit them as <link rel="stylesheet"> tags in <head>, which Qt allows.
        """
        user_css = _load_user_css()

        # Extract @import url(...) lines from user CSS and convert to <link> tags
        import_links = ''
        if user_css:
            import_lines = []
            clean_lines = []
            for line in user_css.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith('@import url('):
                    # Extract the URL from @import url('...') or @import url("...")
                    url_match = re.search(r"@import url\(['\"]?([^'\"\)]+)['\"]?\)", stripped, re.IGNORECASE)
                    if url_match:
                        href = url_match.group(1)
                        import_links += f'<link rel="stylesheet" href="{href}">'
                else:
                    clean_lines.append(line)
            user_css = '\n'.join(clean_lines)

        combined_css = CSS + ('\n/* .openmd.css */\n' + user_css if user_css else '')
        # If a theme is active, pre-apply it so the page loads with the right theme.
        # CSS uses descendant selectors (body.theme-xxx pre, etc.) so body class alone
        # is sufficient — no need to propagate the class to child elements.
        body_class = f' class="theme-{self._current_theme}"' if self._current_theme else ''
        # Download remote images to local cache so Qt WebEngine can display them
        html_body = self._cache_remote_images(html_body)
        # Append meta HTML if present (at the top) followed by body and CDN scripts
        body_content = f"{self._meta_html}{html_body}{self._mermaid_script}{self._katex_script}"
        # Show meta panel by default only if config says so
        if self._show_meta:
            body_content += '<script>try { var m=document.getElementById("meta"); if(m) m.style.visibility="visible"; } catch(e) {}</script>'
        
        # Add JS to catch ArrowLeft for focus switching and to show focus border
        focus_script = """
        <script>
        document.body.style.transition = 'opacity 0.2s';
        if (!document.hasFocus()) {
            document.body.style.opacity = '0.6';
        }
        document.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowLeft') {
                console.log('FOCUS_SIDEBAR');
            }
        });
        window.addEventListener('focus', function() {
            document.body.style.boxShadow = 'inset 0 0 0 4px #58a6ff';
            document.body.style.opacity = '1.0';
        });
        window.addEventListener('blur', function() {
            document.body.style.boxShadow = 'none';
            document.body.style.opacity = '0.6';
        });
        </script>
        """
        body_content += focus_script

        return (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'>{import_links}"
            f"<style>{combined_css}</style>{self._katex_css}</head>"
            f"<body{body_class}>{body_content}</body></html>"
        )

    def _on_load_finished(self, ok: bool):
        """Trigger Mermaid rendering after page load."""
        if ok:
            self.view.page().runJavaScript(
                "try { if(window.mermaid){"
                "  mermaid.initialize({startOnLoad:false,theme:'dark'});"
                "  mermaid.run();"
                "} } catch(e) {}"
            )

    def _reload(self, _path: str = ""):
        """Called by QFileSystemWatcher when the watched file changes."""
        self.watcher.addPath(self.file_path)
        html_body, toc_html = self._render_markdown(self.file_path)
        self.sidebar.clear()
        self._populate_sidebar(toc_html)
        self.view.setHtml(self._build_html(html_body), self._base_url)

    def _jump_to_section(self, item: QTreeWidgetItem):
        """Scroll the web view to the heading whose anchor matches the clicked item."""
        anchor = item.data(0, Qt.UserRole)
        if anchor:
            self.view.page().runJavaScript(
                "try { var el = document.getElementById('" + anchor + "'); if (el) el.scrollIntoView(); } catch(e) {}"
            )

    def _toggle_meta(self):
        """Toggle visibility of the hidden meta div in the rendered page."""
        # Toggle via JavaScript: toggle both visibility and display with safety
        self.view.page().runJavaScript(
            "try {"
            "    var meta = document.getElementById('meta');"
            "    if (meta) {"
            "        if (meta.style.display === 'none') {"
            "            meta.style.display = 'block';"
            "            meta.style.visibility = 'visible';"
            "        } else {"
            "            meta.style.display = 'none';"
            "            meta.style.visibility = 'hidden';"
            "        }"
            "    }"
            "} catch(e) {}"
        )
        # Update internal state and config
        self._show_meta = not self._show_meta
        self.cfg.set('display', 'show_meta', str(self._show_meta).lower())
        _save_config(self.cfg)

    def _zoom_in(self):
        """Increase the zoom factor of the web view."""
        self.view.setZoomFactor(self.view.zoomFactor() + 0.1)

    def _zoom_out(self):
        """Decrease the zoom factor of the web view."""
        factor = self.view.zoomFactor() - 0.1
        if factor > 0.2:
            self.view.setZoomFactor(factor)

    def _show_help(self):
        """Show a concise help dialog with an animated SVG background."""
        dlg = _HelpDialog(self)
        # Use a QWebEngineView for the animated background
        bg_view = QWebEngineView(dlg)
        help_page = _HelpPage(bg_view)
        bg_view.setPage(help_page)
        help_page.closeRequested.connect(dlg.accept)

        bg_view.setHtml("""
<!DOCTYPE html>
<html>
<head>
<style>
  body { margin: 0; overflow: hidden; background: #f8fffb; color: #000; font-family: -apple-system, sans-serif; }
  svg { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1; }
  .content-wrapper { 
      position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
      z-index: 10; display: flex; flex-direction: column; padding: 15px 30px 30px 30px; box-sizing: border-box;
  }
  .help-body { flex: 1; overflow: auto; line-height: 1.5; font-size: 14px; }
  .footer { display: flex; justify-content: space-between; align-items: flex-end; margin-top: 10px; }
  .credit { font-size: 10px; opacity: 0.7; color: #555; }
  .credit a { text-decoration: none; color: inherit; cursor: pointer; }
  .close-btn { 
      background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e1e1e1, stop:1 #a0a0a0);
      border: 1px solid #707070; border-radius: 3px; color: #1a1a1a; 
      padding: 6px 16px; font-weight: bold; font-size: 12px; cursor: pointer;
  }
  h2 { margin-top: 0; margin-bottom: 8px; color: #000; border-bottom: 1px solid rgba(0,0,0,0.1); }
  ul { padding-left: 20px; margin-top: 5px; margin-bottom: 15px; }
  li { margin-bottom: 4px; }
  b { color: #000; }
</style>
</head>
<body>
<svg viewBox="0 0 1000 1000" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
  <defs><filter id="shadowBlur"><feGaussianBlur stdDeviation="50" /></filter></defs>
  <circle r="350" fill="#7db" filter="url(#shadowBlur)">
    <animateMotion path="M-200,500 Q500,-200 1200,500 T-200,500" dur="16s" repeatCount="indefinite" />
    <animate attributeName="opacity" values="0.1; 0.5; 0.1" dur="15.2s" repeatCount="indefinite" />
  </circle>
  <path d="M-100,-100 C200,300 800,0 1100,200 S500,800 -100,1100" fill="#8ec" filter="url(#shadowBlur)">
    <animateTransform attributeName="transform" type="rotate" from="0 500 500" to="360 500 500" dur="29.6s" repeatCount="indefinite" />
    <animate attributeName="opacity" values="0.1; 0.3; 0.1" dur="18.4s" repeatCount="indefinite" />
  </path>
  <circle r="200" fill="#6da" filter="url(#shadowBlur)">
    <animateMotion path="M1200,1200 Q500,500 -200,1200 T1200,1200" dur="20.8s" repeatCount="indefinite" />
    <animate attributeName="opacity" values="0.05; 0.4; 0.05" dur="10.4s" repeatCount="indefinite" />
  </circle>
</svg>
<div class="content-wrapper">
    <div class="help-body">
        <h2>Navigation:</h2>
        <ul>
            <li><b>↑ / ↓</b> – navigate sidebar sections</li>
            <li><b>Page Up / Page Down</b> – scroll display</li>
            <li><b>← / →</b> – move between sidebar and display</li>
            <li><b>Cmd + Shift + &lt; / &gt;</b> – change font size</li>
            <li><b>Cmd + ← / →</b> – navigate among tabs</li>
            <li><b>ESC</b> – close markdown file</li>
        </ul>
        <h2>UI & Features:</h2>
        <ul>
            <li><b>Theme Swatches</b> – click to change colors instantly</li>
            <li><b>Live Reload</b> – updates instantly when file is saved in your editor</li>
            <li><b>Meta Panel (M)</b> – toggle YAML front-matter display</li>
            <li><b>Help (H)</b> – this dialog</li>
        </ul>
        <h2>Tips:</h2>
        <ul>
            <li><b>macOS:</b> select markdown in other apps, right click and use Services/Open in openmd</li>
            <li><b>Themes:</b> edit .openmd.css to make your own themes</li>
        </ul>
    </div>
    <div class="footer">
        <div class="credit">openmd by Rufus Lin (<a href="https://rufuslin.com">rufuslin.com</a>)</div>
        <button class="close-btn" onclick="window.close()">Close</button>
    </div>
</div>
<script>
    window.close = function() {
        console.log("CLOSE_DIALOG");
    };
    // Listen for Escape and Return keys inside the web view
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' || e.key === 'Enter') {
            window.close();
        }
    });
</script>
</body>
</html>
""")
        dlg.layout.addWidget(bg_view)
        dlg.exec()


# ---------------------------------------------------------------------------
# Top-level window: wraps one or more FilePreviewWidget tabs
# ---------------------------------------------------------------------------
# IMPORTANT: The QTabWidget multi-file tab view is intentional and must be
# preserved. When multiple .md files are passed on the command line, each
# opens in its own tab (with its own sidebar). DO NOT collapse to single-file.
# ---------------------------------------------------------------------------

class _UpdatePopup(QDialog):
    """Non-modal, styled popup shown when a newer openmd version is available."""

    def __init__(self, current: str, latest: str, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(False)

        # Outer frame
        frame = QFrame(self)
        frame.setObjectName('updateFrame')
        frame.setStyleSheet("""
            QFrame#updateFrame {
                background: #1c2128;
                border: 1px solid #30363d;
                border-radius: 10px;
            }
            QLabel { color: #c9d1d9; }
            QPushButton {
                background: #238636;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover { background: #2ea043; }
            QPushButton#dismiss {
                background: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
            }
            QPushButton#dismiss:hover { background: #30363d; color: #c9d1d9; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel('\U0001f4e6  openmd update available')
        title.setStyleSheet('font-size: 15px; font-weight: bold; color: #58a6ff;')
        layout.addWidget(title)

        msg = QLabel(
            f'You are on <b>v{current}</b>. '
            f'Version <b>v{latest}</b> is available on PyPI.'
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        cmd_label = QLabel('To upgrade, run:')
        layout.addWidget(cmd_label)

        cmd_box = QLabel('pip install --upgrade openmd')
        cmd_box.setStyleSheet(
            'background: #0d1117; color: #79c0ff; font-family: monospace; '
            'font-size: 13px; padding: 8px 12px; border-radius: 6px; '
            'border: 1px solid #30363d;'
        )
        cmd_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(cmd_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        dismiss_btn = QPushButton('Dismiss')
        dismiss_btn.setObjectName('dismiss')
        dismiss_btn.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(dismiss_btn)
        layout.addLayout(btn_row)

        self.setFixedWidth(380)
        self.adjustSize()

    def show_near_parent(self):
        """Position in the bottom-right corner of the parent window."""
        if self.parent():
            pr = self.parent().geometry()
            x = pr.right() - self.width() - 20
            y = pr.bottom() - self.height() - 20
            self.move(x, y)
        self.show()
        self.raise_()


def _check_for_update(current_version: str, cfg: configparser.ConfigParser,
                      callback) -> None:
    """Run in a background thread. Calls callback(latest_version) if newer.

    Respects a 6-hour cooldown stored in ~/.openmd.config so PyPI is not
    queried on every launch.
    """
    now = time.time()
    last_check = float(cfg.get('update', 'last_check', fallback='0'))
    if now - last_check < UPDATE_CHECK_INTERVAL:
        return

    try:
        url = 'https://pypi.org/pypi/openmd/json'
        req = urllib.request.Request(url, headers={'User-Agent': 'openmd-update-check'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        latest = data['info']['version']

        # Persist the check timestamp regardless of outcome
        if not cfg.has_section('update'):
            cfg.add_section('update')
        cfg.set('update', 'last_check', str(now))
        _save_config(cfg)

        def _parse(v):
            try:
                return tuple(int(x) for x in v.split('.'))
            except Exception:
                return (0,)

        if _parse(latest) > _parse(current_version):
            callback(latest)
    except Exception:
        pass  # silently ignore network errors


class MDPreviewWindow(QMainWindow):
    def __init__(self, tab_widget: QTabWidget, cfg: configparser.ConfigParser):
        super().__init__()
        self.setCentralWidget(tab_widget)
        self.setWindowTitle(f'openmd ({__version__}) by RufusLin')
        self.resize(QSize(1200, 1000))
        self.tab_widget = tab_widget
        self._cfg = cfg
        self._update_popup = None

        # Global shortcuts – M for meta, H for help (no text input in the app)
        self._shortcut_meta = QShortcut(QKeySequence("M"), self)
        self._shortcut_meta.setContext(Qt.WindowShortcut)
        self._shortcut_meta.activated.connect(self._toggle_meta)
        self._shortcut_help = QShortcut(QKeySequence("H"), self)
        self._shortcut_help.setContext(Qt.WindowShortcut)
        self._shortcut_help.activated.connect(self._show_help)
        # Global Escape to quit
        self._shortcut_quit = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._shortcut_quit.setContext(Qt.WindowShortcut)
        self._shortcut_quit.activated.connect(QApplication.quit)

        # Font scaling shortcuts (Cmd+Shift+< and Cmd+Shift+>)
        # Using multiple sequences to ensure it works across all keyboard layouts
        self._shortcut_zoom_in = QShortcut(self)
        self._shortcut_zoom_in.setKey(QKeySequence("Ctrl+Shift+>"))
        self._shortcut_zoom_in.setContext(Qt.WindowShortcut)
        self._shortcut_zoom_in.activated.connect(self._zoom_in)
        
        self._shortcut_zoom_out = QShortcut(self)
        self._shortcut_zoom_out.setKey(QKeySequence("Ctrl+Shift+<"))
        self._shortcut_zoom_out.setContext(Qt.WindowShortcut)
        self._shortcut_zoom_out.activated.connect(self._zoom_out)

        # Fallback for physical keys
        self._shortcut_zoom_in_alt = QShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_Period), self)
        self._shortcut_zoom_in_alt.activated.connect(self._zoom_in)
        self._shortcut_zoom_out_alt = QShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_Comma), self)
        self._shortcut_zoom_out_alt.activated.connect(self._zoom_out)

        # Tab navigation shortcuts
        self._shortcut_prev_tab = QShortcut(QKeySequence("Ctrl+Left"), self)
        self._shortcut_prev_tab.setContext(Qt.WindowShortcut)
        self._shortcut_prev_tab.activated.connect(self._prev_tab)
        
        self._shortcut_next_tab = QShortcut(QKeySequence("Ctrl+Right"), self)
        self._shortcut_next_tab.setContext(Qt.WindowShortcut)
        self._shortcut_next_tab.activated.connect(self._next_tab)

        # Kick off update check in background after a short delay so the
        # window has time to appear before any popup is shown.
        QTimer.singleShot(3000, self._start_update_check)

    def _prev_tab(self):
        """Switch to the previous tab with wraparound."""
        count = self.tab_widget.count()
        if count > 1:
            idx = (self.tab_widget.currentIndex() - 1) % count
            self.tab_widget.setCurrentIndex(idx)

    def _next_tab(self):
        """Switch to the next tab with wraparound."""
        count = self.tab_widget.count()
        if count > 1:
            idx = (self.tab_widget.currentIndex() + 1) % count
            self.tab_widget.setCurrentIndex(idx)

    def _toggle_meta(self):
        """Toggle visibility of the meta panel in the active tab."""
        if self.tab_widget.count() == 0:
            return
        current = self.tab_widget.currentWidget()
        if hasattr(current, '_toggle_meta'):
            current._toggle_meta()

    def _show_help(self):
        """Show the help dialog from the active tab."""
        if self.tab_widget.count() == 0:
            return
        current = self.tab_widget.currentWidget()
        if hasattr(current, '_show_help'):
            current._show_help()

    def _zoom_in(self):
        """Zoom in the active tab."""
        if self.tab_widget.count() == 0:
            return
        current = self.tab_widget.currentWidget()
        if hasattr(current, '_zoom_in'):
            current._zoom_in()

    def _zoom_out(self):
        """Zoom out the active tab."""
        if self.tab_widget.count() == 0:
            return
        current = self.tab_widget.currentWidget()
        if hasattr(current, '_zoom_out'):
            current._zoom_out()

    def _start_update_check(self):
        thread = threading.Thread(
            target=_check_for_update,
            args=(__version__, self._cfg, self._on_update_found),
            daemon=True,
        )
        thread.start()

    def _on_update_found(self, latest: str):
        """Called from background thread — must schedule UI work on main thread."""
        QTimer.singleShot(0, lambda: self._show_update_popup(latest))

    def _show_update_popup(self, latest: str):
        self._update_popup = _UpdatePopup(__version__, latest, parent=self)
        self._update_popup.show_near_parent()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            QApplication.quit()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_markdown(path: str) -> bool:
    return path.lower().endswith('.md')


def pick_file_curses() -> str:
    """Return a selected .md file from the current directory using curses."""
    md_files = [f for f in os.listdir('.') if is_markdown(f) and os.path.isfile(f)]
    md_files.sort()
    if not md_files:
        sys.exit("No markdown files found in the current directory.")
    selected = 0
    if curses:
        def draw(stdscr):
            nonlocal selected
            stdscr.keypad(True)
            curses.curs_set(0)
            while True:
                stdscr.clear()
                stdscr.addstr(0, 0, "Select a Markdown file (\u2191\u2193 navigate, Enter select, Esc quit)")
                for idx, f in enumerate(md_files):
                    y = 2 + idx
                    if y >= curses.LINES - 1:
                        break
                    stdscr.addstr(y, 2, f"{'>' if idx == selected else ' '} {f}")
                stdscr.refresh()
                key = stdscr.getch()
                if key == curses.KEY_UP and selected > 0:
                    selected -= 1
                elif key == curses.KEY_DOWN and selected < len(md_files) - 1:
                    selected += 1
                elif key in (curses.KEY_ENTER, 10, 13):
                    return
                elif key == 27:
                    sys.exit(0)
        try:
            curses.wrapper(draw)
        except SystemExit:
            raise
        except Exception:
            pass
    else:
        for i, f in enumerate(md_files, 1):
            print(f"{i}. {f}")
        choice = input("Select number (or ENTER to cancel): ").strip()
        if not choice:
            sys.exit(0)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(md_files):
                selected = idx
            else:
                sys.exit(0)
        except ValueError:
            sys.exit(0)
    return md_files[selected]


def _ensure_macos_service():
    """Silently install/update the 'Open in openmd' macOS service if on Darwin."""
    if sys.platform != 'darwin':
        return

    service_path = os.path.expanduser('~/Library/Services/Open in openmd.workflow')
    contents_path = os.path.join(service_path, 'Contents')
    res_path = os.path.join(contents_path, 'Resources', 'English.lproj')
    
    try:
        os.makedirs(res_path, exist_ok=True)
        executable_path = os.path.abspath(sys.argv[0])

        # Info.plist ensures the Service name is registered correctly
        info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>English</string>
	<key>CFBundleIdentifier</key>
	<string>com.rufuslin.openmd.service</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>Open in openmd</string>
	<key>CFBundlePackageType</key>
	<string>BNDL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleSignature</key>
	<string>????</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>NSServices</key>
	<array>
		<dict>
			<key>NSMenuItem</key>
			<dict>
				<key>default</key>
				<string>Open in openmd</string>
			</dict>
			<key>NSMessage</key>
			<string>runWorkflow</string>
			<key>NSPortName</key>
			<string>com.rufuslin.openmd.service</string>
			<key>NSSendTypes</key>
			<array>
				<string>public.plain-text</string>
			</array>
		</dict>
	</array>
</dict>
</plist>
"""
        with open(os.path.join(contents_path, 'Info.plist'), 'w', encoding='utf-8') as f:
            f.write(info_plist)

        # Localized name ensures macOS displays it correctly in the menu
        strings_content = '"Open in openmd" = "Open in openmd";\n'
        with open(os.path.join(res_path, 'ServicesMenu.strings'), 'w', encoding='utf-16') as f:
            f.write(strings_content)

        # document.wflow XML content
        wflow_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>actions</key>
	<array>
		<dict>
			<key>action</key>
			<dict>
				<key>AMActionVersion</key>
				<string>2.0.3</string>
				<key>ActionBundlePath</key>
				<string>/System/Library/Automator/Run Shell Script.action</string>
				<key>ActionName</key>
				<string>Run Shell Script</string>
				<key>ActionParameters</key>
				<dict>
					<key>COMMAND_STRING</key>
					<string>TS=$(date +%s)
temp_file="/tmp/openmd_selection_$TS.md"
cat &gt; "$temp_file"
nohup "{executable_path}" "$temp_file" &gt;/dev/null 2&gt;&amp;1</string>
					<key>CheckedForUserDefaultShell</key>
					<true/>
					<key>inputMethod</key>
					<integer>0</integer>
					<key>shell</key>
					<string>/bin/bash</string>
					<key>source</key>
					<string></string>
				</dict>
				<key>BundleIdentifier</key>
				<string>com.apple.RunShellScript</string>
				<key>CFBundleVersion</key>
				<string>2.0.3</string>
				<key>CanShowSelectedItemsWhenRun</key>
				<false/>
				<key>CanShowWhenRun</key>
				<true/>
				<key>Category</key>
				<array>
					<string>AMCategoryUtilities</string>
				</array>
				<key>Class Name</key>
				<string>RunShellScriptAction</string>
				<key>InputUUID</key>
				<string>9B6B676B-066F-4C2E-8E5A-7A574E987E01</string>
				<key>Keywords</key>
				<array>
					<string>Shell</string>
					<string>Script</string>
					<string>Command</string>
					<string>Run</string>
					<string>Unix</string>
				</array>
				<key>OutputUUID</key>
				<string>E8D8E9E8-0D9E-4D9E-8D9E-8E9D8E9D8E9D</string>
				<key>UUID</key>
				<string>9B6B676B-066F-4C2E-8E5A-7A574E987E02</string>
				<key>UnlocalizedApplications</key>
				<array>
					<string>Automator</string>
				</array>
				<key>arguments</key>
				<dict>
					<key>0</key>
					<dict>
						<key>default value</key>
						<integer>0</integer>
						<key>name</key>
						<string>inputMethod</string>
						<key>required</key>
						<string>0</string>
						<key>type</key>
						<string>0</string>
						<key>uuid</key>
						<string>0</string>
					</dict>
					<key>4</key>
					<dict>
						<key>default value</key>
						<string>/bin/sh</string>
						<key>name</key>
						<string>shell</string>
						<key>required</key>
						<string>0</string>
						<key>type</key>
						<string>0</string>
						<key>uuid</key>
						<string>4</string>
					</dict>
				</dict>
			</dict>
		</dict>
	</array>
	<key>workflowMetaData</key>
	<dict>
		<key>serviceInputTypeIdentifier</key>
		<string>com.apple.Automator.text</string>
		<key>serviceOutputTypeIdentifier</key>
		<string>com.apple.Automator.nothing</string>
		<key>serviceProcessesInput</key>
		<integer>0</integer>
		<key>workflowTypeIdentifier</key>
		<string>com.apple.Automator.servicesMenu</string>
	</dict>
</dict>
</plist>
"""
        with open(os.path.join(contents_path, 'document.wflow'), 'w', encoding='utf-8') as f:
            f.write(wflow_content)

        # Force macOS to recognize the updated bundle and its name
        ls_reg = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
        subprocess.run([ls_reg, "-f", service_path], capture_output=True)
        # Flush the pasteboard services cache
        subprocess.run(["/System/Library/CoreServices/pbs", "-flush"], capture_output=True)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point — used both by direct invocation and by the pip console script."""
    # Ensure macOS service is installed first
    _ensure_macos_service()

    # Determine files to open
    if len(sys.argv) < 2:
        file_path = pick_file_curses()
        md_files = [file_path]
    else:
        files = sys.argv[1:]
        md_files = [f for f in files if is_markdown(f)]
        if not md_files:
            sys.exit("No markdown files matched the given pattern(s).")
        if len(md_files) > 6:
            sys.stderr.write("Warning: more than 6 files supplied; showing first 6.\n")
            md_files = md_files[:6]

    # Re-exec as a detached child if needed
    if sys.platform != 'win32' and os.environ.get('_OPENMD_CHILD') != '1':
        env = os.environ.copy()
        env['_OPENMD_CHILD'] = '1'
        # Pass the (potentially picked) file as an argument to the child
        subprocess.Popen(
            [sys.executable] + [sys.argv[0]] + md_files,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
        os._exit(0)

    try:
        # Standard Qt app startup
        app = QApplication(sys.argv)
        cfg = _load_config()
        tab_widget = QTabWidget()
        for f in md_files:
            widget = FilePreviewWidget(f, cfg)
            tab_widget.addTab(widget, os.path.basename(f))
        window = MDPreviewWindow(tab_widget, cfg)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        sys.stderr.write(f"Fatal error: {type(e).__name__}: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
