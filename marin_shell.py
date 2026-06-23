import sys
import os

# Disable sandbox to prevent Chromium crashes on certain Linux/Wayland configurations
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox"


from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEnginePage
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

class WebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS: {message} (Line {lineNumber})")

class YouTubeInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if "youtube.com" in url or "googlevideo.com" in url or "ytimg.com" in url:
            info.setHttpHeader(b"Referer", b"https://www.youtube.com/")
            info.setHttpHeader(
                b"User-Agent",
                b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

class MarinShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Marin OS")
        self.resize(1600, 900)

        self.setStyleSheet("background-color: #0b0f19;")

        self.profile = QWebEngineProfile("MarinProfile", self)

        self.interceptor = YouTubeInterceptor(self)
        self.profile.setUrlRequestInterceptor(self.interceptor)

        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

        self.browser = QWebEngineView(self)

        self.page = WebEnginePage(self.profile, self.browser)
        self.page.featurePermissionRequested.connect(self.on_feature_permission_requested)
        self.browser.setPage(self.page)

        self.setCentralWidget(self.browser)

        self.browser.loadFinished.connect(self.on_load_finished)
        self.browser.load(QUrl("http://localhost:5069"))

    def on_load_finished(self, ok):
        if not ok:
            print("FAILED TO LOAD localhost:5069! Is the backend running?")
        else:
            print("Successfully loaded Marin OS!")

    def on_feature_permission_requested(self, securityOrigin, feature):
        self.page.setFeaturePermission(securityOrigin, feature, QWebEnginePage.PermissionGrantedByUser)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MarinShell()
    window.show()

    sys.exit(app.exec())
