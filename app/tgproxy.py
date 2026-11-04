"""Встроенный Telegram WS Proxy (Flowseal/tg-ws-proxy).

Используется оригинальный код прокси без изменений (vendor/tgws/proxy),
здесь — только запуск/остановка в отдельном потоке и применение настроек,
так же как в оригинальном tray-приложении.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import types
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .paths import IS_FROZEN, PROXY_LOG, ensure_dirs

_VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "tgws"
if not IS_FROZEN and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# ui.connectivity импортирует tkinter.messagebox только для своих окон —
# нам нужны лишь функции тестов, поэтому подставляем заглушку.
if "tkinter" not in sys.modules:
    try:
        import tkinter  # noqa: F401
    except Exception:
        _tk = types.ModuleType("tkinter")
        _tk.messagebox = types.SimpleNamespace(showinfo=lambda *a, **k: None,
                                               showerror=lambda *a, **k: None)
        sys.modules["tkinter"] = _tk
        sys.modules["tkinter.messagebox"] = _tk.messagebox  # type: ignore

from proxy import __version__ as TGWS_VERSION  # noqa: E402
from proxy import coerce_domain_list, get_link_host, parse_dc_ip_list, proxy_config  # noqa: E402
from proxy.config import CFPROXY_DEFAULT_DOMAINS  # noqa: E402
from proxy.stats import stats  # noqa: E402
from proxy.tg_ws_proxy import _run  # noqa: E402
from proxy.utils import DomainCensorFilter, human_bytes  # noqa: E402
from ui.i18n import set_language, t  # noqa: E402
from utils.logging_setup import build_log_handler  # noqa: E402

set_language("ru")
log = logging.getLogger("zapret-tg.tgproxy")


class _RingHandler(logging.Handler):
    def __init__(self, buf: Deque[str]):
        super().__init__()
        self.buf = buf
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            self.buf.append(self.format(record))
        except Exception:
            pass


class TgProxyManager:
    def __init__(self, cfg, on_change: Optional[Callable[[], None]] = None):
        self.cfg = cfg
        self.on_change = on_change or (lambda: None)
        self._thread: Optional[threading.Thread] = None
        self._stop: Optional[Tuple[asyncio.AbstractEventLoop, asyncio.Event]] = None
        self._started_at: Optional[float] = None
        self._want = False
        self._life_lock = threading.RLock()
        self._first_result = threading.Event()
        self._first_ok = False
        self.last_error = ""
        self.output: Deque[str] = deque(maxlen=400)
        self._file_handler = None
        self._setup_logging()

    # ------------------------------------------------------- logging
    def _setup_logging(self) -> None:
        ensure_dirs()
        c = self.cfg.section("tg")
        root = logging.getLogger()
        if self._file_handler:
            root.removeHandler(self._file_handler)
        fh = build_log_handler(str(PROXY_LOG), log_max_mb=c.get("log_max_mb", 5), backups=1)
        fh.setLevel(logging.DEBUG if c.get("verbose") else logging.INFO)
        fh.addFilter(lambda r: not r.name.startswith("zapret-tg"))
        fh.addFilter(DomainCensorFilter())
        root.addHandler(fh)
        self._file_handler = fh
        if not getattr(self, "_ring", None):
            self._ring = _RingHandler(self.output)
            self._ring.addFilter(lambda r: not r.name.startswith("zapret-tg"))
            self._ring.addFilter(DomainCensorFilter())
            root.addHandler(self._ring)
        self._ring.setLevel(logging.DEBUG if c.get("verbose") else logging.INFO)
        root.setLevel(logging.DEBUG if c.get("verbose") else logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    # -------------------------------------------------------- config
    @staticmethod
    def validate(c: Dict) -> Optional[str]:
        import ipaddress
        try:
            ipaddress.ip_address(str(c.get("host", "")).strip())
        except ValueError:
            return t("validation.bad_host")
        try:
            port = int(c.get("port"))
            assert 1 <= port <= 65535
        except Exception:
            return t("validation.bad_port")
        secret = str(c.get("secret", "")).strip()
        if len(secret) != 32:
            return t("validation.bad_secret_len")
        try:
            bytes.fromhex(secret)
        except ValueError:
            return t("validation.bad_secret_hex")
        try:
            parse_dc_ip_list(c.get("dc_ip", []))
        except ValueError as e:
            entry = getattr(e, "entry", "")
            return t("validation.dc_format" if getattr(e, "kind", "") == "format" else "validation.dc_invalid", entry=entry)
        ftls = str(c.get("fake_tls_domain", "") or "").strip()
        if ftls:
            try:
                ftls.encode("ascii")
            except UnicodeEncodeError:
                return "Домен Fake TLS должен состоять из латинских символов"
        return None

    def _apply(self) -> bool:
        c = self.cfg.section("tg")
        try:
            dc = parse_dc_ip_list(c.get("dc_ip", []))
        except ValueError as e:
            self.last_error = t("error.dc_config")
            log.error("Bad dc_ip: %s", e)
            return False
        pc = proxy_config
        pc.port = int(c.get("port", 1443))
        pc.host = str(c.get("host", "127.0.0.1")).strip()
        pc.secret = str(c.get("secret")).strip()
        pc.dc_redirects = dc
        pc.buffer_size = max(4, int(c.get("buf_kb", 256))) * 1024
        pc.pool_size = max(0, int(c.get("pool_size", 4)))
        pc.fallback_cfproxy = bool(c.get("cfproxy", True))
        pc.cfproxy_h2_media = bool(c.get("h2", True))
        user = coerce_domain_list(c.get("cfproxy_user_domain", []))
        worker = coerce_domain_list(c.get("cfproxy_worker_domain", []))
        pc.cfproxy_user_domains = user if c.get("cfproxy_user_domain_enabled") else []
        pc.cfproxy_worker_domains = worker if c.get("cfproxy_worker_enabled") else []
        pc.force_test_dc = bool(c.get("force_test_dc", False))
        pc.disable_secure = bool(c.get("no_secure", False))
        pc.fake_tls_domain = str(c.get("fake_tls_domain", "") or "").strip()
        pc.proxy_protocol = bool(c.get("proxy_protocol", False))
        return True

    # ------------------------------------------------------ lifecycle
    #
    # Прокси работает под «супервизором»: если _run() завершился сам
    # (умер слушающий сокет, сбой после сна/смены сети, исключение), он
    # перезапускается с нарастающей паузой. Новая сессия стартует только
    # после полного завершения старой — у прокси общие глобальные пулы
    # (ws_pool, cf_worker_pool), и пересечение сессий ломало соединения.
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._listening())

    def is_active(self) -> bool:
        """Прокси включён пользователем (работает или перезапускается)."""
        return bool(self._want and self._thread and self._thread.is_alive())

    def start(self) -> Tuple[bool, str]:
        with self._life_lock:
            if self._thread and self._thread.is_alive():
                if self._want:
                    return True, "Прокси уже запущен"
                self._thread.join(timeout=25)
                if self._thread.is_alive():
                    return False, "Предыдущий запуск прокси ещё завершается, попробуйте через пару секунд"
            self._setup_logging()
            if not self._apply():
                return False, self.last_error
            self.last_error = ""
            self._want = True
            self._first_result = threading.Event()
            self._first_ok = False
            self._thread = threading.Thread(target=self._supervisor, daemon=True, name="tg-proxy")
            self._thread.start()
        self._first_result.wait(timeout=12)
        self.on_change()
        if not self._first_ok:
            # первая попытка не удалась (чаще всего занят порт) — не крутимся впустую
            self._want = False
            self._signal_stop()
            if self._thread:
                self._thread.join(timeout=10)
            return False, self.last_error or "Прокси не запустился"
        return True, f"Прокси запущен на {proxy_config.host}:{proxy_config.port}"

    def _listening(self) -> bool:
        try:
            from proxy import tg_ws_proxy as m
            return getattr(m, "_server_instance", None) is not None
        except Exception:
            return True

    def _supervisor(self) -> None:
        delay = 2.0
        first = True
        while self._want:
            t0 = time.time()
            err = self._session(first)
            first = False
            if not self._want or not self._first_ok:
                break  # остановлен пользователем или не смог запуститься ни разу
            lived = time.time() - t0
            if lived > 120:
                delay = 2.0
            self.last_error = (err or "Прокси остановился") + f" — перезапуск через {int(delay)} с"
            log.warning("Прокси завершился (%s), перезапуск через %.0f с", err or "без ошибки", delay)
            self.on_change()
            end = time.time() + delay
            while self._want and time.time() < end:
                time.sleep(0.25)
            delay = min(delay * 2, 60.0)
            if self._want:
                self._apply()
        self._stop = None
        self._started_at = None
        self.on_change()

    def _session(self, first: bool) -> Optional[str]:
        """Один запуск _run(). Возвращает описание ошибки или None."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ev = asyncio.Event()
        self._stop = (loop, ev)
        if not self._want:  # stop() успел раньше, чем появился цикл
            ev.set()
        err: Optional[str] = None

        async def watch_ready():
            for _ in range(200):
                if self._listening():
                    self._started_at = time.time()
                    self.last_error = ""
                    self._first_ok = True
                    self._first_result.set()
                    self.on_change()
                    return
                await asyncio.sleep(0.05)

        try:
            loop.create_task(watch_ready())
            loop.run_until_complete(_run(stop_event=ev))
        except Exception as exc:
            log.error("Прокси упал: %r", exc)
            err = self._describe_error(exc)
            self.last_error = err
        finally:
            try:
                pending = [x for x in asyncio.all_tasks(loop) if not x.done()]
                for x in pending:
                    x.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
            except Exception:
                pass
            try:
                from proxy import tg_ws_proxy as m
                m._server_instance = None
            except Exception:
                pass
            self._stop = None
            self._started_at = None
            if first and not self._first_ok:
                self._first_result.set()
        return err

    @staticmethod
    def _describe_error(exc: BaseException) -> str:
        try:
            from utils.diagnostics import diagnose_listen_error
            res = diagnose_listen_error(exc)
            if res and res[0]:
                return res[0]
        except Exception:
            pass
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10048, 10013):
            return "Порт занят другой программой (возможно, запущен оригинальный TgWsProxy). Закройте её или смените порт."
        return f"Ошибка прокси: {exc}"

    def _signal_stop(self) -> None:
        st = self._stop
        if st:
            loop, ev = st
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:
                pass

    def stop(self) -> Tuple[bool, str]:
        with self._life_lock:
            self._want = False
            self._signal_stop()
            t = self._thread
            if t and t.is_alive():
                # ждём полного завершения, повторяя сигнал (цикл мог ещё не создаться)
                end = time.time() + 20
                while t.is_alive() and time.time() < end:
                    self._signal_stop()
                    t.join(timeout=0.5)
            self.last_error = ""
        self.on_change()
        return True, "Прокси остановлен"

    def restart(self) -> Tuple[bool, str]:
        self.stop()
        return self.start()

    # ------------------------------------------------------ info
    def link(self) -> str:
        c = self.cfg.section("tg")
        host = get_link_host(str(c.get("host", "127.0.0.1")))
        port = c.get("port", 1443)
        secret = c.get("secret", "")
        ftls = str(c.get("fake_tls_domain", "") or "").strip()
        if ftls:
            return f"tg://proxy?server={host}&port={port}&secret=ee{secret}{ftls.encode('ascii', 'ignore').hex()}"
        return f"tg://proxy?server={host}&port={port}&secret=dd{secret}"

    def uptime(self) -> Optional[float]:
        return time.time() - self._started_at if (self.is_running() and self._started_at) else None

    @staticmethod
    def stats() -> Dict[str, object]:
        s = stats
        return {
            "active": s.connections_active,
            "total": s.connections_total,
            "ws": s.connections_ws,
            "cf": s.connections_cfproxy,
            "h2": s.connections_h2,
            "tcp_fb": s.connections_tcp_fallback,
            "errors": s.ws_errors,
            "up": human_bytes(s.bytes_up),
            "down": human_bytes(s.bytes_down),
            "up_raw": s.bytes_up,
            "down_raw": s.bytes_down,
        }

    # -------------------------------------------- connectivity tests
    @staticmethod
    def test_cfproxy(domains: List[str], secure: bool) -> str:
        from ui.connectivity import run_cfproxy_auto_test, run_cfproxy_multi_test
        title = t("connectivity.cfproxy_title")
        if not domains:
            try:
                from proxy.balancer import balancer
                auto = list(balancer.domains) or list(CFPROXY_DEFAULT_DOMAINS)
            except Exception:
                auto = list(CFPROXY_DEFAULT_DOMAINS)
            domain, res = run_cfproxy_auto_test(auto, secure=secure)
            if domain:
                ok = sum(1 for v in res.values() if v is True)
                return t("connectivity.auto_ok", title=title, ok=ok, total=len(res))
            return t("connectivity.cf_auto_fail")
        return _format_multi(run_cfproxy_multi_test(domains, secure=secure))

    @staticmethod
    def test_cfworker(domains: List[str], secure: bool) -> str:
        from ui.connectivity import run_cfworker_multi_test
        if not domains:
            return "Укажите домены Cloudflare Worker"
        return _format_multi(run_cfworker_multi_test(domains, secure=secure))

    @staticmethod
    def check_update() -> Tuple[Optional[str], str]:
        from utils.update_check import get_status, run_check
        run_check(TGWS_VERSION)
        st = get_status()
        if st.get("error"):
            return None, t("updates.status_error")
        if st.get("has_update"):
            return st.get("latest"), t("updates.status_available", latest=st.get("latest"), current=TGWS_VERSION)
        return None, t("updates.status_latest")


def _format_multi(results: Dict[str, Dict]) -> str:
    lines = []
    for domain, res in results.items():
        ok = [dc for dc, v in res.items() if v is True]
        fail = [f"DC{dc}" for dc, v in res.items() if v is not True]
        if len(ok) == len(res):
            lines.append(t("connectivity.multi_all_ok", domain=domain, total=len(res)))
        elif not ok:
            lines.append(t("connectivity.multi_fail", domain=domain))
        else:
            lines.append(t("connectivity.multi_partial", domain=domain,
                           ok_list=", ".join(f"DC{d}" for d in ok), fail_list=", ".join(fail)))
    return "\n".join(lines)
