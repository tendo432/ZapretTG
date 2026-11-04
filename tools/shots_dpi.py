import os, sys
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(here, "vendor", "tgws")); sys.path.insert(0, here)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)
from app.config import Config; from app.zapret import ZapretManager; from app.tgproxy import TgProxyManager; from app.dns import DnsManager
from app.ui.main_window import MainWindow
cfg = Config(); z = ZapretManager(cfg); z.install_files(); tg = TgProxyManager(cfg); dns = DnsManager(cfg)
out, tag = sys.argv[1], sys.argv[2]; w_, h_ = int(sys.argv[3]), int(sys.argv[4])
pages = sys.argv[5].split(",")
win = MainWindow(cfg, z, tg, dns); win.shell.blur = True; win._fitted = True; win.setMinimumSize(200, 200); win.resize(w_, h_); win.show()
def shoot(i=0):
    if i > 0: win.grab().save(f"{out}/{tag}_{pages[i-1]}.png")
    if i == len(pages): app.quit(); return
    win.go(pages[i], animate=False)
    QTimer.singleShot(700, lambda: shoot(i + 1))
QTimer.singleShot(1200, shoot)
app.exec()
