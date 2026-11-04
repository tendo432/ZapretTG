"""Общая основа страниц (заголовок страницы показывается в шапке окна)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


def fmt_uptime(sec) -> str:
    if not sec:
        return ""
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d} д {h} ч"
    if h:
        return f"{h} ч {m} мин"
    return f"{max(m, 1)} мин" if sec >= 60 else "меньше минуты"


def human_speed(bps: float) -> str:
    for unit, div in (("ГБ/с", 1 << 30), ("МБ/с", 1 << 20), ("КБ/с", 1 << 10)):
        if bps >= div:
            return f"{bps / div:.1f} {unit}"
    return f"{bps:.0f} Б/с"


class Page(QWidget):
    title = ""
    subtitle = ""

    def __init__(self, ctx, scroll: bool = True):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        inner = QWidget()
        self.inner = inner
        inner.setAttribute(Qt.WA_TranslucentBackground)
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(26, 12, 22, 24)
        self.body.setSpacing(14)
        if scroll:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QScrollArea.NoFrame)
            # окно не даст сжать себя уже содержимого (см. MainWindow._fit_min_size);
            # прокрутка по горизонтали — запасной вариант, чтобы ничего не обрезалось
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            sa.viewport().setAutoFillBackground(False)
            sa.setWidget(inner)
            outer.addWidget(sa)
            self.scroll = sa
        else:
            outer.addWidget(inner)
            self.scroll = None

    def finish(self) -> None:
        self.body.addStretch(1)

    def on_status(self, zs: dict, ts: dict, ds: dict = None) -> None:
        pass

    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass


def ru_bytes(v: str) -> str:
    """«1.2MB» из прокси → «1.2 МБ»."""
    s = str(v or "0B")
    for en, ru in (("TB", " ТБ"), ("GB", " ГБ"), ("MB", " МБ"), ("KB", " КБ"), ("B", " Б")):
        if s.endswith(en):
            return s[: -len(en)].strip() + ru
    return s
