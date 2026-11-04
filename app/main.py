"""Точка входа ZapretTG."""
from __future__ import annotations

import logging
import logging.handlers
import sys
import threading


def _setup_logging() -> None:
    from .paths import APP_LOG, ensure_dirs
    ensure_dirs()
    h = logging.handlers.RotatingFileHandler(APP_LOG, maxBytes=1024 * 1024, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", "%Y-%m-%d %H:%M:%S"))
    h.addFilter(lambda r: r.name.startswith("zapret-tg"))
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(logging.INFO)
    lg = logging.getLogger("zapret-tg")
    lg.setLevel(logging.INFO)


def _wine_compat() -> None:
    """Под Wine нет CopyFile2, которым пользуется shutil.copy2 в Python 3.12."""
    try:
        import ctypes
        ctypes.windll.ntdll.wine_get_version  # есть только в Wine
    except Exception:
        return
    try:
        import _winapi
        if hasattr(_winapi, "CopyFile2"):
            delattr(_winapi, "CopyFile2")
    except Exception:
        pass


def _selftest(out_path) -> int:
    """Проверка сборки: все модули импортируются, стратегии разбираются, окно создаётся."""
    import os
    import tempfile
    import traceback
    lines = []
    ok = True
    try:
        os.environ["ZAPRETTG_DATA"] = tempfile.mkdtemp(prefix="zaprettg-selftest-")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from importlib import reload
        from . import paths
        reload(paths)
        from .config import Config
        from .zapret import ZapretManager
        from .tgproxy import TgProxyManager, TGWS_VERSION
        from .dns import DnsManager
        cfg = Config()
        z = ZapretManager(cfg)
        z.root = paths.ZAPRET_DIR
        z.install_files()
        strategies = z.strategies()
        for st in strategies:
            args = z.build_args(st)
            assert "%" not in args and "winws" not in args.lower(), st
        lines.append(f"zapret {z.local_version()}: {len(strategies)} стратегий разобрано")
        lines.append(f"tg-ws-proxy {TGWS_VERSION}")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from .ui.main_window import MainWindow
        w = MainWindow(cfg, z, TgProxyManager(cfg), DnsManager(cfg))
        for key in w.pages:
            w.go(key, animate=False)
        lines.append(f"интерфейс: {len(w.pages)} страниц")
        w.timer.stop()
        w.tray.hide()
    except Exception:
        ok = False
        lines.append(traceback.format_exc())
    lines.append("SELFTEST OK" if ok else "SELFTEST FAILED")
    text = "\n".join(lines)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)
    return 0 if ok else 1


def _cleanup() -> int:
    """Вызывается деинсталлятором: вернуть систему в исходное состояние."""
    from . import winutils
    from .config import Config
    from .dns import DnsManager
    from .zapret import SERVICE_NAME
    try:
        cfg = Config()
        if cfg.get("dns", "enabled") or cfg.get("dns", "saved"):
            DnsManager(cfg).disable()
    except Exception:
        pass
    # закрыть работающий ZapretTG, но не себя (и не свой загрузчик onefile)
    try:
        import os
        import psutil
        me = psutil.Process(os.getpid())
        mine = {me.pid} | {p.pid for p in me.parents()}
        for p in psutil.process_iter(["name"]):
            if (p.info.get("name") or "").lower() == "zaprettg.exe" and p.pid not in mine:
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass
    winutils.kill_image("winws.exe")
    winutils.set_autostart(False)
    for svc in (SERVICE_NAME, "WinDivert", "WinDivert14"):
        if winutils.service_info(svc) is not None:
            winutils.stop_and_delete_service(svc)
    return 0


