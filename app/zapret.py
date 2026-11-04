"""Управление zapret (сборка Flowseal/zapret-discord-youtube).

Повторяет функции service.bat, но без консольного меню:
  * запуск любой стратегии general*.bat (аргументы берутся прямо из .bat,
    поэтому новые/обновлённые стратегии подхватываются автоматически);
  * установка стратегии как службы Windows «zapret» (совместимо с service.bat);
  * Game Filter, IPSet Filter, пользовательские списки, замена активных фейков;
  * обновление ipset-all.txt, проверка hosts, проверка/установка обновлений;
  * запуск оригинального скрипта тестов стратегий.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

from . import winutils
from .paths import BUNDLED_ZAPRET, IS_WINDOWS, ZAPRET_DIR, ZAPRET_LOG

log = logging.getLogger("zapret-tg.zapret")

SERVICE_NAME = "zapret"
REPO = "Flowseal/zapret-discord-youtube"
RAW = f"https://raw.githubusercontent.com/{REPO}/refs/heads/main/.service"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/main/.service/version.txt"
IPSET_URL = f"{RAW}/ipset-service.txt"
HOSTS_URL = f"{RAW}/hosts"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

IPSET_NONE_MARK = "203.0.113.113/32"
DEFAULT_GF_RANGE = "1024-65535"

# файлы, которые принадлежат пользователю и не перезаписываются при обновлении
USER_FILES = [
    "lists/list-general-user.txt",
    "lists/list-exclude-user.txt",
    "lists/ipset-exclude-user.txt",
    "utils/game_filter.enabled",
    "utils/check_updates.enabled",
]

HOSTS_FILE = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
HOSTS_BEGIN = "# >>> ZapretTG hosts (Flowseal/zapret-discord-youtube) >>>"
HOSTS_END = "# <<< ZapretTG hosts <<<"


def _natural_key(name: str):
    return re.sub(r"(\d+)", lambda m: m.group(1).zfill(8), name.lower())


def _read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp1251", "cp866"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")) or (0,)


class ZapretManager:
    def __init__(self, cfg, on_change: Optional[Callable[[], None]] = None):
        self.cfg = cfg
        self.root: Path = ZAPRET_DIR
        self.on_change = on_change or (lambda: None)
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._want_running = False
        self._started_at: Optional[float] = None
        self._gen = 0
        self._backoff = 3.0
        self._log_pos = 0
        self.last_error: str = ""
        self._monitor: Optional[threading.Thread] = None

    # ------------------------------------------------------------ файлы
    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def lists_dir(self) -> Path:
        return self.root / "lists"

    @property
    def utils_dir(self) -> Path:
        return self.root / "utils"

    @property
    def winws(self) -> Path:
        return self.bin_dir / "winws.exe"

    @staticmethod
    def version_of(folder: Path) -> str:
        sb = folder / "service.bat"
        if not sb.exists():
            return "0"
        m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', _read_text(sb))
        return m.group(1).strip() if m else "0"

    def local_version(self) -> str:
        return self.version_of(self.root)

    def install_files(self) -> None:
        """Распаковать встроенный zapret в ProgramData (или обновить его)."""
        installed = self.root.exists() and self.winws.exists()
        if installed and _version_tuple(self.version_of(BUNDLED_ZAPRET)) <= _version_tuple(self.local_version()):
            self.ensure_user_lists()
            return
        if not BUNDLED_ZAPRET.exists():
            log.error("Встроенные файлы zapret не найдены: %s", BUNDLED_ZAPRET)
            return
        log.info("Установка файлов zapret %s → %s", self.version_of(BUNDLED_ZAPRET), self.root)
        self._replace_tree(BUNDLED_ZAPRET)

    def _replace_tree(self, src: Path) -> None:
        """Скопировать новую версию zapret поверх старой, сохранив данные пользователя."""
        was_running = self.is_running_app()
        if was_running:
            self.stop()
        saved: Dict[str, bytes] = {}
        for rel in USER_FILES:
            p = self.root / rel
            if p.exists():
                saved[rel] = p.read_bytes()
        ipset_mode = self.ipset_status() if (self.lists_dir / "ipset-all.txt").exists() else None
        self.root.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            dst = self.root / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        for rel, data in saved.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        if ipset_mode and ipset_mode != self.ipset_status():
            self.set_ipset_mode(ipset_mode)
        self.ensure_user_lists()
        if was_running:
            self.start()

    def ensure_user_lists(self) -> None:
        """Аналог :load_user_lists — пользовательские списки не должны быть пустыми."""
        self.lists_dir.mkdir(parents=True, exist_ok=True)
        defaults = {
            "ipset-exclude-user.txt": "203.0.113.113/32\n",
            "list-general-user.txt": "# Never leave this file empty\ndomain.example.abc\n",
            "list-exclude-user.txt": "domain.example.abc\n",
        }
        for name, content in defaults.items():
            p = self.lists_dir / name
            if not p.exists():
                p.write_text(content, encoding="utf-8")

    # -------------------------------------------------------- стратегии
    def strategies(self) -> List[str]:
        if not self.root.exists():
            return []
        files = [p.name for p in self.root.glob("*.bat") if not p.name.lower().startswith("service")]
        return sorted(files, key=_natural_key)

    @staticmethod
    def strategy_title(name: str) -> str:
        n = name[:-4] if name.lower().endswith(".bat") else name
        return n

    def strategy_note(self, name: str) -> str:
        p = self.root / name
        if not p.exists():
            return ""
        notes = []
        for line in _read_text(p).splitlines():
            s = line.strip()
            if s.startswith("::") and "65001" not in s:
                notes.append(s.lstrip(": ").strip())
        return "; ".join(n for n in notes if n)

    def build_args(self, name: str) -> str:
        """Достать из .bat командную строку winws.exe и подставить переменные."""
        p = self.root / name
        lines = _read_text(p).splitlines()
        start = next((i for i, l in enumerate(lines) if "winws.exe" in l.lower()), None)
        if start is None:
            raise ValueError(f"В {name} не найден запуск winws.exe")
        parts: List[str] = []
        for line in lines[start:]:
            s = line.rstrip()
            if s.endswith("^"):
                parts.append(s[:-1])
                continue
            parts.append(s)
            break
        joined = " ".join(parts)
        low = joined.lower()
        idx = low.find('winws.exe"')
        if idx >= 0:
            rest = joined[idx + len('winws.exe"'):]
        else:
            rest = joined[low.find("winws.exe") + len("winws.exe"):]

        gf_tcp, gf_udp, gf_any = self._game_filter_values()
        bin_s = str(self.bin_dir) + "\\"
        lists_s = str(self.lists_dir) + "\\"
        root_s = str(self.root) + "\\"
        variables = {
            "BIN": bin_s, "LISTS": lists_s, "~DP0": root_s,
            "GAMEFILTERTCP": gf_tcp, "GAMEFILTERUDP": gf_udp, "GAMEFILTER": gf_any,
        }

        def subst(m: re.Match) -> str:
            key = m.group(1).upper()
            if key in variables:
                return variables[key]
            return os.environ.get(m.group(1), "")

        rest = rest.replace("%%", "\x00")
        rest = re.sub(r"%(~dp0|[A-Za-z_][A-Za-z0-9_]*)%", subst, rest, flags=re.I)
        rest = rest.replace("%~dp0", root_s).replace("\x00", "%")
        # снять экранирование ^ вне кавычек (как это делает cmd.exe)
        out, in_q, i = [], False, 0
        while i < len(rest):
            ch = rest[i]
            if ch == '"':
                in_q = not in_q
                out.append(ch)
            elif ch == "^" and not in_q and i + 1 < len(rest):
                i += 1
                out.append(rest[i])
            else:
                out.append(ch)
            i += 1
        return re.sub(r"\s+", " ", "".join(out)).strip()

    # ------------------------------------------------------ Game Filter
    @property
    def _gf_file(self) -> Path:
        return self.utils_dir / "game_filter.enabled"

    @staticmethod
    def validate_range(value: str) -> Optional[str]:
        v = (value or "").replace(" ", "")
        if not v:
            return None
        for item in v.split(","):
            m = re.fullmatch(r"([1-9]\d{0,4})(?:-([1-9]\d{0,4}))?", item)
            if not m:
                return None
            a = int(m.group(1))
            b = int(m.group(2) or a)
            if a > 65535 or b > 65535 or a > b:
                return None
        return v

    def game_filter(self) -> Dict[str, str]:
        mode, tcp, udp = "disabled", DEFAULT_GF_RANGE, DEFAULT_GF_RANGE
        if self._gf_file.exists():
            tcp_c = udp_c = None
            for line in _read_text(self._gf_file).splitlines():
                k, _, v = line.strip().partition("=")
                k, v = k.strip().lower(), v.strip()
                if k == "mode":
                    mode = v or mode
                elif k == "all":
                    mode = "all"
                elif k == "udp":
                    if v:
                        udp_c = v
                    else:
                        mode = "udp"
                elif k == "tcp":
                    if v:
                        tcp_c = v
                    else:
                        mode = "tcp"
            tcp = self.validate_range(tcp_c or "") or tcp
            udp = self.validate_range(udp_c or "") or udp
        if mode not in ("disabled", "all", "tcp", "udp"):
            mode = "disabled"
        return {"mode": mode, "tcp": tcp, "udp": udp}

    def set_game_filter(self, mode: str, tcp: str, udp: str) -> None:
        tcp = self.validate_range(tcp) or DEFAULT_GF_RANGE
        udp = self.validate_range(udp) or DEFAULT_GF_RANGE
        self.utils_dir.mkdir(parents=True, exist_ok=True)
        self._gf_file.write_text(f"mode={mode}\r\ntcp={tcp}\r\nudp={udp}\r\n", encoding="ascii")

    def _game_filter_values(self) -> Tuple[str, str, str]:
        gf = self.game_filter()
        mode = gf["mode"]
        if mode == "all":
            return gf["tcp"], gf["udp"], gf["tcp"]
        if mode == "tcp":
            return gf["tcp"], "12", gf["tcp"]
        if mode == "udp":
            return "12", gf["udp"], gf["udp"]
        return "12", "12", "12"

    # -------------------------------------------------------- IPSet
    @property
    def _ipset_file(self) -> Path:
        return self.lists_dir / "ipset-all.txt"

    def ipset_status(self) -> str:
        p = self._ipset_file
        if not p.exists():
            return "any"
        text = _read_text(p)
        if not text.strip("\r\n") and not text.splitlines():
            return "any"
        if not text.splitlines():
            return "any"
        return "none" if IPSET_NONE_MARK in text else "loaded"

    def set_ipset_mode(self, mode: str) -> Tuple[bool, str]:
        cur = self.ipset_status()
        if mode == cur:
            return True, ""
        p, backup = self._ipset_file, self._ipset_file.with_name("ipset-all.txt.backup")
        if mode == "loaded":
            if cur == "none" or cur == "any":
                if backup.exists():
                    shutil.copy2(backup, p)
                    backup.unlink()
                    return True, ""
                return False, "Нет резервной копии списка. Сначала обновите IPSet-список."
        if cur == "loaded":
            shutil.copy2(p, backup)
        if mode == "none":
            p.write_text(IPSET_NONE_MARK + "\r\n", encoding="ascii")
        elif mode == "any":
            p.write_bytes(b"")
        return True, ""

    def update_ipset(self) -> Tuple[bool, str]:
        try:
            data = winutils.http_get(IPSET_URL, timeout=30, binary=True)
            if len(data) < 100:
                return False, "Получен пустой список"
            # если сейчас режим none/any — обновляем резервную копию, режим не меняем
            target = self._ipset_file if self.ipset_status() == "loaded" else self._ipset_file.with_name("ipset-all.txt.backup")
            target.write_bytes(data)
            lines = data.count(b"\n")
            return True, f"Список IPSet обновлён ({lines} записей)"
        except Exception as exc:
            return False, f"Не удалось скачать список: {exc}"

    # ------------------------------------------------- user lists
    USER_LISTS = {
        "list-general-user.txt": "Домены для обхода",
        "list-exclude-user.txt": "Домены-исключения",
        "ipset-exclude-user.txt": "IP-исключения",
    }

    def read_list(self, name: str) -> str:
        p = self.lists_dir / name
        return _read_text(p) if p.exists() else ""

    def write_list(self, name: str, text: str) -> None:
        lines = [l.strip() for l in text.replace("\r", "").split("\n")]
        lines = [l for l in lines if l]
        if not lines:  # файл не должен быть пустым — как в service.bat
            lines = ["203.0.113.113/32"] if name.startswith("ipset") else ["domain.example.abc"]
        (self.lists_dir / name).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

    # ------------------------------------------------------ fakes
    @staticmethod
    def _sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""

    def fakes(self) -> Dict[str, object]:
        files = sorted([p for p in self.bin_dir.glob("*.bin") if not p.stem.upper().startswith("ACTIVE_")],
                       key=lambda p: _natural_key(p.name))
        hashes = {p.stem: self._sha(p) for p in files}
        res = {"files": [p.stem for p in files]}
        for kind, fname in (("discord", "ACTIVE_DISCORD_UDP.bin"), ("game", "ACTIVE_GAME_UDP.bin")):
            h = self._sha(self.bin_dir / fname)
            res[kind] = next((n for n, hh in hashes.items() if h and hh == h), "(не найден)")
        return res

    def replace_fake(self, kind: str, source: str) -> Tuple[bool, str]:
        target = self.bin_dir / ("ACTIVE_DISCORD_UDP.bin" if kind == "discord" else "ACTIVE_GAME_UDP.bin")
        src = self.bin_dir / f"{source}.bin"
        if not src.exists():
            return False, "Файл не найден"
        try:
            shutil.copyfile(src, target)
            return True, "Активный фейк заменён. Перезапустите обход."
        except Exception as exc:
            return False, f"Не удалось заменить: {exc}"

    # --------------------------------------------------- запуск/стоп
    def tcp_enable(self) -> None:
        if not IS_WINDOWS:
            return
        rc, out = winutils.run_english("netsh interface tcp show global")
        if "timestamps" in out.lower() and any("timestamps" in l.lower() and "enabled" in l.lower() for l in out.splitlines()):
            return
        winutils.run(["netsh", "interface", "tcp", "set", "global", "timestamps=enabled"])

    def service_installed(self) -> bool:
        return winutils.service_info(SERVICE_NAME) is not None

    def service_state(self) -> Optional[str]:
        return winutils.service_status(SERVICE_NAME)

    def service_strategy(self) -> Optional[str]:
        if not IS_WINDOWS:
            return None
        import winreg
        return winutils.reg_read(winreg.HKEY_LOCAL_MACHINE,
                                 r"System\CurrentControlSet\Services\zapret", "zapret-discord-youtube")

    def is_running_app(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def is_running(self) -> bool:
        """Работает ли обход вообще (процесс приложения, служба или чужой winws)."""
        return self.is_running_app() or self.service_state() == "running" or bool(winutils.process_running("winws.exe"))

    def uptime(self) -> Optional[float]:
        if self.is_running_app() and self._started_at:
            return time.time() - self._started_at
        return None

    def status(self) -> Dict[str, object]:
        svc = self.service_state()
        app_running = self.is_running_app()
        foreign = [] if app_running else winutils.process_running("winws.exe")
        restarting = self._want_running and not app_running
        return {
            "app_running": app_running,
            "restarting": restarting,
            "service": svc,
            "service_strategy": self.service_strategy() if svc else None,
            "foreign_winws": bool(foreign) and svc != "running",
            "windivert": winutils.service_status("WinDivert"),
            "running": app_running or svc == "running" or bool(foreign),
            "strategy": self.cfg.get("zapret", "strategy"),
            "uptime": self.uptime(),
            "error": self.last_error,
        }

    # Вывод winws.exe идёт прямо в файл, а не в pipe: если читающий поток
    # отстанет или упадёт, заполненный pipe «подвешивал» winws.exe — обход
    # переставал работать, хотя процесс был жив.
    def _session_output(self, limit: int = 60) -> List[str]:
        try:
            with open(ZAPRET_LOG, "rb") as f:
                f.seek(self._log_pos)
                data = f.read(256 * 1024)
            lines = [l.strip() for l in data.decode("utf-8", errors="replace").splitlines()]
            return [l for l in lines if l][-limit:]
        except Exception:
            return []

    @property
    def output(self) -> List[str]:  # совместимость с интерфейсом логов
        return self._session_output(400)

    def _spawn(self, strategy: str) -> Tuple[bool, str]:
        """Запустить winws.exe (вызывать под self._lock)."""
        if self.is_running_app():
            self._stop_proc()
        if winutils.process_running("winws.exe"):
            winutils.kill_image("winws.exe")
            time.sleep(0.5)
        if not self.winws.exists() or not list(self.bin_dir.glob("*.sys")):
            log.warning("winws.exe или WinDivert64.sys отсутствует — восстанавливаю файлы")
            self.repair_files()
            if not self.winws.exists():
                return False, ("Файл winws.exe удалён (скорее всего антивирусом). Добавьте "
                               "C:\\ProgramData\\ZapretTG в исключения Защитника (кнопка на вкладке "
                               "«Диагностика») и включите обход снова.")
        try:
            args = self.build_args(strategy)
        except Exception as exc:
            return False, str(exc)
        self.tcp_enable()
        cmdline = f'"{self.winws}" {args}'
        log.info("Запуск стратегии %s", strategy)
        try:
            ZAPRET_LOG.parent.mkdir(parents=True, exist_ok=True)
            if ZAPRET_LOG.exists() and ZAPRET_LOG.stat().st_size > 1024 * 1024:
                ZAPRET_LOG.write_bytes(ZAPRET_LOG.read_bytes()[-128 * 1024:])
            logf = open(ZAPRET_LOG, "ab")
            logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {strategy} =====\n".encode("utf-8"))
            logf.flush()
            self._log_pos = logf.tell()
        except Exception:
            logf = subprocess.DEVNULL
        try:
            self._proc = subprocess.Popen(
                cmdline if IS_WINDOWS else [str(self.winws)],
                cwd=str(self.bin_dir),
                stdout=logf,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=winutils._startupinfo(),
                creationflags=winutils.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
        except Exception as exc:
            return False, f"Не удалось запустить winws.exe: {exc}"
        finally:
            if logf is not subprocess.DEVNULL:
                logf.close()  # у дочернего процесса своя копия дескриптора
        self._gen += 1
        self._started_at = time.time()
        return True, ""

    def _wait_alive(self, gen: int) -> bool:
        # winws сначала загружает списки, затем открывает WinDivert — ждём до 3 с
        deadline = time.time() + 3
        while time.time() < deadline:
            with self._lock:
                if gen != self._gen or not self.is_running_app():
                    break
            if any("windivert" in l.lower() and "error" in l.lower() for l in self._session_output(6)):
                time.sleep(0.3)
                break
            time.sleep(0.2)
        with self._lock:
            return gen == self._gen and self.is_running_app()

    def start(self, strategy: Optional[str] = None) -> Tuple[bool, str]:
        with self._lock:
            if strategy:
                self.cfg.set("zapret", "strategy", strategy)
            strategy = self.cfg.get("zapret", "strategy")
            strategies = self.strategies()
            if strategy not in strategies:
                if not strategies:
                    return False, "Стратегии не найдены"
                strategy = strategies[0]
                self.cfg.set("zapret", "strategy", strategy)
            if self.service_state() == "running":
                return False, "zapret уже работает как служба Windows. Удалите службу или управляйте ею на вкладке Zapret."
            ok, msg = self._spawn(strategy)
            if not ok:
                self.last_error = msg
                self._want_running = False
                self.on_change()
                return False, msg
            gen = self._gen
            self._want_running = True
            self._backoff = 3.0
            self.last_error = ""
            if not self._monitor or not self._monitor.is_alive():
                self._monitor = threading.Thread(target=self._watch, daemon=True, name="winws-watch")
                self._monitor.start()
        if not self._wait_alive(gen):
            with self._lock:
                if gen == self._gen:
                    # первый запуск провалился — это ошибка настройки, не крутим перезапуски
                    self._want_running = False
                    self.last_error = self.explain_exit()
            self.on_change()
            return False, self.last_error
        self.on_change()
        return True, f"Обход запущен: {self.strategy_title(strategy)}"

    def _watch(self) -> None:
        """Сторож: перезапускает winws.exe, если он завершился сам.

        Не сдаётся после N попыток (после сна/смены сети драйвер может быть
        недоступен минуту-другую), пауза растёт до 60 с и сбрасывается,
        если процесс проработал дольше 90 с. Ручные перезапуски (смена
        стратегии) отличаются по номеру поколения и сбоем не считаются.
        """
        while True:
            time.sleep(1.5)
            with self._lock:
                if not self._want_running:
                    return
                proc, gen = self._proc, self._gen
                alive = proc is not None and proc.poll() is None
            if alive:
                continue
            with self._lock:
                if not self._want_running or gen != self._gen:
                    continue
                code = proc.returncode if proc is not None else None
                lived = time.time() - (self._started_at or time.time())
                if lived > 90:
                    self._backoff = 3.0
                self.last_error = self.explain_exit(code)
                log.warning("winws.exe завершился (код %s, работал %.0f с)", code, lived)
            self.on_change()
            if not self.cfg.get("zapret", "auto_restart", True):
                with self._lock:
                    self._want_running = False
                self.on_change()
                return
            delay = self._backoff
            self._backoff = min(self._backoff * 2, 60.0)
            end = time.time() + delay
            while time.time() < end:
                time.sleep(0.25)
                with self._lock:
                    if not self._want_running or gen != self._gen:
                        break
            with self._lock:
                if not self._want_running or gen != self._gen:
                    continue
                if self.service_state() == "running":
                    self._want_running = False
                    return
                log.info("Автоперезапуск winws.exe (пауза была %.0f с)", delay)
                ok, msg = self._spawn(self.cfg.get("zapret", "strategy"))
                if ok:
                    self.last_error = ""
                else:
                    self.last_error = msg
                    # _spawn не создал процесс — следующий круг повторит попытку
                    self._proc = None
                    self._gen += 1
            self.on_change()

    def explain_exit(self, code=None) -> str:
        """Понятное описание, почему winws.exe завершился."""
        lines = self._session_output(12)
        low = "\n".join(lines).lower()
        if "windivert" in low:
            hint = ("Не удалось загрузить драйвер WinDivert. Возможные причины: антивирус удалил или "
                    "блокирует WinDivert64.sys (добавьте C:\\ProgramData\\ZapretTG в исключения), "
                    "запущен другой обход (GoodbyeDPI и т.п.) или служба zapret. Откройте «Диагностику».")
        elif "could not" in low or "error" in low or "invalid" in low:
            hint = "winws.exe сообщил об ошибке — подробности на вкладке «Логи»."
        else:
            hint = "winws.exe завершился" + (f" (код {code})" if code is not None else " сразу после запуска") + "."
        last = [l for l in lines if "cygwin" not in l.lower() and "fast_cwd" not in l.lower()][-1:]
        return hint + (f"\n{last[0]}" if last else "")

    def repair_files(self) -> bool:
        """Вернуть файлы bin из встроенной копии (например, после антивируса)."""
        src = BUNDLED_ZAPRET / "bin"
        if not src.exists():
            return False
        ok = True
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            dst = self.bin_dir / f.name
            if dst.exists() and f.name.upper().startswith("ACTIVE_"):
                continue
            if not dst.exists() or dst.stat().st_size != f.stat().st_size:
                try:
                    shutil.copyfile(f, dst)
                except Exception as exc:
                    log.warning("Не удалось восстановить %s: %r", f.name, exc)
                    ok = False
        return ok

    def _stop_proc(self) -> None:
        p = self._proc
        self._proc = None
        self._gen += 1
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def stop(self) -> Tuple[bool, str]:
        with self._lock:
            self._want_running = False
            self._stop_proc()
            self._started_at = None
            self.last_error = ""
        self.on_change()
        return True, "Обход остановлен"

    # ----------------------------------------------- служба Windows
    def install_service(self, strategy: str) -> Tuple[bool, str]:
        """То же, что «Install Service» в service.bat."""
        if not IS_WINDOWS:
            return False, "Только для Windows"
        self.stop()
        try:
            args = self.build_args(strategy)
        except Exception as exc:
            return False, str(exc)
        self.tcp_enable()
        winutils.run(["net", "stop", SERVICE_NAME], timeout=40)
        winutils.run(["sc", "delete", SERVICE_NAME], timeout=20)
        time.sleep(0.5)
        binpath = f'"{self.winws}" {args}'
        quoted = '"' + binpath.replace('"', '\\"') + '"'
        rc, out = winutils.run(f'sc create {SERVICE_NAME} binPath= {quoted} DisplayName= "zapret" start= auto', timeout=30)
        if rc != 0:
            return False, f"Не удалось создать службу:\n{out.strip()}"
        winutils.run(["sc", "description", SERVICE_NAME, "Zapret DPI bypass software"], timeout=15)
        import winreg
        winutils.reg_write_sz(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Services\zapret",
                              "zapret-discord-youtube", self.strategy_title(strategy))
        rc, out = winutils.run(["sc", "start", SERVICE_NAME], timeout=30)
        self.cfg.set("zapret", "strategy", strategy)
        self.cfg.set("zapret", "mode", "service")
        self.on_change()
        if rc != 0:
            return False, f"Служба создана, но не запустилась:\n{out.strip()}"
        return True, f"Служба zapret установлена: {self.strategy_title(strategy)}"

    def remove_services(self) -> Tuple[bool, str]:
        """То же, что «Remove Services» в service.bat."""
        self.stop()
        msgs = []
        if self.service_installed():
            winutils.stop_and_delete_service(SERVICE_NAME)
            msgs.append("служба zapret удалена")
        if winutils.process_running("winws.exe"):
            winutils.kill_image("winws.exe")
        for svc in ("WinDivert", "WinDivert14"):
            if winutils.service_info(svc) is not None:
                winutils.stop_and_delete_service(svc)
                msgs.append(f"{svc} удалён")
        self.cfg.set("zapret", "mode", "app")
        self.on_change()
        return True, ("Готово: " + ", ".join(msgs)) if msgs else "Службы не установлены"

    def service_start(self) -> Tuple[bool, str]:
        rc, out = winutils.run(["sc", "start", SERVICE_NAME], timeout=30)
        self.on_change()
        return rc == 0, out.strip()

    def service_stop(self) -> Tuple[bool, str]:
        rc, out = winutils.run(["net", "stop", SERVICE_NAME], timeout=40)
        self.on_change()
        return rc == 0, out.strip()

    # ---------------------------------------------------- hosts
    def hosts_check(self) -> Tuple[Optional[bool], str, str]:
        """(актуален?, сообщение, содержимое из репозитория)."""
        try:
            remote = winutils.http_get(f"{HOSTS_URL}?t={int(time.time())}", timeout=20)
        except Exception as exc:
            return None, f"Не удалось скачать hosts из репозитория: {exc}", ""
        lines = [l for l in remote.splitlines() if l.strip()]
        if not lines:
            return None, "Файл hosts в репозитории пуст", ""
        try:
            current = HOSTS_FILE.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return None, f"Не удалось прочитать hosts: {exc}", remote
        ok = lines[0] in current and lines[-1] in current
        return ok, ("Файл hosts актуален" if ok else "Файл hosts нужно обновить"), remote

    def hosts_apply(self, remote: str) -> Tuple[bool, str]:
        try:
            current = HOSTS_FILE.read_text(encoding="utf-8", errors="replace")
            backup = HOSTS_FILE.with_name("hosts.zaprettg.bak")
            if not backup.exists():
                shutil.copy2(HOSTS_FILE, backup)
            pattern = re.compile(re.escape(HOSTS_BEGIN) + r".*?" + re.escape(HOSTS_END) + r"\r?\n?", re.S)
            current = pattern.sub("", current).rstrip("\r\n")
            block = "\r\n".join([HOSTS_BEGIN] + remote.replace("\r", "").strip("\n").split("\n") + [HOSTS_END])
            HOSTS_FILE.write_text(current + "\r\n\r\n" + block + "\r\n", encoding="utf-8")
            winutils.run(["ipconfig", "/flushdns"], timeout=15)
            return True, f"hosts обновлён (резервная копия: {backup.name})"
        except Exception as exc:
            return False, f"Не удалось изменить hosts: {exc}"

    def hosts_remove(self) -> Tuple[bool, str]:
        try:
            current = HOSTS_FILE.read_text(encoding="utf-8", errors="replace")
            pattern = re.compile(r"\r?\n?" + re.escape(HOSTS_BEGIN) + r".*?" + re.escape(HOSTS_END) + r"\r?\n?", re.S)
            new = pattern.sub("\r\n", current)
            HOSTS_FILE.write_text(new, encoding="utf-8")
            winutils.run(["ipconfig", "/flushdns"], timeout=15)
            return True, "Записи ZapretTG удалены из hosts"
        except Exception as exc:
            return False, f"Не удалось изменить hosts: {exc}"

    # -------------------------------------------------- обновления
    def check_update(self) -> Tuple[Optional[str], str]:
        """(новая версия или None, сообщение)."""
        try:
            latest = winutils.http_get(VERSION_URL, timeout=10).strip()
        except Exception as exc:
            return None, f"Не удалось проверить обновления: {exc}"
        local = self.local_version()
        if _version_tuple(latest) > _version_tuple(local):
            return latest, f"Доступна новая версия zapret: {latest} (у вас {local})"
        return None, f"Установлена последняя версия zapret: {local}"

    def download_update(self, progress: Callable[[str], None] = lambda s: None) -> Tuple[bool, str]:
        """Скачать последний релиз с GitHub и установить, сохранив настройки."""
        try:
            progress("Получение информации о релизе…")
            info = json.loads(winutils.http_get(RELEASES_API, timeout=20))
            asset = next((a for a in info.get("assets", []) if a.get("name", "").lower().endswith(".zip")), None)
            if not asset:
                winutils.open_url(info.get("html_url") or RELEASES_PAGE)
                return False, "В релизе нет zip-архива — открыта страница релиза, обновите вручную."
            progress(f"Загрузка {asset['name']}…")
            data = winutils.http_get(asset["browser_download_url"], timeout=120, binary=True)
            progress("Распаковка…")
            tmp = self.root.parent / "_update"
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(tmp)
            src = next((p.parent.parent for p in tmp.rglob("winws.exe") if p.parent.name.lower() == "bin"), None)
            if src is None:
                shutil.rmtree(tmp, ignore_errors=True)
                return False, "В архиве не найден bin\\winws.exe"
            progress("Установка…")
            self._replace_tree(src)
            shutil.rmtree(tmp, ignore_errors=True)
            return True, f"zapret обновлён до версии {self.local_version()}"
        except Exception as exc:
            return False, f"Ошибка обновления: {exc}"

    # ------------------------------------------------------- тесты
    def run_tests(self) -> Tuple[bool, str]:
        """Открыть оригинальный интерактивный тест стратегий (PowerShell)."""
        script = self.utils_dir / "test zapret.ps1"
        if not script.exists():
            return False, "Скрипт тестов не найден"
        if self.is_running_app():
            self.stop()
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=str(self.root), creationflags=winutils.CREATE_NEW_CONSOLE if IS_WINDOWS else 0,
            )
            return True, "Тесты запущены в отдельном окне. Обход приложения остановлен на время тестов — включите его после."
        except Exception as exc:
            return False, f"Не удалось запустить тесты: {exc}"
