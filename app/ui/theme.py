"""Цвета и стили интерфейса (полупрозрачный «неоновый» стиль)."""
from __future__ import annotations

PALETTES = {
    "dark": {
        "window": (18, 20, 36),          # тон окна (RGB), альфа задаётся отдельно
        "bg": "transparent",
        "rail": "rgba(14,15,28,0.55)",
        "surface": "rgba(36,39,64,0.62)",
        "surface_solid": "#232640",
        "surface2": "rgba(255,255,255,0.045)",
        "surface3": "rgba(255,255,255,0.08)",
        "border": "rgba(255,255,255,0.07)",
        "border_strong": "rgba(255,255,255,0.13)",
        "text": "#eef0ff",
        "muted": "#8b90b2",
        "faint": "#5f6488",
        "accent": "#c13cf0",
        "accent2": "#7b4dff",
        "accent3": "#2ee6d6",
        "accent_hover": "#d35cff",
        "accent_soft": "rgba(193,60,240,0.16)",
        "on": "#2ee6a8",
        "on_soft": "rgba(46,230,168,0.14)",
        "warn": "#ffc14d",
        "warn_soft": "rgba(255,193,77,0.15)",
        "err": "#ff5c7a",
        "err_soft": "rgba(255,92,122,0.15)",
        "input": "rgba(10,11,22,0.55)",
        "knob": "#ffffff",
        "track_off": "#3a3e60",
        "disc_off_top": "#3a3d5c",
        "disc_off_side": "#25273f",
        "menu": "#202339",
    },
    "light": {
        "window": (246, 246, 252),
        "bg": "transparent",
        "rail": "rgba(255,255,255,0.55)",
        "surface": "rgba(255,255,255,0.72)",
        "surface_solid": "#ffffff",
        "surface2": "rgba(20,20,60,0.04)",
        "surface3": "rgba(20,20,60,0.08)",
        "border": "rgba(20,20,60,0.08)",
        "border_strong": "rgba(20,20,60,0.16)",
        "text": "#171933",
        "muted": "#5d6185",
        "faint": "#9a9dba",
        "accent": "#a62fd6",
        "accent2": "#6a3df0",
        "accent3": "#10b9ab",
        "accent_hover": "#b844e6",
        "accent_soft": "rgba(166,47,214,0.12)",
        "on": "#12a978",
        "on_soft": "rgba(18,169,120,0.12)",
        "warn": "#c88a00",
        "warn_soft": "rgba(200,138,0,0.12)",
        "err": "#e03a5a",
        "err_soft": "rgba(224,58,90,0.10)",
        "input": "rgba(255,255,255,0.8)",
        "knob": "#ffffff",
        "track_off": "#c9cbe0",
        "disc_off_top": "#dcdcec",
        "disc_off_side": "#c4c5da",
        "menu": "#ffffff",
    },
}

FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif'
DISPLAY = '"Segoe UI Variable Display", "Segoe UI", "Inter", "Noto Sans", sans-serif'


