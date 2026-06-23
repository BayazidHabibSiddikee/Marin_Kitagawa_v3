import sys
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

class WebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS: {message}")

class MarinShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.browser = QWebEngineView(self)
        self.page = WebEnginePage(self.browser)
        self.browser.setPage(self.page)
        self.setCentralWidget(self.browser)
        self.browser.load(QUrl("http://localhost:5069"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MarinShell()
    window.show()
    # close after 5 seconds automatically
    from PySide6.QtCore import QTimer
    QTimer.singleShot(5000, app.quit)
    sys.exit(app.exec())
