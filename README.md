# openmd - by Rufus Lin

**Markdown viewer for humans (not AI models).**

I got tired of reading raw Markdown with `less` or opening VS Code/Cursor just to see it nicely rendered. So I built **openmd**.

Run `openmd *.md` (or any Markdown file) from the shell and a window pops up instantly. Independent Qt window, ESC closes it. Think of it as "less" but for markdown files.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Platform: macOS / Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey) ![PyPI version](https://img.shields.io/pypi/v/openmd)

**GitHub:** [RufusLin/openmd](https://github.com/RufusLin/openmd)

**Warning - Lazy Maintainer:** Yeah, not a fan of reading PRs, but will pay attention to issues to fix bugs. Feel free to fork, but remember to give credit, please.🙏🏻

X: @rufuslinjapan

---

## What it looks like

<video src="https://github.com/user-attachments/assets/42f0b30d-5d7a-4e61-98c6-c3354ad10e16" width="85%" controls></video>

###openmd renders markdown
<img src="https://raw.githubusercontent.com/RufusLin/openmd/main/pix/1.jpg" width="85%" alt="openmd with multiple tabs and TOC sidebar">

###CSS themes (customizable)
<img src="https://raw.githubusercontent.com/RufusLin/openmd/main/pix/2.png" width="85%" alt="CSS themes (customizable)">

###Mermaid, KaTeX too!
<img src="https://raw.githubusercontent.com/RufusLin/openmd/main/pix/3.png" width="85%" alt="Mermaid diagram and KaTeX math rendered">

---

## Usage

```
# Open a single file (extension optional!)
openmd README
openmd README.md

# Open most recently viewed file
openmd -r

# Open multiple files (each in its own tab, up to 12)
openmd doc1 doc2.markdown doc3

# No arguments — interactive picker (choose from .md files in current directory)
openmd

# Glob expansion (works on Windows & POSIX shells)
openmd docs/*.md

# Check CLI version or help
openmd -v
openmd --help

# Pipe stdio
tail -100 x.md | openmd

# on MacOS, render selected markdown
Select text, right click, Services, "Open in openmd"
```

### Remote preview via SSH (optional)

```
remotemd() {
    local remote_path="$1"
    local filename=$(basename "$remote_path")
    local tmp_file="/tmp/remote_preview_${filename}.md"
    scp "home:$remote_path" "$tmp_file" && openmd "$tmp_file"
}
```

---

## Features

- **Auto `.md` Extension & Path Resolution** — run `openmd filename` without `.md` and openmd automatically resolves `.md`, `.markdown`, `.mdown`, or `.mkd` files (with case-insensitive fallback)
- **Local & Remote Link Navigation** — click relative links (`[Doc](./doc.md)`) or remote Markdown URLs (`https://.../file.md`) and openmd opens them directly in new tabs
- **Re-open Last Viewed File** — run `openmd -r` (or `--recent` / `--last`) to instantly reopen your most recently viewed document
- **Closable Multi-file Tabs (up to 12)** — open up to 12 files at once; tabs feature close buttons and `Cmd+W` / `Ctrl+W` closing shortcuts
- **Native CLI Flags** — fast terminal stdout output for `openmd -v` / `--version` and `openmd -h` / `--help` without launching GUI windows
- **Cross-Platform Glob Expansion** — wildcards like `openmd docs/*.md` work on Windows `cmd.exe`/PowerShell as well as POSIX shells
- **Quick Clipboard Shortcuts** — `Cmd+Shift+C` copies absolute file path, `Cmd+Alt+C` copies document text
- **Meta panel** — shows YAML front‑matter in a hidden-by-default div; toggle via the **META** button or the **M** shortcut key
- **Quick Help** — access a concise help dialog with navigation and shortcuts via the **HELP** button or the **H** shortcut key
- **Instant launch** — the shell prompt returns immediately; openmd runs as a fully detached GUI app (no `&` needed, no blocking)
- **GitHub-dark theme by default** — comfortable reading in low-light environments
- **16 built-in themes** — dark and light, switch instantly via the swatch bar at the bottom of the sidebar; fully customizable via `.openmd.css`
- **Live reload** — the display pane updates instantly when the file is saved; no manual refresh needed
- **Mermaid diagrams** — fenced mermaid blocks render automatically via CDN
- **KaTeX math** — inline `$…$` and display `$$…$$` expressions render out of the box
- **Sidebar TOC** — hierarchical (H1 → H2 → H3); click or press Return to jump to any heading. The sidebar takes up 20% of your screen, and you can easily jump between the sidebar and display using the left/right arrow keys.
- **Dynamic Pane Focus** — unselected panes automatically dim to 60% opacity so you always know exactly where your keyboard focus is.
- **Unix pipes** - accepts markdown from stdin, e.g. ```echo 'markdown string here' | openmd```
- **Interactive file picker** — run with no arguments and choose from `.md` files in the current directory via a curses-based picker
- **Remote image caching** — remote images in your Markdown are downloaded to a local temp cache so they render correctly in the Qt WebEngine view
- **External link handling** — clicking general `http`/`https` web links opens them in your default browser; the display window never navigates away
- **Update notifications** — on startup, openmd quietly checks PyPI (at most once every 6 hours) and shows a non-intrusive popup if a newer version is available
- **Version in title bar** — the window title shows the running version for quick reference
- **Keyboard shortcuts** — `Esc` closes the window; Up/Down arrows and Return navigate the sidebar, Left/Right switch panes, Cmd+Left/Right switch tabs, Cmd+W closes tabs, and Cmd+Shift+C copies paths

---

## Theming with `.openmd.css`

**Preview:** Open ```openmd-preview-themes.html``` in a browser to see what the 16 themes look like.
**Customization:** Copy ```openmd-default.css``` to your home directory (```$HOME/.openmd.css #note the dot```), then edit it to your liking.

openmd ships with 16 built-in themes (8 dark, 8 light) selectable from the swatch bar. Automatically loaded from `openmd-default.css`. To customize further, create an `.openmd.css` file — it is appended after the built-in CSS so any rule you write overrides the default via normal CSS cascade.

**Lookup order** (first match wins):

| Priority | Location |
|----------|----------|
| 1 | Current working directory (`./`) |
| 2 | openmd install directory |
| 3 | Home directory (`~/`) |

To make your own CSS themes, add `body.theme-yourname { ... }` blocks to your `.openmd.css`. The swatch bar automatically discovers and displays the first 16 themes defined there.

---

## Requirements

- macOS or Linux (POSIX)
- **Python 3.10+**
- [PySide6](https://pypi.org/project/PySide6/) + PySide6-WebEngine
- [Markdown](https://pypi.org/project/Markdown/)
- [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/)
- [PyYAML](https://pypi.org/project/PyYAML/)

**Note:** Mermaid and KaTeX require an internet connection to load from CDN.

---

## Installation

The easiest way to install openmd (recommended, just two steps):

1. Install **uv** (the fastest Python tool manager):
   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
*(Windows users: use the same curl command in PowerShell or run winget install astral-sh.uv)*

2. Install openmd: ```uv tool install openmd```

That’s it! You can now run openmd like this:
```openmd <filename(s)>```

###From source
```
git clone https://github.com/RufusLin/openmd.git
cd openmd
pip install -e .
```

After this, the openmd command will be available in your shell.


---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Esc` | Close the preview window |
| `↑` / `↓` | Navigate the sidebar TOC |
| `←` / `→` | Move focus between sidebar and display |
| `Cmd + ← / →` | Navigate among tabs |
| `Cmd + W` | Close current active tab |
| `Cmd + Shift + C` | Copy active file path to clipboard |
| `Cmd + Alt + C` | Copy active document text to clipboard |
| `Cmd + Shift + < / >` | Change font size |
| `Return` | Jump to selected heading |
| `M` | Toggle Meta Panel (YAML front-matter) |
| `H` | Show Quick Help dialog |

---

## License

MIT

---

### Troubleshooting

**If you still see an old version after upgrading**  
This happens if you previously installed with `pip install -e .` or plain `pip`.  
Run this once:

```bash
rm -f ~/Library/Python/*/bin/openmd          # remove old pip executable (macOS)
uv tool uninstall openmd
uv tool install openmd
```
