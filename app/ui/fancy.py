"""Графические виджеты: кольца, полосы, график трафика, «стопка» модулей, диалоги."""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, List, Optional

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QMenu, QVBoxLayout, QWidget)

from .widgets import Palette, button, label, row


def C(key: str, alpha: Optional[float] = None) -> QColor:
    v = Palette.p.get(key, "#888888")
    c = QColor(v) if isinstance(v, str) and v.startswith("#") else _rgba(v)
    if alpha is not None:
        c.setAlphaF(alpha)
    return c


def _rgba(v) -> QColor:
    if isinstance(v, tuple):
        return QColor(*v)
    s = str(v)
    if s.startswith("rgba"):
        r, g, b, a = [x.strip() for x in s[s.index("(") + 1:s.index(")")].split(",")]
        c = QColor(int(r), int(g), int(b))
        c.setAlphaF(float(a))
        return c
    return QColor(s)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


class _Anim:
    """Плавно анимируемое число 0..1."""

    def __init__(self, owner: QWidget, prop: bytes, ms: int = 450):
        self.a = QPropertyAnimation(owner, prop, owner)
        self.a.setDuration(ms)
        self.a.setEasingCurve(QEasingCurve.OutCubic)

    def go(self, start: float, end: float) -> None:
        self.a.stop()
        self.a.setStartValue(start)
        self.a.setEndValue(end)
        self.a.start()


# ------------------------------------------------------------------ Ring

class Ring(QWidget):
    """Круговой индикатор как на референсе. Кликабелен (переключатель)."""
    clicked = Signal()

    def __init__(self, title: str, color_key: str = "accent", size: int = 104):
        super().__init__()
        self.setFixedSize(size, size + 26)
        self.setCursor(Qt.PointingHandCursor)
        self.title = title
        self.color_key = color_key
        self.text = "—"
        self._v = 0.0
        self._target = 0.0
        self.anim = _Anim(self, b"value", 700)

    def get_value(self) -> float:
        return self._v

    def set_value_(self, v: float) -> None:
        self._v = v
        self.update()

    value = Property(float, get_value, set_value_)

    def set(self, fraction: float, text: str) -> None:
        fraction = max(0.0, min(1.0, fraction))
        self.text = text
        if abs(fraction - self._target) > 0.001:
            self._target = fraction
            self.anim.go(self._v, fraction)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()
        r = QRectF(9, 9, s - 18, s - 18)
        track = QPen(C("surface3"), 7)
        p.setPen(track)
        p.drawEllipse(r)
        col = C(self.color_key)
        if self._v > 0.002:
            grad = QConicalGradient(r.center(), 90)
            grad.setColorAt(0.0, col)
            grad.setColorAt(0.5, _mix(col, C("accent2"), 0.6))
            grad.setColorAt(1.0, col)
            # свечение
            glow = QPen(QColor(col.red(), col.green(), col.blue(), 50), 15)
            glow.setCapStyle(Qt.RoundCap)
            p.setPen(glow)
            p.drawArc(r, 90 * 16, int(-self._v * 360 * 16))
            pen = QPen(QBrush(grad), 7)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, int(-self._v * 360 * 16))
        p.setPen(C("text"))
        f = QFont(self.font())
        f.setPointSizeF(13.5)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, self.text)
        f.setPointSizeF(9)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(C("muted"))
        p.drawText(QRectF(0, s, s, 24), Qt.AlignHCenter | Qt.AlignTop, self.title)
        p.end()


# ------------------------------------------------------------ GradientBar

