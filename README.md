# openmd

**Markdown viewer for humans — not AI models.**

I got tired of reading raw Markdown with `less` or opening VS Code/Cursor just to see it nicely rendered. So I built **openmd**.

Run `openmd *.md` (or any Markdown files) from the shell and a window pops up with:
- Tabs for multiple files (up to 6)
- Live reload when you save in your editor
- Mermaid diagrams and KaTeX math
- Collapsible navigation sidebar (TOC)
- Full customization via `.openmd.css`

No browser, no TUI — just proper rendering with nice fonts and styles. It runs in the background so the window stays completely independent.

**Built this for myself and I use it every day - because nice-looking text matters!** 🤣

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey) ![PyPI version](https://img.shields.io/pypi/v/openmd)

**GitHub:** [RufusLin/openmd](https://github.com/RufusLin/openmd)

**Warning - Lazy Maintainer:** Yeah, not a fan of reading PRs, but will pay attention to issues to fix bugs. Feel free to fork, but remember to give credit, please.🙏🏻

X: @rufuslinjapan

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

Add to your `~/.zshrc` or `~/.bashrc` for quick access to remote files:

```zsh
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

## What it looks like

![openmd with multiple tabs and TOC sidebar](pix/1.png)
![Mermaid diagram and KaTeX math rendered](pix/2.png)

*(Click any image to enlarge)*

## Features

- **GitHub-dark theme** — comfortable reading in low-light environments. BUT! Change it to whatever you like in `.openmd.css`
- **Live reload** — the preview updates instantly when the file is saved; no manual refresh needed
- **Mermaid diagrams** — fenced ` ```mermaid ` blocks render automatically via CDN
- **KaTeX math** — Formulae? inline `$…$` and display `$$…$$` expressions render out of the box
- **Collapsible sidebar TOC** — hierarchical, of course; click any heading to jump to it
- **Multi-file tabs** — pass multiple `.md` files (even `*.md` globs) and each opens in its own tab, max 6
- **Interactive file picker** — run with no arguments and choose from `.md` files in the current directory via a curses-based picker — no need to copy and paste file names
- **Remote preview** — optional `remotemd` shell alias pulls a file from a remote host via `scp` and opens it instantly
- **Keyboard shortcuts** — `Esc` closes the window; arrow keys navigate the sidebar

---

## Requirements

- macOS, Linux, Posix 
- Python 3.8+ 
- [PySide6](https://pypi.org/project/PySide6/)
- [Markdown](https://pypi.org/project/Markdown/)
- [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/)

**Note:** Mermaid and KaTeX require an internet connection to load from CDN.

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

## Keyboard shortcuts in sidebar

| Key | Action |
|-----|--------|
| `Esc` | Close the preview window |
| `↑` / `↓` | Navigate the sidebar TOC |
| Return | Jump to selected section |

---

## License

MIT
