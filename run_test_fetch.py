import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication


class WebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS: {message}")

app = QApplication(sys.argv)
view = QWebEngineView()
page = WebEnginePage(view)
view.setPage(page)
view.load(QUrl("http://localhost:5069"))
view.show()

def test_fetch():
    print("Injecting JS to test fetch...")
    view.page().runJavaScript("""
    fetch('/health').then(r => r.text()).then(t => console.log('Fetch /health:', t)).catch(e => console.error('Fetch err:', e));
    """)

QTimer.singleShot(3000, test_fetch)
QTimer.singleShot(6000, app.quit)

sys.exit(app.exec())
