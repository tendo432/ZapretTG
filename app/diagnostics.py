"""Диагностика — те же проверки, что «Run Diagnostics» в service.bat."""
from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import winutils
from .paths import IS_WINDOWS

OK, WARN, ERR = "ok", "warn", "err"


@dataclass
class Check:
    level: str
    title: str
    detail: str = ""
    link: str = ""
    action: str = ""          # идентификатор действия-исправления
    action_label: str = ""


CONFLICTING = ["GoodbyeDPI", "discordfix_zapret", "winws1", "winws2"]


def run_all(zapret_root: Path) -> List[Check]:
    res: List[Check] = []
    res.append(Check(OK, "Папка zapret", str(zapret_root)))

    if not IS_WINDOWS:
        res.append(Check(WARN, "Проверки доступны только в Windows"))
        return res

    services = winutils.list_services()
    names = " ".join(f"{s['name']} {s['display_name']}" for s in services).lower()

    # Base Filtering Engine
    if winutils.service_status("BFE") == "running":
        res.append(Check(OK, "Base Filtering Engine работает"))
    else:
        res.append(Check(ERR, "Служба Base Filtering Engine не запущена",
                         "Она необходима для работы zapret"))

    # Системный прокси
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    if winutils.reg_read(winreg.HKEY_CURRENT_USER, key, "ProxyEnable") == 1:
        server = winutils.reg_read(winreg.HKEY_CURRENT_USER, key, "ProxyServer") or ""
        res.append(Check(WARN, f"Включён системный прокси: {server}",
                         "Убедитесь, что он рабочий, или отключите его, если не используете"))
    else:
        res.append(Check(OK, "Системный прокси не используется"))

    # TCP timestamps
    rc, out = winutils.run_english("netsh interface tcp show global")
    ts_on = any("timestamps" in l.lower() and "enabled" in l.lower() for l in out.splitlines())
    if ts_on:
        res.append(Check(OK, "TCP timestamps включены"))
    else:
        rc, _ = winutils.run(["netsh", "interface", "tcp", "set", "global", "timestamps=enabled"])
        res.append(Check(OK if rc == 0 else ERR,
                         "TCP timestamps были выключены — " + ("включены" if rc == 0 else "не удалось включить")))

    # Adguard
    if winutils.process_running("AdguardSvc.exe"):
        res.append(Check(ERR, "Найден Adguard — может мешать Discord",
                         link="https://github.com/Flowseal/zapret-discord-youtube/issues/417"))
    else:
        res.append(Check(OK, "Adguard не найден"))

    # Killer
    if "killer" in names:
        res.append(Check(ERR, "Найдены службы Killer — конфликтуют с zapret",
                         link="https://github.com/Flowseal/zapret-discord-youtube/issues/2512#issuecomment-2821119513"))
    else:
        res.append(Check(OK, "Службы Killer не найдены"))

    # Intel Connectivity Network Service
    if any("intel" in s["display_name"].lower() and "connectivity" in s["display_name"].lower()
           and "network" in s["display_name"].lower() for s in services):
        res.append(Check(ERR, "Найдена Intel Connectivity Network Service — конфликтует с zapret",
                         link="https://github.com/ValdikSS/GoodbyeDPI/issues/541#issuecomment-2661670982"))
    else:
        res.append(Check(OK, "Intel Connectivity Network Service не найдена"))

    # Check Point
    if "tracsrvwrapper" in names or "epwd" in names:
        res.append(Check(ERR, "Найдены службы Check Point — конфликтуют с zapret", "Попробуйте удалить Check Point"))
    else:
        res.append(Check(OK, "Check Point не найден"))

    # SmartByte
    if "smartbyte" in names:
        res.append(Check(ERR, "Найдены службы SmartByte — конфликтуют с zapret",
                         "Удалите или отключите SmartByte через services.msc"))
    else:
        res.append(Check(OK, "SmartByte не найден"))

    # Кириллица в пути
    if re.search("[а-яА-ЯёЁ]", str(zapret_root)):
        res.append(Check(WARN, "В пути к zapret есть кириллица", "Перенесите программу, например, в C:\\zapret"))
    else:
        res.append(Check(OK, "Путь без кириллицы"))

    # OneDrive
    od = os.environ.get("OneDrive")
    if od and str(zapret_root).lower().startswith(od.lower()):
        res.append(Check(ERR, "zapret находится в папке OneDrive"))
    else:
        res.append(Check(OK, "Не в папке OneDrive"))

    # WinDivert64.sys
    if not list((zapret_root / "bin").glob("*.sys")):
        res.append(Check(ERR, "Файл WinDivert64.sys не найден",
                         "Возможно, его удалил антивирус. Добавьте папку в исключения и переустановите файлы."))

    # VPN
    vpn = [s["name"] for s in services if "vpn" in (s["name"] + s["display_name"]).lower() or "happservice" in s["name"].lower()]
    if vpn:
        res.append(Check(WARN, "Найдены службы VPN: " + ", ".join(vpn[:6]),
                         "Некоторые VPN конфликтуют с zapret — отключите их на время работы обхода"))
    else:
        res.append(Check(OK, "Службы VPN не найдены"))

    # Secure DNS
    doh = _doh_configured()
    if doh:
        res.append(Check(OK, "Защищённый DNS настроен"))
    else:
        res.append(Check(WARN, "Защищённый DNS (DoH) не настроен",
                         "Настройте безопасный DNS в браузере или в параметрах Windows 11"))

    # hosts
    hosts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
    try:
        h = hosts.read_text(encoding="utf-8", errors="replace").lower()
        if "youtube.com" in h or "youtu.be" in h:
            res.append(Check(WARN, "В hosts есть записи youtube.com / youtu.be", "Это может мешать работе YouTube"))
    except Exception:
        pass

    # WinDivert без winws
    winws = bool(winutils.process_running("winws.exe"))
    wd = winutils.service_status("WinDivert")
    if not winws and wd in ("running", "stop_pending"):
        res.append(Check(WARN, "WinDivert активен, но winws.exe не запущен",
                         "Возможно, WinDivert занят другой программой обхода",
                         action="fix_windivert", action_label="Удалить WinDivert"))

    # Конфликтующие обходы
    found = [s for s in CONFLICTING if winutils.service_info(s) is not None]
    if found:
        res.append(Check(ERR, "Найдены конфликтующие службы обхода: " + ", ".join(found),
                         action="remove_conflicts", action_label="Удалить их"))
    else:
        res.append(Check(OK, "Конфликтующих служб обхода нет"))

    return res


