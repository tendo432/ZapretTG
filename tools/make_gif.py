"""Анимация интерфейса для README: последовательное включение модулей (демо-состояния)."""
import os, sys, random, math
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(here, "vendor", "tgws")); sys.path.insert(0, here)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QPointF
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QRadialGradient, QImage
app = QApplication(sys.argv)
from app.config import Config; from app.zapret import ZapretManager; from app.tgproxy import TgProxyManager; from app.dns import DnsManager
from app.ui.main_window import MainWindow
from PIL import Image
cfg = Config(); z = ZapretManager(cfg); z.install_files(); tg = TgProxyManager(cfg); dns = DnsManager(cfg)
cfg.set("zapret", "strategy", "general (ALT).bat")
win = MainWindow(cfg, z, tg, dns); win.timer.stop(); win._fitted = True; win.shell.blur = True
win.resize(1200, 800); win.show(); win.go("home", animate=False)
home = win.pages["home"]
for _ in range(60): home.spark.push(0)
frames, durs = [], []
OUT = sys.argv[1]

def status(z_on, t_on, d_on, active=0, up=0, down=0):
    zs = {"running": z_on, "app_running": z_on, "uptime": 75 if z_on else None, "strategy": "general (ALT).bat", "error": ""}
    hb = lambda b: f"{b/1048576:.1f}MB" if b > 1048576 else f"{b/1024:.0f}KB"
    ts = {"running": t_on, "active": t_on, "host": "127.0.0.1", "port": 1443, "uptime": 40 if t_on else None, "error": "",
          "stats": {"active": active, "up": hb(up), "down": hb(down), "up_raw": up, "down_raw": down}}
    ds = {"enabled": d_on, "provider_name": "XBox DNS", "mode": "system"}
    return zs, ts, ds

def wallpaper(w, h):
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied); p = QPainter(img)
    g = QLinearGradient(0, 0, w, h); g.setColorAt(0, QColor("#5b1fc9")); g.setColorAt(0.55, QColor("#951ed0")); g.setColorAt(1, QColor("#d41a9e"))
    p.fillRect(0, 0, w, h, g); p.end(); return img

def grab(ms):
    shot = win.grab()
    W, H = shot.width() + 60, shot.height() + 60
    c = QPixmap.fromImage(wallpaper(W, H)); p = QPainter(c); p.drawPixmap(30, 30, shot); p.end()
    img = c.toImage().convertToFormat(QImage.Format_RGB888)
    pil = Image.frombuffer("RGB", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGB", img.bytesPerLine())
    pil = pil.resize((960, int(pil.height * 960 / pil.width)), Image.LANCZOS)
    frames.append(pil); durs.append(ms)

script = []  # (действие, сколько кадров снять, длительность кадра)
state = {"z": False, "t": False, "d": False, "up": 0, "down": 0}
def apply(extra_traffic=False):
    if extra_traffic and state["t"]:
        s1 = 60_000 + random.random() * 400_000 + 250_000 * (1 + math.sin(len(frames) / 3))
        state["down"] += s1 * 0.12; state["up"] += s1 * 0.03
        home.spark.push(s1)
        home.speed_down.setText(f"{s1*0.8/1024:.0f} КБ/с"); home.speed_up.setText(f"{s1*0.2/1024:.0f} КБ/с")
    win.on_status(*status(state["z"], state["t"], state["d"], 7 if state["t"] else 0, int(state["up"]), int(state["down"])))

steps = [("hold", 6, 160, None), ("z", 14, 55, None), ("hold", 6, 130, None), ("t", 14, 55, None), ("traffic", 10, 120, None),
         ("d", 14, 55, None), ("traffic", 22, 120, None)]
def run(i=0, k=0):
    if i >= len(steps):
        finish(); return
    kind, n, ms, _ = steps[i]
    if k == 0 and kind in ("z", "t", "d"):
        state[kind] = True
    apply(extra_traffic=(kind in ("traffic", "d", "t")))
    grab(ms)
    if k + 1 < n:
        QTimer.singleShot(ms, lambda: run(i, k + 1))
    else:
        QTimer.singleShot(ms, lambda: run(i + 1, 0))

def finish():
    durs[-1] = 1800
    pal = [f.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG) for f in frames]
    pal[0].save(OUT, save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True, disposal=1)
    print("frames", len(frames), "size", os.path.getsize(OUT) // 1024, "KB")
    app.quit()

QTimer.singleShot(1500, run)
app.exec()
