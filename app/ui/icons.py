"""Векторные иконки (простые линейные SVG) и иконка приложения/трея."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient
from PySide6.QtSvg import QSvgRenderer

_P = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h5v-6h4v6h5V9.5"/>',
    "shield": '<path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.3 7.5 9.5 4.4-1.2 7.5-4.9 7.5-9.5V6L12 3z"/><path d="m8.8 12 2.2 2.2 4.4-4.4"/>',
    "send": '<path d="M21 3 3 10.5l7 2.5 2.5 7L21 3z"/><path d="m10 13 4.5-4.5"/>',
    "pulse": '<path d="M3 12h4l2.5-6 5 12 2.5-6H21"/>',
    "gear": '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>',
    "doc": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 3.5V8h4.5"/><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M20 20.5V16h-4.5"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "warn": '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/>',
    "x": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.3"/>',
    "game": '<rect x="2.5" y="7" width="19" height="11" rx="4.5"/><path d="M7.5 10.5v4M5.5 12.5h4M15.5 11.5v.1M18 13.5v.1"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.1M4.5 12h.1M4.5 18h.1"/>',
    "download": '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5"/><path d="M4.5 19.5h15"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.7 3.8 5.7 3.8 9s-1.2 6.3-3.8 9c-2.6-2.7-3.8-5.7-3.8-9S9.4 5.7 12 3z"/>',
    "flask": '<path d="M9.5 3h5M10 3v6L4.8 18.2A1.9 1.9 0 0 0 6.5 21h11a1.9 1.9 0 0 0 1.7-2.8L14 9V3"/><path d="M7.3 15h9.4"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6 7l1 13h10l1-13"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "min": '<path d="M6 12h12"/>',
    "max": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "restore": '<rect x="5" y="8.5" width="10.5" height="10.5" rx="2"/><path d="M8.5 8.5V6.5A1.5 1.5 0 0 1 10 5h7.5A1.5 1.5 0 0 1 19 6.5V14a1.5 1.5 0 0 1-1.5 1.5h-2"/>',
    "close": '<path d="m6.5 6.5 11 11M17.5 6.5l-11 11"/>',
    "sparkle": '<path d="M12 3.5 13.8 9 19.5 10.8 13.8 12.6 12 18.2 10.2 12.6 4.5 10.8 10.2 9z"/><path d="M18.5 3.5v3M17 5h3"/>',
    "bolt": '<path d="M13 3 5 13.5h6L10.5 21 19 10h-6z"/>',
    "power": '<path d="M12 3v8"/><path d="M6.4 6.6a8 8 0 1 0 11.2 0"/>',
}


def icon(name: str, color: str = "#8e96a8", size: int = 20, stroke: float = 1.8) -> QIcon:
    return QIcon(pixmap(name, color, size, stroke))


def pixmap(name: str, color: str, size: int = 20, stroke: float = 1.8, scale: float = 2.0) -> QPixmap:
    body = _P.get(name, _P["info"])
    fill = color if name == "play" else "none"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" '
           f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    px = QPixmap(int(size * scale), int(size * scale))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    px.setDevicePixelRatio(scale)
    return px


def _shield_path(s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(s * 0.5, s * 0.06)
    path.lineTo(s * 0.88, s * 0.2)
    path.cubicTo(s * 0.88, s * 0.62, s * 0.74, s * 0.84, s * 0.5, s * 0.95)
    path.cubicTo(s * 0.26, s * 0.84, s * 0.12, s * 0.62, s * 0.12, s * 0.2)
    path.closeSubpath()
    return path


def app_pixmap(size: int = 256, state: str = "on") -> QPixmap:
    """Щит с бумажным самолётиком. state: on / partial / off."""
    colors = {
        "on": ("#5b8cff", "#2fc4a0"),
        "partial": ("#f0b429", "#f08a29"),
        "off": ("#6b7385", "#4a5160"),
    }[state]
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(colors[0]))
    g.setColorAt(1, QColor(colors[1]))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(_shield_path(size))
    # самолётик
    s = size
    plane = QPainterPath()
    plane.moveTo(s * 0.30, s * 0.50)
    plane.lineTo(s * 0.71, s * 0.33)
    plane.lineTo(s * 0.61, s * 0.71)
    plane.lineTo(s * 0.50, s * 0.58)
    plane.closeSubpath()
    p.setBrush(QColor(255, 255, 255, 240))
    p.drawPath(plane)
    pen = QPen(QColor(colors[0]).darker(115), max(1.0, s * 0.025))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.50, s * 0.58), QPointF(s * 0.66, s * 0.40))
    p.end()
    return px


def app_icon(state: str = "on") -> QIcon:
    ic = QIcon()
    for sz in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(sz, state))
    return ic