def qss(p: dict, arrow: str = "", check: str = "") -> str:
    return f"""
* {{
    font-family: {FONT};
    font-size: 13px;
    color: {p['text']};
    outline: none;
}}
QMainWindow, #root, #content, QStackedWidget {{ background: transparent; }}
QToolTip {{
    background: {p['menu']}; color: {p['text']};
    border: 1px solid {p['border_strong']}; border-radius: 8px; padding: 6px 9px;
}}

/* --- оболочка --- */
#rail {{ background: {p['rail']}; border-right: 1px solid {p['border']}; }}
QToolButton#railBtn {{
    background: transparent; border: none; border-radius: 14px; padding: 6px 0 4px 0;
    color: {p['faint']}; font-size: 10px; font-weight: 600;
}}
QToolButton#railBtn:hover {{ background: {p['surface2']}; color: {p['muted']}; }}
QToolButton#railBtn:checked {{ background: {p['accent_soft']}; color: {p['text']}; }}
#titleBar {{ background: transparent; }}
#titleText {{ font-family: {DISPLAY}; font-size: 20px; font-weight: 700; }}
#titleSub {{ color: {p['muted']}; font-size: 12px; }}
QPushButton#winBtn {{ background: transparent; border: none; border-radius: 8px; padding: 0; }}
QPushButton#winBtn:hover {{ background: {p['surface3']}; }}
QPushButton#winClose {{ background: transparent; border: none; border-radius: 8px; padding: 0; }}
QPushButton#winClose:hover {{ background: #e8455f; }}

/* --- карточки и тексты --- */
#card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 18px; }}
#cardTitle {{ font-size: 15px; font-weight: 650; }}
#sectionTitle {{ font-size: 14px; font-weight: 650; }}
#heroTitle {{ font-family: {DISPLAY}; font-size: 24px; font-weight: 700; }}
#display {{ font-family: {DISPLAY}; font-size: 30px; font-weight: 700; }}
#muted {{ color: {p['muted']}; }}
#faint {{ color: {p['faint']}; font-size: 12px; }}
#hint {{ color: {p['muted']}; font-size: 12px; }}
#tiny {{ color: {p['faint']}; font-size: 11px; }}
#statValue {{ font-size: 17px; font-weight: 650; }}
#statLabel {{ color: {p['muted']}; font-size: 11px; }}
#statBox {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 12px; }}
#pill {{ border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
#pill[state="on"] {{ background: {p['on_soft']}; color: {p['on']}; }}
#pill[state="off"] {{ background: {p['surface3']}; color: {p['muted']}; }}
#pill[state="warn"] {{ background: {p['warn_soft']}; color: {p['warn']}; }}
#pill[state="err"] {{ background: {p['err_soft']}; color: {p['err']}; }}
#pill[state="accent"] {{ background: transparent; color: {p['accent']}; border: 1px solid {p['accent']}; }}
#moduleRow {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 14px; }}
#moduleRow:hover {{ border: 1px solid {p['border_strong']}; }}
#diagRow {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 12px; }}
#divider {{ background: {p['border']}; max-height: 1px; min-height: 1px; }}
#tile {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 14px; }}
#tile:hover {{ border: 1px solid {p['border_strong']}; }}
#tile[selected="true"] {{ background: {p['accent_soft']}; border: 1px solid {p['accent']}; }}

/* --- кнопки --- */
QPushButton {{
    background: {p['surface3']}; border: 1px solid {p['border']}; border-radius: 11px;
    padding: 8px 15px; font-weight: 600;
}}
QPushButton:hover {{ background: {p['border_strong']}; }}
QPushButton:pressed {{ background: {p['surface2']}; }}
QPushButton:disabled {{ color: {p['faint']}; }}
QPushButton#primary {{
    border: none; color: white; padding: 9px 18px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['accent']}, stop:1 {p['accent2']});
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['accent_hover']}, stop:1 {p['accent2']});
}}
QPushButton#primary:disabled {{ background: {p['surface3']}; color: {p['faint']}; }}
QPushButton#danger {{ color: {p['err']}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {p['border_strong']}; }}
QPushButton#ghost:hover {{ background: {p['surface2']}; }}
QPushButton#link {{ background: transparent; border: none; color: {p['accent']}; padding: 2px 4px; font-weight: 600; }}
QPushButton#link:hover {{ color: {p['accent_hover']}; }}
QPushButton#seg {{
    border-radius: 0; border: 1px solid {p['border']}; border-right: none; padding: 7px 14px;
    background: {p['surface2']}; color: {p['muted']};
}}
QPushButton#seg:hover {{ color: {p['text']}; }}
QPushButton#seg[first="true"] {{ border-top-left-radius: 10px; border-bottom-left-radius: 10px; }}
QPushButton#seg[last="true"] {{ border-top-right-radius: 10px; border-bottom-right-radius: 10px; border-right: 1px solid {p['border']}; }}
QPushButton#seg:checked {{
    color: white; border-color: transparent;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['accent']}, stop:1 {p['accent2']});
}}

/* --- поля ввода --- */
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {p['input']}; border: 1px solid {p['border']}; border-radius: 10px;
    padding: 7px 10px; selection-background-color: {p['accent']}; selection-color: white;
    min-height: 20px;
}}
QPlainTextEdit {{ padding: 6px; }}
QSpinBox {{ min-width: 90px; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
QLineEdit:read-only {{ color: {p['muted']}; }}
QPlainTextEdit#mono, QLineEdit#mono {{ font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; font-size: 12px; }}
QComboBox {{ padding-right: 30px; }}
QComboBox::drop-down {{ border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({arrow}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {p['menu']}; border: 1px solid {p['border_strong']}; border-radius: 10px; padding: 5px;
    selection-background-color: {p['accent_soft']}; selection-color: {p['text']}; outline: none;
}}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 0 8px; border-radius: 6px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid {p['border_strong']}; background: {p['input']}; }}
QCheckBox::indicator:checked {{ image: url({check}); border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p['accent']}, stop:1 {p['accent2']}); }}

/* --- прокрутка, вкладки, меню --- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {p['surface3']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0; background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {p['surface3']}; border-radius: 3px; min-width: 30px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {p['muted']}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {p['accent']}; }}
QTabBar::tab:hover {{ color: {p['text']}; }}
QMenu {{ background: {p['menu']}; border: 1px solid {p['border_strong']}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 28px 8px 14px; border-radius: 7px; }}
QMenu::item:selected {{ background: {p['accent_soft']}; }}
QMenu::item:disabled {{ color: {p['faint']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 5px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; margin-left: 6px; }}
QMenu::right-arrow {{ width: 10px; height: 10px; }}

#toast {{ background: {p['menu']}; border: 1px solid {p['border_strong']}; border-radius: 14px; }}
#toast QLabel {{ font-size: 13px; background: transparent; }}
#dialog {{ background: {p['menu']}; border: 1px solid {p['border_strong']}; border-radius: 18px; }}
"""
