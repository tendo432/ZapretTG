"""Системные функции Windows: скрытый запуск команд, службы, автозапуск."""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import tempfile
from typing import List, Optional, Sequence, Tuple, Union

from .paths import APP_NAME, IS_FROZEN, IS_WINDOWS, exe_path

log = logging.getLogger("zapret-tg.win")

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def _startupinfo():
    if not IS_WINDOWS:
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return si


def run(cmd: Union[str, Sequence[str]], timeout: float = 30, shell: bool = False,
        encoding: str = "cp437") -> Tuple[int, str]:
    """Запустить команду без окна консоли и вернуть (код, вывод)."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            shell=shell,
            startupinfo=_startupinfo(),
            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        out = (p.stdout or b"") + (p.stderr or b"")
        return p.returncode, out.decode(encoding, errors="replace")
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as exc:
        return -1, repr(exc)


def run_english(command: str, timeout: float = 30) -> Tuple[int, str]:
    """Выполнить консольную команду с кодовой страницей 437.

    netsh/sc при chcp 437 выводят текст по-английски независимо от языка
    Windows — так же делает оригинальный service.bat.
    """
    return run(f'cmd /d /c "chcp 437 >nul & {command}"', timeout=timeout, shell=False)


def is_admin() -> bool:
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(args: List[str]) -> bool:
    if not IS_WINDOWS:
        return False
    import sys
    if IS_FROZEN:
        exe, params = sys.executable, subprocess.list2cmdline(args)
    else:
        exe = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + args)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return rc > 32


def open_path(path: str) -> None:
    try:
        if IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        log.warning("Не удалось открыть %s: %r", path, exc)


def open_url(url: str) -> bool:
    try:
        if IS_WINDOWS:
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            import webbrowser
            webbrowser.open(url)
        return True
    except Exception as exc:
        log.warning("Не удалось открыть ссылку %s: %r", url, exc)
        return False


# ---------------------------------------------------------------- службы

def service_info(name: str) -> Optional[dict]:
    """Состояние службы Windows или None, если её нет."""
    if not IS_WINDOWS:
        return None
    try:
        import psutil
        return psutil.win_service_get(name).as_dict()
    except Exception:
        return None


def service_status(name: str) -> Optional[str]:
    info = service_info(name)
    return info.get("status") if info else None


def list_services() -> List[dict]:
    if not IS_WINDOWS:
        return []
    import psutil
    out = []
    try:
        for s in psutil.win_service_iter():
            try:
                out.append({"name": s.name(), "display_name": s.display_name()})
            except Exception:
                continue
    except Exception:
        pass
    return out


def stop_and_delete_service(name: str) -> bool:
    run(["net", "stop", name], timeout=40)
    rc, _ = run(["sc", "delete", name], timeout=20)
    return rc == 0


def process_running(image: str) -> List[int]:
    try:
        import psutil
        res = []
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == image.lower():
                    res.append(p.pid)
            except Exception:
                continue
        return res
    except Exception:
        return []


def kill_image(image: str) -> None:
    run(["taskkill", "/IM", image, "/F"], timeout=15)


# -------------------------------------------------------------- автозапуск

TASK_NAME = APP_NAME


def _task_xml(command: str, arguments: str) -> str:
    # Задача планировщика: при входе пользователя, с наивысшими правами (без
    # запроса UAC), без ограничения по питанию от батареи и по времени работы.
    import getpass
    user = os.environ.get("USERDOMAIN", "") + "\\" + getpass.getuser() if os.environ.get("USERDOMAIN") else getpass.getuser()
    esc = lambda s: (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{APP_NAME}: zapret + Telegram WS proxy</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{esc(user)}</UserId>
      <Delay>PT5S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{esc(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{esc(command)}</Command>
      <Arguments>{esc(arguments)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def autostart_refresh() -> None:
    """Если exe перенесли, обновить путь в задаче планировщика."""
    if not IS_WINDOWS or not IS_FROZEN or not autostart_enabled():
        return
    import sys
    rc, out = run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"], timeout=15, encoding="utf-16")
    if rc == 0 and sys.executable.lower() not in out.lower():
        rc2, out2 = run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"], timeout=15, encoding="utf-8")
        if sys.executable.lower() not in out2.lower():
            set_autostart(True)


def autostart_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    rc, _ = run(["schtasks", "/Query", "/TN", TASK_NAME], timeout=15)
    return rc == 0


def set_autostart(enabled: bool) -> Tuple[bool, str]:
    if not IS_WINDOWS:
        return False, "Только для Windows"
    if not enabled:
        rc, out = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=15)
        return (rc == 0 or not autostart_enabled()), out
    import sys
    if IS_FROZEN:
        command, arguments = sys.executable, "--autostart"
    else:
        command = sys.executable.replace("python.exe", "pythonw.exe")
        arguments = f'"{os.path.abspath(sys.argv[0])}" --autostart'
    xml = _task_xml(command, arguments)
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-16") as f:
            f.write(xml)
        rc, out = run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", path, "/F"], timeout=20)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    # убрать возможные старые записи автозапуска оригинального tg-ws-proxy,
    # чтобы прокси не запускался дважды и не занимал порт
    _remove_legacy_tgws_autostart()
    return rc == 0, out


def _remove_legacy_tgws_autostart() -> None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                winreg.QueryValueEx(k, "TgWsProxy")
                winreg.DeleteValue(k, "TgWsProxy")
                log.info("Удалён старый автозапуск TgWsProxy")
            except FileNotFoundError:
                pass
    except Exception:
        pass


def reg_read(root, path: str, name: str):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


def reg_write_sz(root, path: str, name: str, value: str) -> bool:
    try:
        import winreg
        with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        return True
    except Exception:
        return False


def http_get(url: str, timeout: float = 15, binary: bool = False):
    """Скачивание через urllib с сертификатами certifi."""
    import ssl
    import urllib.request
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


# ------------------------------------------------------------ прочее

_mutex_handle = None


def acquire_single_instance(name: str) -> bool:
    """Именованный мьютекс Windows: True, если мы первый экземпляр.

    Надёжнее, чем только QLocalServer: два экземпляра (автозапуск + ручной
    запуск) убивали winws.exe друг друга и боролись за порт прокси — со
    стороны это выглядело как «обход и прокси сами выключаются».
    """
    global _mutex_handle
    if not IS_WINDOWS:
        return True
    try:
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        h = k32.CreateMutexW(None, False, f"Local\\{name}")
        if not h:
            return True
        if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            k32.CloseHandle(ctypes.c_void_p(h))
            return False
        _mutex_handle = h
        return True
    except Exception:
        return True


def windows_build() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        import sys
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def powershell(script: str, timeout: float = 60) -> Tuple[int, str]:
    """Выполнить скрипт PowerShell без окна. Вывод в UTF-8."""
    import base64
    wrapped = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';" + script
    enc = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", enc], timeout=timeout, encoding="utf-8")


def defender_add_exclusions(paths: List[str]) -> Tuple[bool, str]:
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in paths)
    rc, out = powershell(f"Add-MpPreference -ExclusionPath {quoted} -ErrorAction Stop; 'OK'", timeout=60)
    if rc == 0 and "OK" in out:
        return True, "Папки добавлены в исключения Защитника Windows"
    return False, ("Не удалось добавить исключения автоматически (возможно, включена «Защита от подделки» "
                   "или установлен другой антивирус). Добавьте папку вручную.\n" + out.strip()[:300])


def defender_has_exclusion(path: str) -> Optional[bool]:
    rc, out = powershell("(Get-MpPreference).ExclusionPath -join \"`n\"", timeout=40)
    if rc != 0:
        return None
    items = [l.strip().rstrip("\\").lower() for l in out.splitlines() if l.strip()]
    return path.rstrip("\\").lower() in items
