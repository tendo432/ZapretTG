"""Аудит раскладки: обрезанный текст, вылезающие элементы, сжатые кнопки."""
import os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(here, "vendor", "tgws")); sys.path.insert(0, here)
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton, QAbstractButton, QWidget, QScrollArea,
                               QLineEdit, QComboBox, QToolButton)
from PySide6.QtCore import QTimer, QRect, QPoint
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from app.config import Config; from app.zapret import ZapretManager; from app.tgproxy import TgProxyManager; from app.dns import DnsManager
from app.ui.main_window import MainWindow
cfg = Config(); z = ZapretManager(cfg); z.install_files(); tg = TgProxyManager(cfg); dns = DnsManager(cfg)
W, H = int(sys.argv[1]), int(sys.argv[2])
win = MainWindow(cfg, z, tg, dns); win._fitted = True; win.setMinimumSize(200, 200); win.resize(W, H); win.show()
QTimer.singleShot(300, lambda: print('content min width:', win._content_min_width()))
issues = []
def visible_rect_in_window(w):
    r = QRect(w.mapTo(win, QPoint(0, 0)), w.size())
    return r
def audit(page_key):
    page = win.pages[page_key]
    for sa in page.findChildren(QScrollArea):
        inner = sa.widget()
        if inner and inner.minimumSizeHint().width() > sa.viewport().width() + 1:
            issues.append(f"[{page_key}] горизонтальное переполнение: нужно {inner.minimumSizeHint().width()} > {sa.viewport().width()}")
    for w in page.findChildren(QWidget):
        if not w.isVisible() or w.width() <= 0:
            continue
        name = type(w).__name__
        if type(w).__name__ == "ElidedLabel":
            if w.width() < 100:
                issues.append(f"[{page_key}] слишком узкая подпись '{w.text()[:30]}' {w.width()}px")
            continue
        if isinstance(w, QLabel) and not w.wordWrap() and w.text() and not w.pixmap():
            need = w.fontMetrics().horizontalAdvance(w.text().split("\n")[0]) + 2
            if "<" not in w.text() and need > w.width() + 4:
                issues.append(f"[{page_key}] обрезан текст QLabel '{w.text()[:40]}' нужно {need} > {w.width()}")
        if isinstance(w, QAbstractButton) and not isinstance(w, QToolButton) and type(w).__name__ == "QPushButton":
            if w.text() and w.sizeHint().width() > w.width() + 1:
                issues.append(f"[{page_key}] сжата кнопка '{w.text()[:30]}' {w.width()} < {w.sizeHint().width()}")
        if isinstance(w, QComboBox) and w.currentText():
            need = w.fontMetrics().horizontalAdvance(w.currentText()) + 44
            if need > w.width() + 1:
                issues.append(f"[{page_key}] обрезан выбор в списке '{w.currentText()[:30]}' {w.width()} < {need}")
        par = w.parentWidget()
        if par is not None and par.isVisible() and not isinstance(par, QScrollArea) and par.objectName() != "qt_scrollarea_viewport":
            pr = par.rect()
            g = w.geometry()
            if (g.right() > pr.right() + 2 or g.left() < -2) and name not in ("QScrollBar",):
                issues.append(f"[{page_key}] {name} '{getattr(w,'text',lambda:'')()[:20] if hasattr(w,'text') else ''}' вылезает за родителя {type(par).__name__}: {g.left()}..{g.right()} vs 0..{pr.right()}")
pages = ["home", "zapret", "tg", "dns", "diag", "settings", "logs"]
def step(i=0):
    if i > 0:
        audit(pages[i - 1])
    if i == len(pages):
        seen = set()
        for x in issues:
            if x not in seen:
                seen.add(x); print(x)
        print("TOTAL", len(seen)); app.quit(); return
    win.go(pages[i], animate=False)
    QTimer.singleShot(500, lambda: step(i + 1))
QTimer.singleShot(1000, step)
app.exec()
