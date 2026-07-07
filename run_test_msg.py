import sys

from PySide6.QtCore import QTimer, QUrl
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

def send_msg():
    print("Injecting JS to send message...")
    view.page().runJavaScript("document.getElementById('msg-input').value = 'hello'; document.getElementById('send-btn').click();")

QTimer.singleShot(5000, send_msg)
QTimer.singleShot(12000, app.quit)

sys.exit(app.exec())
