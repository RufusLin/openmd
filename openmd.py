#!/usr/bin/env python3
# Version: 1.4.16
# Added hierarchical QTreeWidget TOC sidebar (H1→top, H2→children, H3→grandchildren).
# Tabs are intentionally preserved — DO NOT remove the QTabWidget multi-file tab view.
# openmd.py - Simple Markdown previewer with sidebar TOC
# -------------------------------------------------
# This script is invoked by shell aliases defined in ~/.zshrc:
#
#   localmd() {
#       $MD_VIEWER_PY $MD_VIEWER_SCRIPT "$@" >/dev/null 2>&1 &
#   }
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

import sys, os, re, markdown, configparser, hashlib, tempfile, subprocess
import urllib.request

# Try to import curses for file picker; fallback to simple list
try:
    import curses
except Exception:
    curses = None

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem, QPushButton,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QSize, Qt, QFileSystemWatcher, QUrl
from PySide6.QtGui import QKeyEvent, QColor, QDesktopServices
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
code { background-color: rgba(110,118,129,0.4); padding: 0.2em 0.4em; border-radius: 6px; font-size: 85%; }
table { border-collapse: collapse; width: 100%; margin: 24px 0; border: 1px solid #30363d; }
table th, table td { border: 1px solid #30363d; padding: 8px 12px; }
table tr:nth-child(even) { background-color: #161b22; }
h1 a, h2 a, h3 a, h4 a, h5 a, h6 a { color: inherit; text-decoration: none; }
"""

# Sidebar Qt stylesheet
SIDEBAR_CSS = """
QTreeWidget {
    background: #161b22;
    color: #c9d1d9;
    border-right: 1px solid #30363d;
    font-size: 13px;
}
QTreeWidget::item:hover { background: #212730; }
QTreeWidget::item:selected { background: #1f6feb; color: #ffffff; }
"""

CONFIG_PATH = os.path.expanduser('~/.openmd.config')


def _load_user_css() -> str:
    """Load .openmd.css from cwd, script install dir, or home dir (first match wins).

    The user CSS is appended after the built-in CSS so any rule in .openmd.css
    overrides the matching default via normal CSS cascade.
    """
    candidates = [
        os.path.join(os.getcwd(), '.openmd.css'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.openmd.css'),
        os.path.expanduser('~/.openmd.css'),
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

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        scheme = url.scheme()
        if scheme in ('http', 'https'):
            try:
                QDesktopServices.openUrl(url)
            except Exception:
                pass
            return False  # block in-window navigation regardless
        return True  # allow file://, data:, about:blank, anchor jumps, etc.


class _SidebarTree(QTreeWidget):
    """QTreeWidget that fires itemClicked when Return/Enter is pressed."""

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            item = self.currentItem()
            if item:
                self.itemClicked.emit(item, 0)
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Per-file preview window: sidebar TOC (QTreeWidget) + QWebEngineView
# ---------------------------------------------------------------------------
# NOTE: This class renders a single markdown file with a collapsible sidebar.
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

        # KaTeX CDN snippets
        self._katex_css = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css">'
        self._katex_script = (
            '<script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js"></script>\n'
            '<script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/contrib/auto-render.min.js"></script>\n'
            '<script>'
            'document.addEventListener("DOMContentLoaded",function(){'
            'if(window.renderMathInElement)renderMathInElement(document.body,{'
            'delimiters:[{left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false}]'
            '});});'
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
        self.sidebar.setStyleSheet(SIDEBAR_CSS)
        self.sidebar.setFixedWidth(220)
        self.sidebar.itemClicked.connect(self._jump_to_section)
        self._populate_sidebar(toc_html)

        # --- Theme swatch bar at the foot of the sidebar ---
        self._swatch_bar = self._build_swatch_bar()

        # --- Sidebar column: tree + swatch bar ---
        sidebar_col = QWidget()
        sidebar_col.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar_col)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(self.sidebar)
        sidebar_layout.addWidget(self._swatch_bar)

        # --- Web view ---
        self.view = QWebEngineView()
        self.view.setPage(_OpenMDPage(self.view))  # intercept external links
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

        # --- Live reload ---
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(self.file_path)
        self.watcher.fileChanged.connect(self._reload)

        # --- Layout: sidebar left, preview right ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar_col)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

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
        """Apply a theme by setting a class on <body>.

        The CSS uses descendant selectors (body.theme-xxx pre, body.theme-xxx code, etc.)
        so setting the class on <body> alone is sufficient — all child elements inherit
        the theme via normal CSS cascade.
        """
        self._current_theme = theme_name
        _set_saved_theme(self.cfg, theme_name)
        self.view.page().runJavaScript(
            f"document.body.className = 'theme-{theme_name}';"
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
            md = markdown.Markdown(
                extensions=['toc', 'extra', 'sane_lists'],
                extension_configs={'toc': {'permalink': False, 'anchorlink': True}},
            )
            html_body = md.convert(raw)
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
        return html_body, toc_html

    def _cache_remote_images(self, html_body: str) -> str:
        """Download remote http/https images to a temp cache dir and rewrite src.

        Qt WebEngine cannot load remote images from a file:// origin even with
        LocalContentCanAccessRemoteUrls. This workaround fetches remote images
        once, caches them by URL hash in tempfile.gettempdir(), and rewrites
        the <img src> to a local file:// path so Qt can display them.
        Uses BeautifulSoup for robust attribute parsing (handles all quote styles
        and HTML-encoded URLs).
        """
        cache_dir = os.path.join(tempfile.gettempdir(), 'openmd_img_cache')
        os.makedirs(cache_dir, exist_ok=True)

        soup = BeautifulSoup(html_body, 'html.parser')
        modified = False
        for img in soup.find_all('img'):
            url = img.get('src', '')
            if not url.startswith(('http://', 'https://')):
                continue
            url_hash = hashlib.md5(url.encode()).hexdigest()
            # Guess extension from URL path component, default to .png
            ext = os.path.splitext(url.split('?')[0])[1]
            if not ext or len(ext) > 5:
                ext = '.png'
            cached_path = os.path.join(cache_dir, url_hash + ext)
            if not os.path.exists(cached_path):
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'openmd/1.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        with open(cached_path, 'wb') as f:
                            f.write(resp.read())
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
        return (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'>{import_links}"
            f"<style>{combined_css}</style>{self._katex_css}</head>"
            f"<body{body_class}>{html_body}{self._mermaid_script}{self._katex_script}</body></html>"
        )

    def _on_load_finished(self, ok: bool):
        """Trigger Mermaid rendering after page load."""
        if ok:
            self.view.page().runJavaScript(
                "if(window.mermaid){"
                "  mermaid.initialize({startOnLoad:false,theme:'dark'});"
                "  mermaid.run();"
                "}"
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
                f"var el = document.getElementById('{anchor}'); if (el) el.scrollIntoView();"
            )


# ---------------------------------------------------------------------------
# Top-level window: wraps one or more FilePreviewWidget tabs
# ---------------------------------------------------------------------------
# IMPORTANT: The QTabWidget multi-file tab view is intentional and must be
# preserved. When multiple .md files are passed on the command line, each
# opens in its own tab (with its own sidebar). DO NOT collapse to single-file.
# ---------------------------------------------------------------------------

class MDPreviewWindow(QMainWindow):
    def __init__(self, tab_widget: QTabWidget):
        super().__init__()
        self.setCentralWidget(tab_widget)
        self.setWindowTitle("openmd by RufusLin")
        self.resize(QSize(1200, 1000))
        self.tab_widget = tab_widget

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point — used both by direct invocation and by the pip console script."""
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

    # Re-exec as a detached child so the shell prompt returns immediately.
    # Using subprocess.Popen instead of os.fork() avoids the macOS
    # DeprecationWarning about fork() in a multi-threaded process (Qt/ObjC
    # runtime threads are already running by the time main() is called).
    # The _OPENMD_CHILD env var prevents the child from re-spawning itself.
    # start_new_session=True is the setsid() equivalent — detaches from the
    # terminal's process group so SIGHUP on terminal close does not reach it.
    # Skip on Windows (no start_new_session support in the same way).
    if sys.platform != 'win32' and os.environ.get('_OPENMD_CHILD') != '1':
        env = os.environ.copy()
        env['_OPENMD_CHILD'] = '1'
        subprocess.Popen(
            [sys.executable] + sys.argv,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
        os._exit(0)

    try:
        app = QApplication(sys.argv)
        cfg = _load_config()
        tab_widget = QTabWidget()
        for f in md_files:
            widget = FilePreviewWidget(f, cfg)
            tab_widget.addTab(widget, os.path.basename(f))
        window = MDPreviewWindow(tab_widget)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        sys.stderr.write(f"Fatal error while building the preview window: {type(e).__name__}: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
