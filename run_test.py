import sys

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication


class WebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS: {message} (Line {lineNumber})")

app = QApplication(sys.argv)
view = QWebEngineView()
page = WebEnginePage(view)
view.setPage(page)
view.load(QUrl("http://localhost:5069"))
view.show()

from PySide6.QtCore import QTimer

QTimer.singleShot(8000, app.quit)
sys.exit(app.exec())
