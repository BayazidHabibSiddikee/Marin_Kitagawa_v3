import sys
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer

class WebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS: {message}")

app = QApplication(sys.argv)
view = QWebEngineView()
page = WebEnginePage(view)
view.setPage(page)
view.load(QUrl("http://localhost:5069"))
view.show()

def send_msg():
    print("Injecting JS to fetch /message...")
    view.page().runJavaScript("""
    const fd = new FormData();
    fd.append('message', 'hello');
    fd.append('session_id', 'default');
    fetch('/message', { method: 'POST', body: fd })
      .then(r => r.text())
      .then(t => console.log('Message response:', t.substring(0, 50)))
      .catch(e => console.error('Message err:', e));
    """)

QTimer.singleShot(4000, send_msg)
QTimer.singleShot(15000, app.quit)

sys.exit(app.exec())
