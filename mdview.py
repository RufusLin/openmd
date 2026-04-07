# Updated with curses file picker and markdown-only filter
# mdview.py - Simple Markdown previewer
# -------------------------------------------------
# This script is invoked by shell aliases defined in ~/.zshrc:
#
#   localmd() {
#       $MD_VIEWER_PY $MD_VIEWER_SCRIPT "$1" >/dev/null 2>&1 &
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
#
# -------------------------------------------------

import sys, os, markdown

# Try to import curses for file picker; fallback to simple list
try:
    import curses
except Exception:
    curses = None

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QSize

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

def is_markdown(path):
    return path.lower().endswith('.md')

def pick_file_curses():
    # List .md files in current directory
    md_files = [f for f in os.listdir('.') if is_markdown(f) and os.path.isfile(f)]
    md_files.sort()
    if not md_files:
        sys.exit("No markdown files found in the current directory.")
    # Use curses to let user select a file
    selected = 0
    if curses:
        def draw(stdscr):
            nonlocal selected
            stdscr.clear()
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
                # Enter pressed
                sys.exit(0)  # will be caught later; we'll just return after wrapper
        curses.wrapper(draw)
        # After wrapper, selected holds the index; return that file
        return md_files[selected]
    else:
        for i, f in enumerate(md_files, 1):
            print(f"{i}. {f}")
        choice = input("Select number (or ENTER to cancel): ").strip()
        if not choice:
            sys.exit(0)
        try:
            idx = int(choice) - 1
            return md_files[idx] if 0 <= idx < len(md_files) else None
        except ValueError:
            sys.exit(0)



if __name__ == "__main__":
    # No arguments -> interactive picker
    if len(sys.argv) < 2:
        file_path = pick_file_curses()
    else:
        # Collect all arguments (shell may have expanded globs)
        files = sys.argv[1:]
        # Filter to markdown files only
        md_files = [f for f in files if is_markdown(f)]
        if not md_files:
            sys.exit("No markdown files matched the given pattern(s).")
        # Limit to 6 files
        if len(md_files) > 6:
            sys.stderr.write(f"Warning: more than 6 files supplied; showing first 6.\\n")
            md_files = md_files[:6]
        # Create tabbed window
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
                html_body = f"<h1>Error</h1><p>{str(e)}</p>"
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