class GradientBar(QWidget):
    def __init__(self, title: str, c1: str = "accent", c2: str = "accent2"):
        super().__init__()
        self.title, self.c1, self.c2 = title, c1, c2
        self.right = ""
        self._v = 0.0
        self.anim = _Anim(self, b"value", 600)
        self.setFixedHeight(22)

    def get_value(self) -> float:
        return self._v

    def set_value_(self, v: float) -> None:
        self._v = v
        self.update()

    value = Property(float, get_value, set_value_)

    def set(self, fraction: float, right: str = "") -> None:
        self.right = right
        fraction = max(0.0, min(1.0, fraction))
        if abs(fraction - getattr(self, "_target", -1)) > 0.001:
            self._target = fraction
            self.anim.go(self._v, fraction)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        label_w = 118
        right_w = 70
        p.setPen(C("muted"))
        p.drawText(QRectF(0, 0, label_w, h), Qt.AlignVCenter | Qt.AlignLeft, self.title)
        bar = QRectF(label_w, h / 2 - 3, max(20, w - label_w - right_w - 8), 6)
        p.setPen(Qt.NoPen)
        p.setBrush(C("surface3"))
        p.drawRoundedRect(bar, 3, 3)
        if self._v > 0.001:
            fill = QRectF(bar.left(), bar.top(), bar.width() * self._v, bar.height())
            g = QLinearGradient(fill.topLeft(), fill.topRight())
            g.setColorAt(0, C(self.c1))
            g.setColorAt(1, C(self.c2))
            p.setBrush(g)
            p.drawRoundedRect(fill, 3, 3)
        p.setPen(C("text"))
        p.drawText(QRectF(w - right_w, 0, right_w, h), Qt.AlignVCenter | Qt.AlignRight, self.right)
        p.end()


# ---------------------------------------------------------------- Sparkline

