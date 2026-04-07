import sys
import os
import markdown
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtCore import QSize

# GitHub-Modern Dark Theme
CSS = """
body { 
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

class MDWindow(QMainWindow):
    def __init__(self, file_path):
        super().__init__()

        self.view = QWebEngineView()
        
        # --- MODERN RAM OPTIMIZATION (PySide6 2026 API) ---
        profile = self.view.page().profile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        
        # Access settings via the page profile instead of globalSettings
        settings = self.view.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        # --------------------------------------------------

        self.setCentralWidget(self.view)
        self.setWindowTitle(f"MD Preview: {os.path.basename(file_path)}")
        self.resize(QSize(1000, 1100))
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                html_body = markdown.markdown(content, extensions=['extra', 'sane_lists'])
        except Exception as e:
            html_body = f"<h1>Error</h1><p>{str(e)}</p>"
            
        full_html = f"<html><head><style>{CSS}</style></head><body>{html_body}</body></html>"
        self.view.setHtml(full_html)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
        
    app = QApplication(sys.argv)
    window = MDWindow(sys.argv[1])
    window.show()
    sys.exit(app.exec())

