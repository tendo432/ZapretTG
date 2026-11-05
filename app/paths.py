"""Пути приложения.

Все рабочие данные лежат в C:\\ProgramData\\ZapretTG — путь без кириллицы и
пробелов (zapret/WinDivert плохо работает с кириллицей в пути), доступный
приложению с правами администратора.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ZapretTG"
APP_VERSION = "1.2.2"

IS_FROZEN = bool(getattr(sys, "frozen", False))
IS_WINDOWS = sys.platform == "win32"


def _resource_root() -> Path:
    if IS_FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


RESOURCE_DIR = _resource_root() / "resources"
BUNDLED_ZAPRET = RESOURCE_DIR / "zapret"


def _data_root() -> Path:
    override = os.environ.get("ZAPRETTG_DATA")
    if override:
        return Path(override)
    if IS_WINDOWS:
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


DATA_DIR = _data_root()
ZAPRET_DIR = DATA_DIR / "zapret"
CONFIG_FILE = DATA_DIR / "config.json"
LOG_DIR = DATA_DIR / "logs"
APP_LOG = LOG_DIR / "app.log"
PROXY_LOG = LOG_DIR / "tg-proxy.log"
ZAPRET_LOG = LOG_DIR / "zapret.log"


def exe_path() -> str:
    if IS_FROZEN:
        return sys.executable
    return f'"{sys.executable}" "{Path(sys.argv[0]).resolve()}"'


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