def main() -> int:
    from .paths import APP_NAME, IS_WINDOWS, APP_VERSION
    if IS_WINDOWS:
        _wine_compat()
    from . import winutils

    args = sys.argv[1:]
    autostart = "--autostart" in args

    # служебные режимы (для установщика и CI) — без окна
    for a in args:
        if a.startswith("--selftest"):
            return _selftest(a.partition("=")[2] or None)
    if "--cleanup" in args:
        return _cleanup()
    if "--autostart-on" in args:
        ok, _ = winutils.set_autostart(True)
        return 0 if ok else 1

    if IS_WINDOWS and not winutils.is_admin():
        # zapret (WinDivert) требует прав администратора
        if winutils.relaunch_as_admin(args):
            return 0

    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.App")
        except Exception:
            pass

    from PySide6.QtCore import Qt
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    # один экземпляр: второй запуск только показывает окно первого.
    # Мьютекс — основная защита (два экземпляра «воевали» за winws.exe и порт
    # прокси), локальный сокет — чтобы попросить первый экземпляр показаться.
    key = f"{APP_NAME}-single-instance"
    first_instance = winutils.acquire_single_instance(f"{APP_NAME}-mutex")
    sock = QLocalSocket()
    sock.connectToServer(key)
    if sock.waitForConnected(1500 if not first_instance else 300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        return 0
    if not first_instance:
        return 0  # первый экземпляр ещё запускается
    QLocalServer.removeServer(key)
    server = QLocalServer()
    server.listen(key)

    _setup_logging()
    log = logging.getLogger("zapret-tg")
    log.info("===== %s %s запуск (autostart=%s, admin=%s) =====", APP_NAME, APP_VERSION, autostart, winutils.is_admin())

    from .config import Config
    from .zapret import ZapretManager
    from .tgproxy import TgProxyManager
    from .dns import DnsManager
    from .ui.main_window import MainWindow

    cfg = Config()
    zapret = ZapretManager(cfg)
    try:
        zapret.install_files()
    except Exception as exc:
        log.exception("Не удалось установить файлы zapret")
        QMessageBox.critical(None, APP_NAME, f"Не удалось подготовить файлы zapret:\n{exc}")
    tg = TgProxyManager(cfg)
    dns = DnsManager(cfg)

    # реальное состояние автозапуска
    try:
        cfg.set("app", "autostart", winutils.autostart_enabled())
        winutils.autostart_refresh()  # exe перенесли — обновить путь в планировщике
    except Exception:
        pass
    if cfg.get("zapret", "mode") == "service" and not zapret.service_installed():
        cfg.set("zapret", "mode", "app")

    win = MainWindow(cfg, zapret, tg, dns)

    def on_new_connection():
        c = server.nextPendingConnection()
        if c:
            c.waitForReadyRead(300)
            c.readAll()
            c.disconnectFromServer()
        win.show_window()

    server.newConnection.connect(on_new_connection)

    first_run = not cfg.get("app", "first_run_done")
    if autostart and cfg.get("app", "start_minimized", True) and not first_run:
        pass  # только трей
    else:
        win.show()

    def start_components():
        warnings = []
        # оригинальный TgWsProxy занимает тот же порт — прокси не смог бы запуститься
        if winutils.process_running("TgWsProxy.exe") or winutils.process_running("TgWsProxy_windows.exe"):
            warnings.append("Запущен оригинальный TgWsProxy — он занимает порт прокси. Закройте его "
                            "(значок в трее → Выход) и уберите из автозагрузки.")
        if cfg.get("dns", "enabled"):
            try:
                ok, msg = dns.enable()
                if not ok:
                    warnings.append("DNS: " + msg)
            except Exception as exc:
                log.exception("dns")
        if cfg.get("zapret", "enabled_on_start", True):
            if cfg.get("zapret", "mode") == "service":
                if zapret.service_state() != "running":
                    zapret.service_start()
            else:
                ok, msg = zapret.start()
                if not ok:
                    log.warning("zapret: %s", msg)
        if cfg.get("tg", "enabled_on_start", True):
            ok, msg = tg.start()
            if not ok:
                log.warning("tg: %s", msg)
                warnings.append("Telegram прокси: " + msg.split("\n")[0])
        return warnings

    def after_start(warnings):
        win.refresh_now()
        for w in warnings or []:
            win.toast(w, "warn", 10000)
        if first_run:
            cfg.set("app", "first_run_done", True)
            win.toast("Готово! Обход и Telegram прокси включены. Нажмите «Подключить Telegram», "
                      "чтобы добавить прокси в Telegram Desktop.", "ok", 9000)

    from .ui.widgets import run_bg
    run_bg(start_components, after_start, lambda e: log.error("Ошибка запуска: %r", e))
    win.check_updates_later()

    app.aboutToQuit.connect(win.quit_app)
    return app.exec()