class Sparkline(QWidget):
    """Плавная кривая скорости с градиентной заливкой и светящейся точкой."""

    def __init__(self, points: int = 60):
        super().__init__()
        self.data: Deque[float] = deque([0.0] * points, maxlen=points)
        self.setMinimumHeight(150)
        self.unit = lambda v: f"{v:.0f}"

    def push(self, v: float) -> None:
        self.data.append(max(0.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        vals = list(self.data)
        vmax = max(vals) if vals else 0
        scale = _nice(max(vmax * 1.15, 1024.0))
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        fm = p.fontMetrics()
        left = max(fm.horizontalAdvance(self.unit(scale * i / 4)) for i in range(5)) + 14
        top, bottom = 10, 12
        area = QRectF(left, top, w - left - 14, h - top - bottom)
        for i in range(5):
            y = area.bottom() - area.height() * i / 4
            p.setPen(QPen(C("border"), 1, Qt.DashLine))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(C("faint"))
            p.drawText(QRectF(0, y - 8, left - 10, 16), Qt.AlignRight | Qt.AlignVCenter, self.unit(scale * i / 4))
        if len(vals) < 2:
            p.end()
            return
        pts = [QPointF(area.left() + area.width() * i / (len(vals) - 1),
                       area.bottom() - area.height() * (v / scale)) for i, v in enumerate(vals)]
        path = QPainterPath(pts[0])
        for a, b in zip(pts, pts[1:]):
            mx = (a.x() + b.x()) / 2
            path.cubicTo(QPointF(mx, a.y()), QPointF(mx, b.y()), b)
        fill = QPainterPath(path)
        fill.lineTo(area.right(), area.bottom())
        fill.lineTo(area.left(), area.bottom())
        fill.closeSubpath()
        g = QLinearGradient(0, area.top(), 0, area.bottom())
        g.setColorAt(0, C("accent", 0.32))
        g.setColorAt(1, C("accent", 0.0))
        p.fillPath(fill, g)
        lg = QLinearGradient(area.left(), 0, area.right(), 0)
        lg.setColorAt(0, C("accent2"))
        lg.setColorAt(1, C("accent"))
        p.setPen(QPen(QColor(C("accent").red(), C("accent").green(), C("accent").blue(), 45), 7,
                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(QBrush(lg), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        last = pts[-1]
        rg = QRadialGradient(last, 12)
        rg.setColorAt(0, C("accent", 0.6))
        rg.setColorAt(1, C("accent", 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(last, 12, 12)
        p.setBrush(QColor("white"))
        p.drawEllipse(last, 4, 4)
        p.end()


def _nice(v: float) -> float:
    if v <= 0:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


# --------------------------------------------------------------- StackEmblem

class StackEmblem(QWidget):
    """Три «диска» друг на друге — Telegram, Zapret, DNS. Включённый модуль светится."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 250)
        self.layers = [  # сверху вниз
            {"title": "Telegram", "sub": "", "key": "accent3", "v": 0.0},
            {"title": "Zapret", "sub": "", "key": "accent", "v": 0.0},
            {"title": "DNS", "sub": "", "key": "accent2", "v": 0.0},
        ]
        self._anims = []
        for i in range(3):
            a = QPropertyAnimation(self, f"l{i}".encode(), self)
            a.setDuration(650)
            a.setEasingCurve(QEasingCurve.OutCubic)
            self._anims.append(a)

    def _g(i):
        return lambda self: self.layers[i]["v"]

    def _s(i):
        def f(self, v):
            self.layers[i]["v"] = v
            self.update()
        return f

    l0 = Property(float, _g(0), _s(0))
    l1 = Property(float, _g(1), _s(1))
    l2 = Property(float, _g(2), _s(2))

    def set_layer(self, i: int, on: bool, sub: str) -> None:
        L = self.layers[i]
        L["sub"] = sub
        target = 1.0 if on else 0.0
        if L.get("target") != target:
            L["target"] = target
            a = self._anims[i]
            a.stop()
            a.setStartValue(L["v"])
            a.setEndValue(target)
            a.start()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        dw = min(210.0, w * 0.48)
        dh = dw * 0.30          # высота эллипса крышки
        thick = dw * 0.20       # толщина диска
        gap = thick * 0.62
        cx = w - dw / 2 - 18
        total = 3 * thick + 2 * gap + dh
        top0 = (h - total) / 2
        # тень под стопкой
        base_y = top0 + 3 * thick + 2 * gap + dh * 0.5
        rg = QRadialGradient(QPointF(cx, base_y + thick * 0.4), dw * 0.6)
        rg.setColorAt(0, QColor(0, 0, 0, 90))
        rg.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, base_y + thick * 0.5), dw * 0.62, dh * 0.7)
        # рисуем снизу вверх, чтобы верхние перекрывали нижние
        f = QFont(self.font())
        for i in (2, 1, 0):
            L = self.layers[i]
            t = L["v"]
            y = top0 + i * (thick + gap)
            col = C(L["key"])
            off_top, off_side = C("disc_off_top"), C("disc_off_side")
            top_c = _mix(off_top, col.lighter(118), t)
            side1 = _mix(off_side, col, t)
            side2 = _mix(off_side.darker(120), col.darker(160), t)
            rect_top = QRectF(cx - dw / 2, y, dw, dh)
            # боковина
            side = QPainterPath()
            side.moveTo(cx - dw / 2, y + dh / 2)
            side.lineTo(cx - dw / 2, y + dh / 2 + thick)
            side.arcTo(QRectF(cx - dw / 2, y + thick, dw, dh), 180, 180)
            side.lineTo(cx + dw / 2, y + dh / 2)
            side.arcTo(rect_top, 0, -180)
            side.closeSubpath()
            p.setPen(Qt.NoPen)
            if t > 0.01:  # свечение
                gc = QPointF(cx, y + dh / 2 + thick / 2)
                glow = QRadialGradient(gc, dw * 0.62)
                glow.setColorAt(0, QColor(col.red(), col.green(), col.blue(), int(70 * t)))
                glow.setColorAt(0.6, QColor(col.red(), col.green(), col.blue(), int(18 * t)))
                glow.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
                p.setBrush(glow)
                p.drawEllipse(gc, dw * 0.62, dw * 0.62)
            sg = QLinearGradient(cx - dw / 2, 0, cx + dw / 2, 0)
            sg.setColorAt(0, side2)
            sg.setColorAt(0.45, side1)
            sg.setColorAt(1, side2)
            p.setBrush(sg)
            p.drawPath(side)
            tg = QLinearGradient(rect_top.topLeft(), rect_top.bottomRight())
            tg.setColorAt(0, top_c.lighter(110))
            tg.setColorAt(1, top_c)
            p.setBrush(tg)
            p.drawEllipse(rect_top)
            p.setPen(QPen(QColor(255, 255, 255, int(22 + 40 * t)), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(rect_top.adjusted(1, 1, -1, -1))
            p.setPen(Qt.NoPen)
            # выноска с подписью слева
            ly = y + dh / 2 + thick / 2
            lx2 = cx - dw / 2 - 10
            lx1 = max(150.0, lx2 - 60)
            p.setPen(QPen(_mix(C("faint"), col, t), 1))
            p.drawLine(QPointF(lx1, ly), QPointF(lx2, ly))
            p.setBrush(_mix(C("faint"), col, t))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(lx2, ly), 2.5, 2.5)
            f.setPointSizeF(10.5)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(_mix(C("muted"), C("text"), t))
            p.drawText(QRectF(0, ly - 19, lx1 - 8, 18), Qt.AlignRight | Qt.AlignVCenter, L["title"])
            f.setPointSizeF(8.5)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(_mix(C("faint"), col, t * 0.85))
            p.drawText(QRectF(0, ly + 1, lx1 - 8, 18), Qt.AlignRight | Qt.AlignVCenter, L["sub"])
        p.end()


# --------------------------------------------------------- стили всплывашек

def style_popup(widget) -> None:
    """Скруглённые всплывающие меню/списки без чёрных углов."""
    try:
        win = widget if isinstance(widget, QMenu) else widget.window()
        win.setWindowFlag(Qt.FramelessWindowHint, True)
        win.setWindowFlag(Qt.NoDropShadowWindowHint, True)
        win.setAttribute(Qt.WA_TranslucentBackground, True)
    except Exception:
        pass


class Combo(QComboBox):
    """Список, который не растягивает окно под самый длинный пункт."""

    def __init__(self, parent=None, min_chars: int = 14):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(min_chars)
        self._styled = False

    def showPopup(self):
        if not self._styled:
            style_popup(self.view())
            self._styled = True
        fm = self.view().fontMetrics()
        widest = max((fm.horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=0)
        self.view().setMinimumWidth(max(self.width(), widest + 48))
        super().showPopup()


# ------------------------------------------------------------- диалог

class ConfirmDialog(QDialog):
    def __init__(self, parent, title: str, text: str, ok: str = "Да", cancel: str = "Отмена",
                 danger: bool = False, extra: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        box = QFrame()
        box.setObjectName("dialog")
        sh = QGraphicsDropShadowEffect(box)
        sh.setBlurRadius(40)
        sh.setOffset(0, 10)
        sh.setColor(QColor(0, 0, 0, 120))
        box.setGraphicsEffect(sh)
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(label(title, "cardTitle"))
        t = label(text, "muted", wrap=True)
        t.setMinimumWidth(380)
        t.setMaximumWidth(520)
        lay.addWidget(t)
        if extra is not None:
            lay.addWidget(extra, 1)
        lay.addSpacing(6)
        btns = row(None, spacing=8)
        if cancel:
            btns.addWidget(button(cancel, "ghost", "", self.reject))
        okb = button(ok, "danger" if danger else "primary", "", self.accept)
        okb.setDefault(True)
        btns.addWidget(okb)
        lay.addLayout(btns)

    @staticmethod
    def ask(parent, title: str, text: str, ok: str = "Да", danger: bool = False) -> bool:
        return ConfirmDialog(parent, title, text, ok=ok, danger=danger).exec() == QDialog.Accepted
