"""Полупрозрачное окно с размытием фона на Windows 10/11.

Windows 11 22H2+: системный Acrylic (DWMWA_SYSTEMBACKDROP_TYPE).
Windows 10 / ранний 11: SetWindowCompositionAttribute (blur behind).
Если размытие недоступно — окно остаётся непрозрачным (без «мутного» фона).
"""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger("zapret-tg.ui")

IS_WIN = sys.platform == "win32"


def _build() -> int:
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


class _ACCENT(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WCA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


class _MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]


def _dwm_set(hwnd: int, attr: int, value: int) -> bool:
    try:
        v = ctypes.c_int(value)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v))
        return hr == 0
    except Exception:
        return False


def apply_backdrop(hwnd: int, dark: bool, enable: bool) -> bool:
    """Включить размытие. Возвращает True, если фон действительно размыт."""
    if not IS_WIN or not hwnd:
        return False
    build = _build()
    if build >= 22000:
        _dwm_set(hwnd, 20, 1 if dark else 0)      # DWMWA_USE_IMMERSIVE_DARK_MODE
        _dwm_set(hwnd, 33, 2)                     # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND
    if not enable:
        if build >= 22621:
            _dwm_set(hwnd, 38, 1)                 # DWMSBT_NONE
        _set_accent(hwnd, 0, 0)
        return False
    try:
        # Qt делает безрамочные полупрозрачные окна «слоёными» (WS_EX_LAYERED) —
        # к ним системный backdrop Windows 11 не применяется, а accent-policy работает.
        if build >= 22000:
            return _set_accent(hwnd, 4, 0x01000000)   # ACCENT_ENABLE_ACRYLICBLURBEHIND
        return _set_accent(hwnd, 3, 0)                # ACCENT_ENABLE_BLURBEHIND (Windows 10)
    except Exception as exc:
        log.debug("backdrop: %r", exc)
        return False


def _set_accent(hwnd: int, state: int, color: int) -> bool:
    try:
        accent = _ACCENT(state, 0, color, 0)
        data = _WCA(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent))
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        return bool(fn(ctypes.c_void_p(hwnd), ctypes.byref(data)))
    except Exception:
        return False


def round_corners_native() -> bool:
    """Слоёные окна Windows не скругляет — углы рисуем сами."""
    return False
