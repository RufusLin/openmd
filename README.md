# openmd

A fast, minimal Markdown previewer for macOS with a GitHub-dark theme, collapsible sidebar TOC, and multi-file tab support.

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)

---

## Features

- **GitHub-dark theme** — comfortable reading in low-light environments
- **Collapsible sidebar TOC** — H1 → top-level, H2 → children, H3 → grandchildren; click any heading to jump to it
- **Multi-file tabs** — pass multiple `.md` files and each opens in its own tab
- **Interactive file picker** — run with no arguments and choose from `.md` files in the current directory via a curses-based picker
- **Remote preview** — optional `remotemd` shell alias pulls a file from a remote host via `scp` and opens it instantly
- **Keyboard shortcuts** — `Esc` closes the window; arrow keys navigate the sidebar

---

## Requirements

- macOS (uses PySide6/Qt WebEngine)
- Python 3.8+
- [PySide6](https://pypi.org/project/PySide6/)
- [Markdown](https://pypi.org/project/Markdown/)
- [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/)

---

## Installation

### pip (recommended)

```bash
pip install openmd
```

After installing, the `openmd` command is available in your shell.

### From source

```bash
git clone https://github.com/RufusLin/openmd.git
cd openmd
pip install -e .
```

---

## Usage

```bash
# Open a single file
openmd README.md

# Open multiple files (each in its own tab)
openmd doc1.md doc2.md doc3.md

# No arguments — interactive picker (choose from .md files in current directory)
openmd

# Glob expansion
openmd docs/*.md
```

### Shell aliases (optional)

Add to your `~/.zshrc` or `~/.bashrc` for quick access:

```zsh
# Local preview — opens in background
localmd() {
    openmd "$@" >/dev/null 2>&1 &
}

# Remote preview via SSH (requires a 'home' SSH alias in ~/.ssh/config)
remotemd() {
    local remote_path="$1"
    local filename=$(basename "$remote_path")
    local tmp_file="/tmp/remote_preview_${filename}.md"
    scp "home:$remote_path" "$tmp_file" && \
    openmd "$tmp_file" >/dev/null 2>&1 &
}
```

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Esc` | Close the preview window |
| `↑` / `↓` | Navigate the sidebar TOC |
| Click heading | Jump to that section |

---

## License

MIT
