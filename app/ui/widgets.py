"""Небольшие собственные виджеты."""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import (Property, QEasingCurve, QObject, QPropertyAnimation, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import icons


class Palette:
    """Текущая палитра (меняется при смене темы)."""
    p: dict = {}


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, big: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._big = big
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(52, 30) if self._big else QSize(40, 22)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:  # без анимации при программной установке
        blocked = self.blockSignals(True)
        super().setChecked(on)
        self.blockSignals(blocked)
        self._pos = 1.0 if on else 0.0
        self.update()

    def get_pos(self) -> float:
        return self._pos

    def set_pos(self, v: float) -> None:
        self._pos = v
        self.update()

    # НЕ «pos»: у QWidget уже есть свойство pos (положение), и анимация двигала сам виджет
    knob = Property(float, get_pos, set_pos)

    def paintEvent(self, _):
        from PySide6.QtGui import QLinearGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = Palette.p
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setOpacity(1.0 if self.isEnabled() else 0.45)
        p.setBrush(QColor(pal.get("track_off", "#3a4150")))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self._pos > 0.001:
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, QColor(pal.get("accent", "#c13cf0")))
            g.setColorAt(1, QColor(pal.get("accent2", "#7b4dff")))
            p.setOpacity((1.0 if self.isEnabled() else 0.45) * self._pos)
            p.setBrush(g)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setOpacity(1.0 if self.isEnabled() else 0.45)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF(x, r.top() + 4, d, d))
        p.setBrush(QColor(pal.get("knob", "#ffffff")))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()


class Card(QFrame):
    def __init__(self, parent=None, padding: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(spacing)


class ElidedLabel(QLabel):
    """Однострочная подпись, которая сокращается многоточием и не распирает раскладку."""

    def __init__(self, text: str = "", obj: str = ""):
        super().__init__(text)
        if obj:
            self.setObjectName(obj)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text if self.fontMetrics().horizontalAdvance(text) > self.width() else "")
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setToolTip(self.text() if self.fontMetrics().horizontalAdvance(self.text()) > self.width() else "")

    def paintEvent(self, _):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        r = self.contentsRect()
        p.drawText(r, int(self.alignment() | Qt.AlignVCenter),
                   self.fontMetrics().elidedText(self.text(), Qt.ElideRight, r.width()))
        p.end()


def label(text: str = "", obj: str = "", wrap: bool = False, selectable: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    if wrap:
        lb.setWordWrap(True)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lb


def button(text: str, obj: str = "", icon_name: str = "", on_click: Optional[Callable] = None,
           tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if icon_name:
        color = "#ffffff" if obj == "primary" else Palette.p.get("muted", "#8e96a8")
        b.setIcon(icons.icon(icon_name, color, 16))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.PointingHandCursor)
    if on_click:
        b.clicked.connect(on_click)
    if tip:
        b.setToolTip(tip)
    return b


class Pill(QLabel):
    def __init__(self, text: str = "", state: str = "off"):
        super().__init__(text)
        self.setObjectName("pill")
        self.set(text, state)

    def set(self, text: str, state: str) -> None:
        self.setText(text)
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, options: Sequence[Tuple[str, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for i, (key, text) in enumerate(options):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("first", i == 0)
            b.setProperty("last", i == len(options) - 1)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
        lay.addStretch(1)

    def set_value(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def value(self) -> str:
        for k, b in self.buttons.items():
            if b.isChecked():
                return k
        return ""


class StatBox(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("statBox")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(1)
        self.value = label("—", "statValue")
        lay.addWidget(self.value)
        lay.addWidget(label(title, "statLabel"))

    def set(self, v: str) -> None:
        self.value.setText(v)


class IconBadge(QLabel):
    def __init__(self, name: str, size: int = 42):
        super().__init__()
        self.setObjectName("iconBadge")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._name = name
        self._size = size

    def set_color(self, fg: str, bg: str) -> None:
        self.setPixmap(icons.pixmap(self._name, fg, int(self._size * 0.5)))
        self.setStyleSheet(f"#iconBadge {{ background: {bg}; border-radius: {self._size // 3.5}px; }}")


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.NoFrame)
    return f


def row(*widgets, spacing: int = 10, stretch_at: Optional[int] = None) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for i, w in enumerate(widgets):
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        elif hasattr(w, "addWidget") and not isinstance(w, QWidget):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return lay


def setting_row(title: str, hint: str, control: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 2, 0, 2)
    lay.setSpacing(14)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(label(title))
    if hint:
        col.addWidget(label(hint, "hint", wrap=True))
    lay.addLayout(col, 1)
    lay.addWidget(control, 0, Qt.AlignVCenter)
    return w


# ---------------------------------------------------------- фоновые задачи
#
# Обычные потоки Python + один мост-QObject, живущий в GUI-потоке.
# Результат всегда доставляется в GUI-поток через сигнал (queued connection),
# поэтому виджеты никогда не трогаются из фоновых потоков.

class _Bridge(QObject):
    done = Signal(int, object, object)

    def __init__(self):
        super().__init__()
        self._cbs = {}
        self._n = 0
        self.done.connect(self._dispatch, Qt.QueuedConnection)

    def _dispatch(self, key, res, exc):
        cb, err_cb = self._cbs.pop(key, (None, None))
        try:
            if exc is not None:
                if err_cb:
                    err_cb(exc)
            elif cb:
                cb(res)
        except Exception:
            import logging
            logging.getLogger("zapret-tg.ui").exception("Ошибка в обработчике результата")


_bridge: Optional[_Bridge] = None


def run_bg(fn: Callable, cb: Optional[Callable] = None, err_cb: Optional[Callable] = None) -> None:
    global _bridge
    import threading
    if _bridge is None:
        _bridge = _Bridge()
    _bridge._n += 1
    key = _bridge._n
    _bridge._cbs[key] = (cb, err_cb)
    br = _bridge

    def work():
        try:
            res = fn()
            br.done.emit(key, res, None)
        except Exception as exc:  # noqa
            import logging
            logging.getLogger("zapret-tg.ui").exception("Фоновая задача упала")
            br.done.emit(key, None, exc)

    threading.Thread(target=work, daemon=True, name="bg").start()


# ---------------------------------------------------------------- toast

class Toast(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self.ic = QLabel()
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setMaximumWidth(520)
        lay.addWidget(self.ic, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_msg(self, text: str, level: str = "info", ms: int = 4500) -> None:
        p = Palette.p
        color = {"ok": p["on"], "warn": p["warn"], "err": p["err"]}.get(level, p["accent"])
        name = {"ok": "check", "warn": "warn", "err": "x"}.get(level, "info")
        self.ic.setPixmap(icons.pixmap(name, color, 18))
        self.text.setText(text)
        self.adjustSize()
        self.reposition()
        self.raise_()
        eff = self.graphicsEffect()
        if eff is None:
            eff = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(eff)
            self._fade = QPropertyAnimation(eff, b"opacity", self)
            self._fade.setDuration(220)
        self._fade.stop()
        self._fade.setStartValue(0.0 if not self.isVisible() else eff.opacity())
        self._fade.setEndValue(1.0)
        self.show()
        self._fade.start()
        self._timer.start(max(ms, 1500 + len(text) * 35))

    def reposition(self) -> None:
        par = self.parentWidget()
        if par:
            self.move(par.width() - self.width() - 26, par.height() - self.height() - 26)
