import sys
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

class YouTubeInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if "youtube.com" in url or "googlevideo.com" in url:
            # Spoof the referer to trick YouTube into allowing the embed
            info.setHttpHeader(b"Referer", b"https://www.youtube.com/")
            # Optionally set a standard User-Agent
            info.setHttpHeader(
                b"User-Agent", 
                b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

class MarinShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Marin OS")
        self.resize(1600, 900)

        # Apply dark theme to window
        self.setStyleSheet("background-color: #0b0f19;")

        # Set up the WebEngine profile and bypass security restrictions
        self.profile = QWebEngineProfile("MarinProfile", self)
        
        # Add interceptor for YouTube
        self.interceptor = YouTubeInterceptor(self)
        self.profile.setUrlRequestInterceptor(self.interceptor)

        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False) # Allow autoplay!

        # Set up the view
        self.browser = QWebEngineView(self)
        self.browser.setPage(self.browser.page()) # Just re-assigning page
        
        # We must create a new page with our custom profile
        from PySide6.QtWebEngineCore import QWebEnginePage
        self.page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(self.page)

        self.setCentralWidget(self.browser)

        # Load Marin OS
        self.browser.load(QUrl("http://localhost:5069"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Optional: Enable high DPI scaling
    app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    window = MarinShell()
    window.show()

    sys.exit(app.exec())
