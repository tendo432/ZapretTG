"""Скриншоты всех страниц поверх «обоев» (имитация полупрозрачного окна)."""
import os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(here, "vendor", "tgws")); sys.path.insert(0, here)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt, QPointF
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QRadialGradient, QImage
app = QApplication(sys.argv)
from app.config import Config
from app.zapret import ZapretManager
from app.tgproxy import TgProxyManager
from app.dns import DnsManager
from app.ui.main_window import MainWindow
cfg = Config(); z = ZapretManager(cfg); z.install_files(); tg = TgProxyManager(cfg); dns = DnsManager(cfg)
theme = sys.argv[1] if len(sys.argv) > 1 else "dark"
out = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
win = MainWindow(cfg, z, tg, dns); win.set_theme(theme); win.shell.blur = True; win.show()
tg.start()
# немного «трафика» для графика
import random
for i in range(60): win.pages["home"].spark.push(abs(random.gauss(0, 1)) * 180_000 + 40_000 * (1 + (i % 17) / 6))
pages = only or ["home", "zapret", "tg", "dns", "diag", "settings", "logs"]

def wallpaper(w, h):
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#6a1fd1")); g.setColorAt(0.55, QColor("#a01ed6")); g.setColorAt(1, QColor("#e01aa8"))
    p.fillRect(0, 0, w, h, g)
    rg = QRadialGradient(QPointF(w * 0.2, h * 0.3), w * 0.5); rg.setColorAt(0, QColor(255, 255, 255, 60)); rg.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(0, 0, w, h, rg); p.end()
    # имитация размытия: фон и так гладкий
    return img

def save(name):
    shot = win.grab()
    W, H = shot.width() + 120, shot.height() + 120
    canvas = QPixmap.fromImage(wallpaper(W, H))
    p = QPainter(canvas); p.drawPixmap(60, 60, shot); p.end()
    canvas.save(f"{out}/{theme}_{name}.png")

def shoot(i=0):
    if i > 0:
        save(pages[i - 1])
    if i == len(pages):
        app.quit(); return
    win.go(pages[i], animate=False); win.refresh_now()
    QTimer.singleShot(1300, lambda: shoot(i + 1))
QTimer.singleShot(1800, shoot)
app.exec(); tg.stop()
