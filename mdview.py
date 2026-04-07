#!/usr/bin/env python3
# Version: 1.2.1
# Updated with curses file picker and markdown-only filter
# mdview.py - Simple Markdown previewer
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

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QSize, Qt

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

class MDPreviewWindow(QMainWindow):
    def __init__(self, tab_widget):
        super().__init__()
        self.setCentralWidget(tab_widget)
        self.setWindowTitle("MD Preview")
        self.resize(QSize(1000, 1100))
        self.tab_widget = tab_widget
        self.keyPressEvent = self._keyPressEvent

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            QApplication.quit()
        else:
            super().keyPressEvent(event)

def is_markdown(path):
    return path.lower().endswith('.md')

def pick_file_curses():
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
            stdscr.keypad(True)
            stdscr.addstr(0, 0, "Select a Markdown file")
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
                # selection made; exit draw function to let wrapper return
                return
        try:
            curses.wrapper(draw)
        except SystemExit:
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

if __name__ == "__main__":
    # No arguments → interactive picker
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
        # Limit to 6 files
        if len(md_files) > 6:
            sys.stderr.write("Warning: more than 6 files supplied; showing first 6.\n")
            md_files = md_files[:6]

    # -----------------------------------------------------------------
    # Build the tabbed window – wrapped in a top-level try/except so we
    # can report any unexpected error (e.g. a file that cannot be opened)
    # -----------------------------------------------------------------
    try:
        app = QApplication(sys.argv)
        tab_widget = QTabWidget()
        for f in md_files:
            tab = QWidget()
            view = QWebEngineView()
            try:
                with open(f, 'r', encoding='utf-8') as file_obj:
                    content = file_obj.read()
                    html_body = markdown.markdown(content, extensions=['extra', 'sane_lists'])
            except Exception as e:
                # Show the exact path that failed – this will appear in the UI
                html_body = f"<h1>Error loading {os.path.basename(f)}</h1><p>{type(e).__name__}: {e}</p>"
            full_html = f"<html><head><style>{CSS}</style></head><body>{html_body}</body></html>"
            view.setHtml(full_html)
            tab_layout = QVBoxLayout()
            tab_layout.addWidget(view)
            tab.setLayout(tab_layout)
            tab_widget.addTab(tab, os.path.basename(f))
        tab_widget.setWindowTitle("MD Preview")
        tab_widget.resize(QSize(1000, 1100))
        tab_widget.show()
        sys.exit(app.exec())
    except Exception as e:
        # If something goes wrong *after* the loop (e.g. Qt init failure),
        # we still want to tell the user what happened.
        sys.stderr.write(f"Fatal error while building the preview window: {type(e).__name__}: {e}\n")
        sys.exit(1)