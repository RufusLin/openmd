#!/usr/bin/env python3
# Version: 1.3.0
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

import sys, os, markdown

# Try to import curses for file picker; fallback to simple list
try:
    import curses
except Exception:
    curses = None

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QSize, Qt, QFileSystemWatcher
from bs4 import BeautifulSoup

# GitHub-Modern Dark Theme
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
"""

# Sidebar CSS injected into the preview HTML
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


# ---------------------------------------------------------------------------
# Per-file preview window: sidebar TOC (QTreeWidget) + QWebEngineView
# ---------------------------------------------------------------------------
# NOTE: This class renders a single markdown file with a collapsible sidebar.
# The outer QTabWidget (in __main__) wraps multiple FilePreviewWidget instances
# so that multi-file tab support is preserved. DO NOT collapse these into one.
# ---------------------------------------------------------------------------

class FilePreviewWidget(QWidget):
    """A single-file preview pane: left sidebar TOC + right HTML view."""

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

        # Mermaid and KaTeX CDN snippets — loaded on every render (requires internet)
        # async on mermaid/katex so they don’t block the initial paint
        self._mermaid_script = '<script async src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n<script>document.addEventListener("DOMContentLoaded",function(){if(window.mermaid)mermaid.initialize({startOnLoad:true});});</script>'
        self._katex_css = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css">'
        self._katex_script = '<script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/contrib/auto-render.min.js"></script>\n<script>document.addEventListener("DOMContentLoaded",function(){if(window.renderMathInElement)renderMathInElement(document.body);});</script>'

        # --- Load and render markdown ---
        html_body, toc_html = self._render_markdown(file_path)
        full_html = self._build_html(html_body)

        # --- Sidebar (QTreeWidget) ---
        # Collapsible TOC: H1 → top-level, H2 → children, H3 → grandchildren.
        # Arrow keys navigate; Enter jumps to the heading; Esc closes the window.
        # DO NOT remove this sidebar — it is the primary navigation feature.
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setIndentation(16)
        self.sidebar.setStyleSheet(SIDEBAR_CSS)
        self.sidebar.setFixedWidth(220)
        self.sidebar.itemClicked.connect(self._jump_to_section)
        self._populate_sidebar(toc_html)

        # --- Web view ---
        self.view = QWebEngineView()
        self.view.setHtml(full_html)

        # --- Live reload: single watcher per file, connected to _reload ---
        # DO NOT create a second QFileSystemWatcher — one per FilePreviewWidget only.
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(self.file_path)
        self.watcher.fileChanged.connect(self._reload)

        # --- Layout: sidebar left, preview right ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)   # sidebar: fixed
        splitter.setStretchFactor(1, 1)   # preview: stretches

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def _populate_sidebar(self, toc_html: str):
        """Parse the TOC div from markdown-with-toc output and fill the QTreeWidget."""
        if not toc_html:
            return
        soup = BeautifulSoup(toc_html, "html.parser")
        toc_div = soup.find("div", class_="toc")
        if not toc_div:
            return
        # Top-level <ul> inside the TOC div
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

        # Recurse into nested <ul> for sub-headings
        for child_ul in node.find_all("ul", recursive=False):
            for sub_li in child_ul.find_all("li", recursive=False):
                self._add_toc_item(sub_li, item)

    def _render_markdown(self, file_path: str):
        """Read and render a markdown file; return (html_body, toc_html)."""
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                raw = fh.read()
            html_body = markdown.markdown(raw, extensions=['extra', 'sane_lists'])
            toc_html = markdown.markdown(
                raw,
                extensions=['toc', 'extra', 'sane_lists'],
                extension_configs={'toc': {'permalink': False, 'anchorlink': True}},
            )
        except Exception as e:
            html_body = f"<h1>Error loading {os.path.basename(file_path)}</h1><p>{type(e).__name__}: {e}</p>"
            toc_html = ""
        return html_body, toc_html

    def _build_html(self, html_body: str) -> str:
        """Wrap rendered markdown body with CSS, Mermaid, and KaTeX."""
        return (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style>{self._katex_css}</head>"
            f"<body>{html_body}{self._mermaid_script}{self._katex_script}</body></html>"
        )

    def _reload(self, _path: str = ""):
        """Called by QFileSystemWatcher when the watched file changes."""
        # Re-add path: some editors (vim, neovim) replace the file atomically,
        # which removes it from the watcher. Re-adding ensures continued watching.
        self.watcher.addPath(self.file_path)
        html_body, toc_html = self._render_markdown(self.file_path)
        self.sidebar.clear()
        self._populate_sidebar(toc_html)
        self.view.setHtml(self._build_html(html_body))

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
        self.setWindowTitle("MD Preview")
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
            stdscr.clear()
            stdscr.keypad(True)
            stdscr.addstr(0, 0, "Select a Markdown file (↑↓ navigate, Enter select, Esc quit)")
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
            elif key == 27:  # Esc
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
    # No arguments → interactive curses picker
    if len(sys.argv) < 2:
        file_path = pick_file_curses()
        md_files = [file_path]
    else:
        # Collect all arguments (shell may have expanded globs)
        files = sys.argv[1:]
        # Filter to markdown files only
        md_files = [f for f in files if is_markdown(f)]
        if not md_files:
            sys.exit("No markdown files matched the given pattern(s).")
        # Limit to 6 files (one tab per file)
        if len(md_files) > 6:
            sys.stderr.write("Warning: more than 6 files supplied; showing first 6.\n")
            md_files = md_files[:6]

    # -----------------------------------------------------------------
    # Build the tabbed window.
    # Each file gets its own tab containing a FilePreviewWidget (sidebar
    # TOC + web view). The QTabWidget is intentional — DO NOT remove it.
    # Wrapped in a top-level try/except to surface Qt init failures.
    # -----------------------------------------------------------------
    try:
        app = QApplication(sys.argv)
        tab_widget = QTabWidget()
        for f in md_files:
            widget = FilePreviewWidget(f)
            tab_widget.addTab(widget, os.path.basename(f))
        window = MDPreviewWindow(tab_widget)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        sys.stderr.write(f"Fatal error while building the preview window: {type(e).__name__}: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