def _doh_configured() -> bool:
    try:
        import winreg
        base = r"System\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            i = 0
            while True:
                try:
                    iface = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if _has_doh_flags(winreg, f"{base}\\{iface}"):
                    return True
    except Exception:
        pass
    return False


def _has_doh_flags(winreg, path: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            try:
                if int(winreg.QueryValueEx(k, "DohFlags")[0]) > 0:
                    return True
            except (OSError, ValueError):
                pass
            j = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, j)
                except OSError:
                    return False
                j += 1
                if _has_doh_flags(winreg, f"{path}\\{sub}"):
                    return True
    except OSError:
        return False


def fix_windivert() -> str:
    winutils.stop_and_delete_service("WinDivert")
    if winutils.service_info("WinDivert") is None:
        return "WinDivert удалён"
    for s in ("GoodbyeDPI",):
        if winutils.service_info(s) is not None:
            winutils.stop_and_delete_service(s)
    winutils.stop_and_delete_service("WinDivert")
    if winutils.service_info("WinDivert") is None:
        return "WinDivert удалён после удаления конфликтующих служб"
    return "WinDivert всё ещё нельзя удалить — проверьте, не использует ли его другая программа обхода"


def remove_conflicts() -> str:
    removed = []
    for s in CONFLICTING:
        if winutils.service_info(s) is not None:
            winutils.stop_and_delete_service(s)
            removed.append(s)
    for s in ("WinDivert", "WinDivert14"):
        winutils.stop_and_delete_service(s)
    return ("Удалены: " + ", ".join(removed)) if removed else "Конфликтующих служб нет"


DISCORDS = [
    ("Discord.exe", "Discord", "discord"),
    ("DiscordPTB.exe", "Discord PTB", "discordptb"),
    ("DiscordCanary.exe", "Discord Canary", "discordcanary"),
    ("DiscordDevelopment.exe", "Discord Development", "discorddevelopment"),
]


def clear_discord_cache() -> List[str]:
    appdata = os.environ.get("APPDATA", "")
    out: List[str] = []
    found = False
    for proc, title, folder in DISCORDS:
        d = Path(appdata) / folder
        if not d.is_dir():
            continue
        found = True
        if winutils.process_running(proc):
            winutils.kill_image(proc)
            time.sleep(1)
            out.append(f"{title} закрыт")
        for sub in ("Cache", "Code Cache", "GPUCache"):
            p = d / sub
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                out.append(("Не удалось удалить " if p.exists() else "Удалено ") + str(p))
    if not found:
        out.append("Discord не найден")
    return out
